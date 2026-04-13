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
    monkeypatch.setattr("app.api.internal._db", mock_db)

    response = client.post("/internal/renew-watches")
    assert response.status_code == 200
    assert response.json()["renewed"] == 0


def test_renew_watches_renews_active_client(monkeypatch):
    """Active watch → renewed successfully."""
    monkeypatch.setattr("app.api.internal._PUBSUB_TOPIC", "projects/p/topics/t")

    doc = MagicMock()
    doc.reference.path = "gestorias/g1/clientes/c1"
    mock_db = MagicMock()
    mock_db.collection_group.return_value.where.return_value.get.return_value = [doc]
    monkeypatch.setattr("app.api.internal._db", mock_db)

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
    doc.reference.path = "gestorias/g1/clientes/c1"
    mock_db = MagicMock()
    mock_db.collection_group.return_value.where.return_value.get.return_value = [doc]
    monkeypatch.setattr("app.api.internal._db", mock_db)

    monkeypatch.setattr(
        "app.api.internal.get_gmail_service",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("creds expired")),
    )

    response = client.post("/internal/renew-watches")
    assert response.status_code == 200
    data = response.json()
    assert data["failed"] == 1
    assert len(data["errors"]) == 1
