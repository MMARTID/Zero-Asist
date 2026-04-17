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
# GET /dashboard/cuentas
# ---------------------------------------------------------------------------

def test_list_clients_empty(monkeypatch):
    """No clients → empty list."""
    mock_db = MagicMock()
    mock_db.collection.return_value.get.return_value = []
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas")
    assert response.status_code == 200
    data = response.json()
    assert data["gestoria_id"] == _GESTORIA
    assert data["cuentas"] == []


def test_list_clients_returns_data(monkeypatch):
    """Returns client list with expected fields."""
    docs = [
        _mock_client_doc("c1", {
            "nombre": "Acme",
            "phone_number": "+34600111222",
            "gmail_email": "acme@gmail.com",
            "gmail_watch_status": "active",
        }),
        _mock_client_doc("c2", {
            "nombre": "Beta",
            "phone_number": "+34600333444",
            "gmail_email": None,
            "gmail_watch_status": None,
        }),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.get.return_value = docs
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas")
    assert response.status_code == 200
    clientes = response.json()["cuentas"]
    assert len(clientes) == 2
    assert clientes[0]["cuenta_id"] == "c1"
    assert clientes[0]["gmail_watch_status"] == "active"
    assert clientes[1]["gmail_email"] is None


# ---------------------------------------------------------------------------
# GET /dashboard/cuentas/{cuenta_id}
# ---------------------------------------------------------------------------

def test_get_client_not_found(monkeypatch):
    """Non-existent client → 404."""
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c-missing")
    assert response.status_code == 404


def test_get_client_found(monkeypatch):
    """Existing client → returns detail with watch state."""
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.id = "c1"
    mock_doc.to_dict.return_value = {
        "nombre": "Acme",
        "phone_number": "+34600111222",
        "gmail_email": "acme@gmail.com",
        "gmail_watch_status": "active",
        "gmail_watch_state": {"status": "active", "history_id": "123"},
    }
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1")
    assert response.status_code == 200
    data = response.json()
    assert data["cuenta_id"] == "c1"
    assert data["gmail_watch_state"]["history_id"] == "123"


# ---------------------------------------------------------------------------
# GET /dashboard/cuentas/{cuenta_id}/documentos
# ---------------------------------------------------------------------------

def test_list_documents_empty(monkeypatch):
    """No documents → empty list."""
    mock_db = MagicMock()
    mock_db.collection.return_value.order_by.return_value.limit.return_value.get.return_value = []
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/documentos")
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
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/documentos")
    assert response.status_code == 200
    documentos = response.json()["documentos"]
    assert len(documentos) == 1
    assert documentos[0]["doc_hash"] == "hash1"
    assert documentos[0]["document_type"] == "invoice_received"


def test_list_documents_respects_limit(monkeypatch):
    """Custom limit parameter is forwarded."""
    mock_db = MagicMock()
    mock_db.collection.return_value.order_by.return_value.limit.return_value.get.return_value = []
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/documentos?limit=10")
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
    monkeypatch.setattr("app.api.deps._db", mock_db)

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
    # For gestorias/g-test/cuentas collection
    mock_db.collection.return_value.get.side_effect = [
        client_docs,                    # list clients
        [MagicMock(), MagicMock()],     # c1 has 2 docs
        [MagicMock()],                  # c2 has 1 doc
    ]
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_clients"] == 2
    assert data["connected_gmail"] == 1
    assert data["active_watches"] == 1
    assert data["total_documents"] == 3


# ---------------------------------------------------------------------------
# GET /dashboard/cuentas/{cuenta_id}/contactos
# ---------------------------------------------------------------------------

def test_list_contacts_empty(monkeypatch):
    """No contacts → empty list."""
    mock_db = MagicMock()
    mock_db.collection.return_value.get.return_value = []
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/contactos")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["contactos"] == []


def test_list_contacts_returns_data(monkeypatch):
    """Returns contact list with expected fields."""
    docs = [
        _mock_client_doc("ct1", {
            "nombre_fiscal": "Acme S.L.",
            "tax_id": "B12345678",
            "tax_country": "ES",
            "tax_type": "company",
            "roles": ["proveedor"],
            "confidence": 0.9,
            "source": "ai_extracted",
            "total_documentos": 5,
            "ultima_interaccion": "2026-04-01T00:00:00Z",
        }),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.get.return_value = docs
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/contactos")
    assert response.status_code == 200
    contactos = response.json()["contactos"]
    assert len(contactos) == 1
    assert contactos[0]["contacto_id"] == "ct1"
    assert contactos[0]["tax_id"] == "B12345678"
    assert contactos[0]["roles"] == ["proveedor"]


def test_list_contacts_filter_by_role(monkeypatch):
    """Filtering by role calls Firestore where with array_contains."""
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.get.return_value = []
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/contactos?rol=proveedor")
    assert response.status_code == 200
    mock_db.collection.return_value.where.assert_called_once_with(
        "roles", "array_contains", "proveedor"
    )


# ---------------------------------------------------------------------------
# GET /dashboard/cuentas/{cuenta_id}/contactos/{contacto_id}
# ---------------------------------------------------------------------------

def test_get_contact_not_found(monkeypatch):
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/contactos/ct-missing")
    assert response.status_code == 404


def test_get_contact_found(monkeypatch):
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.id = "ct1"
    mock_doc.to_dict.return_value = {
        "nombre_fiscal": "Acme S.L.",
        "tax_id": "B12345678",
        "tax_country": "ES",
        "tax_type": "company",
        "roles": ["proveedor"],
        "confidence": 0.9,
    }
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/contactos/ct1")
    assert response.status_code == 200
    data = response.json()
    assert data["contacto_id"] == "ct1"
    assert data["tax_id"] == "B12345678"


# ---------------------------------------------------------------------------
# PATCH /dashboard/cuentas/{cuenta_id}/contactos/{contacto_id}
# ---------------------------------------------------------------------------

def test_update_contact_not_found(monkeypatch):
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.patch(
        "/dashboard/cuentas/c1/contactos/ct-missing",
        json={"nombre_fiscal": "New Name"},
    )
    assert response.status_code == 404


def test_update_contact_success(monkeypatch):
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.patch(
        "/dashboard/cuentas/c1/contactos/ct1",
        json={"nombre_fiscal": "Corrected Name", "tax_id": "B99999999"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "updated"
    assert "nombre_fiscal" in data["fields_updated"]
    # Verify source and confidence are set to user_verified
    call_args = mock_db.document.return_value.update.call_args[0][0]
    assert call_args["source"] == "user_verified"
    assert call_args["confidence"] == 1.0
    assert "verified_at" in call_args
    assert "updated_at" in call_args


def test_update_contact_ignores_invalid_fields(monkeypatch):
    """Disallowed fields are silently ignored; verify still happens."""
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.patch(
        "/dashboard/cuentas/c1/contactos/ct1",
        json={"hacker_field": "bad", "total_documentos": 999},
    )
    assert response.status_code == 200
    call_args = mock_db.document.return_value.update.call_args[0][0]
    # Invalid fields are NOT in the update
    assert "hacker_field" not in call_args
    assert "total_documentos" not in call_args
    # But verification still happened
    assert call_args["source"] == "user_verified"
    assert call_args["confidence"] == 1.0


def test_update_contact_verify_only(monkeypatch):
    """Empty body {} should verify the contact without changing data fields."""
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.patch(
        "/dashboard/cuentas/c1/contactos/ct1",
        json={},
    )
    assert response.status_code == 200
    call_args = mock_db.document.return_value.update.call_args[0][0]
    assert call_args["source"] == "user_verified"
    assert call_args["confidence"] == 1.0
    assert "verified_at" in call_args


# ---------------------------------------------------------------------------
# GET /dashboard/cuentas/{cuenta_id}/fiscal-summary
# ---------------------------------------------------------------------------

def _mock_fiscal_doc(id: str, doc_type: str, norm_data: dict) -> MagicMock:
    """Create a mock Firestore document for fiscal-summary tests."""
    doc = MagicMock()
    doc.id = id
    doc.to_dict.return_value = {
        "document_type": doc_type,
        "normalized_data": norm_data,
    }
    return doc


def test_fiscal_summary_empty(monkeypatch):
    """No documents → all zeros."""
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.get.return_value = []
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/fiscal-summary?year=2026")
    assert response.status_code == 200
    data = response.json()
    assert data["year"] == 2026
    for q in ("T1", "T2", "T3", "T4"):
        assert data["quarters"][q]["iva_soportado"] == 0
        assert data["quarters"][q]["iva_repercutido"] == 0
        assert data["quarters"][q]["irpf_retenido"] == 0
        assert data["quarters"][q]["total_facturado"] == 0
    assert data["annual"]["iva_soportado"] == 0


def test_fiscal_summary_invoice_sent(monkeypatch):
    """Invoice sent contributes to iva_repercutido, irpf_retenido, total_facturado."""
    from datetime import datetime as dt

    docs = [
        _mock_fiscal_doc("d1", "invoice_sent", {
            "issue_date": dt(2026, 2, 15),  # T1
            "total_amount": 1210.0,
            "tax_lines": [
                {"tax_type": "iva", "rate": 21.0, "base_amount": 1000.0, "amount": 210.0},
                {"tax_type": "irpf", "rate": 15.0, "base_amount": 1000.0, "amount": -150.0},
            ],
        }),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.get.return_value = docs
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/fiscal-summary?year=2026")
    assert response.status_code == 200
    data = response.json()
    assert data["quarters"]["T1"]["iva_repercutido"] == 210.0
    assert data["quarters"]["T1"]["irpf_retenido"] == 150.0
    assert data["quarters"]["T1"]["total_facturado"] == 1210.0
    assert data["quarters"]["T1"]["iva_soportado"] == 0
    assert data["annual"]["iva_repercutido"] == 210.0
    assert data["annual"]["total_facturado"] == 1210.0


def test_fiscal_summary_invoice_received(monkeypatch):
    """Invoice received contributes to iva_soportado and irpf_retenido."""
    from datetime import datetime as dt

    docs = [
        _mock_fiscal_doc("d2", "invoice_received", {
            "issue_date": dt(2026, 5, 10),  # T2
            "total_amount": 605.0,
            "tax_lines": [
                {"tax_type": "iva", "rate": 21.0, "base_amount": 500.0, "amount": 105.0},
                {"tax_type": "irpf", "rate": 15.0, "base_amount": 500.0, "amount": -75.0},
            ],
        }),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.get.return_value = docs
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/fiscal-summary?year=2026")
    assert response.status_code == 200
    data = response.json()
    assert data["quarters"]["T2"]["iva_soportado"] == 105.0
    assert data["quarters"]["T2"]["irpf_retenido"] == 75.0
    assert data["quarters"]["T2"]["iva_repercutido"] == 0
    assert data["quarters"]["T2"]["total_facturado"] == 0
    assert data["annual"]["iva_soportado"] == 105.0
    assert data["annual"]["irpf_retenido"] == 75.0


def test_fiscal_summary_expense_ticket(monkeypatch):
    """Expense ticket contributes to iva_soportado only — IRPF ignored."""
    from datetime import datetime as dt

    docs = [
        _mock_fiscal_doc("d3", "expense_ticket", {
            "issue_date": dt(2026, 11, 20),  # T4
            "total_amount": 12.10,
            "tax_lines": [
                {"tax_type": "iva", "rate": 10.0, "base_amount": 11.0, "amount": 1.10},
                {"tax_type": "irpf", "rate": 15.0, "base_amount": 11.0, "amount": -1.65},
            ],
        }),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.get.return_value = docs
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/fiscal-summary?year=2026")
    assert response.status_code == 200
    data = response.json()
    assert data["quarters"]["T4"]["iva_soportado"] == 1.1
    assert data["quarters"]["T4"]["irpf_retenido"] == 0  # IRPF not counted for expense_ticket
    assert data["annual"]["iva_soportado"] == 1.1
    assert data["annual"]["irpf_retenido"] == 0


def test_fiscal_summary_filters_by_year(monkeypatch):
    """Documents from other years are excluded."""
    from datetime import datetime as dt

    docs = [
        _mock_fiscal_doc("d1", "invoice_sent", {
            "issue_date": dt(2025, 3, 15),
            "total_amount": 1000.0,
            "tax_lines": [{"tax_type": "iva", "rate": 21.0, "base_amount": 1000.0, "amount": 210.0}],
        }),
        _mock_fiscal_doc("d2", "invoice_sent", {
            "issue_date": dt(2026, 3, 15),
            "total_amount": 500.0,
            "tax_lines": [{"tax_type": "iva", "rate": 21.0, "base_amount": 500.0, "amount": 105.0}],
        }),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.get.return_value = docs
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/fiscal-summary?year=2026")
    assert response.status_code == 200
    data = response.json()
    assert data["annual"]["total_facturado"] == 500.0
    assert data["annual"]["iva_repercutido"] == 105.0


def test_fiscal_summary_skips_docs_without_date(monkeypatch):
    """Documents with no issue_date are gracefully skipped."""
    docs = [
        _mock_fiscal_doc("d1", "invoice_sent", {
            "total_amount": 1000.0,
            "tax_lines": [{"tax_type": "iva", "rate": 21.0, "amount": 210.0}],
        }),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.get.return_value = docs
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/fiscal-summary?year=2026")
    assert response.status_code == 200
    assert response.json()["annual"]["total_facturado"] == 0


def test_fiscal_summary_default_year(monkeypatch):
    """Omitting year param defaults to current year."""
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.get.return_value = []
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/fiscal-summary")
    assert response.status_code == 200
    from datetime import datetime, timezone
    assert response.json()["year"] == datetime.now(timezone.utc).year


def test_fiscal_summary_mixed_quarters(monkeypatch):
    """Mixed doc types and quarters aggregate correctly, including IRPF from both sides."""
    from datetime import datetime as dt

    docs = [
        _mock_fiscal_doc("d1", "invoice_sent", {
            "issue_date": dt(2026, 1, 10),
            "total_amount": 1210.0,
            "tax_lines": [
                {"tax_type": "iva", "rate": 21.0, "amount": 210.0},
                {"tax_type": "irpf", "rate": 15.0, "amount": -150.0},
            ],
        }),
        _mock_fiscal_doc("d2", "invoice_received", {
            "issue_date": dt(2026, 1, 20),
            "total_amount": 484.0,
            "tax_lines": [
                {"tax_type": "iva", "rate": 21.0, "amount": 84.0},
                {"tax_type": "irpf", "rate": 15.0, "amount": -60.0},
            ],
        }),
        _mock_fiscal_doc("d3", "invoice_sent", {
            "issue_date": dt(2026, 7, 5),
            "total_amount": 2420.0,
            "tax_lines": [{"tax_type": "iva", "rate": 21.0, "amount": 420.0}],
        }),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.get.return_value = docs
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/fiscal-summary?year=2026")
    data = response.json()

    assert data["quarters"]["T1"]["iva_repercutido"] == 210.0
    assert data["quarters"]["T1"]["irpf_retenido"] == 210.0  # 150 (sent) + 60 (received)
    assert data["quarters"]["T1"]["total_facturado"] == 1210.0
    assert data["quarters"]["T1"]["iva_soportado"] == 84.0

    assert data["quarters"]["T3"]["iva_repercutido"] == 420.0
    assert data["quarters"]["T3"]["total_facturado"] == 2420.0

    assert data["quarters"]["T2"]["total_facturado"] == 0

    assert data["annual"]["iva_repercutido"] == 630.0
    assert data["annual"]["iva_soportado"] == 84.0
    assert data["annual"]["irpf_retenido"] == 210.0
    assert data["annual"]["total_facturado"] == 3630.0


def test_fiscal_summary_string_date(monkeypatch):
    """Documents with ISO string dates are handled correctly."""
    docs = [
        _mock_fiscal_doc("d1", "invoice_sent", {
            "issue_date": "2026-06-15T00:00:00",
            "total_amount": 500.0,
            "tax_lines": [{"tax_type": "iva", "rate": 21.0, "amount": 105.0}],
        }),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.get.return_value = docs
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/fiscal-summary?year=2026")
    assert response.status_code == 200
    assert response.json()["quarters"]["T2"]["iva_repercutido"] == 105.0
    assert response.json()["quarters"]["T2"]["total_facturado"] == 500.0


def test_fiscal_summary_igic_counts_as_iva(monkeypatch):
    """IGIC (Canarias) is aggregated into iva_soportado / iva_repercutido."""
    from datetime import datetime as dt

    docs = [
        _mock_fiscal_doc("d1", "invoice_sent", {
            "issue_date": dt(2026, 2, 10),
            "total_amount": 1095.0,
            "tax_lines": [
                {"tax_type": "igic", "rate": 9.5, "base_amount": 1000.0, "amount": 95.0},
            ],
        }),
        _mock_fiscal_doc("d2", "invoice_received", {
            "issue_date": dt(2026, 2, 15),
            "total_amount": 547.5,
            "tax_lines": [
                {"tax_type": "igic", "rate": 9.5, "base_amount": 500.0, "amount": 47.5},
            ],
        }),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.get.return_value = docs
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/fiscal-summary?year=2026")
    data = response.json()
    assert data["quarters"]["T1"]["iva_repercutido"] == 95.0
    assert data["quarters"]["T1"]["iva_soportado"] == 47.5
    assert data["quarters"]["T1"]["total_facturado"] == 1095.0
    assert data["annual"]["iva_repercutido"] == 95.0
    assert data["annual"]["iva_soportado"] == 47.5


def test_fiscal_summary_ipsi_counts_as_iva(monkeypatch):
    """IPSI (Ceuta/Melilla) is aggregated into iva_soportado / iva_repercutido."""
    from datetime import datetime as dt

    docs = [
        _mock_fiscal_doc("d1", "invoice_sent", {
            "issue_date": dt(2026, 4, 1),
            "total_amount": 1100.0,
            "tax_lines": [
                {"tax_type": "ipsi", "rate": 10.0, "base_amount": 1000.0, "amount": 100.0},
            ],
        }),
        _mock_fiscal_doc("d2", "expense_ticket", {
            "issue_date": dt(2026, 4, 5),
            "total_amount": 22.0,
            "tax_lines": [
                {"tax_type": "ipsi", "rate": 10.0, "base_amount": 20.0, "amount": 2.0},
            ],
        }),
    ]
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.get.return_value = docs
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/cuentas/c1/fiscal-summary?year=2026")
    data = response.json()
    assert data["quarters"]["T2"]["iva_repercutido"] == 100.0
    assert data["quarters"]["T2"]["iva_soportado"] == 2.0
    assert data["annual"]["iva_repercutido"] == 100.0
    assert data["annual"]["iva_soportado"] == 2.0


# ---------------------------------------------------------------------------
# GET /dashboard/documentos  (global inbox)
# ---------------------------------------------------------------------------

def _mock_global_docs_db(clients_data: dict[str, dict], docs_per_client: dict[str, list]):
    """Build a mock Firestore that supports the global-documentos endpoint.

    ``clients_data`` maps client-id → client dict (e.g. {"nombre": "Acme"}).
    ``docs_per_client`` maps client-id → list of (doc_id, doc_data) tuples.
    """
    mock_db = MagicMock()

    # cuentas collection → returns client docs
    client_docs = [_mock_client_doc(cid, cdata) for cid, cdata in clients_data.items()]

    def _collection_router(path: str):
        col = MagicMock()
        if path.endswith("/cuentas"):
            col.get.return_value = client_docs
        else:
            # documents collection for a specific client
            matching_client = None
            for cid in clients_data:
                if cid in path:
                    matching_client = cid
                    break
            raw = docs_per_client.get(matching_client, [])
            doc_mocks = [_mock_client_doc(did, ddata) for did, ddata in raw]
            col.order_by.return_value.limit.return_value.get.return_value = doc_mocks
        return col

    mock_db.collection.side_effect = _collection_router
    return mock_db


def test_list_all_documents_empty(monkeypatch):
    """No cuentas → empty list."""
    mock_db = _mock_global_docs_db({}, {})
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/documentos")
    assert response.status_code == 200
    data = response.json()
    assert data["gestoria_id"] == _GESTORIA
    assert data["documentos"] == []
    assert data["total"] == 0


def test_list_all_documents_returns_data(monkeypatch):
    """Multiple cuentas with docs → merged, sorted by created_at desc."""
    clients = {"c1": {"nombre": "Acme"}, "c2": {"nombre": "Beta"}}
    docs = {
        "c1": [
            ("h1", {
                "document_type": "invoice_received",
                "file_name": "factura1.pdf",
                "created_at": "2026-04-01T10:00:00Z",
                "normalized_data": {"total": 100},
                "storage_path": "gs://bucket/path",
            }),
        ],
        "c2": [
            ("h2", {
                "document_type": "expense_ticket",
                "file_name": "ticket.jpg",
                "created_at": "2026-04-02T08:00:00Z",
                "normalized_data": None,
            }),
        ],
    }
    mock_db = _mock_global_docs_db(clients, docs)
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/documentos")
    assert response.status_code == 200
    data = response.json()
    documentos = data["documentos"]
    assert len(documentos) == 2
    assert data["total"] == 2
    # Most recent first (c2/h2 = 2026-04-02)
    assert documentos[0]["doc_hash"] == "h2"
    assert documentos[0]["cuenta_nombre"] == "Beta"
    assert documentos[0]["has_original"] is False
    assert documentos[1]["doc_hash"] == "h1"
    assert documentos[1]["cuenta_nombre"] == "Acme"
    assert documentos[1]["has_original"] is True


def test_list_all_documents_respects_limit(monkeypatch):
    """When limit < total docs, only top N returned."""
    clients = {"c1": {"nombre": "Acme"}}
    docs = {
        "c1": [
            ("h1", {"document_type": "invoice_received", "file_name": "a.pdf",
                     "created_at": "2026-01-01T00:00:00Z", "normalized_data": None}),
            ("h2", {"document_type": "invoice_received", "file_name": "b.pdf",
                     "created_at": "2026-02-01T00:00:00Z", "normalized_data": None}),
            ("h3", {"document_type": "invoice_received", "file_name": "c.pdf",
                     "created_at": "2026-03-01T00:00:00Z", "normalized_data": None}),
        ],
    }
    mock_db = _mock_global_docs_db(clients, docs)
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/dashboard/documentos?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["documentos"]) == 2
    assert data["total"] == 3
    # Most recent two
    assert data["documentos"][0]["doc_hash"] == "h3"
    assert data["documentos"][1]["doc_hash"] == "h2"
