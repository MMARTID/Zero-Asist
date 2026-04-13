"""Gmail Watch API helpers — start, stop, renew watches and fetch new messages.

Each tenant's Gmail account has an independent watch subscription that pushes
notifications to a shared Pub/Sub topic.  This module wraps the Gmail API
calls and the Firestore state that tracks ``historyId`` and ``expiration``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from google.cloud import firestore
from googleapiclient.discovery import Resource

from app.services.tenant import TenantContext

logger = logging.getLogger(__name__)

# Lazy Firestore client — reuses the one from firestore_client at runtime.
_db: Optional[firestore.Client] = None


def _get_db() -> firestore.Client:
    global _db
    if _db is None:
        from app.services.firestore_client import db
        _db = db
    return _db


def _watch_doc_path(ctx: TenantContext) -> str:
    return f"gestorias/{ctx.gestoria_id}/clientes/{ctx.cliente_id}"


# ---------------------------------------------------------------------------
# Watch lifecycle
# ---------------------------------------------------------------------------

def start_watch(
    service: Resource,
    topic_name: str,
    ctx: TenantContext,
) -> dict:
    """Register a Gmail watch and persist state in Firestore.

    Returns the raw Gmail API response (``historyId``, ``expiration``).
    """
    response = service.users().watch(
        userId="me",
        body={
            "topicName": topic_name,
            "labelIds": ["INBOX"],
        },
    ).execute()

    history_id = response["historyId"]
    expiration = int(response["expiration"])

    db = _get_db()
    db.document(_watch_doc_path(ctx)).set(
        {
            "gmail_watch_state": {
                "history_id": history_id,
                "expiration": expiration,
                "status": "active",
                "updated_at": datetime.now(timezone.utc),
            },
            "gmail_watch_status": "active",
        },
        merge=True,
    )

    logger.info(
        "Watch started for %s/%s — historyId=%s expiration=%s",
        ctx.gestoria_id, ctx.cliente_id, history_id, expiration,
    )
    return response


def stop_watch(service: Resource, ctx: TenantContext) -> None:
    """Stop the Gmail watch for a tenant."""
    service.users().stop(
        userId="me",
        body={},
    ).execute()

    db = _get_db()
    db.document(_watch_doc_path(ctx)).set(
        {
            "gmail_watch_state": {
                "status": "stopped",
                "updated_at": datetime.now(timezone.utc),
            },
            "gmail_watch_status": "stopped",
        },
        merge=True,
    )
    logger.info("Watch stopped for %s/%s", ctx.gestoria_id, ctx.cliente_id)


def renew_watch(
    service: Resource,
    topic_name: str,
    ctx: TenantContext,
) -> dict:
    """Renew an existing watch (idempotent — calls ``watch()`` again)."""
    return start_watch(service, topic_name, ctx)


# ---------------------------------------------------------------------------
# History-based message retrieval (with atomic historyId update)
# ---------------------------------------------------------------------------

def get_new_messages(
    service: Resource,
    ctx: TenantContext,
) -> list[dict]:
    """Fetch messages added since the last known ``historyId``.

    Uses a Firestore transaction to atomically read and update ``historyId``,
    preventing duplicate processing when concurrent pushes arrive.

    Returns a list of message dicts (``{"id": ..., "threadId": ...}``).
    """
    db = _get_db()
    doc_ref = db.document(_watch_doc_path(ctx))

    @firestore.transactional
    def _atomic_history_fetch(transaction):
        snapshot = doc_ref.get(transaction=transaction)
        if not snapshot.exists:
            logger.warning("No watch state for %s/%s", ctx.gestoria_id, ctx.cliente_id)
            return []

        watch_state = snapshot.to_dict().get("gmail_watch_state", {})
        start_history_id = watch_state.get("history_id")
        if not start_history_id:
            logger.warning("No historyId for %s/%s", ctx.gestoria_id, ctx.cliente_id)
            return []

        # Fetch history records from Gmail
        messages: list[dict] = []
        max_history_id = start_history_id

        try:
            response = service.users().history().list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
                labelId="INBOX",
            ).execute()
        except Exception as e:
            # historyId may have expired (> ~30 days old); log and return empty.
            logger.error(
                "history.list failed for %s/%s: %s",
                ctx.gestoria_id, ctx.cliente_id, e,
            )
            return []

        for record in response.get("history", []):
            record_id = record.get("id", "0")
            if int(record_id) > int(max_history_id):
                max_history_id = record_id
            for added in record.get("messagesAdded", []):
                msg = added.get("message", {})
                if msg.get("id"):
                    messages.append(msg)

        # Handle pagination
        while "nextPageToken" in response:
            response = service.users().history().list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
                labelId="INBOX",
                pageToken=response["nextPageToken"],
            ).execute()
            for record in response.get("history", []):
                record_id = record.get("id", "0")
                if int(record_id) > int(max_history_id):
                    max_history_id = record_id
                for added in record.get("messagesAdded", []):
                    msg = added.get("message", {})
                    if msg.get("id"):
                        messages.append(msg)

        # Atomically advance historyId so concurrent webhook calls skip these messages.
        if int(max_history_id) > int(start_history_id):
            transaction.update(doc_ref, {
                "gmail_watch_state.history_id": max_history_id,
                "gmail_watch_state.updated_at": datetime.now(timezone.utc),
            })

        return messages

    transaction = db.transaction()
    return _atomic_history_fetch(transaction)


# ---------------------------------------------------------------------------
# Watch state queries
# ---------------------------------------------------------------------------

def get_watch_state(ctx: TenantContext) -> Optional[dict]:
    """Return the ``gmail_watch_state`` sub-document for *ctx*, or ``None``."""
    db = _get_db()
    doc = db.document(_watch_doc_path(ctx)).get()
    if not doc.exists:
        return None
    return doc.to_dict().get("gmail_watch_state")


def is_watch_expiring_soon(ctx: TenantContext, threshold_ms: int = 86_400_000) -> bool:
    """Return ``True`` if the watch expires within *threshold_ms* (default 24 h)."""
    state = get_watch_state(ctx)
    if not state or state.get("status") != "active":
        return True
    expiration = state.get("expiration", 0)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return (expiration - now_ms) < threshold_ms
