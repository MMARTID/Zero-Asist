# tests/test_main.py

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_procesar_documento(monkeypatch):

    def fake_extract(file_bytes, mime_type):
        return {
            "issuer_name": "Empresa Test",
            "issue_date": "2024-01-01",
            "base_amount": 100,
            "tax_amount": 21,
            "total_amount": 121,
            "currency": "EUR",
            "tax_breakdown": [],
            "line_items": []
        }

    def fake_guardar(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.main.extract_from_file",
        fake_extract
    )

    monkeypatch.setattr(
        "app.main.guardar_documento",
        fake_guardar
    )

    response = client.post(
        "/procesar-documento",
        files={"file": ("test.pdf", b"fake content", "application/pdf")}
    )

    assert response.status_code == 200
    data = response.json()
    assert "documento_id" in data
    assert data["normalized_data"]["issuer_name"] == "Empresa Test"