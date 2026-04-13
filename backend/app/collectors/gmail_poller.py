import logging
from typing import Optional

from app.collectors.gmail_service import get_gmail_service
from app.collectors.gmail_reader import (
    list_candidate_messages,
    is_invoice_candidate,
    get_attachments,
)
from app.services.document_processor import process_document
from app.services.errors import PipelineError
from app.services.firestore_client import (
    is_message_processed,
    mark_message_processed,
)
from app.services.tenant import TenantContext

logger = logging.getLogger(__name__)


def _process_attachment(
    attachment: dict, msg_id: str, subject: str, from_addr: str,
    ctx: Optional[TenantContext] = None,
) -> tuple[str, dict]:
    """Process a single attachment and return (category, summary_entry).

    *category* is one of ``"procesados"``, ``"duplicados"`` or ``"errores"``.
    """
    filename = attachment["filename"]
    mime_type = attachment["mime_type"]
    data = attachment["data"]

    try:
        result = process_document(
            file_bytes=data,
            mime_type=mime_type,
            filename=filename,
            file_size=len(data),
            extra={
                "source": "gmail",
                "gmail_message_id": msg_id,
                "gmail_subject": subject,
                "gmail_from": from_addr,
            },
            ctx=ctx,
        )
    except PipelineError as e:
        logger.error("❌ Error procesando %s: %s", filename, e)
        return "errores", {
            "file_name": filename,
            "gmail_message_id": msg_id,
            "error_code": e.code,
            "error_message": e.message,
        }
    except Exception as e:
        pipeline_err = PipelineError.from_exception(e)
        logger.exception("❌ Error inesperado procesando %s: %s", filename, e)
        return "errores", {
            "file_name": filename,
            "gmail_message_id": msg_id,
            "error_code": pipeline_err.code,
            "error_message": pipeline_err.message,
        }

    if result.status == "duplicate":
        logger.info(f"🔁 Duplicado, ignorado: {filename}")
        return "duplicados", {
            "file_name": filename,
            "document_hash": result.doc_hash,
            "gmail_message_id": msg_id,
            "gmail_subject": subject,
        }

    logger.info(f"✅ Guardado: {filename} ({result.document_type})")
    return "procesados", {
        "document_hash": result.doc_hash,
        "file_name": filename,
        "document_type": result.document_type,
        "normalized_data": result.normalized_data,
    }


def _derive_message_status(
    categories: list[str],
) -> tuple[str, str | None]:
    """Derive the final message status and error reason from attachment outcomes.

    Returns ``(status, reason)`` where *reason* is only set for ``"error"`` status.
    """
    has_processed = "procesados" in categories
    has_error = "errores" in categories

    if has_error:
        return "error", None
    if has_processed:
        return "processed", None
    if not has_error:
        # All duplicates (no errors, no processed)
        return "duplicate", None
    return "error", None


def poll_gmail(
    query: str = "has:attachment (filename:pdf OR filename:xml OR filename:jpg OR filename:png)",
    max_results: int = 10,
    ctx: Optional[TenantContext] = None,
) -> dict:
    """
    Orquesta el flujo completo:
    1. Conecta con Gmail
    2. Lista candidatos (Capa 1 - filtro Gmail)
    3. Filtra por heurística local (Capa 2 - sin LLM)
    4. Descarga adjuntos
    5. Extrae con Gemini solo los que pasan los filtros
    6. Normaliza y guarda en Firestore

    Devuelve un resumen con:
    - procesados: documentos nuevos guardados correctamente
    - duplicados: documentos ya existentes en Firestore
    - errores: adjuntos que fallaron en extracción/guardado
    - descartados: mensajes que no pasaron la heurística o no tenían adjuntos válidos
    """
    service = get_gmail_service(ctx=ctx)

    summary = {
        "procesados": [],
        "duplicados": [],
        "errores": [],
        "descartados": [],
    }

    candidates = list_candidate_messages(service, query=query, max_results=max_results)
    logger.info(f"📬 Candidatos encontrados: {len(candidates)}")

    for msg in candidates:
        subject = msg["subject"]
        snippet = msg["snippet"]
        msg_id = msg["id"]
        thread_id = msg.get("thread_id", "")
        from_addr = msg.get("from", "")

        if is_message_processed(msg_id, include_errors=False, ctx=ctx):
            logger.debug(f"⏭️  Ya procesado, ignorando: '{subject}'")
            continue

        if not is_invoice_candidate(subject, snippet):
            logger.debug(f"⏭️  Descartado por heurística: '{subject}'")
            summary["descartados"].append({
                "gmail_message_id": msg_id,
                "subject": subject,
                "reason": "heuristica",
            })
            mark_message_processed(
                msg_id, "discarded", subject,
                reason="heuristica", thread_id=thread_id, from_addr=from_addr,
                ctx=ctx,
            )
            continue

        attachments = get_attachments(service, msg_id)
        if not attachments:
            logger.debug(f"⏭️  Sin adjuntos válidos: '{subject}'")
            summary["descartados"].append({
                "gmail_message_id": msg_id,
                "subject": subject,
                "reason": "sin_adjuntos",
            })
            mark_message_processed(
                msg_id, "discarded", subject,
                reason="sin_adjuntos", thread_id=thread_id, from_addr=from_addr,
                ctx=ctx,
            )
            continue

        logger.info(f"📎 {len(attachments)} adjunto/s encontrado/s en: '{subject}'")

        categories: list[str] = []
        msg_hashes: list[str] = []
        error_reason: str | None = None

        for attachment in attachments:
            category, entry = _process_attachment(attachment, msg_id, subject, from_addr, ctx=ctx)
            summary[category].append(entry)
            categories.append(category)
            if doc_hash := entry.get("document_hash"):
                msg_hashes.append(doc_hash)
            if category == "errores" and (code := entry.get("error_code")):
                if error_reason is None or code != "UNKNOWN":
                    error_reason = code

        final_status, _ = _derive_message_status(categories)

        mark_message_processed(
            msg_id, final_status, subject,
            reason=error_reason if final_status == "error" else None,
            document_hashes=msg_hashes,
            thread_id=thread_id,
            from_addr=from_addr,
            ctx=ctx,
        )

    logger.info(
        f"✅ Resumen: {len(summary['procesados'])} procesados | "
        f"{len(summary['duplicados'])} duplicados | "
        f"{len(summary['errores'])} errores | "
        f"{len(summary['descartados'])} descartados"
    )
    return summary