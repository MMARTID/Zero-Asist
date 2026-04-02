# tests/test_gemini_client.py

from app.services import gemini_client

def test_extract_from_file_mock(monkeypatch):
    fake_response = '{"document_type": "invoice_received", "data": {"issuer_name": "Test SL"}}'

    class FakeResponse:
        text = fake_response

    def fake_generate_content(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        gemini_client.client.models,
        "generate_content",
        fake_generate_content
    )

    result = gemini_client.extract_from_file(b"fake", "application/pdf")

    assert result["document_type"] == "invoice_received"
    assert result["data"]["issuer_name"] == "Test SL"