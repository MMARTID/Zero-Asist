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
    def fake_extract(file_bytes, mime_type):
        return {
            "document_type": "invoice_received",
            "data": {
                "issuer_name": "Empresa SL",
                "issue_date": "2024-01-15",
                "total_amount": 121.0,
            },
        }

    monkeypatch.setattr(document_processor, "extract_from_file", fake_extract)

    doc_type, normalized, extracted = extract_and_normalize(b"fake pdf", "application/pdf")

    assert doc_type == "invoice_received"
    assert normalized["issuer_name"] == "Empresa SL"
    assert normalized["total_amount"] == pytest.approx(121.0)
    # issue_date should be converted from date to datetime by dates_to_firestore
    assert isinstance(normalized["issue_date"], datetime)
    assert extracted["issuer_name"] == "Empresa SL"


def test_extract_and_normalize_unknown_type_uses_generic(monkeypatch):
    def fake_extract(file_bytes, mime_type):
        return {"document_type": "tipo_desconocido", "data": {"custom_field": "valor"}}

    monkeypatch.setattr(document_processor, "extract_from_file", fake_extract)

    doc_type, normalized, extracted = extract_and_normalize(b"x", "application/pdf")

    assert doc_type == "tipo_desconocido"
    assert normalized["custom_field"] == "valor"


def test_extract_and_normalize_propagates_gemini_error(monkeypatch):
    def fake_extract(file_bytes, mime_type):
        raise RuntimeError("Gemini unavailable")

    monkeypatch.setattr(document_processor, "extract_from_file", fake_extract)

    with pytest.raises(RuntimeError, match="Gemini unavailable"):
        extract_and_normalize(b"x", "application/pdf")


def test_extract_and_normalize_bank_statement_dates(monkeypatch):
    """Date fields in bank_statement are converted to datetime for Firestore."""
    def fake_extract(file_bytes, mime_type):
        return {
            "document_type": "bank_statement",
            "data": {
                "bank_name": "Banco Test",
                "period_start": "2024-01-01",
                "period_end": "2024-01-31",
            },
        }

    monkeypatch.setattr(document_processor, "extract_from_file", fake_extract)

    _, normalized, _ = extract_and_normalize(b"x", "application/pdf")

    assert isinstance(normalized["period_start"], datetime)
    assert isinstance(normalized["period_end"], datetime)


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
        monkeypatch.setattr(document_processor, "extract_from_file", MagicMock(side_effect=gemini_raises))
    else:
        monkeypatch.setattr(document_processor, "extract_from_file", MagicMock(return_value={
            "document_type": "invoice_received",
            "data": {"issuer_name": "Empresa SL", "total_amount": 121.0},
        }))

    if save_raises:
        monkeypatch.setattr(document_processor, "guardar_si_no_existe", MagicMock(side_effect=save_raises))
    else:
        monkeypatch.setattr(document_processor, "guardar_si_no_existe", MagicMock())


def test_process_document_invalid_mime_raises_value_error(monkeypatch):
    """MIME no soportado → ValueError antes de tocar Firestore o Gemini."""
    fake_db = MagicMock()
    monkeypatch.setattr(document_processor, "db", fake_db)

    with pytest.raises(ValueError, match="no soportado"):
        process_document(b"data", "application/zip", "file.zip", 4)

    fake_db.collection.assert_not_called()


def test_process_document_returns_duplicate_on_existing_hash(monkeypatch):
    """Documento ya existe → status=duplicate sin llamar a Gemini."""
    extract_mock = MagicMock()
    _patch_pipeline(monkeypatch, is_duplicate=True)
    monkeypatch.setattr(document_processor, "extract_from_file", extract_mock)

    result = process_document(b"pdf bytes", "application/pdf", "factura.pdf", 9)

    assert result.status == "duplicate"
    assert result.doc_hash == hashlib.sha256(b"pdf bytes").hexdigest()
    assert result.document_type is None
    assert result.normalized_data is None
    extract_mock.assert_not_called()


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
    """ValueError de guardar_si_no_existe (race condition) → status=duplicate, no excepción."""
    _patch_pipeline(monkeypatch, is_duplicate=False, save_raises=ValueError("Documento duplicado"))

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