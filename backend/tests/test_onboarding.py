"""Tests for app.api.onboarding — client creation + OAuth flow."""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_gestoria
from app.main import app

# Override auth dependency for ALL onboarding tests.
_GESTORIA = "g-test"
app.dependency_overrides[get_current_gestoria] = lambda: _GESTORIA

client = TestClient(app)


# ---------------------------------------------------------------------------
# POST /onboarding/cuentas
# ---------------------------------------------------------------------------

def test_create_client(monkeypatch):
    """Creates a client and returns its id."""
    mock_ref = MagicMock()
    mock_ref.id = "new-client-id"

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value = mock_ref
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.post(
        "/onboarding/cuentas",
        json={"nombre": "Test Client", "phone_number": "+34600123456", "tax_id": "B12345678"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cuenta_id"] == "new-client-id"
    assert data["gestoria_id"] == _GESTORIA
    assert data["nombre"] == "Test Client"
    assert data["tax_id"] == "B12345678"
    assert data["tax_country"] == "ES"
    assert data["tax_type"] == "company"
    mock_ref.set.assert_called_once()


def test_create_client_missing_fields():
    """Missing required fields → 422."""
    response = client.post("/onboarding/cuentas", json={"nombre": "Only name"})
    assert response.status_code == 422


def test_create_client_missing_phone():
    """Missing phone_number → 422."""
    response = client.post("/onboarding/cuentas", json={"nombre": "No phone", "tax_id": "B12345678"})
    assert response.status_code == 422


def test_create_client_invalid_tax_id(monkeypatch):
    """Unrecognizable tax_id → 422."""
    mock_ref = MagicMock()
    mock_ref.id = "wont-be-used"
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value = mock_ref
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.post(
        "/onboarding/cuentas",
        json={"nombre": "Test", "phone_number": "+34600123456", "tax_id": "INVALID"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /onboarding/gmail/authorize/{cliente_id}
# ---------------------------------------------------------------------------

def test_authorize_client_not_found(monkeypatch):
    """Non-existent client → 404."""
    mock_doc = MagicMock()
    mock_doc.exists = False

    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get(
        "/onboarding/gmail/authorize/c-missing",
        follow_redirects=False,
    )
    assert response.status_code == 404


def test_authorize_missing_oauth_config(monkeypatch):
    """OAUTH_CLIENT_CONFIG_PATH not set → 500."""
    mock_doc = MagicMock()
    mock_doc.exists = True

    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)
    monkeypatch.setattr("app.api.onboarding._OAUTH_CLIENT_CONFIG_PATH", "")

    response = client.get(
        "/onboarding/gmail/authorize/c1",
        follow_redirects=False,
    )
    assert response.status_code == 500


def test_authorize_returns_url(monkeypatch):
    """Valid client + OAuth config → 200 JSON with authorization_url."""
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    mock_flow = MagicMock()
    mock_flow.authorization_url.return_value = ("https://accounts.google.com/auth?x=1", "dummy")
    mock_flow.code_verifier = "test-verifier"
    monkeypatch.setattr("app.api.onboarding._build_flow", lambda: mock_flow)

    response = client.get(
        "/onboarding/gmail/authorize/c1",
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "accounts.google.com" in response.json()["authorization_url"]


# ---------------------------------------------------------------------------
# GET /onboarding/gmail/callback
# ---------------------------------------------------------------------------

def test_callback_invalid_state(monkeypatch):
    """State without ':' → 400."""
    response = client.get("/onboarding/gmail/callback?code=abc&state=badstate")
    assert response.status_code == 400


def test_callback_client_not_found(monkeypatch):
    """Valid state format but client doesn't exist → 404."""
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    mock_flow = MagicMock()
    monkeypatch.setattr("app.api.onboarding._build_flow", lambda: mock_flow)

    response = client.get("/onboarding/gmail/callback?code=abc&state=g1:c1")
    assert response.status_code == 404


def test_callback_happy_path(monkeypatch):
    """Full callback flow → saves creds, stores email, returns connected."""
    # Client exists
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    # OAuth flow
    mock_creds = MagicMock()
    mock_flow = MagicMock()
    mock_flow.credentials = mock_creds
    monkeypatch.setattr("app.api.onboarding._build_flow", lambda: mock_flow)

    # save_credentials
    save_mock = MagicMock()
    monkeypatch.setattr("app.api.onboarding.save_credentials", save_mock)

    # Gmail profile
    mock_service = MagicMock()
    mock_service.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": "cliente@gmail.com",
    }
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *a, **kw: mock_service)

    # No Pub/Sub topic → skip watch start
    monkeypatch.setattr("app.api.onboarding._PUBSUB_TOPIC", "")

    response = client.get("/onboarding/gmail/callback?code=AUTH_CODE&state=g1:c1", follow_redirects=False)
    assert response.status_code == 302
    assert "/dashboard/cuentas/c1" in response.headers["location"]
    save_mock.assert_called_once()


def test_callback_starts_watch(monkeypatch):
    """When PUBSUB_TOPIC is set, watch is started after OAuth."""
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_db = MagicMock()
    mock_db.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    mock_creds = MagicMock()
    mock_flow = MagicMock()
    mock_flow.credentials = mock_creds
    monkeypatch.setattr("app.api.onboarding._build_flow", lambda: mock_flow)
    monkeypatch.setattr("app.api.onboarding.save_credentials", MagicMock())

    mock_service = MagicMock()
    mock_service.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": "cliente@gmail.com",
    }
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *a, **kw: mock_service)

    monkeypatch.setattr("app.api.onboarding._PUBSUB_TOPIC", "projects/p/topics/t")
    watch_mock = MagicMock()
    monkeypatch.setattr("app.api.onboarding.start_watch", watch_mock)

    response = client.get("/onboarding/gmail/callback?code=AUTH_CODE&state=g1:c1", follow_redirects=False)
    assert response.status_code == 302
    watch_mock.assert_called_once()
