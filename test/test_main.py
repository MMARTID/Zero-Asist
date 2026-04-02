# tests/test_main.py

from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_procesar_documento(monkeypatch):

    def fake_extract(file_bytes, mime_type):
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
                "line_items": []
            }
        }

    def fake_guardar_si_no_existe(*args, **kwargs):
        return None

    fake_snapshot = MagicMock()
    fake_snapshot.exists = False
    fake_doc_ref = MagicMock()
    fake_doc_ref.get.return_value = fake_snapshot
    fake_collection = MagicMock()
    fake_collection.document.return_value = fake_doc_ref
    fake_db = MagicMock()
    fake_db.collection.return_value = fake_collection
    fake_db.transaction.return_value = MagicMock()

    monkeypatch.setattr(
        "app.main.extract_from_file",
        fake_extract
    )

    monkeypatch.setattr(
        "app.main.guardar_si_no_existe",
        fake_guardar_si_no_existe
    )

    monkeypatch.setattr(
        "app.main.db",
        fake_db
    )

    response = client.post(
        "/procesar-documento",
        files={"file": ("test.pdf", b"fake content", "application/pdf")}
    )

    assert response.status_code == 200
    data = response.json()
    assert "documento_id" in data
    assert data["document_type"] == "invoice_received"
    assert data["normalized_data"]["issuer_name"] == "Empresa Test"
