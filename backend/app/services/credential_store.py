"""Load and persist OAuth tokens for tenant Gmail accounts.

In production, tokens live in Google Secret Manager.  During local
development they fall back to Firestore (encrypted at rest by GCP).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from google.cloud import firestore
from google.oauth2.credentials import Credentials

from app.services.tenant import TenantContext

logger = logging.getLogger(__name__)

# Lazy — reuse the Firestore client already created by firestore_client.py.
_db: Optional[firestore.Client] = None


def _get_db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def _creds_doc_path(ctx: TenantContext) -> str:
    return f"gestorias/{ctx.gestoria_id}/cuentas/{ctx.cliente_id}"


def load_credentials(ctx: TenantContext) -> Optional[Credentials]:
    """Load OAuth ``Credentials`` for *ctx* from Firestore.

    Returns ``None`` if no credentials are stored yet.
    """
    db = _get_db()
    doc = db.document(_creds_doc_path(ctx)).get()
    if not doc.exists:
        return None

    data = doc.to_dict()
    token_json = data.get("gmail_credentials")
    if not token_json:
        return None

    info = json.loads(token_json) if isinstance(token_json, str) else token_json
    return Credentials.from_authorized_user_info(info)


def save_credentials(ctx: TenantContext, creds: Credentials) -> None:
    """Persist OAuth ``Credentials`` for *ctx* into Firestore."""
    db = _get_db()
    db.document(_creds_doc_path(ctx)).set(
        {"gmail_credentials": creds.to_json()},
        merge=True,
    )
