# tests/test_main.py

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.services.document_processor import ProcessingResult
from app.services.errors import PipelineError

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures compartidos
# ---------------------------------------------------------------------------

def _processed_result(document_type="invoice_received", doc_hash="abc123"):
    return ProcessingResult(
        status="processed",
        doc_hash=doc_hash,
        document_type=document_type,
        normalized_data={"issuer_name": "Empresa Test", "base_amount": 100.0},
        extracted_data={"issuer_name": "Empresa Test"},
    )


def _duplicate_result(doc_hash="abc123"):
    return ProcessingResult(
        status="duplicate",
        doc_hash=doc_hash,
        document_type=None,
        normalized_data=None,
        extracted_data=None,
    )


@pytest.fixture
def mock_process(monkeypatch):
    """Stub process_document to return a successful ProcessingResult by default."""
    mock = MagicMock(return_value=_processed_result())
    monkeypatch.setattr("app.api.documents.process_document", mock)
    return mock


# ---------------------------------------------------------------------------
# /procesar-documento — happy path
# ---------------------------------------------------------------------------

def test_procesar_documento(mock_process):
    response = client.post(
        "/procesar-documento",
        files={"file": ("test.pdf", b"fake content", "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "documento_id" in data
    assert data["document_type"] == "invoice_received"
    assert data["normalized_data"]["issuer_name"] == "Empresa Test"


def test_procesar_documento_mime_detectado_por_extension(mock_process):
    """Sin Content-Type, el mime se infiere por extensión."""
    response = client.post(
        "/procesar-documento",
        files={"file": ("factura.png", b"fake content", "")},
    )
    assert response.status_code == 200


def test_procesar_documento_document_type_unknown_to_other(mock_process):
    """process_document ya normalizó a 'other'; endpoint lo devuelve tal cual."""
    mock_process.return_value = _processed_result(document_type="other")
    response = client.post(
        "/procesar-documento",
        files={"file": ("doc.pdf", b"x", "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["document_type"] == "other"


# ---------------------------------------------------------------------------
# /procesar-documento — errores de validación
# ---------------------------------------------------------------------------

def test_procesar_documento_archivo_vacio():
    response = client.post(
        "/procesar-documento",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400
    assert "vacío" in response.json()["detail"]


def test_procesar_documento_mime_no_soportado(monkeypatch):
    """MIME no soportado → process_document lanza PipelineError(INVALID_MIME) → 400."""
    monkeypatch.setattr(
        "app.api.documents.process_document",
        MagicMock(side_effect=PipelineError(
            code="INVALID_MIME",
            message="Tipo de archivo no soportado: application/octet-stream",
        )),
    )
    response = client.post(
        "/procesar-documento",
        files={"file": ("doc.exe", b"fake", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "no soportado" in response.json()["detail"]


def test_procesar_documento_extension_desconocida():
    """Sin Content-Type y extensión no soportada → 400 (bloqueado antes de process_document)."""
    response = client.post(
        "/procesar-documento",
        files={"file": ("archivo.xyz", b"fake", "")},
    )
    assert response.status_code == 400
    assert "Extensión no soportada" in response.json()["detail"]


def test_procesar_documento_duplicado(monkeypatch):
    """process_document devuelve status='duplicate' → 409."""
    monkeypatch.setattr(
        "app.api.documents.process_document",
        MagicMock(return_value=_duplicate_result()),
    )
    response = client.post(
        "/procesar-documento",
        files={"file": ("dup.pdf", b"fake content", "application/pdf")},
    )
    assert response.status_code == 409
    assert "duplicado" in response.json()["detail"].lower()


def test_procesar_documento_servicio_externo_no_disponible(monkeypatch):
    """Gemini devuelve 503 → PipelineError(UNAVAILABLE) → 503."""
    monkeypatch.setattr(
        "app.api.documents.process_document",
        MagicMock(side_effect=PipelineError(
            code="UNAVAILABLE",
            message="El servicio externo no está disponible temporalmente (503).",
        )),
    )
    response = client.post(
        "/procesar-documento",
        files={"file": ("factura.pdf", b"fake", "application/pdf")},
    )
    assert response.status_code == 503
    assert "disponible" in response.json()["detail"]


def test_procesar_documento_error_inesperado(monkeypatch):
    """Error inesperado no clasificado → PipelineError(UNKNOWN) → 500."""
    monkeypatch.setattr(
        "app.api.documents.process_document",
        MagicMock(side_effect=PipelineError(
            code="UNKNOWN",
            message="Error inesperado durante el procesamiento.",
        )),
    )
    response = client.post(
        "/procesar-documento",
        files={"file": ("err.pdf", b"fake", "application/pdf")},
    )
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# /poll-gmail
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_poll(monkeypatch):
    """Stub de poll_gmail que devuelve un resumen vacío."""
    monkeypatch.setattr(
        "app.api.gmail.poll_gmail",
        lambda: {"procesados": [], "duplicados": [], "errores": [], "descartados": []},
    )


def test_poll_gmail_200(mock_poll):
    """Sin auth scheduler, el endpoint responde 200 directamente."""
    response = client.post("/poll-gmail")
    assert response.status_code == 200
    assert "procesados" in response.json()
