# tests/test_gemini_client.py

import json
import pytest
from app.services import gemini_client

# Ensure registry is populated (normalizer registers all types on import)
import app.ingestion.normalizer  # noqa: F401


# ---------------------------------------------------------------------------
# Fixture base
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_generate(monkeypatch):
    """Returns a factory to mock generate_content with arbitrary text."""
    def _setup(text: str):
        class FakeResponse:
            pass
        FakeResponse.text = text

        monkeypatch.setattr(
            gemini_client.client.models,
            "generate_content",
            lambda *a, **kw: FakeResponse(),
        )
    return _setup


# ---------------------------------------------------------------------------
# classify_document
# ---------------------------------------------------------------------------

def test_classify_document_invoice(fake_generate):
    fake_generate('{"document_type": "invoice_received"}')
    result = gemini_client.classify_document(b"fake pdf bytes", "application/pdf")
    assert result == "invoice_received"


def test_classify_document_bank(fake_generate):
    fake_generate('{"document_type": "bank_document"}')
    result = gemini_client.classify_document(b"fake", "application/pdf")
    assert result == "bank_document"


def test_classify_document_xml(fake_generate):
    fake_generate('{"document_type": "invoice_received"}')
    result = gemini_client.classify_document(b"<?xml version='1.0'?><factura/>", "application/xml")
    assert result == "invoice_received"


def test_classify_document_xml_by_content(fake_generate):
    """XML detected by content even with generic mime type."""
    fake_generate('{"document_type": "other"}')
    result = gemini_client.classify_document(b"<?xml version='1.0'?>", "application/octet-stream")
    assert result == "other"


# ---------------------------------------------------------------------------
# extract_document
# ---------------------------------------------------------------------------

def test_extract_document_invoice_received(fake_generate):
    fake_generate('{"issuer_name": "Test SL", "total_amount": 121.0}')
    result = gemini_client.extract_document(b"fake pdf", "application/pdf", "invoice_received")
    assert result["issuer_name"] == "Test SL"
    assert result["total_amount"] == 121.0


def test_extract_document_bank_document(fake_generate):
    fake_generate('{"bank_name": "BBVA", "iban": "ES00"}')
    result = gemini_client.extract_document(b"fake", "application/pdf", "bank_document")
    assert result["bank_name"] == "BBVA"


def test_extract_document_expense_ticket(fake_generate):
    fake_generate('{"issuer_name": "Bar Central", "total_amount": 12.50}')
    result = gemini_client.extract_document(b"fake", "image/jpeg", "expense_ticket")
    assert result["issuer_name"] == "Bar Central"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def test_classify_document_mime_no_soportado():
    with pytest.raises(ValueError, match="Tipo MIME no soportado"):
        gemini_client.classify_document(b"data", "application/zip")


def test_extract_document_unknown_type():
    with pytest.raises(ValueError, match="No extraction schema"):
        gemini_client.extract_document(b"data", "application/pdf", "other")


def test_classify_document_json_invalido(monkeypatch):
    """If Gemini returns malformed JSON → PipelineError."""
    from app.services.errors import PipelineError

    class BadResponse:
        text = "esto no es json {{{"

    monkeypatch.setattr(
        gemini_client.client.models,
        "generate_content",
        lambda *a, **kw: BadResponse(),
    )
    with pytest.raises(PipelineError) as exc_info:
        gemini_client.classify_document(b"fake", "application/pdf")
    assert exc_info.value.code == "UNKNOWN"


def test_extract_document_json_invalido(monkeypatch):
    """If Gemini returns malformed JSON during extraction → PipelineError."""
    from app.services.errors import PipelineError

    class BadResponse:
        text = "not json"

    monkeypatch.setattr(
        gemini_client.client.models,
        "generate_content",
        lambda *a, **kw: BadResponse(),
    )
    with pytest.raises(PipelineError) as exc_info:
        gemini_client.extract_document(b"fake", "application/pdf", "invoice_received")
    assert exc_info.value.code == "UNKNOWN"