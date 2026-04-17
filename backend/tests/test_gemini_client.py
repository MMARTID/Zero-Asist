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


def test_classify_document_with_cuenta_context(fake_generate):
    """classify_document acepta cuenta_context y devuelve el tipo correctamente."""
    from app.ingestion.context import CuentaContext
    fake_generate('{"document_type": "invoice_sent"}')
    ctx = CuentaContext(nombre="Mi Empresa SA", tax_id="A87654321")
    result = gemini_client.classify_document(b"fake pdf", "application/pdf", cuenta_context=ctx)
    assert result == "invoice_sent"


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
    assert exc_info.value.code == "PARSE_ERROR"


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
    assert exc_info.value.code == "PARSE_ERROR"


# ---------------------------------------------------------------------------
# _build_prompt (cuenta context enrichment)
# ---------------------------------------------------------------------------

def test_build_prompt_no_context():
    """Without CuentaContext, prompt is returned unchanged."""
    base = "Eres un experto."
    assert gemini_client._build_prompt(base, None) == base


def test_build_prompt_with_full_context():
    """CuentaContext with nombre + tax_id appends a context suffix."""
    from app.ingestion.context import CuentaContext
    ctx = CuentaContext(nombre="Mi Empresa SL", tax_id="B12345678")
    result = gemini_client._build_prompt("Prompt base.", ctx)
    assert "Prompt base." in result
    assert "Mi Empresa SL" in result
    assert "B12345678" in result
    assert "DATOS DE LA CUENTA" in result


def test_build_prompt_with_only_nombre():
    from app.ingestion.context import CuentaContext
    ctx = CuentaContext(nombre="Solo Nombre")
    result = gemini_client._build_prompt("Base.", ctx)
    assert "Solo Nombre" in result


def test_build_prompt_with_empty_context():
    """CuentaContext with all None fields returns base prompt unchanged."""
    from app.ingestion.context import CuentaContext
    ctx = CuentaContext()
    assert gemini_client._build_prompt("Base.", ctx) == "Base."


def test_extract_document_with_cuenta_context(fake_generate):
    """extract_document accepts cuenta_context and produces a valid result."""
    from app.ingestion.context import CuentaContext

    fake_generate('{"issuer_name": "Proveedor SL", "total_amount": 100.0}')
    ctx = CuentaContext(nombre="Mi Gestoría", tax_id="A12345678")
    result = gemini_client.extract_document(
        b"fake pdf", "application/pdf", "invoice_received",
        cuenta_context=ctx,
    )
    assert result["issuer_name"] == "Proveedor SL"


def test_extract_document_without_cuenta_context(fake_generate):
    """extract_document works normally without cuenta_context (backward compat)."""
    fake_generate('{"issuer_name": "Test SL", "total_amount": 50.0}')
    result = gemini_client.extract_document(b"fake", "application/pdf", "invoice_received")
    assert result["issuer_name"] == "Test SL"