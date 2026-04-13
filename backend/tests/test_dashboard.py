"""Tests for app.api.dashboard — list clients, documents, stats."""

from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_gestoria
from app.main import app

# Override auth dependency for ALL dashboard tests.
_GESTORIA = "g-test"
app.dependency_overrides[get_current_gestoria] = lambda: _GESTORIA

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_client_doc(id: str, data: dict) -> MagicMock:
    doc = MagicMock()
    doc.id = id
    doc.to_dict.return_value = data
    doc.exists = True
    return doc


# ---------------------------------------------------------------------------
# GET /dashboard/clientes
# ---------------------------------------------------------------------------

def test_list_clients_empty(monkeypatch):
    """No clients → empty list."""
    mock_db = MagicMock()
    mock_db.collection.return_value.get.return_value = []
    monkeypatch.setattr("app.api.dashboard._db", mock_db)

    response = client.get("/dashboard/clientes")
    assert response.status_code == 200
    data = response.json()
    assert data["gestoria_id"] == _GESTORIA
    assert data["clientes"] == []


def test_list_clients_returns_data(monkeypatch):
    """Returns client list with expected fields."""
    docs = [
        _mock_client_doc("c1", {
            "nombre": "Acme",
            "email": "acme@example.com",
            "gmail_email": "acme@gmail.com",
            "gmail_watch_status": "active",
        }),
        _mock_client_doc("c2", {
            "nombre": "Beta",
            "email": "beta@example.com",
            "gmail_email": None,
            "gmail_watch_status": None,
        }),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.get.return_value = docs
    monkeypatch.setattr("app.api.dashboard._db", mock_db)

    response = client.get("/dashboard/clientes")
    assert response.status_code == 200
    clientes = response.json()["clientes"]
    assert len(clientes) == 2
    assert clientes[0]["cliente_id"] == "c1"
    assert clientes[0]["gmail_watch_status"] == "active"
    assert clientes[1]["gmail_email"] is None


# ---------------------------------------------------------------------------
# GET /dashboard/clientes/{cliente_id}
# ---------------------------------------------------------------------------

def test_get_client_not_found(monkeypatch):
    """Non-existent client → 404."""
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.dashboard._db", mock_db)

    response = client.get("/dashboard/clientes/c-missing")
    assert response.status_code == 404


def test_get_client_found(monkeypatch):
    """Existing client → returns detail with watch state."""
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.id = "c1"
    mock_doc.to_dict.return_value = {
        "nombre": "Acme",
        "email": "acme@example.com",
        "gmail_email": "acme@gmail.com",
        "gmail_watch_status": "active",
        "gmail_watch_state": {"status": "active", "history_id": "123"},
    }
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.dashboard._db", mock_db)

    response = client.get("/dashboard/clientes/c1")
    assert response.status_code == 200
    data = response.json()
    assert data["cliente_id"] == "c1"
    assert data["gmail_watch_state"]["history_id"] == "123"


# ---------------------------------------------------------------------------
# GET /dashboard/clientes/{cliente_id}/documentos
# ---------------------------------------------------------------------------

def test_list_documents_empty(monkeypatch):
    """No documents → empty list."""
    mock_db = MagicMock()
    mock_db.collection.return_value.order_by.return_value.limit.return_value.get.return_value = []
    monkeypatch.setattr("app.api.dashboard._db", mock_db)

    response = client.get("/dashboard/clientes/c1/documentos")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["documentos"] == []


def test_list_documents_returns_data(monkeypatch):
    """Returns document list with expected fields."""
    docs = [
        _mock_client_doc("hash1", {
            "document_type": "invoice_received",
            "file_name": "factura.pdf",
            "created_at": "2026-04-01T00:00:00Z",
            "normalized_data": {"total": 100},
        }),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.order_by.return_value.limit.return_value.get.return_value = docs
    monkeypatch.setattr("app.api.dashboard._db", mock_db)

    response = client.get("/dashboard/clientes/c1/documentos")
    assert response.status_code == 200
    documentos = response.json()["documentos"]
    assert len(documentos) == 1
    assert documentos[0]["doc_hash"] == "hash1"
    assert documentos[0]["document_type"] == "invoice_received"


def test_list_documents_respects_limit(monkeypatch):
    """Custom limit parameter is forwarded."""
    mock_db = MagicMock()
    mock_db.collection.return_value.order_by.return_value.limit.return_value.get.return_value = []
    monkeypatch.setattr("app.api.dashboard._db", mock_db)

    response = client.get("/dashboard/clientes/c1/documentos?limit=10")
    assert response.status_code == 200
    # Verify limit was passed down
    mock_db.collection.return_value.order_by.return_value.limit.assert_called_with(10)


# ---------------------------------------------------------------------------
# GET /dashboard/stats
# ---------------------------------------------------------------------------

def test_stats_empty_gestoria(monkeypatch):
    """No clients → all zeros."""
    mock_db = MagicMock()
    mock_db.collection.return_value.get.return_value = []
    monkeypatch.setattr("app.api.dashboard._db", mock_db)

    response = client.get("/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_clients"] == 0
    assert data["connected_gmail"] == 0
    assert data["active_watches"] == 0
    assert data["total_documents"] == 0


def test_stats_with_clients(monkeypatch):
    """Counts clients, watches, and documents."""
    client_docs = [
        _mock_client_doc("c1", {
            "gmail_email": "c1@gmail.com",
            "gmail_watch_status": "active",
        }),
        _mock_client_doc("c2", {
            "gmail_email": None,
            "gmail_watch_status": None,
        }),
    ]

    # First .get() returns clients, subsequent .get() calls return docs per client
    mock_db = MagicMock()
    # For gestorias/g-test/clientes collection
    mock_db.collection.return_value.get.side_effect = [
        client_docs,                    # list clients
        [MagicMock(), MagicMock()],     # c1 has 2 docs
        [MagicMock()],                  # c2 has 1 doc
    ]
    monkeypatch.setattr("app.api.dashboard._db", mock_db)

    response = client.get("/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_clients"] == 2
    assert data["connected_gmail"] == 1
    assert data["active_watches"] == 1
    assert data["total_documents"] == 3
