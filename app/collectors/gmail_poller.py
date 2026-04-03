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
    query: str = "has:attachment (filename:pdf OR filename:PDF OR filename:xml OR filename:jpg OR filename:png)",
    max_results: int = 10,
) -> list[dict]:
    """
    Orquesta el flujo completo:
    1. Conecta con Gmail
    2. Lista candidatos (Capa 1 - filtro Gmail)
    3. Filtra por heurística local (Capa 2 - sin LLM)
    4. Descarga adjuntos
    5. Extrae con Gemini solo los que pasan los filtros
    6. Normaliza y guarda en Firestore
    Devuelve la lista de documentos procesados.
    """
    service = get_gmail_service()
    processed = []

    candidates = list_candidate_messages(service, query=query, max_results=max_results)
    logger.info(f"📬 Candidatos encontrados: {len(candidates)}")

    for msg in candidates:
        subject = msg["subject"]
        snippet = msg["snippet"]
        msg_id = msg["id"]

        # Capa 2 — heurística local
        if not is_invoice_candidate(subject, snippet):
            logger.debug(f"⏭️  Descartado por heurística: '{subject}'")
            continue

        attachments = get_attachments(service, msg_id)
        if not attachments:
            logger.debug(f"⏭️  Sin adjuntos válidos: '{subject}'")
            continue

        for attachment in attachments:
            filename = attachment["filename"]
            mime_type = attachment["mime_type"]
            data = attachment["data"]

            doc_hash = hashlib.sha256(data).hexdigest()

            # Evitar reprocesar documentos ya guardados
            doc_ref = db.collection("documentos").document(doc_hash)
            if doc_ref.get().exists:
                logger.info(f"🔁 Duplicado, ignorado: {filename}")
                continue

            try:
                # Capa 3 — Gemini solo si pasa todo lo anterior
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
                processed.append({
                    "document_hash": doc_hash,
                    "file_name": filename,
                    "document_type": document_type_str,
                    "normalized_data": normalized_dict,
                })

            except ValueError:
                logger.warning(f"🔁 Duplicado en transacción: {filename}")
            except Exception as e:
                logger.error(f"❌ Error procesando {filename}: {e}")

    logger.info(f"✅ Procesados: {len(processed)} documentos")
    return processed