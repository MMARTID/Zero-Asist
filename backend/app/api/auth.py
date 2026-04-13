"""Firebase Auth dependency for the management API.

Verifies Firebase ID tokens sent by the frontend in the ``Authorization``
header and resolves the caller to a ``gestoria_id``.

This module is a *dependency*, not a router — it is consumed by
``onboarding.py`` and ``dashboard.py`` via ``Depends(get_current_gestoria)``.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request
from google.cloud import firestore

logger = logging.getLogger(__name__)

# Lazy Firestore client
_db: Optional[firestore.Client] = None


def _get_db() -> firestore.Client:
    global _db
    if _db is None:
        from app.services.firestore_client import db
        _db = db
    return _db


def _verify_firebase_token(request: Request) -> dict:
    """Extract and verify a Firebase ID token from the ``Authorization`` header.

    Returns the decoded token claims dict.
    Raises HTTP 401 on missing / invalid token.

    ``firebase_admin`` is imported inside the function body so that modules
    which import ``auth.py`` do not trigger a top-level dependency on the
    package (important for testing and for endpoints that skip auth such as
    the OAuth callback).
    """
    import firebase_admin
    from firebase_admin import auth as firebase_auth

    # Initialise the default Firebase app once.
    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header",
        )

    token = auth_header[len("Bearer "):]
    try:
        decoded = firebase_auth.verify_id_token(token)
    except Exception as e:
        logger.warning("Firebase token verification failed: %s", e)
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        ) from e

    return decoded


def get_current_gestoria(
    claims: dict = Depends(_verify_firebase_token),
) -> str:
    """FastAPI dependency — returns the ``gestoria_id`` for the authenticated user.

    Resolution:
    1. Custom claim ``gestoria_id`` (set via Firebase Admin SDK) — fast path.
    2. Firestore lookup ``usuarios/{uid}`` → ``gestoria_id`` field — fallback.
    3. If no record exists, auto-register as a new gestoría (self-service).
    """
    gestoria_id = claims.get("gestoria_id")
    if gestoria_id:
        return gestoria_id

    uid = claims.get("uid", "")
    if not uid:
        raise HTTPException(status_code=403, detail="Token missing uid")

    db = _get_db()
    doc = db.collection("usuarios").document(uid).get()
    if not doc.exists:
        # Auto-register: create a new gestoría for this user
        gestoria_ref = db.collection("gestorias").document()
        gestoria_ref.set({
            "nombre": claims.get("name", "Mi Gestoría"),
            "email": claims.get("email", ""),
            "owner_uid": uid,
        })
        db.collection("usuarios").document(uid).set({
            "gestoria_id": gestoria_ref.id,
            "email": claims.get("email", ""),
            "nombre": claims.get("name", ""),
        })
        logger.info("Auto-registered new gestoría %s for user %s", gestoria_ref.id, uid)
        return gestoria_ref.id

    gestoria_id = doc.to_dict().get("gestoria_id")
    if not gestoria_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with any gestoría",
        )

    return gestoria_id