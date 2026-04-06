# tests/test_main.py

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.main import app, verify_scheduler_token

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures compartidos
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_db(monkeypatch):
    """Firestore db con snapshot.exists=False (documento nuevo)."""
    fake_snapshot = MagicMock()
    fake_snapshot.exists = False
    fake_doc_ref = MagicMock()
    fake_doc_ref.get.return_value = fake_snapshot
    fake_collection = MagicMock()
    fake_collection.document.return_value = fake_doc_ref
    db = MagicMock()
    db.collection.return_value = fake_collection
    db.transaction.return_value = MagicMock()
    monkeypatch.setattr("app.main.db", db)
    return db


@pytest.fixture
def fake_extract(monkeypatch):
    """Gemini que devuelve una factura recibida estándar."""
    def _extract(file_bytes, mime_type):
        return {
            "document_type": "invoice_received",
            "data": {
                "issuer_name": "Empresa Test",
                "issue_date": "2024-01-01",
                "base_amount": 100,
                "tax_amount": 21,
                "total_amount": 121,
                "currency": "EUR",
                "tax_breakdown": [],
                "line_items": [],
            },
        }
    monkeypatch.setattr("app.main.extract_from_file", _extract)
    return _extract


@pytest.fixture
def fake_guardar(monkeypatch):
    monkeypatch.setattr("app.main.guardar_si_no_existe", lambda *a, **kw: None)


# ---------------------------------------------------------------------------
# /procesar-documento — happy path
# ---------------------------------------------------------------------------

def test_procesar_documento(monkeypatch, fake_db, fake_extract, fake_guardar):
    response = client.post(
        "/procesar-documento",
        files={"file": ("test.pdf", b"fake content", "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "documento_id" in data
    assert data["document_type"] == "invoice_received"
    assert data["normalized_data"]["issuer_name"] == "Empresa Test"


def test_procesar_documento_mime_detectado_por_extension(monkeypatch, fake_db, fake_extract, fake_guardar):
    """Sin Content-Type, el mime se infiere por extensión."""
    response = client.post(
        "/procesar-documento",
        files={"file": ("factura.png", b"fake content", "")},
    )
    assert response.status_code == 200


def test_procesar_documento_document_type_unknown_to_other(monkeypatch, fake_db, fake_guardar):
    """Si Gemini devuelve un tipo desconocido, se mapea a 'other'."""
    monkeypatch.setattr(
        "app.main.extract_from_file",
        lambda *a, **kw: {"document_type": "tipo_inventado", "data": {}},
    )
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


def test_procesar_documento_mime_no_soportado():
    response = client.post(
        "/procesar-documento",
        files={"file": ("doc.exe", b"fake", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_procesar_documento_extension_desconocida():
    """Sin Content-Type y extensión no soportada → 400."""
    response = client.post(
        "/procesar-documento",
        files={"file": ("archivo.xyz", b"fake", "")},
    )
    assert response.status_code == 400
    assert "Extensión no soportada" in response.json()["detail"]


def test_procesar_documento_duplicado_precheck(monkeypatch):
    """El documento ya existe en Firestore (pre-check) → 409."""
    fake_snapshot = MagicMock()
    fake_snapshot.exists = True
    fake_doc_ref = MagicMock()
    fake_doc_ref.get.return_value = fake_snapshot
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value = fake_doc_ref
    monkeypatch.setattr("app.main.db", fake_db)

    response = client.post(
        "/procesar-documento",
        files={"file": ("dup.pdf", b"fake content", "application/pdf")},
    )
    assert response.status_code == 409
    assert "duplicado" in response.json()["detail"].lower()


def test_procesar_documento_duplicado_transaccion(monkeypatch, fake_db, fake_extract):
    """guardar_si_no_existe lanza ValueError (race condition) → 409."""
    def _raise(*a, **kw):
        raise ValueError("Documento duplicado")

    monkeypatch.setattr("app.main.guardar_si_no_existe", _raise)
    response = client.post(
        "/procesar-documento",
        files={"file": ("dup2.pdf", b"fake content", "application/pdf")},
    )
    assert response.status_code == 409


def test_procesar_documento_gemini_error(monkeypatch, fake_db):
    """Si Gemini falla → 500."""
    monkeypatch.setattr(
        "app.main.extract_from_file",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("Gemini down")),
    )
    response = client.post(
        "/procesar-documento",
        files={"file": ("err.pdf", b"fake", "application/pdf")},
    )
    assert response.status_code == 500
    assert "Error en extracción" in response.json()["detail"]


# ---------------------------------------------------------------------------
# /poll-gmail — autenticación
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_poll(monkeypatch):
    """Stub de poll_gmail que devuelve un resumen vacío."""
    monkeypatch.setattr(
        "app.main.poll_gmail",
        lambda: {"procesados": [], "duplicados": [], "errores": [], "descartados": []},
    )


def test_poll_gmail_sin_auth_401():
    """Sin cabecera de autenticación → 401."""
    response = client.post("/poll-gmail")
    assert response.status_code == 401


def test_poll_gmail_x_scheduler_token_incorrecto_401(monkeypatch):
    """X-Scheduler-Token presente pero incorrecto → 401."""
    monkeypatch.setattr("app.main._DEV_TOKEN", "token-correcto")
    response = client.post("/poll-gmail", headers={"X-Scheduler-Token": "token-malo"})
    assert response.status_code == 401


def test_poll_gmail_x_scheduler_token_sin_configurar_401(monkeypatch):
    """X-Scheduler-Token enviado pero SCHEDULER_DEV_TOKEN no configurado → 401."""
    monkeypatch.setattr("app.main._DEV_TOKEN", None)
    response = client.post("/poll-gmail", headers={"X-Scheduler-Token": "cualquier-cosa"})
    assert response.status_code == 401


def test_poll_gmail_x_scheduler_token_correcto_200(monkeypatch, mock_poll):
    """X-Scheduler-Token correcto → 200."""
    monkeypatch.setattr("app.main._DEV_TOKEN", "mi-token-dev")
    response = client.post("/poll-gmail", headers={"X-Scheduler-Token": "mi-token-dev"})
    assert response.status_code == 200
    assert "procesados" in response.json()


def test_poll_gmail_oidc_sin_audience_401(monkeypatch):
    """Authorization: Bearer enviado pero SCHEDULER_AUDIENCE no configurado → 401."""
    monkeypatch.setattr("app.main._OIDC_AUDIENCE", None)
    response = client.post("/poll-gmail", headers={"Authorization": "Bearer fake.token"})
    assert response.status_code == 401


def test_poll_gmail_oidc_token_invalido_401(monkeypatch):
    """Authorization: Bearer con token inválido → 401."""
    monkeypatch.setattr("app.main._OIDC_AUDIENCE", "https://example.run.app")
    monkeypatch.setattr(
        "app.main.id_token.verify_oauth2_token",
        lambda *a, **kw: (_ for _ in ()).throw(ValueError("bad token")),
    )
    response = client.post("/poll-gmail", headers={"Authorization": "Bearer invalid.jwt"})
    assert response.status_code == 401


def test_poll_gmail_oidc_token_valido_200(monkeypatch, mock_poll):
    """Authorization: Bearer con token OIDC válido → 200."""
    monkeypatch.setattr("app.main._OIDC_AUDIENCE", "https://example.run.app")
    monkeypatch.setattr(
        "app.main.id_token.verify_oauth2_token",
        lambda *a, **kw: {"sub": "sa@project.iam.gserviceaccount.com"},
    )
    response = client.post("/poll-gmail", headers={"Authorization": "Bearer valid.jwt"})
    assert response.status_code == 200
