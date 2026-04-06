# tests/test_gemini_client.py

import json
import pytest
from app.services import gemini_client


# ---------------------------------------------------------------------------
# Fixture base
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_generate(monkeypatch):
    """Devuelve una función factory para mockear generate_content con texto arbitrario."""
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
# Happy paths
# ---------------------------------------------------------------------------

def test_extract_from_file_pdf(fake_generate):
    fake_generate('{"document_type": "invoice_received", "data": {"issuer_name": "Test SL"}}')
    result = gemini_client.extract_from_file(b"fake pdf bytes", "application/pdf")
    assert result["document_type"] == "invoice_received"
    assert result["data"]["issuer_name"] == "Test SL"


def test_extract_from_file_jpeg(fake_generate):
    fake_generate('{"document_type": "receipt", "data": {"total_amount": 50.0}}')
    result = gemini_client.extract_from_file(b"fake jpeg", "image/jpeg")
    assert result["document_type"] == "receipt"


def test_extract_from_file_xml(fake_generate):
    fake_generate('{"document_type": "invoice_received", "data": {"invoice_number": "F-001"}}')
    xml_bytes = b"<?xml version='1.0'?><factura/>"
    result = gemini_client.extract_from_file(xml_bytes, "application/xml")
    assert result["document_type"] == "invoice_received"
    assert result["data"]["invoice_number"] == "F-001"


def test_extract_from_file_text_xml(fake_generate):
    fake_generate('{"document_type": "other", "data": {}}')
    result = gemini_client.extract_from_file(b"<root/>", "text/xml")
    assert result["document_type"] == "other"


def test_extract_from_file_xml_detectado_por_contenido(fake_generate):
    """Aunque el mime_type sea genérico, si empieza por <?xml se trata como XML."""
    fake_generate('{"document_type": "other", "data": {}}')
    result = gemini_client.extract_from_file(b"<?xml version='1.0'?>", "application/octet-stream")
    # No debe lanzar ValueError; el contenido XML se procesa como texto
    assert "document_type" in result


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------

def test_extract_from_file_mime_no_soportado():
    with pytest.raises(ValueError, match="Tipo MIME no soportado"):
        gemini_client.extract_from_file(b"data", "application/zip")


def test_extract_from_file_respuesta_json_invalida(monkeypatch):
    """Si Gemini devuelve JSON malformado → JSONDecodeError propagado."""
    class BadResponse:
        text = "esto no es json {{{"

    monkeypatch.setattr(
        gemini_client.client.models,
        "generate_content",
        lambda *a, **kw: BadResponse(),
    )
    with pytest.raises(json.JSONDecodeError):
        gemini_client.extract_from_file(b"fake", "application/pdf")


# ---------------------------------------------------------------------------
# Alias extract_from_pdf
# ---------------------------------------------------------------------------

def test_extract_from_pdf_alias(fake_generate):
    fake_generate('{"document_type": "bank_statement", "data": {}}')
    result = gemini_client.extract_from_pdf(b"pdf bytes")
    assert result["document_type"] == "bank_statement"