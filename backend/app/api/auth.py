"""Firebase Auth dependency for the management API.

Verifies Firebase ID tokens sent by the frontend in the ``Authorization``
header and resolves the caller to a ``gestoria_id``.

This module is a *dependency*, not a router — it is consumed by
``onboarding.py`` and ``dashboard.py`` via ``Depends(get_current_gestoria)``.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request
from google.cloud import firestore

from app.api.deps import get_db as _get_db

logger = logging.getLogger(__name__)


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
    usuario_ref = db.collection("usuarios").document(uid)
    doc = usuario_ref.get()
    if not doc.exists:
        # Auto-register: create a new gestoría for this user using a transaction
        # to avoid race conditions (duplicate gestorías on concurrent requests).
        gestoria_ref = db.collection("gestorias").document()

        @firestore.transactional
        def _register(transaction: firestore.Transaction) -> str:
            snap = usuario_ref.get(transaction=transaction)
            if snap.exists:
                return snap.to_dict().get("gestoria_id", "")
            transaction.set(gestoria_ref, {
                "nombre": claims.get("name", "Mi Gestoría"),
                "email": claims.get("email", ""),
                "owner_uid": uid,
                "onboarding_complete": False,
            })
            transaction.set(usuario_ref, {
                "gestoria_id": gestoria_ref.id,
                "email": claims.get("email", ""),
                "nombre": claims.get("name", ""),
            })
            return gestoria_ref.id

        new_id = _register(db.transaction())
        logger.info("Auto-registered new gestoría %s for user %s", new_id, uid)
        return new_id

    gestoria_id = doc.to_dict().get("gestoria_id")
    if not gestoria_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with any gestoría",
        )

    return gestoria_id