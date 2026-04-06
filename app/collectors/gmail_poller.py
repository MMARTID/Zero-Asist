import logging
from datetime import datetime
from app.collectors.gmail_service import get_gmail_service
from app.collectors.gmail_reader import (
    list_candidate_messages,
    is_invoice_candidate,
    get_attachments,
)
from app.services.gemini_client import extract_from_file
from app.ingestion.normalizer import normalize_document
from app.services.firestore_client import db, guardar_si_no_existe
import hashlib

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

        # Capa 2 — heurística local
        if not is_invoice_candidate(subject, snippet):
            logger.debug(f"⏭️  Descartado por heurística: '{subject}'")
            summary["descartados"].append({
                "gmail_message_id": msg_id,
                "subject": subject,
                "reason": "heuristica",
            })
            continue

        attachments = get_attachments(service, msg_id)
        if not attachments:
            logger.debug(f"⏭️  Sin adjuntos válidos: '{subject}'")
            summary["descartados"].append({
                "gmail_message_id": msg_id,
                "subject": subject,
                "reason": "sin_adjuntos",
            })
            continue

        logger.info(f"📎 {len(attachments)} adjunto/s encontrado/s en: '{subject}'")

        for attachment in attachments:
            filename = attachment["filename"]
            mime_type = attachment["mime_type"]
            data = attachment["data"]

            doc_hash = hashlib.sha256(data).hexdigest()
            logger.debug(f"🔍 Revisando adjunto: {filename} | hash={doc_hash}")

            # Evitar reprocesar documentos ya guardados
            try:
                doc_ref = db.collection("documentos").document(doc_hash)
                if doc_ref.get().exists:
                    logger.info(f"🔁 Duplicado, ignorado: {filename}")
                    summary["duplicados"].append({
                        "file_name": filename,
                        "document_hash": doc_hash,
                        "gmail_message_id": msg_id,
                        "gmail_subject": subject,
                    })
                    continue
            except Exception as e:
                logger.error(f"❌ Error comprobando duplicado para {filename}: {e}")
                summary["errores"].append({
                    "file_name": filename,
                    "document_hash": doc_hash,
                    "gmail_message_id": msg_id,
                    "reason": f"error_check_duplicado: {str(e)}",
                })
                continue

            try:
                # Capa 3 — Gemini solo si pasa todo lo anterior
                logger.debug(f"🤖 Enviando a Gemini: {filename}")
                raw_extracted = extract_from_file(data, mime_type)
                document_type_str = raw_extracted.get("document_type", "other")
                extracted_data = raw_extracted.get("data", {})

                normalized = normalize_document(extracted_data, document_type_str)

                # Convertir fechas date → datetime para Firestore
                normalized_dict = dict(normalized)
                for field in ["issue_date", "due_date", "period_start", "period_end"]:
                    val = normalized_dict.get(field)
                    if val and hasattr(val, "year"):
                        normalized_dict[field] = datetime.combine(val, datetime.min.time())

                transaction = db.transaction()
                guardar_si_no_existe(
                    transaction,
                    "documentos",
                    doc_hash,
                    {
                        "document_hash": doc_hash,
                        "file_name": filename,
                        "file_size": len(data),
                        "document_type": document_type_str,
                        "normalized_data": normalized_dict,
                        "extracted_data": extracted_data,
                        "source": "gmail",
                        "gmail_message_id": msg_id,
                        "gmail_subject": subject,
                        "gmail_from": msg["from"],
                        "created_at": datetime.utcnow(),
                    },
                )

                logger.info(f"✅ Guardado: {filename} ({document_type_str})")
                summary["procesados"].append({
                    "document_hash": doc_hash,
                    "file_name": filename,
                    "document_type": document_type_str,
                    "normalized_data": normalized_dict,
                })

            except ValueError:
                logger.warning(f"🔁 Duplicado en transacción: {filename}")
                summary["duplicados"].append({
                    "file_name": filename,
                    "document_hash": doc_hash,
                    "gmail_message_id": msg_id,
                    "reason": "duplicado_transaccion",
                })
            except Exception as e:
                logger.error(f"❌ Error procesando {filename}: {e}")
                summary["errores"].append({
                    "file_name": filename,
                    "document_hash": doc_hash,
                    "gmail_message_id": msg_id,
                    "reason": str(e),
                })

    logger.info(
        f"✅ Resumen: {len(summary['procesados'])} procesados | "
        f"{len(summary['duplicados'])} duplicados | "
        f"{len(summary['errores'])} errores | "
        f"{len(summary['descartados'])} descartados"
    )
    return summary