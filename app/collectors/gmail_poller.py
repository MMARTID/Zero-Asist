import logging
from app.collectors.gmail_service import get_gmail_service
from app.collectors.gmail_reader import (
    list_candidate_messages,
    is_invoice_candidate,
    get_attachments,
)
from app.services.document_processor import process_document
from app.services.firestore_client import (
    is_message_processed,
    mark_message_processed,
)

logger = logging.getLogger(__name__)


def poll_gmail(
    query: str = "has:attachment (filename:pdf OR filename:xml OR filename:jpg OR filename:png)",
    max_results: int = 10,
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
    service = get_gmail_service()

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

        if is_message_processed(msg_id):
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
            )
            continue

        logger.info(f"📎 {len(attachments)} adjunto/s encontrado/s en: '{subject}'")

        msg_hashes: list = []
        msg_has_processed = False
        msg_has_duplicate = False
        msg_has_error = False
        msg_error_reason: str | None = None

        for attachment in attachments:
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
                )
            except Exception as e:
                logger.error(f"❌ Error procesando {filename}: {e}")
                summary["errores"].append({
                    "file_name": filename,
                    "gmail_message_id": msg_id,
                    "reason": str(e),
                })
                msg_has_error = True
                msg_error_reason = str(e)
                continue

            if result.status == "duplicate":
                logger.info(f"🔁 Duplicado, ignorado: {filename}")
                summary["duplicados"].append({
                    "file_name": filename,
                    "document_hash": result.doc_hash,
                    "gmail_message_id": msg_id,
                    "gmail_subject": subject,
                })
                msg_hashes.append(result.doc_hash)
                msg_has_duplicate = True
            else:
                logger.info(f"✅ Guardado: {filename} ({result.document_type})")
                summary["procesados"].append({
                    "document_hash": result.doc_hash,
                    "file_name": filename,
                    "document_type": result.document_type,
                    "normalized_data": result.normalized_data,
                })
                msg_hashes.append(result.doc_hash)
                msg_has_processed = True

        if msg_has_processed:
            final_status = "processed"
        elif msg_has_error:
            final_status = "error"
        else:
            final_status = "duplicate"

        mark_message_processed(
            msg_id, final_status, subject,
            reason=msg_error_reason,
            document_hashes=msg_hashes,
            thread_id=thread_id,
            from_addr=from_addr,
        )

    logger.info(
        f"✅ Resumen: {len(summary['procesados'])} procesados | "
        f"{len(summary['duplicados'])} duplicados | "
        f"{len(summary['errores'])} errores | "
        f"{len(summary['descartados'])} descartados"
    )
    return summary