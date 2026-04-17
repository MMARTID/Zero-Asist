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

from app.ingestion.normalizer import dates_to_firestore, normalize_document, CuentaContext
from app.models.contact import ContactRef
from app.models.document import DocumentType
from app.models.registry import DOCUMENT_TYPE_REGISTRY
from app.services.constants import COLLECTION_DOCS
from app.services.entity_resolver import resolve_and_link
from app.services.errors import PipelineError
from app.services.firestore_client import db, DocumentDuplicateError, guardar_si_no_existe
from app.services.gemini_client import classify_document, extract_document
from app.services import storage_client as _gcs
from app.services.tax_id import normalize_tax_id_raw, tax_ids_match
from app.ingestion.helpers import _normalize_tax_id
from app.services.tenant import TenantContext, resolve_docs_collection

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
    contact_refs: list[ContactRef] | None = None


def compute_hash(file_bytes: bytes) -> str:
    """Returns the SHA-256 hex digest of *file_bytes*."""
    return hashlib.sha256(file_bytes).hexdigest()


def is_document_duplicate(
    doc_hash: str,
    ctx: Optional[TenantContext] = None,
) -> bool:
    """Returns ``True`` if a document with *doc_hash* already exists in Firestore."""
    collection = resolve_docs_collection(ctx)
    return db.collection(collection).document(doc_hash).get().exists


def _load_cuenta_context(
    ctx: Optional[TenantContext],
) -> Optional[CuentaContext]:
    """Load the cuenta's identity from Firestore for prompt enrichment."""
    if ctx is None:
        return None
    doc = db.document(f"gestorias/{ctx.gestoria_id}/cuentas/{ctx.cliente_id}").get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    raw_tax_id = data.get("tax_id")
    return CuentaContext(
        nombre=data.get("nombre"),
        tax_id=normalize_tax_id_raw(raw_tax_id) if raw_tax_id else None,
        tax_country=data.get("tax_country"),
        tax_type=data.get("tax_type"),
    )


def extract_and_normalize(
    file_bytes: bytes,
    mime_type: str,
    ctx: Optional[TenantContext] = None,
) -> tuple[str, dict, dict]:
    """Run the two-phase Gemini extraction + normalisation pipeline.

    Phase 1: classify the document type.
    Phase 2: extract fields using a type-specific schema and prompt.
    Then normalise and convert dates for Firestore.

    Returns:
        A three-tuple ``(document_type_str, normalized_dict, extracted_data)``.
    """
    # Load cuenta context once — used for both prompt enrichment and validation
    cuenta_context = _load_cuenta_context(ctx)

    # Phase 1 — classify (con contexto de cuenta para mejorar invoice_received vs invoice_sent)
    document_type_str = classify_document(file_bytes, mime_type, cuenta_context=cuenta_context)

    # Validate against enum; coerce invalid values to "other".
    valid_types = {t.value for t in DocumentType}
    if document_type_str not in valid_types:
        logger.warning(
            "Unknown document_type from Gemini: %r — coercing to 'other'",
            document_type_str,
        )
        document_type_str = "other"

    # Phase 2 — extract (skip if no schema registered, e.g. "other")
    config = DOCUMENT_TYPE_REGISTRY.get(document_type_str)
    if config and config.extraction_schema:
        extracted_data = extract_document(
            file_bytes, mime_type, document_type_str,
            cuenta_context=cuenta_context,
        )
    else:
        extracted_data = {}

    normalized = normalize_document(extracted_data, document_type_str, cuenta_context=cuenta_context)
    normalized_dict = dates_to_firestore(dict(normalized))

    # ── Post-classification correction ────────────────────────────
    # If Gemini classified an invoice in the wrong direction, the
    # cuenta's tax_id will appear in the wrong position.  Detect and
    # fix: for invoice_received the cuenta should be the client
    # (receptor), for invoice_sent the cuenta should be the issuer
    # (emisor).  If it's the other way around, flip the type.
    if cuenta_context and cuenta_context.tax_id and document_type_str in (
        "invoice_received", "invoice_sent",
    ):
        issuer_nif = _normalize_tax_id(normalized_dict.get("issuer_nif"))
        client_nif = _normalize_tax_id(normalized_dict.get("client_nif"))
        cuenta_nif = normalize_tax_id_raw(cuenta_context.tax_id)
        flipped = None
        if document_type_str == "invoice_received":
            # cuenta debería ser el client (receptor); si es el issuer → flip
            if issuer_nif and cuenta_nif and tax_ids_match(issuer_nif, cuenta_nif):
                if not (client_nif and tax_ids_match(client_nif, cuenta_nif)):
                    flipped = "invoice_sent"
        else:  # invoice_sent
            # cuenta debería ser el issuer (emisor); si es el client → flip
            if client_nif and cuenta_nif and tax_ids_match(client_nif, cuenta_nif):
                if not (issuer_nif and tax_ids_match(issuer_nif, cuenta_nif)):
                    flipped = "invoice_received"
        if flipped:
            logger.warning(
                "Post-classification flip: %s → %s (cuenta NIF %s found in wrong position)",
                document_type_str, flipped, cuenta_nif,
            )
            document_type_str = flipped

    return document_type_str, normalized_dict, extracted_data

def save_document(
    doc_hash: str,
    filename: str,
    file_size: int,
    document_type_str: str,
    normalized_dict: dict,
    extracted_data: dict,
    extra: dict | None = None,
    ctx: Optional[TenantContext] = None,
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
    collection = resolve_docs_collection(ctx)
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
    guardar_si_no_existe(transaction, collection, doc_hash, record)


def _duplicate_result(doc_hash: str) -> ProcessingResult:
    return ProcessingResult(
        status="duplicate",
        doc_hash=doc_hash,
        document_type=None,
        normalized_data=None,
        extracted_data=None,
        contact_refs=None,
    )


def process_document(
    file_bytes: bytes,
    mime_type: str,
    filename: str,
    file_size: int,
    extra: dict | None = None,
    ctx: Optional[TenantContext] = None,
) -> ProcessingResult:
    """Orchestrates the full document processing pipeline.

    Steps:
    1. Validate *mime_type* against :data:`ALLOWED_MIME_TYPES`.
    2. Compute SHA-256 hash.
    3. Check for duplicates in Firestore (cheap — no Gemini call).
    4. Extract and normalise via Gemini.
    5. Persist to Firestore (transactional).

    Args:
        file_bytes: Raw bytes of the document.
        mime_type:  MIME type of the document.
        filename:   Original file name (stored in Firestore).
        file_size:  File size in bytes (stored in Firestore).
        extra:      Optional dict merged into the Firestore record
                    (e.g. Gmail metadata: ``source``, ``gmail_message_id``).

    Returns:
        :class:`ProcessingResult` with ``status="processed"`` or ``status="duplicate"``.

    Raises:
        ValueError: If *mime_type* is not in :data:`ALLOWED_MIME_TYPES`.
        Exception:  Any error raised by Gemini, the normaliser, or Firestore
                    (excluding duplicate race conditions, which return ``status="duplicate"``).
    """
    if mime_type not in ALLOWED_MIME_TYPES:
        raise PipelineError(
            code="INVALID_MIME",
            message=f"Tipo de archivo no soportado: {mime_type}",
        )

    doc_hash = compute_hash(file_bytes)

    if is_document_duplicate(doc_hash, ctx=ctx):
        logger.debug("Duplicado detectado (pre-Gemini): hash=%s file=%s", doc_hash, filename)
        return _duplicate_result(doc_hash)

    document_type_str, normalized_dict, extracted_data = extract_and_normalize(
        file_bytes, mime_type, ctx=ctx,
    )

    # Entity resolution — create/update contacts and get refs
    contact_refs = resolve_and_link(
        db, normalized_dict, document_type_str, doc_hash=doc_hash, ctx=ctx,
    )

    # Merge contact_refs into extra so they are persisted with the document
    save_extra = dict(extra) if extra else {}
    if contact_refs:
        save_extra["contact_refs"] = [ref.model_dump() for ref in contact_refs]

    # Upload original to GCS (best-effort — never blocks the pipeline)
    if ctx:
        gcs_path = _gcs.upload_document(
            file_bytes=file_bytes,
            gestoria_id=ctx.gestoria_id,
            cuenta_id=ctx.cliente_id,
            doc_hash=doc_hash,
            filename=filename,
            mime_type=mime_type,
        )
        if gcs_path:
            save_extra["storage_path"] = gcs_path
            save_extra["mime_type"] = mime_type

    try:
        save_document(
            doc_hash=doc_hash,
            filename=filename,
            file_size=file_size,
            document_type_str=document_type_str,
            normalized_dict=normalized_dict,
            extracted_data=extracted_data,
            extra=save_extra or None,
            ctx=ctx,
        )
    except DocumentDuplicateError:
        # Race condition: otro proceso guardó el mismo hash entre el check y el save.
        logger.debug("Duplicado detectado (race condition): hash=%s file=%s", doc_hash, filename)
        return _duplicate_result(doc_hash)

    return ProcessingResult(
        status="processed",
        doc_hash=doc_hash,
        document_type=document_type_str,
        normalized_data=normalized_dict,
        extracted_data=extracted_data,
        contact_refs=contact_refs,
    )