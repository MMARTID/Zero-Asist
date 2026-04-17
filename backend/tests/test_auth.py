"""Tests for app.api.auth — Firebase Auth dependency."""

from unittest.mock import MagicMock, patch
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import _verify_firebase_token, get_current_gestoria


# ---------------------------------------------------------------------------
# Minimal app with a single protected route for testing the dependency chain
# ---------------------------------------------------------------------------

_test_app = FastAPI()


@_test_app.get("/protected")
def protected(gestoria_id: str = pytest.importorskip("fastapi").Depends(get_current_gestoria)):
    return {"gestoria_id": gestoria_id}


client = TestClient(_test_app)


# ---------------------------------------------------------------------------
# _verify_firebase_token
# ---------------------------------------------------------------------------

def test_missing_auth_header():
    """No Authorization header → 401."""
    response = client.get("/protected")
    assert response.status_code == 401


def test_malformed_auth_header():
    """Authorization header without 'Bearer ' → 401."""
    response = client.get("/protected", headers={"Authorization": "Token abc"})
    assert response.status_code == 401


def test_invalid_token(monkeypatch):
    """verify_id_token raises → 401."""
    import firebase_admin.auth as fa_auth

    monkeypatch.setattr(fa_auth, "verify_id_token", MagicMock(side_effect=Exception("bad")))

    response = client.get("/protected", headers={"Authorization": "Bearer bad-token"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# get_current_gestoria
# ---------------------------------------------------------------------------

def test_gestoria_from_custom_claim(monkeypatch):
    """Custom claim gestoria_id → returned directly."""
    import firebase_admin.auth as fa_auth

    monkeypatch.setattr(
        fa_auth,
        "verify_id_token",
        MagicMock(return_value={"uid": "u1", "gestoria_id": "g1"}),
    )

    response = client.get("/protected", headers={"Authorization": "Bearer ok"})
    assert response.status_code == 200
    assert response.json()["gestoria_id"] == "g1"


def test_gestoria_from_firestore_lookup(monkeypatch):
    """No custom claim → look up usuarios/{uid} in Firestore."""
    import firebase_admin.auth as fa_auth

    monkeypatch.setattr(
        fa_auth,
        "verify_id_token",
        MagicMock(return_value={"uid": "u1"}),
    )

    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"gestoria_id": "g2"}

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/protected", headers={"Authorization": "Bearer ok"})
    assert response.status_code == 200
    assert response.json()["gestoria_id"] == "g2"


def test_user_not_in_firestore_auto_registers(monkeypatch):
    """No custom claim + user not in Firestore → auto-register and return 200."""
    import firebase_admin.auth as fa_auth

    monkeypatch.setattr(
        fa_auth,
        "verify_id_token",
        MagicMock(return_value={"uid": "u1", "name": "Test", "email": "t@t.com"}),
    )

    mock_doc = MagicMock()
    mock_doc.exists = False

    mock_gestoria_ref = MagicMock()
    mock_gestoria_ref.id = "auto-g1"

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
    mock_db.collection.return_value.document.return_value = mock_gestoria_ref
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/protected", headers={"Authorization": "Bearer ok"})
    assert response.status_code == 200


def test_user_without_gestoria_id(monkeypatch):
    """User exists in Firestore but has no gestoria_id field → 403."""
    import firebase_admin.auth as fa_auth

    monkeypatch.setattr(
        fa_auth,
        "verify_id_token",
        MagicMock(return_value={"uid": "u1"}),
    )

    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"email": "test@example.com"}

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
    monkeypatch.setattr("app.api.deps._db", mock_db)

    response = client.get("/protected", headers={"Authorization": "Bearer ok"})
    assert response.status_code == 403
