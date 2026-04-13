"""Dashboard endpoints — list clients, documents, and stats for a gestoría.

All endpoints require Firebase Auth (``Depends(get_current_gestoria)``).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from google.cloud import firestore

from app.api.auth import get_current_gestoria
from app.services.tenant import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Lazy Firestore client
_db: Optional[firestore.Client] = None


def _get_db() -> firestore.Client:
    global _db
    if _db is None:
        from app.services.firestore_client import db
        _db = db
    return _db


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

@router.get("/clientes")
def list_clients(
    gestoria_id: str = Depends(get_current_gestoria),
):
    """List all clients for the authenticated gestoría."""
    db = _get_db()
    docs = db.collection(f"gestorias/{gestoria_id}/clientes").get()

    clients = []
    for doc in docs:
        data = doc.to_dict()
        clients.append({
            "cliente_id": doc.id,
            "nombre": data.get("nombre", ""),
            "email": data.get("email", ""),
            "gmail_email": data.get("gmail_email"),
            "gmail_watch_status": data.get("gmail_watch_status"),
        })

    return {"gestoria_id": gestoria_id, "clientes": clients}


@router.get("/clientes/{cliente_id}")
def get_client(
    cliente_id: str,
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Get details for a single client."""
    db = _get_db()
    doc = db.document(f"gestorias/{gestoria_id}/clientes/{cliente_id}").get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Client not found")

    data = doc.to_dict()
    return {
        "cliente_id": doc.id,
        "gestoria_id": gestoria_id,
        "nombre": data.get("nombre", ""),
        "email": data.get("email", ""),
        "gmail_email": data.get("gmail_email"),
        "gmail_watch_status": data.get("gmail_watch_status"),
        "gmail_watch_state": data.get("gmail_watch_state"),
    }


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@router.get("/clientes/{cliente_id}/documentos")
def list_documents(
    cliente_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    gestoria_id: str = Depends(get_current_gestoria),
):
    """List documents for a client, most recent first."""
    ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=cliente_id)
    db = _get_db()

    docs = (
        db.collection(ctx.docs_collection)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .get()
    )

    documents = []
    for doc in docs:
        data = doc.to_dict()
        documents.append({
            "doc_hash": doc.id,
            "document_type": data.get("document_type"),
            "filename": data.get("file_name"),
            "created_at": data.get("created_at"),
            "normalized": data.get("normalized_data"),
        })

    return {
        "gestoria_id": gestoria_id,
        "cliente_id": cliente_id,
        "documentos": documents,
        "count": len(documents),
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats")
def get_stats(
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Summary stats for the authenticated gestoría.

    Performs N+1 reads (clients + docs per client).  Acceptable at low scale;
    for larger deployments, denormalise counters on the gestoría document.
    """
    db = _get_db()
    client_snapshots = list(
        db.collection(f"gestorias/{gestoria_id}/clientes").get(),
    )

    total_clients = len(client_snapshots)
    active_watches = 0
    connected_gmail = 0
    total_documents = 0

    for snap in client_snapshots:
        data = snap.to_dict()
        if data.get("gmail_watch_status") == "active":
            active_watches += 1
        if data.get("gmail_email"):
            connected_gmail += 1

        ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=snap.id)
        total_documents += len(list(db.collection(ctx.docs_collection).get()))

    return {
        "gestoria_id": gestoria_id,
        "total_clients": total_clients,
        "connected_gmail": connected_gmail,
        "active_watches": active_watches,
        "total_documents": total_documents,
    }
