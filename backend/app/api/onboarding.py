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
from app.services.gemini_client import normalize_import_data
from app.services.tax_id import classify_tax_id, normalize_tax_id_raw
from app.services.tenant import TenantContext, extract_tenant_from_doc
from app.services.errors import PipelineError

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
# Bulk Import — Analyze and Create
# ---------------------------------------------------------------------------

class AnalyzeImportRequest(BaseModel):
    """CSV/Excel rows from frontend to be analyzed by Gemini."""
    headers: list[str]
    rows: list[list[str]]


class NormalizedContact(BaseModel):
    """Normalized contact data from Gemini analysis."""
    nombre_fiscal: Optional[str] = None
    tax_id: Optional[str] = None
    phone_number: Optional[str] = None
    email_contacto: Optional[str] = None
    direccion_fiscal: Optional[str] = None
    codigo_postal: Optional[str] = None
    confidence: Optional[dict] = None


class AnalyzeImportResponse(BaseModel):
    """Response from Gemini analysis."""
    mapping: dict[str, str]
    normalized_rows: list[NormalizedContact]
    warnings: list[str]


class BulkCreateRequest(BaseModel):
    """Bulk create request."""
    cuentas: list[NormalizedContact]


class BulkCreateResponse(BaseModel):
    """Response from bulk create."""
    created: int
    skipped: int
    errors: list[dict]


@router.post("/cuentas/import/analyze")
def analyze_import(
    body: AnalyzeImportRequest,
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Analyze CSV/Excel rows using Gemini to normalize column mapping and data.
    
    Retry strategy: 
    - 1 attempt on gemini-3-pro (fail fast)
    - 2 attempts on gemini-2.5-flash (1 reintento)
    - 4 attempts on gemini-2.5-flash-lite (3 reintentos)
    
    This endpoint:
    1. Takes raw headers and rows from a parsed CSV/Excel file
    2. Sends to gemini-3-pro first (via normalize_import_data service)
    3. If saturated/unavailable, retries with fallback models
    4. Returns normalized contacts with confidence scores
    """
    if not body.rows:
        raise HTTPException(status_code=422, detail="No rows provided")

    try:
        analysis = normalize_import_data(body.headers, body.rows)
        
        # Convert to Pydantic models for validation
        normalized_rows = [NormalizedContact(**row) for row in analysis["normalized_rows"]]
        
        return AnalyzeImportResponse(
            mapping=analysis.get("mapping", {}),
            normalized_rows=normalized_rows,
            warnings=analysis.get("warnings", []),
        )
    except PipelineError as e:
        logger.error("Import analysis failed (PipelineError): %s", e)
        raise HTTPException(status_code=502, detail=f"LLM analysis failed: {str(e)}")
    except ValueError as e:
        logger.error("Import analysis validation failed: %s", e)
        raise HTTPException(status_code=422, detail=f"Invalid data: {str(e)}")
    except Exception as e:
        logger.error("Import analysis failed: %s", e)
        raise HTTPException(status_code=502, detail=f"LLM analysis failed: {str(e)}")


@router.post("/cuentas/bulk")
def bulk_create_clients(
    body: BulkCreateRequest,
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Bulk create clients from normalized import data.
    
    This endpoint:
    1. Validates each contact's tax_id
    2. Creates documents in Firestore batch (max 500 operations)
    3. Returns success count and any errors
    """
    if not body.cuentas:
        raise HTTPException(status_code=422, detail="No cuentas provided")
    
    if len(body.cuentas) > 500:
        raise HTTPException(status_code=422, detail="Maximum 500 cuentas per request")

    db = _get_db()
    created = 0
    skipped = 0
    errors = []

    # Fetch all existing tax_ids for this gestoria to detect duplicates
    existing_tax_ids: set[str] = set()
    try:
        existing_docs = db.collection(f"gestorias/{gestoria_id}/cuentas").select(["tax_id"]).stream()
        for doc in existing_docs:
            tid = doc.to_dict().get("tax_id") or ""
            if tid:
                existing_tax_ids.add(tid.upper())
    except Exception as e:
        logger.warning("Could not fetch existing tax_ids for dedup check: %s", e)

    # Use Firestore batch for efficiency
    batch = db.batch()
    # Track tax_ids seen within this batch to avoid intra-batch duplicates
    seen_in_batch: set[str] = set()

    for idx, contact in enumerate(body.cuentas):
        try:
            # Try to classify tax_id if provided, otherwise use it as-is
            tax_id_to_use = contact.tax_id or ""
            classified = None

            if tax_id_to_use:
                normalized = normalize_tax_id_raw(tax_id_to_use)
                if normalized:
                    classified = classify_tax_id(normalized)

            final_tax_id = (classified.tax_id if classified else tax_id_to_use).upper() if (classified or tax_id_to_use) else ""

            # Skip if tax_id already exists (in DB or in this batch)
            if final_tax_id and (
                final_tax_id in existing_tax_ids or final_tax_id in seen_in_batch
            ):
                logger.info("Skipping duplicate tax_id %s at row %d", final_tax_id, idx)
                skipped += 1
                continue

            if final_tax_id:
                seen_in_batch.add(final_tax_id)

            # Create document reference
            doc_ref = db.collection(f"gestorias/{gestoria_id}/cuentas").document()

            # Prepare data - use classified if available, otherwise use raw
            data = {
                "nombre": contact.nombre_fiscal or "",
                "phone_number": contact.phone_number or "",
                "tax_id": classified.tax_id if classified else tax_id_to_use,
                "tax_country": classified.tax_country if classified else None,
                "tax_type": classified.tax_type if classified else None,
                "gmail_email": None,
                "gmail_watch_status": None,
                "min_income": None,
                "max_income": None,
                "created_at": firestore.SERVER_TIMESTAMP,
            }

            # Add optional fields if provided
            if contact.email_contacto:
                data["email_contacto"] = contact.email_contacto
            if contact.direccion_fiscal:
                data["direccion_fiscal"] = contact.direccion_fiscal
            if contact.codigo_postal:
                data["codigo_postal"] = contact.codigo_postal

            batch.set(doc_ref, data)
            created += 1

        except Exception as e:
            logger.error("Error preparing bulk create for row %d: %s", idx, e)
            errors.append({
                "index": idx,
                "message": str(e),
            })

    # Commit batch
    try:
        batch.commit()
    except Exception as e:
        logger.error("Batch commit failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Failed to save cuentas: {str(e)}")

    return BulkCreateResponse(created=created, skipped=skipped, errors=errors)


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
