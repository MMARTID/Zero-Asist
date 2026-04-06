from datetime import datetime
from typing import Optional
from google.cloud import firestore
import os

# Inicializar cliente de Firestore (usa las credenciales por defecto en Cloud Run)
db = firestore.Client()

@firestore.transactional
def guardar_si_no_existe(transaction, coleccion: str, doc_hash: str, data: dict):
    ref = db.collection(coleccion).document(doc_hash)
    snapshot = ref.get(transaction=transaction)
    if snapshot.exists:
        raise ValueError("Documento duplicado")
    transaction.set(ref, data)
    
def guardar_documento(coleccion: str, doc_id: str, data: dict):
    doc_ref = db.collection(coleccion).document(doc_id)
    doc_ref.set(data)
    return doc_id


def is_message_processed(msg_id: str, include_errors: bool = True) -> bool:
    """Devuelve True si msg_id ya existe en gmail_processed.
    Si include_errors=False, los mensajes con status='error' se consideran no procesados
    para permitir reintentos.
    """
    doc = db.collection("gmail_processed").document(msg_id).get()
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
) -> None:
    """Escribe (o sobreescribe) el registro de un mensaje Gmail en gmail_processed."""
    db.collection("gmail_processed").document(msg_id).set({
        "msg_id": msg_id,
        "thread_id": thread_id or "",
        "from": from_addr or "",
        "subject": subject,
        "status": status,
        "reason": reason,
        "processed_at": datetime.utcnow(),
        "document_hashes": document_hashes or [],
        "provider": "gmail",
    })