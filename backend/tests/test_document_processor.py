# tests/test_document_processor.py
"""Tests for the shared document-processing pipeline in app.services.document_processor."""

import hashlib
import pytest
from datetime import date, datetime
from unittest.mock import MagicMock

from app.services import document_processor
from app.services.document_processor import (
    compute_hash,
    extract_and_normalize,
    is_document_duplicate,
    process_document,
    ProcessingResult,
    save_document,
    DocumentDuplicateError,
)



# ---------------------------------------------------------------------------
# compute_hash
# ---------------------------------------------------------------------------

def test_compute_hash_returns_sha256():
    data = b"hello world"
    expected = hashlib.sha256(data).hexdigest()
    assert compute_hash(data) == expected


def test_compute_hash_empty_bytes():
    assert compute_hash(b"") == hashlib.sha256(b"").hexdigest()


def test_compute_hash_deterministic():
    data = b"test document content"
    assert compute_hash(data) == compute_hash(data)


# ---------------------------------------------------------------------------
# is_document_duplicate
# ---------------------------------------------------------------------------

def test_is_document_duplicate_returns_false_when_not_found(monkeypatch):
    fake_snap = MagicMock()
    fake_snap.exists = False
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value.get.return_value = fake_snap
    monkeypatch.setattr(document_processor, "db", fake_db)

    assert is_document_duplicate("abc123") is False


def test_is_document_duplicate_returns_true_when_found(monkeypatch):
    fake_snap = MagicMock()
    fake_snap.exists = True
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value.get.return_value = fake_snap
    monkeypatch.setattr(document_processor, "db", fake_db)

    assert is_document_duplicate("abc123") is True


# ---------------------------------------------------------------------------
# extract_and_normalize
# ---------------------------------------------------------------------------

def test_extract_and_normalize_happy_path(monkeypatch):
    """extract_and_normalize returns the processed triple."""
    monkeypatch.setattr(document_processor, "classify_document",
                        lambda fb, mt, **kw: "invoice_received")
    monkeypatch.setattr(document_processor, "extract_document",
                        lambda fb, mt, dt, **kw: {
                            "issuer_name": "Empresa SL",
                            "issue_date": "2024-01-15",
                            "total_amount": 121.0,
                        })

    doc_type, normalized, extracted = extract_and_normalize(b"fake pdf", "application/pdf")

    assert doc_type == "invoice_received"
    assert normalized["issuer_name"] == "Empresa SL"
    assert normalized["total_amount"] == pytest.approx(121.0)
    # issue_date should be converted from date to datetime by dates_to_firestore
    assert isinstance(normalized["issue_date"], datetime)
    assert extracted["issuer_name"] == "Empresa SL"


def test_extract_and_normalize_unknown_type_uses_generic(monkeypatch):
    monkeypatch.setattr(document_processor, "classify_document",
                        lambda fb, mt, **kw: "tipo_desconocido")

    doc_type, normalized, extracted = extract_and_normalize(b"x", "application/pdf")

    # Unknown types are coerced to 'other' to always be a valid DocumentType.
    assert doc_type == "other"
    # No extraction schema for 'other' → empty extracted data
    assert extracted == {}


def test_extract_and_normalize_propagates_gemini_error(monkeypatch):
    monkeypatch.setattr(document_processor, "classify_document",
                        MagicMock(side_effect=RuntimeError("Gemini unavailable")))

    with pytest.raises(RuntimeError, match="Gemini unavailable"):
        extract_and_normalize(b"x", "application/pdf")


def test_extract_and_normalize_bank_document_dates(monkeypatch):
    """Date fields in bank_document are converted to datetime for Firestore."""
    monkeypatch.setattr(document_processor, "classify_document",
                        lambda fb, mt, **kw: "bank_document")
    monkeypatch.setattr(document_processor, "extract_document",
                        lambda fb, mt, dt, **kw: {
                            "bank_name": "Banco Test",
                            "document_date": "2024-01-15",
                        })

    _, normalized, _ = extract_and_normalize(b"x", "application/pdf")

    assert isinstance(normalized["document_date"], datetime)


# ---------------------------------------------------------------------------
# save_document
# ---------------------------------------------------------------------------

def test_save_document_calls_guardar_si_no_existe(monkeypatch):
    """save_document calls guardar_si_no_existe with the correct record."""
    calls = []

    def fake_guardar(transaction, coleccion, doc_hash, data):
        calls.append((coleccion, doc_hash, data))

    fake_db = MagicMock()
    fake_db.transaction.return_value = MagicMock()
    monkeypatch.setattr(document_processor, "db", fake_db)
    monkeypatch.setattr(document_processor, "guardar_si_no_existe", fake_guardar)

    save_document(
        doc_hash="deadbeef",
        filename="factura.pdf",
        file_size=1024,
        document_type_str="invoice_received",
        normalized_dict={"issuer_name": "SL"},
        extracted_data={"raw": True},
    )

    assert len(calls) == 1
    coleccion, doc_hash, record = calls[0]
    assert coleccion == "documentos"
    assert doc_hash == "deadbeef"
    assert record["file_name"] == "factura.pdf"
    assert record["file_size"] == 1024
    assert record["document_type"] == "invoice_received"
    assert record["normalized_data"] == {"issuer_name": "SL"}
    assert record["extracted_data"] == {"raw": True}
    assert "created_at" in record


def test_save_document_merges_extra_fields(monkeypatch):
    """Extra metadata (e.g. Gmail fields) is merged into the Firestore record."""
    calls = []

    def fake_guardar(transaction, coleccion, doc_hash, data):
        calls.append(data)

    fake_db = MagicMock()
    fake_db.transaction.return_value = MagicMock()
    monkeypatch.setattr(document_processor, "db", fake_db)
    monkeypatch.setattr(document_processor, "guardar_si_no_existe", fake_guardar)

    save_document(
        doc_hash="abc",
        filename="f.pdf",
        file_size=100,
        document_type_str="invoice_received",
        normalized_dict={},
        extracted_data={},
        extra={"source": "gmail", "gmail_message_id": "msg1"},
    )

    record = calls[0]
    assert record["source"] == "gmail"
    assert record["gmail_message_id"] == "msg1"


def test_save_document_propagates_duplicate_error(monkeypatch):
    """ValueError from guardar_si_no_existe propagates (race condition)."""
    def fake_guardar(transaction, coleccion, doc_hash, data):
        raise ValueError("Documento duplicado")

    fake_db = MagicMock()
    fake_db.transaction.return_value = MagicMock()
    monkeypatch.setattr(document_processor, "db", fake_db)
    monkeypatch.setattr(document_processor, "guardar_si_no_existe", fake_guardar)

    with pytest.raises(ValueError, match="Documento duplicado"):
        save_document(
            doc_hash="dup",
            filename="dup.pdf",
            file_size=0,
            document_type_str="other",
            normalized_dict={},
            extracted_data={},
        )
# ---------------------------------------------------------------------------
# process_document
# ---------------------------------------------------------------------------


def _patch_pipeline(monkeypatch, *, is_duplicate=False, gemini_raises=None, save_raises=None):
    """Helper que parchea las 3 dependencias de process_document."""
    fake_snap = MagicMock()
    fake_snap.exists = is_duplicate
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value.get.return_value = fake_snap
    fake_db.transaction.return_value = MagicMock()
    monkeypatch.setattr(document_processor, "db", fake_db)

    if gemini_raises:
        monkeypatch.setattr(document_processor, "classify_document", MagicMock(side_effect=gemini_raises))
    else:
        monkeypatch.setattr(document_processor, "classify_document",
                            MagicMock(return_value="invoice_received"))
        monkeypatch.setattr(document_processor, "extract_document",
                            MagicMock(return_value={"issuer_name": "Empresa SL", "total_amount": 121.0}))

    if save_raises:
        monkeypatch.setattr(document_processor, "guardar_si_no_existe", MagicMock(side_effect=save_raises))
    else:
        monkeypatch.setattr(document_processor, "guardar_si_no_existe", MagicMock())


def test_process_document_invalid_mime_raises_value_error(monkeypatch):
    """MIME no soportado → PipelineError(INVALID_MIME) antes de tocar Firestore o Gemini."""
    from app.services.errors import PipelineError
    fake_db = MagicMock()
    monkeypatch.setattr(document_processor, "db", fake_db)

    with pytest.raises(PipelineError) as exc_info:
        process_document(b"data", "application/zip", "file.zip", 4)

    assert exc_info.value.code == "INVALID_MIME"
    assert "no soportado" in exc_info.value.message
    fake_db.collection.assert_not_called()


def test_process_document_returns_duplicate_on_existing_hash(monkeypatch):
    """Documento ya existe → status=duplicate sin llamar a Gemini."""
    classify_mock = MagicMock()
    _patch_pipeline(monkeypatch, is_duplicate=True)
    monkeypatch.setattr(document_processor, "classify_document", classify_mock)

    result = process_document(b"pdf bytes", "application/pdf", "factura.pdf", 9)

    assert result.status == "duplicate"
    assert result.doc_hash == hashlib.sha256(b"pdf bytes").hexdigest()
    assert result.document_type is None
    assert result.normalized_data is None
    classify_mock.assert_not_called()


def test_process_document_happy_path(monkeypatch):
    """Flujo completo → status=processed con datos correctos."""
    _patch_pipeline(monkeypatch, is_duplicate=False)

    result = process_document(b"pdf bytes", "application/pdf", "factura.pdf", 9)

    assert result.status == "processed"
    assert result.doc_hash == hashlib.sha256(b"pdf bytes").hexdigest()
    assert result.document_type == "invoice_received"
    assert result.normalized_data["issuer_name"] == "Empresa SL"
    assert result.extracted_data["issuer_name"] == "Empresa SL"


def test_process_document_race_condition_returns_duplicate(monkeypatch):
    """DocumentDuplicateError de guardar_si_no_existe (race condition) → status=duplicate."""
    from app.services.firestore_client import DocumentDuplicateError
    _patch_pipeline(monkeypatch, is_duplicate=False, save_raises=DocumentDuplicateError("Race condition duplicado"))

    result = process_document(b"pdf bytes", "application/pdf", "factura.pdf", 9)

    assert result.status == "duplicate"
    assert result.doc_hash == hashlib.sha256(b"pdf bytes").hexdigest()
    assert result.document_type is None


def test_process_document_gemini_error_propagates(monkeypatch):
    """Error de Gemini se propaga como excepción — el caller decide qué hacer."""
    _patch_pipeline(monkeypatch, is_duplicate=False, gemini_raises=RuntimeError("Gemini unavailable"))

    with pytest.raises(RuntimeError, match="Gemini unavailable"):
        process_document(b"pdf bytes", "application/pdf", "factura.pdf", 9)


def test_process_document_extra_passed_to_firestore(monkeypatch):
    """El dict extra (metadata Gmail) llega al registro de Firestore."""
    saved_records = []

    def fake_guardar(transaction, coleccion, doc_hash, data):
        saved_records.append(data)

    _patch_pipeline(monkeypatch, is_duplicate=False)
    monkeypatch.setattr(document_processor, "guardar_si_no_existe", fake_guardar)

    process_document(
        b"pdf bytes", "application/pdf", "factura.pdf", 9,
        extra={"source": "gmail", "gmail_message_id": "msg42"},
    )

    assert len(saved_records) == 1
    assert saved_records[0]["source"] == "gmail"
    assert saved_records[0]["gmail_message_id"] == "msg42"


def test_process_document_all_mime_types_accepted(monkeypatch):
    """Todos los MIME de ALLOWED_MIME_TYPES son aceptados sin ValueError."""
    from app.services.document_processor import ALLOWED_MIME_TYPES
    _patch_pipeline(monkeypatch, is_duplicate=False)

    for mime in ALLOWED_MIME_TYPES:
        result = process_document(b"data", mime, "file", 4)
        assert result.status == "processed", f"Falló para mime={mime}"


# ---------------------------------------------------------------------------
# _load_cuenta_context
# ---------------------------------------------------------------------------

def test_load_cuenta_context_none_ctx():
    """None ctx returns None immediately without Firestore call."""
    from app.services.document_processor import _load_cuenta_context
    assert _load_cuenta_context(None) is None


def test_load_cuenta_context_returns_cuenta(monkeypatch):
    """Loads nombre, tax_id, tax_country, tax_type from Firestore cuenta doc."""
    from app.services.document_processor import _load_cuenta_context
    from app.services.tenant import TenantContext

    fake_doc = MagicMock()
    fake_doc.exists = True
    fake_doc.to_dict.return_value = {
        "nombre": "Empresa Test SL",
        "tax_id": "B12345678",
        "tax_country": "ES",
        "tax_type": "cif_empresa",
    }
    fake_db = MagicMock()
    fake_db.document.return_value.get.return_value = fake_doc
    monkeypatch.setattr(document_processor, "db", fake_db)

    ctx = TenantContext(gestoria_id="g1", cliente_id="c1")
    result = _load_cuenta_context(ctx)

    assert result is not None
    assert result.nombre == "Empresa Test SL"
    assert result.tax_id == "B12345678"
    assert result.tax_country == "ES"
    assert result.tax_type == "cif_empresa"


def test_load_cuenta_context_missing_doc(monkeypatch):
    """Missing cuenta doc returns None."""
    from app.services.document_processor import _load_cuenta_context
    from app.services.tenant import TenantContext

    fake_doc = MagicMock()
    fake_doc.exists = False
    fake_db = MagicMock()
    fake_db.document.return_value.get.return_value = fake_doc
    monkeypatch.setattr(document_processor, "db", fake_db)

    ctx = TenantContext(gestoria_id="g1", cliente_id="c1")
    assert _load_cuenta_context(ctx) is None


# ---------------------------------------------------------------------------
# extract_and_normalize with ctx
# ---------------------------------------------------------------------------

def test_extract_and_normalize_with_ctx_passes_cuenta_context(monkeypatch):
    """When ctx is provided, extract_document receives cuenta_context."""
    from app.services.tenant import TenantContext

    # Mock Firestore for _load_cuenta_context
    fake_doc = MagicMock()
    fake_doc.exists = True
    fake_doc.to_dict.return_value = {
        "nombre": "Test SL",
        "tax_id": "B12345678",
        "tax_country": "ES",
        "tax_type": "cif_empresa",
    }
    fake_db = MagicMock()
    fake_db.document.return_value.get.return_value = fake_doc
    monkeypatch.setattr(document_processor, "db", fake_db)

    monkeypatch.setattr(document_processor, "classify_document",
                        lambda fb, mt, **kw: "invoice_received")

    captured_kwargs = {}
    def fake_extract(fb, mt, dt, **kwargs):
        captured_kwargs.update(kwargs)
        return {"issuer_name": "Empresa SL", "total_amount": 121.0}

    monkeypatch.setattr(document_processor, "extract_document", fake_extract)

    ctx = TenantContext(gestoria_id="g1", cliente_id="c1")
    doc_type, normalized, extracted = extract_and_normalize(b"fake", "application/pdf", ctx=ctx)

    assert doc_type == "invoice_received"
    assert "cuenta_context" in captured_kwargs
    assert captured_kwargs["cuenta_context"].nombre == "Test SL"
    assert captured_kwargs["cuenta_context"].tax_id == "B12345678"