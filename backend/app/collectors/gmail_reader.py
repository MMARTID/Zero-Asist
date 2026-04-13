import base64
import logging
import time
from typing import Optional
from googleapiclient.discovery import Resource
from tenacity import retry, stop_after_attempt, wait_exponential
from app.services.document_processor import ALLOWED_MIME_TYPES

logger = logging.getLogger(__name__)

# Map file extensions → canonical MIME type for when Gmail reports
# application/octet-stream or an otherwise incorrect content-type.
_EXT_MIME: dict[str, str] = {
    ".pdf":  "application/pdf",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".xml":  "application/xml",
}

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

    if filename:
        # Normalise MIME type — Gmail sometimes reports application/octet-stream
        # for attachments whose sender didn't set an explicit content-type.
        effective_mime = mime_type
        if effective_mime not in ALLOWED_MIME_TYPES:
            ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            effective_mime = _EXT_MIME.get(ext, mime_type)

        if effective_mime in ALLOWED_MIME_TYPES:
            data = None
            attachment_id = body.get("attachmentId")
            if attachment_id:
                try:
                    data = _download_attachment(service, message_id, attachment_id)
                except Exception as e:
                    logger.error(
                        "Fallo definitivo descargando adjunto '%s' tras reintentos: %s",
                        filename, e,
                    )
            elif body.get("data"):
                data = base64.urlsafe_b64decode(body["data"])

            if data:
                if effective_mime != mime_type:
                    logger.info(
                        "MIME type corregido para '%s': %s → %s",
                        filename, mime_type, effective_mime,
                    )
                result.append({
                    "filename": filename,
                    "mime_type": effective_mime,
                    "data": data,
                })
            else:
                logger.warning(
                    "No se pudo descargar el adjunto '%s' (attachmentId=%s)",
                    filename, body.get("attachmentId", "N/A"),
                )
        else:
            logger.debug("Adjunto ignorado (tipo no soportado): %s [%s]", filename, mime_type)

    # Recorrer sub-partes (multipart/*)
    for sub_part in part.get("parts", []):
        _extract_parts(service, message_id, sub_part, result)


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _download_attachment(
    service: Resource,
    message_id: str,
    attachment_id: str,
) -> Optional[bytes]:
    """Descarga un adjunto por su attachmentId y devuelve los bytes.

    Reintenta hasta 4 veces con backoff exponencial.
    """
    try:
        attachment = service.users().messages().attachments().get(
            userId="me",
            messageId=message_id,
            id=attachment_id,
        ).execute()
        return base64.urlsafe_b64decode(attachment["data"])
    except Exception as e:
        logger.warning(
            "Error descargando adjunto %s del mensaje %s: %s",
            attachment_id, message_id, e,
        )
        raise