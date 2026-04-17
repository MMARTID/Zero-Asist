"""Shared API dependencies."""

from __future__ import annotations

from typing import Optional

from google.cloud import firestore

_db: Optional[firestore.Client] = None


def get_db() -> firestore.Client:
    """Lazily initialised Firestore client shared across all API modules."""
    global _db
    if _db is None:
        from app.services.firestore_client import db
        _db = db
    return _db
