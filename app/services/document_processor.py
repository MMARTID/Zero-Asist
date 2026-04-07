"""Shared document-processing pipeline.

Centralises the logic that was previously duplicated between the
``/procesar-documento`` HTTP endpoint (``app/main.py``) and the Gmail poller
(``app/collectors/gmail_poller.py``):

- SHA-256 hash computation
- Duplicate detection in Firestore
- Gemini extraction + normalisation + date conversion
- Transactional save to Firestore
"""
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

from app.ingestion.normalizer import dates_to_firestore, normalize_document
from app.services.firestore_client import db, guardar_si_no_existe
from app.services.gemini_client import extract_from_file

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "application/xml",
    "text/xml",
}


@dataclass
class ProcessingResult:
    status: Literal["processed", "duplicate"]
    doc_hash: str
    document_type: Optional[str]
    normalized_data: Optional[dict]
    extracted_data: Optional[dict]


def compute_hash(file_bytes: bytes) -> str:
    """Returns the SHA-256 hex digest of *file_bytes*."""
    return hashlib.sha256(file_bytes).hexdigest()


def is_document_duplicate(doc_hash: str) -> bool:
    """Returns ``True`` if a document with *doc_hash* already exists in Firestore."""
    return db.collection("documentos").document(doc_hash).get().exists


def extract_and_normalize(file_bytes: bytes, mime_type: str) -> tuple[str, dict, dict]:
    """Run the Gemini extraction + normalisation pipeline.

    Args:
        file_bytes: Raw bytes of the document.
        mime_type:  MIME type used to select the Gemini input format.

    Returns:
        A three-tuple ``(document_type_str, normalized_dict, extracted_data)`` where:

        * ``document_type_str`` – the document type returned by Gemini (e.g. ``"invoice_received"``).
        * ``normalized_dict``   – the normalised, Firestore-ready dict (date fields converted to ``datetime``).
        * ``extracted_data``    – the raw ``data`` dict as returned by Gemini before normalisation.

    Raises:
        ValueError: If the MIME type is not supported by Gemini.
        Exception:  Any error raised by the Gemini API call or the normaliser.
    """
    raw_extracted = extract_from_file(file_bytes, mime_type)
    document_type_str = raw_extracted.get("document_type", "other")
    extracted_data = raw_extracted.get("data", {})
    normalized = normalize_document(extracted_data, document_type_str)
    normalized_dict = dates_to_firestore(dict(normalized))
    return document_type_str, normalized_dict, extracted_data


def save_document(
    doc_hash: str,
    filename: str,
    file_size: int,
    document_type_str: str,
    normalized_dict: dict,
    extracted_data: dict,
    extra: dict | None = None,
) -> None:
    """Persist a document to the ``documentos`` Firestore collection.

    Uses a Firestore transaction via :func:`guardar_si_no_existe` to prevent
    race-condition duplicates.

    Args:
        doc_hash:          SHA-256 hash used as the document ID.
        filename:          Original file name.
        file_size:         File size in bytes.
        document_type_str: Document type string (e.g. ``"invoice_received"``).
        normalized_dict:   Normalised, Firestore-ready dict.
        extracted_data:    Raw data dict as returned by Gemini.
        extra:             Optional dict of additional fields to merge into the record
                           (e.g. Gmail metadata: ``gmail_message_id``, ``gmail_subject``).

    Raises:
        ValueError: If the document already exists (race condition caught by the transaction).
    """
    transaction = db.transaction()
    record: dict = {
        "document_hash": doc_hash,
        "file_name": filename,
        "file_size": file_size,
        "document_type": document_type_str,
        "normalized_data": normalized_dict,
        "extracted_data": extracted_data,
        "created_at": datetime.now(timezone.utc),
    }
    if extra:
        record.update(extra)
    guardar_si_no_existe(transaction, "documentos", doc_hash, record)
