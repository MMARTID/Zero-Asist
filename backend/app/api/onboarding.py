"""Onboarding endpoints — create clients and connect their Gmail accounts.

The OAuth flow uses the server-side (web application) flow:

1. ``POST /onboarding/cuentas`` — register a new client.
2. ``GET  /onboarding/gmail/authorize/{cliente_id}`` — redirect to Google consent.
3. ``GET  /onboarding/gmail/callback`` — exchange code, save creds, start watch.

Environment variables:
    ``OAUTH_CLIENT_CONFIG_PATH``  JSON string with the OAuth web-client config
                             (same format as the ``credentials.json`` downloaded
                             from the Google Cloud Console for *Web application*).
    ``OAUTH_REDIRECT_URI``   e.g. ``https://my-svc.run.app/onboarding/gmail/callback``
    ``GMAIL_PUBSUB_TOPIC``   (shared with webhook / internal modules)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from google.cloud import firestore
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel

from app.api.auth import get_current_gestoria
from app.api.deps import get_db as _get_db
from app.collectors.gmail_service import SCOPES
from app.collectors.gmail_watch import start_watch
from app.services.credential_store import save_credentials
from app.services.tax_id import classify_tax_id, normalize_tax_id_raw
from app.services.tenant import TenantContext, extract_tenant_from_doc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

_PUBSUB_TOPIC = os.environ.get("GMAIL_PUBSUB_TOPIC", "")
_OAUTH_CLIENT_CONFIG_PATH = os.environ.get("OAUTH_CLIENT_CONFIG_PATH", "oauth_client_config.json")
_OAUTH_REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "")
_FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")


def _build_flow() -> Flow:
    """Build a Google OAuth ``Flow`` from config file."""
    if not _OAUTH_CLIENT_CONFIG_PATH:
        raise HTTPException(status_code=500, detail="OAUTH_CLIENT_CONFIG_PATH not configured")
    if not _OAUTH_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="OAUTH_REDIRECT_URI not configured")

    with open(_OAUTH_CLIENT_CONFIG_PATH) as f:
        client_config = json.load(f)
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=_OAUTH_REDIRECT_URI,
    )


# ---------------------------------------------------------------------------
# Create client
# ---------------------------------------------------------------------------

class CreateClientRequest(BaseModel):
    nombre: str
    phone_number: str
    tax_id: str


@router.post("/cuentas")
def create_client(
    body: CreateClientRequest,
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Register a new client under the authenticated gestoría."""
    # Normalize + classify the tax identifier
    normalized = normalize_tax_id_raw(body.tax_id)
    if not normalized:
        raise HTTPException(status_code=422, detail="Identificador fiscal vacío")
    classified = classify_tax_id(normalized)
    if classified is None:
        raise HTTPException(
            status_code=422,
            detail=f"Identificador fiscal no reconocido: {body.tax_id}",
        )

    db = _get_db()
    doc_ref = db.collection(f"gestorias/{gestoria_id}/cuentas").document()
    doc_ref.set({
        "nombre": body.nombre,
        "phone_number": body.phone_number,
        "tax_id": classified.tax_id,
        "tax_country": classified.tax_country,
        "tax_type": classified.tax_type,
        "gmail_email": None,
        "gmail_watch_status": None,
        "min_income": None,
        "max_income": None,
        "created_at": firestore.SERVER_TIMESTAMP,
    })

    return {
        "cuenta_id": doc_ref.id,
        "gestoria_id": gestoria_id,
        "nombre": body.nombre,
        "tax_id": classified.tax_id,
        "tax_country": classified.tax_country,
        "tax_type": classified.tax_type,
    }


# ---------------------------------------------------------------------------
# Gmail OAuth — Step 1: authorize
# ---------------------------------------------------------------------------

@router.get("/gmail/authorize/{cuenta_id}")
def gmail_authorize(
    cuenta_id: str,
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Redirect the user to Google's OAuth consent screen.

    Encodes ``gestoria_id:cuenta_id`` in the OAuth ``state`` parameter so
    the callback can associate the tokens with the right tenant.
    """
    db = _get_db()
    client_doc = db.document(
        f"gestorias/{gestoria_id}/cuentas/{cuenta_id}",
    ).get()
    if not client_doc.exists:
        raise HTTPException(status_code=404, detail="Client not found")

    flow = _build_flow()

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )

    # Persist the PKCE code_verifier in the state so the callback can use it
    code_verifier = flow.code_verifier or ""
    state = f"{gestoria_id}:{cuenta_id}:{code_verifier}"

    # Re-generate the URL with our custom state
    flow2 = _build_flow()
    flow2.code_verifier = code_verifier
    authorization_url, _ = flow2.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )

    return {"authorization_url": authorization_url}

# ---------------------------------------------------------------------------
# Gmail OAuth — Step 2: callback
# ---------------------------------------------------------------------------

@router.get("/gmail/callback")
def gmail_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    """Handle the OAuth callback from Google.

    Exchanges the authorization code for tokens, stores them, records the
    Gmail email on the client document, and starts the watch.

    **No Firebase Auth here** — this is a redirect from Google.  The caller
    is authenticated implicitly: only a valid ``code`` exchangeable with
    Google counts, and the ``state`` is verified against an existing tenant.
    """
    parts = state.split(":", 2)
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    gestoria_id = parts[0]
    cuenta_id = parts[1]
    code_verifier = parts[2] if len(parts) > 2 else ""
    ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=cuenta_id)

    # Verify tenant exists (prevents orphan documents from forged state)
    db = _get_db()
    client_doc = db.document(
        f"gestorias/{gestoria_id}/cuentas/{cuenta_id}",
    ).get()
    if not client_doc.exists:
        raise HTTPException(status_code=404, detail="Client not found")

    # Exchange code for credentials (restore PKCE code_verifier)
    try:
        flow = _build_flow()
        if code_verifier:
            flow.code_verifier = code_verifier
        flow.fetch_token(code=code)
    except Exception as e:
        logger.error("OAuth token exchange failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {e}")
    creds: Credentials = flow.credentials

    # Persist tokens
    save_credentials(ctx, creds)

    # Fetch Gmail email for webhook lookups
    from googleapiclient.discovery import build

    try:
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        gmail_email = profile.get("emailAddress", "")
    except Exception as e:
        logger.error("Failed to fetch Gmail profile: %s", e)
        raise HTTPException(status_code=502, detail=f"Gmail profile fetch failed: {e}")

    # Guard: reject if this Gmail account is already connected to a DIFFERENT
    # client (in any gestoria). Same-client re-connections are allowed.
    existing = (
        db.collection_group("cuentas")
        .where(filter=firestore.FieldFilter("gmail_email", "==", gmail_email))
        .where(filter=firestore.FieldFilter("gmail_watch_status", "==", "active"))
        .limit(5)
        .get()
    )
    for ex_doc in existing:
        ex_ctx = extract_tenant_from_doc(ex_doc)
        if ex_ctx and ex_ctx.cliente_id != cuenta_id:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"La cuenta Gmail {gmail_email} ya está conectada a otro "
                        f"cliente. Desconéctala primero antes de reutilizarla."
                    ),
                )

    db.document(f"gestorias/{gestoria_id}/cuentas/{cuenta_id}").set(
        {"gmail_email": gmail_email},
        merge=True,
    )

    # Start Gmail watch (best-effort; tokens are already saved)
    watch_started = False
    if _PUBSUB_TOPIC:
        try:
            start_watch(service, _PUBSUB_TOPIC, ctx)
            watch_started = True
            logger.info(
                "Watch started for %s/%s after OAuth",
                gestoria_id, cuenta_id,
            )
        except Exception as e:
            logger.error(
                "Failed to start watch after OAuth for %s/%s: %s",
                gestoria_id, cuenta_id, e,
            )
    else:
        logger.warning("GMAIL_PUBSUB_TOPIC not set — skipping watch start")

    # Redirect back to the frontend cuenta page (Gmail tab)
    redirect_url = f"{_FRONTEND_URL}/dashboard/cuentas/{cuenta_id}"
    return RedirectResponse(url=redirect_url, status_code=302)
