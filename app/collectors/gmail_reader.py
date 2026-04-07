import base64
from typing import Optional
from googleapiclient.discovery import Resource
from app.services.document_processor import ALLOWED_MIME_TYPES

# ---------------------------------------------------------------------------
# Palabras clave para la heurística local (Capa 2)
# ---------------------------------------------------------------------------
INVOICE_KEYWORDS = [
    "factura", "invoice", "fra.", "fra ",
    "recibo", "receipt",
    "albarán", "albaran",
    "importe", "total", "iva", "irpf",
    "vencimiento", "due date",
    "pago recibido", "payment received", "cargo", "abono",
]


# ---------------------------------------------------------------------------
# Capa 1 — Filtrado por query de Gmail (gratis)
# ---------------------------------------------------------------------------
def list_candidate_messages(
    service: Resource,
    query: str = "has:attachment (filename:pdf OR filename:PDF OR filename:xml OR filename:XML OR filename:jpg OR filename:JPG OR filename:png OR filename:PNG)",
    max_results: int = 50,
) -> list[dict]:
    """
    Devuelve una lista de mensajes que pasan el filtro de Gmail.
    Cada item contiene: id, snippet, subject, from.
    """
    result = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=max_results,
        labelIds=["INBOX"],
    ).execute()

    messages = result.get("messages", [])
    if not messages:
        return []

    candidates = []
    for msg in messages:
        detail = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="metadata",
            metadataHeaders=["Subject", "From"],
        ).execute()

        headers = {
            h["name"]: h["value"]
            for h in detail.get("payload", {}).get("headers", [])
        }

        candidates.append({
            "id": msg["id"],
            "thread_id": msg.get("threadId", ""),
            "snippet": detail.get("snippet", ""),
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
        })

    return candidates


# ---------------------------------------------------------------------------
# Capa 2 — Heurística local sin LLM (gratis)
# ---------------------------------------------------------------------------
def is_invoice_candidate(subject: str, snippet: str) -> bool:
    """
    Devuelve True si el subject o snippet contienen palabras clave de factura.
    Se ejecuta localmente, sin coste.
    """
    text = (subject + " " + snippet).lower()
    return any(kw in text for kw in INVOICE_KEYWORDS)


# ---------------------------------------------------------------------------
# Descarga de adjuntos
# ---------------------------------------------------------------------------
def get_attachments(service: Resource, message_id: str) -> list[dict]:
    """
    Descarga los adjuntos de un mensaje que sean de tipo permitido.
    Devuelve lista de dicts: { filename, mime_type, data }
    """
    message = service.users().messages().get(
        userId="me",
        id=message_id,
        format="full",
    ).execute()

    attachments = []
    _extract_parts(service, message_id, message.get("payload", {}), attachments)
    return attachments


def _extract_parts(
    service: Resource,
    message_id: str,
    part: dict,
    result: list,
) -> None:
    """Recorre recursivamente las partes MIME del mensaje."""
    mime_type = part.get("mimeType", "")
    filename = part.get("filename", "")
    body = part.get("body", {})

    # Parte con adjunto permitido: priorizar attachmentId y, si no existe,
    # usar los datos inline en base64.
    if filename and mime_type in ALLOWED_MIME_TYPES:
        data = None
        attachment_id = body.get("attachmentId")

        if attachment_id:
            data = _download_attachment(service, message_id, attachment_id)
        elif body.get("data"):
            data = base64.urlsafe_b64decode(body["data"])

        if data:
            result.append({
                "filename": filename,
                "mime_type": mime_type,
                "data": data,
            })

    # Recorrer sub-partes (multipart/*)
    for sub_part in part.get("parts", []):
        _extract_parts(service, message_id, sub_part, result)


def _download_attachment(
    service: Resource,
    message_id: str,
    attachment_id: str,
) -> Optional[bytes]:
    """Descarga un adjunto por su attachmentId y devuelve los bytes."""
    try:
        attachment = service.users().messages().attachments().get(
            userId="me",
            messageId=message_id,
            id=attachment_id,
        ).execute()
        return base64.urlsafe_b64decode(attachment["data"])
    except Exception:
        return None