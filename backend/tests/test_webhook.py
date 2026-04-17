# tests/test_webhook.py
"""Tests for app.api.webhook and app.api.internal endpoints."""

import base64
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.services.tenant import TenantContext

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pubsub_body(email: str = "cliente@gmail.com", history_id: str = "12345") -> dict:
    payload = json.dumps({"emailAddress": email, "historyId": history_id})
    data_b64 = base64.b64encode(payload.encode()).decode()
    return {"message": {"data": data_b64, "messageId": "m1"}}


# ---------------------------------------------------------------------------
# POST /webhook/gmail
# ---------------------------------------------------------------------------

def test_webhook_missing_data(monkeypatch):
    """Empty Pub/Sub message → 400."""
    # Skip JWT verification (CLOUD_RUN_URL not set)
    monkeypatch.setattr("app.api.webhook._CLOUD_RUN_URL", "")
    response = client.post("/webhook/gmail", json={"message": {}})
    assert response.status_code == 400


def test_webhook_invalid_payload(monkeypatch):
    """Non-base64 data → 400."""
    monkeypatch.setattr("app.api.webhook._CLOUD_RUN_URL", "")
    response = client.post("/webhook/gmail", json={"message": {"data": "!!!not-base64"}})
    assert response.status_code == 400


def test_webhook_missing_email(monkeypatch):
    """Payload without emailAddress → 400."""
    monkeypatch.setattr("app.api.webhook._CLOUD_RUN_URL", "")
    payload = base64.b64encode(json.dumps({"historyId": "123"}).encode()).decode()
    response = client.post("/webhook/gmail", json={"message": {"data": payload}})
    assert response.status_code == 400


def test_webhook_unknown_email_returns_200(monkeypatch):
    """Unknown email → 200 with status=accepted (no retry)."""
    monkeypatch.setattr("app.api.webhook._CLOUD_RUN_URL", "")
    monkeypatch.setattr("app.api.webhook._find_tenant_by_email", lambda email: None)

    response = client.post("/webhook/gmail", json=_pubsub_body())
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_webhook_happy_path(monkeypatch):
    """Known email → processes messages → 200 with status=accepted."""
    monkeypatch.setattr("app.api.webhook._CLOUD_RUN_URL", "")

    ctx = TenantContext(gestoria_id="g1", cliente_id="c1")
    monkeypatch.setattr("app.api.webhook._find_tenant_by_email", lambda email: ctx)

    mock_service = MagicMock()
    monkeypatch.setattr("app.api.webhook.get_gmail_service", lambda **kw: mock_service)

    # No new messages
    monkeypatch.setattr("app.api.webhook.get_new_messages", lambda svc, c: [])
    monkeypatch.setattr("app.api.webhook._PUBSUB_TOPIC", "")

    response = client.post("/webhook/gmail", json=_pubsub_body())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"


def test_webhook_processes_new_message(monkeypatch):
    """New message in history → processed through pipeline."""
    monkeypatch.setattr("app.api.webhook._CLOUD_RUN_URL", "")

    ctx = TenantContext(gestoria_id="g1", cliente_id="c1")
    monkeypatch.setattr("app.api.webhook._find_tenant_by_email", lambda email: ctx)

    mock_service = MagicMock()
    monkeypatch.setattr("app.api.webhook.get_gmail_service", lambda **kw: mock_service)
    monkeypatch.setattr(
        "app.api.webhook.get_new_messages",
        lambda svc, c: [{"id": "msg1", "threadId": "t1"}],
    )
    monkeypatch.setattr("app.api.webhook._PUBSUB_TOPIC", "")

    # Mock _process_single_message
    monkeypatch.setattr(
        "app.api.webhook._process_single_message",
        lambda svc, mid, c: {"msg_id": mid, "procesados": 1, "duplicados": 0, "errores": 0, "descartados": False},
    )

    response = client.post("/webhook/gmail", json=_pubsub_body())
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_webhook_jwt_required_when_cloud_run_url_set(monkeypatch):
    """When CLOUD_RUN_URL is set, missing Authorization → 403."""
    monkeypatch.setattr("app.api.webhook._CLOUD_RUN_URL", "https://my-service.run.app")

    response = client.post("/webhook/gmail", json=_pubsub_body())
    assert response.status_code == 403


def test_webhook_opportunistic_renewal(monkeypatch):
    """Watch expiring soon → renewed after processing."""
    monkeypatch.setattr("app.api.webhook._CLOUD_RUN_URL", "")

    ctx = TenantContext(gestoria_id="g1", cliente_id="c1")
    monkeypatch.setattr("app.api.webhook._find_tenant_by_email", lambda email: ctx)

    mock_service = MagicMock()
    monkeypatch.setattr("app.api.webhook.get_gmail_service", lambda **kw: mock_service)
    monkeypatch.setattr("app.api.webhook.get_new_messages", lambda svc, c: [])
    monkeypatch.setattr("app.api.webhook._PUBSUB_TOPIC", "projects/p/topics/t")
    monkeypatch.setattr("app.api.webhook.is_watch_expiring_soon", lambda c: True)

    renew_mock = MagicMock()
    monkeypatch.setattr("app.api.webhook.renew_watch", renew_mock)

    response = client.post("/webhook/gmail", json=_pubsub_body())
    assert response.status_code == 200
    renew_mock.assert_called_once_with(mock_service, "projects/p/topics/t", ctx)


# ---------------------------------------------------------------------------
# POST /internal/renew-watches
# ---------------------------------------------------------------------------

def test_renew_watches_no_topic(monkeypatch):
    """GMAIL_PUBSUB_TOPIC not set → 500."""
    monkeypatch.setattr("app.api.internal._PUBSUB_TOPIC", "")

    response = client.post("/internal/renew-watches")
    assert response.status_code == 500


def test_renew_watches_no_active_clients(monkeypatch):
    """No active watches → empty result."""
    monkeypatch.setattr("app.api.internal._PUBSUB_TOPIC", "projects/p/topics/t")

    mock_db = MagicMock()
    mock_db.collection_group.return_value.where.return_value.get.return_value = []
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.post("/internal/renew-watches")
    assert response.status_code == 200
    assert response.json()["renewed"] == 0


def test_renew_watches_renews_active_client(monkeypatch):
    """Active watch → renewed successfully."""
    monkeypatch.setattr("app.api.internal._PUBSUB_TOPIC", "projects/p/topics/t")

    doc = MagicMock()
    doc.reference.path = "gestorias/g1/cuentas/c1"
    mock_db = MagicMock()
    mock_db.collection_group.return_value.where.return_value.get.return_value = [doc]
    monkeypatch.setattr("app.api.deps._db", mock_db)

    mock_service = MagicMock()
    monkeypatch.setattr("app.api.internal.get_gmail_service", lambda **kw: mock_service)

    renew_mock = MagicMock()
    monkeypatch.setattr("app.api.internal.renew_watch", renew_mock)

    response = client.post("/internal/renew-watches")
    assert response.status_code == 200
    data = response.json()
    assert data["renewed"] == 1
    assert data["failed"] == 0
    renew_mock.assert_called_once()


def test_renew_watches_handles_failure(monkeypatch):
    """Renewal failure → counted, doesn't crash."""
    monkeypatch.setattr("app.api.internal._PUBSUB_TOPIC", "projects/p/topics/t")

    doc = MagicMock()
    doc.reference.path = "gestorias/g1/cuentas/c1"
    mock_db = MagicMock()
    mock_db.collection_group.return_value.where.return_value.get.return_value = [doc]
    monkeypatch.setattr("app.api.deps._db", mock_db)

    monkeypatch.setattr(
        "app.api.internal.get_gmail_service",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("creds expired")),
    )

    response = client.post("/internal/renew-watches")
    assert response.status_code == 200
    data = response.json()
    assert data["failed"] == 1
    assert len(data["errors"]) == 1


# ---------------------------------------------------------------------------
# POST /internal/reprocess-normalizer
# ---------------------------------------------------------------------------

def test_reprocess_normalizer_no_clients(monkeypatch):
    """No active watches → zero updates."""
    mock_db = MagicMock()
    mock_db.collection_group.return_value.where.return_value.get.return_value = []
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.post("/internal/reprocess-normalizer")
    assert response.status_code == 200
    assert response.json()["updated"] == 0


def test_reprocess_normalizer_updates_document(monkeypatch):
    """Active client with a document → normalized_data is re-written."""
    client_doc = MagicMock()
    client_doc.reference.path = "gestorias/g1/cuentas/c1"
    client_doc.to_dict.return_value = {"nombre": "Test Co", "tax_id": "B12345678"}

    doc = MagicMock()
    doc.id = "abc123"
    doc.to_dict.return_value = {
        "document_type": "invoice_received",
        "extracted_data": {
            "issuer_name": "ACME SL",
            "issue_date": "11.11.2024",
            "total_amount": 100.0,
        },
        "normalized_data": {"issue_date": None},
    }

    mock_db = MagicMock()
    mock_db.collection_group.return_value.where.return_value.get.return_value = [client_doc]
    mock_db.collection.return_value.stream.return_value = [doc]
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.post("/internal/reprocess-normalizer")
    assert response.status_code == 200
    data = response.json()
    assert data["updated"] == 1
    assert data["skipped"] == 0

    # Verify normalized_data was written back
    doc.reference.update.assert_called_once()
    written = doc.reference.update.call_args[0][0]["normalized_data"]
    assert written["issue_date"] is not None  # date was now parsed


def test_reprocess_normalizer_skips_incomplete(monkeypatch):
    """Documents without extracted_data are skipped."""
    client_doc = MagicMock()
    client_doc.reference.path = "gestorias/g1/cuentas/c1"
    client_doc.to_dict.return_value = {"nombre": "Test"}

    doc = MagicMock()
    doc.id = "abc"
    doc.to_dict.return_value = {"document_type": "invoice_received", "extracted_data": None}

    mock_db = MagicMock()
    mock_db.collection_group.return_value.where.return_value.get.return_value = [client_doc]
    mock_db.collection.return_value.stream.return_value = [doc]
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.post("/internal/reprocess-normalizer")
    assert response.status_code == 200
    assert response.json()["skipped"] == 1


# ---------------------------------------------------------------------------
# POST /internal/reprocess-document/{gestoria_id}/{cuenta_id}/{doc_id}
# ---------------------------------------------------------------------------

def test_reprocess_single_document_not_found(monkeypatch):
    """Non-existent document → 404."""
    mock_db = MagicMock()
    snap = MagicMock()
    snap.exists = False
    mock_db.document.return_value.get.return_value = snap
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.post("/internal/reprocess-document/g1/c1/missing")
    assert response.status_code == 404


def test_reprocess_single_document_no_extracted(monkeypatch):
    """Document without extracted_data → 400."""
    mock_db = MagicMock()
    snap = MagicMock()
    snap.exists = True
    snap.to_dict.return_value = {"document_type": "invoice_received", "extracted_data": None}
    mock_db.document.return_value.get.return_value = snap
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.post("/internal/reprocess-document/g1/c1/doc1")
    assert response.status_code == 400


def test_reprocess_single_document_success(monkeypatch):
    """Full re-normalization round-trip with diff."""
    doc_snap = MagicMock()
    doc_snap.exists = True
    doc_snap.to_dict.return_value = {
        "document_type": "invoice_received",
        "extracted_data": {
            "issuer_name": "APPLE",
            "issue_date": "11.11.2024",
            "total_amount": 719.0,
            "invoice_number": "UA17160357",
        },
        "normalized_data": {
            "issuer_name": "APPLE",
            "issue_date": None,
            "total_amount": 719.0,
            "invoice_number": "UA17160357",
        },
    }

    cuenta_snap = MagicMock()
    cuenta_snap.exists = True
    cuenta_snap.to_dict.return_value = {"nombre": "Mi Empresa", "tax_id": "B99999999"}

    mock_db = MagicMock()

    def _document_side_effect(path):
        m = MagicMock()
        if "documentos" in path:
            m.get.return_value = doc_snap
        else:
            m.get.return_value = cuenta_snap
        return m
    mock_db.document.side_effect = _document_side_effect
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.post(
        "/internal/reprocess-document/g1/c1/dbf05cda"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == "dbf05cda"
    assert data["document_type"] == "invoice_received"
    # issue_date should have changed from None
    assert "issue_date" in data["changes"]

    # Verify Firestore was updated
    doc_snap.reference.update.assert_called_once()
