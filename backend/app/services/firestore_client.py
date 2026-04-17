from datetime import datetime, timezone
from typing import Optional
from google.cloud import firestore

from app.services.constants import COLLECTION_GMAIL
from app.services.tenant import TenantContext, resolve_docs_collection, resolve_gmail_collection

# Inicializar cliente de Firestore (usa las credenciales por defecto en Cloud Run)
db = firestore.Client()


class DocumentDuplicateError(Exception):
    """Raised when a document already exists in Firestore."""


@firestore.transactional
def guardar_si_no_existe(transaction, coleccion: str, doc_hash: str, data: dict):
    ref = db.collection(coleccion).document(doc_hash)
    snapshot = ref.get(transaction=transaction)
    if snapshot.exists:
        raise DocumentDuplicateError(f"Documento duplicado: {doc_hash}")
    transaction.set(ref, data)

def is_message_processed(
    msg_id: str,
    include_errors: bool = False,
    ctx: Optional[TenantContext] = None,
) -> bool:
    """Devuelve True si msg_id ya existe en gmail_processed.
    Si include_errors=False (default), los mensajes con status='error' se consideran
    no procesados para permitir reintentos.
    """
    collection = resolve_gmail_collection(ctx)
    doc = db.collection(collection).document(msg_id).get()
    if not doc.exists:
        return False
    if not include_errors and doc.to_dict().get("status") == "error":
        return False
    return True


def mark_message_processed(
    msg_id: str,
    status: str,
    subject: str,
    reason: Optional[str] = None,
    document_hashes: Optional[list] = None,
    thread_id: Optional[str] = None,
    from_addr: Optional[str] = None,
    ctx: Optional[TenantContext] = None,
) -> None:
    """Escribe (o sobreescribe) el registro de un mensaje Gmail en gmail_processed."""
    collection = resolve_gmail_collection(ctx)
    db.collection(collection).document(msg_id).set({
        "msg_id": msg_id,
        "thread_id": thread_id or "",
        "from": from_addr or "",
        "subject": subject,
        "status": status,
        "reason": reason,
        "processed_at": datetime.now(timezone.utc),
        "document_hashes": document_hashes or [],
        "provider": "gmail",
    })