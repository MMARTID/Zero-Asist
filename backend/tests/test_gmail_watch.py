# tests/test_gmail_watch.py
"""Tests for app.collectors.gmail_watch."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from app.collectors.gmail_watch import (
    start_watch,
    stop_watch,
    renew_watch,
    get_new_messages,
    get_watch_state,
    is_watch_expiring_soon,
)
from app.services.tenant import TenantContext


@pytest.fixture
def ctx():
    return TenantContext(gestoria_id="g1", cliente_id="c1")


@pytest.fixture
def mock_db(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr("app.collectors.gmail_watch._db", db)
    return db


@pytest.fixture
def mock_service():
    return MagicMock()


# ---------------------------------------------------------------------------
# start_watch
# ---------------------------------------------------------------------------

def test_start_watch(mock_service, mock_db, ctx):
    mock_service.users().watch.return_value.execute.return_value = {
        "historyId": "12345",
        "expiration": 1700000000000,
    }

    result = start_watch(mock_service, "projects/p/topics/t", ctx)

    assert result["historyId"] == "12345"
    assert result["expiration"] == 1700000000000
    mock_db.document.assert_called_with("gestorias/g1/cuentas/c1")
    mock_db.document().set.assert_called_once()
    saved = mock_db.document().set.call_args
    state = saved[0][0]["gmail_watch_state"]
    assert state["history_id"] == "12345"
    assert state["status"] == "active"


# ---------------------------------------------------------------------------
# stop_watch
# ---------------------------------------------------------------------------

def test_stop_watch(mock_service, mock_db, ctx):
    stop_watch(mock_service, ctx)

    mock_service.users().stop.assert_called_once()
    saved = mock_db.document().set.call_args
    state = saved[0][0]["gmail_watch_state"]
    assert state["status"] == "stopped"


# ---------------------------------------------------------------------------
# renew_watch (delegates to start_watch)
# ---------------------------------------------------------------------------

def test_renew_watch(mock_service, mock_db, ctx):
    mock_service.users().watch.return_value.execute.return_value = {
        "historyId": "99999",
        "expiration": 1800000000000,
    }

    result = renew_watch(mock_service, "projects/p/topics/t", ctx)

    assert result["historyId"] == "99999"


# ---------------------------------------------------------------------------
# get_new_messages
# ---------------------------------------------------------------------------

def test_get_new_messages_returns_added_messages(mock_service, mock_db, ctx):
    """New messages from history.list are returned and historyId is advanced."""
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "gmail_watch_state": {"history_id": "100", "status": "active"},
    }
    mock_db.document.return_value.get.return_value = snapshot
    mock_db.transaction.return_value = MagicMock()

    mock_service.users().history().list.return_value.execute.return_value = {
        "history": [
            {
                "id": "200",
                "messagesAdded": [{"message": {"id": "msg1", "threadId": "t1"}}],
            },
        ],
    }

    messages = get_new_messages(mock_service, ctx)

    assert len(messages) == 1
    assert messages[0]["id"] == "msg1"


def test_get_new_messages_no_watch_state(mock_service, mock_db, ctx):
    """No watch state → returns empty list."""
    snapshot = MagicMock()
    snapshot.exists = False
    mock_db.document.return_value.get.return_value = snapshot
    mock_db.transaction.return_value = MagicMock()

    messages = get_new_messages(mock_service, ctx)
    assert messages == []


def test_get_new_messages_history_api_error(mock_service, mock_db, ctx):
    """history.list fails → returns empty list, does not raise."""
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "gmail_watch_state": {"history_id": "100"},
    }
    mock_db.document.return_value.get.return_value = snapshot
    mock_db.transaction.return_value = MagicMock()

    mock_service.users().history().list.return_value.execute.side_effect = RuntimeError("expired")

    messages = get_new_messages(mock_service, ctx)
    assert messages == []


# ---------------------------------------------------------------------------
# get_watch_state
# ---------------------------------------------------------------------------

def test_get_watch_state_returns_state(mock_db, ctx):
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "gmail_watch_state": {"history_id": "100", "status": "active"},
    }
    mock_db.document.return_value.get.return_value = snapshot

    state = get_watch_state(ctx)
    assert state["status"] == "active"


def test_get_watch_state_missing(mock_db, ctx):
    snapshot = MagicMock()
    snapshot.exists = False
    mock_db.document.return_value.get.return_value = snapshot

    assert get_watch_state(ctx) is None


# ---------------------------------------------------------------------------
# is_watch_expiring_soon
# ---------------------------------------------------------------------------

def test_is_watch_expiring_soon_true(mock_db, ctx):
    """Expiration in the past → expiring soon."""
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "gmail_watch_state": {"status": "active", "expiration": 0},
    }
    mock_db.document.return_value.get.return_value = snapshot

    assert is_watch_expiring_soon(ctx) is True


def test_is_watch_expiring_soon_false(mock_db, ctx):
    """Expiration far in the future → not expiring soon."""
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "gmail_watch_state": {
            "status": "active",
            "expiration": int(datetime.now(timezone.utc).timestamp() * 1000) + 7 * 86_400_000,
        },
    }
    mock_db.document.return_value.get.return_value = snapshot

    assert is_watch_expiring_soon(ctx) is False


def test_is_watch_expiring_soon_no_state(mock_db, ctx):
    """No watch state → considered expiring."""
    snapshot = MagicMock()
    snapshot.exists = False
    mock_db.document.return_value.get.return_value = snapshot

    assert is_watch_expiring_soon(ctx) is True
