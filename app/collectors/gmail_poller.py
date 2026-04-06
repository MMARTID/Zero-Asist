import logging
from app.collectors.gmail_service import get_gmail_service
from app.collectors.gmail_reader import (
    list_candidate_messages,
    is_invoice_candidate,
    get_attachments,
)
from app.services.document_processor import (
    compute_hash,
    extract_and_normalize,
    is_document_duplicate,
    save_document,
)
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

        # Skip — mensaje ya procesado en una ejecución anterior
        if is_message_processed(msg_id):
            logger.debug(f"⏭️  Ya procesado, ignorando: '{subject}'")
            continue

        # Capa 2 — heurística local
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

        # Acumuladores por mensaje (un mark_message_processed al final)
        msg_hashes: list = []
        msg_has_processed = False
        msg_has_duplicate = False
        msg_has_error = False
        msg_error_reason: str | None = None

        for attachment in attachments:
            filename = attachment["filename"]
            mime_type = attachment["mime_type"]
            data = attachment["data"]

            doc_hash = compute_hash(data)
            logger.debug(f"🔍 Revisando adjunto: {filename} | hash={doc_hash}")

            # Evitar reprocesar documentos ya guardados
            try:
                if is_document_duplicate(doc_hash):
                    logger.info(f"🔁 Duplicado, ignorado: {filename}")
                    summary["duplicados"].append({
                        "file_name": filename,
                        "document_hash": doc_hash,
                        "gmail_message_id": msg_id,
                        "gmail_subject": subject,
                    })
                    msg_hashes.append(doc_hash)
                    msg_has_duplicate = True
                    continue
            except Exception as e:
                logger.error(f"❌ Error comprobando duplicado para {filename}: {e}")
                summary["errores"].append({
                    "file_name": filename,
                    "document_hash": doc_hash,
                    "gmail_message_id": msg_id,
                    "reason": f"error_check_duplicado: {str(e)}",
                })
                msg_has_error = True
                msg_error_reason = f"error_check_duplicado: {str(e)}"
                continue

            try:
                # Capa 3 — Gemini solo si pasa todo lo anterior
                logger.debug(f"🤖 Enviando a Gemini: {filename}")
                document_type_str, normalized_dict, extracted_data = extract_and_normalize(data, mime_type)

                save_document(
                    doc_hash=doc_hash,
                    filename=filename,
                    file_size=len(data),
                    document_type_str=document_type_str,
                    normalized_dict=normalized_dict,
                    extracted_data=extracted_data,
                    extra={
                        "source": "gmail",
                        "gmail_message_id": msg_id,
                        "gmail_subject": subject,
                        "gmail_from": from_addr,
                    },
                )

                logger.info(f"✅ Guardado: {filename} ({document_type_str})")
                summary["procesados"].append({
                    "document_hash": doc_hash,
                    "file_name": filename,
                    "document_type": document_type_str,
                    "normalized_data": normalized_dict,
                })
                msg_hashes.append(doc_hash)
                msg_has_processed = True

            except ValueError:
                logger.warning(f"🔁 Duplicado en transacción: {filename}")
                summary["duplicados"].append({
                    "file_name": filename,
                    "document_hash": doc_hash,
                    "gmail_message_id": msg_id,
                    "reason": "duplicado_transaccion",
                })
                msg_hashes.append(doc_hash)
                msg_has_duplicate = True
            except Exception as e:
                logger.error(f"❌ Error procesando {filename}: {e}")
                summary["errores"].append({
                    "file_name": filename,
                    "document_hash": doc_hash,
                    "gmail_message_id": msg_id,
                    "reason": str(e),
                })
                msg_has_error = True
                msg_error_reason = str(e)

        # Determinar status global del mensaje y registrar en historial
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