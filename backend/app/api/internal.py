"""Internal endpoint for periodic watch renewal.

Called by Cloud Scheduler (e.g. every 6 days) to renew all active Gmail
watches before they expire (~7 days).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from google.cloud import firestore

from app.collectors.gmail_service import get_gmail_service
from app.collectors.gmail_watch import renew_watch
from app.services.tenant import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter()

_PUBSUB_TOPIC = os.environ.get("GMAIL_PUBSUB_TOPIC", "")

# Lazy Firestore client
_db: Optional[firestore.Client] = None


def _get_db() -> firestore.Client:
    global _db
    if _db is None:
        from app.services.firestore_client import db
        _db = db
    return _db


@router.post("/internal/renew-watches")
def renew_watches_endpoint(
    x_cloudscheduler: Optional[str] = Header(None, alias="X-CloudScheduler"),
):
    """Renew all active Gmail watches.

    Intended to be called by Cloud Scheduler.  Iterates all clients with
    ``gmail_watch_state.status == "active"`` and calls ``renew_watch()``.
    """
    if not _PUBSUB_TOPIC:
        raise HTTPException(
            status_code=500,
            detail="GMAIL_PUBSUB_TOPIC not configured",
        )

    db = _get_db()

    # Collection-group query: all clientes documents with active watches.
    docs = (
        db.collection_group("clientes")
        .where(filter=firestore.FieldFilter("gmail_watch_status", "==", "active"))
        .get()
    )

    results = {"renewed": 0, "failed": 0, "errors": []}

    for doc in docs:
        parts = doc.reference.path.split("/")
        if len(parts) < 4:
            continue
        ctx = TenantContext(gestoria_id=parts[1], cliente_id=parts[3])

        try:
            service = get_gmail_service(ctx=ctx)
            renew_watch(service, _PUBSUB_TOPIC, ctx)
            results["renewed"] += 1
            logger.info("Renewed watch for %s/%s", ctx.gestoria_id, ctx.cliente_id)
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "gestoria_id": ctx.gestoria_id,
                "cliente_id": ctx.cliente_id,
                "error": str(e),
            })
            logger.error(
                "Failed to renew watch for %s/%s: %s",
                ctx.gestoria_id, ctx.cliente_id, e,
            )

    logger.info(
        "Watch renewal complete: %d renewed, %d failed",
        results["renewed"], results["failed"],
    )
    return results

@router.post("/internal/retry-failed")
def retry_failed_endpoint(
    x_cloudscheduler: Optional[str] = Header(None, alias="X-CloudScheduler"),
):
    """Retry Gmail messages that failed processing (status='error').

    Much cheaper than a full poll — only queries Firestore for failed messages
    and re-processes those specific message IDs through the existing pipeline.
    Called by Cloud Scheduler every 30 minutes.
    """
    db = _get_db()

    # Find all clients with active watches
    clients = (
        db.collection_group("clientes")
        .where(filter=firestore.FieldFilter("gmail_watch_status", "==", "active"))
        .get()
    )

    results = {"retried": 0, "succeeded": 0, "failed_again": 0, "errors": []}

    for doc in clients:
        parts = doc.reference.path.split("/")
        if len(parts) < 4:
            continue
        ctx = TenantContext(gestoria_id=parts[1], cliente_id=parts[3])

        # Query this client's gmail_processed for failed messages
        failed_docs = (
            db.collection(ctx.gmail_collection)
            .where(filter=firestore.FieldFilter("status", "==", "error"))
            .get()
        )

        if not failed_docs:
            continue

        try:
            service = get_gmail_service(ctx=ctx)
        except Exception as e:
            logger.error(
                "Cannot get Gmail service for %s/%s: %s",
                ctx.gestoria_id, ctx.cliente_id, e,
            )
            continue

        for failed_doc in failed_docs:
            msg_id = failed_doc.id
            results["retried"] += 1

            try:
                from app.api.webhook import _process_single_message
                summary = _process_single_message(service, msg_id, ctx)

                if summary["procesados"] > 0:
                    results["succeeded"] += 1
                    logger.info("Retry succeeded for message %s", msg_id)
                elif summary["errores"] > 0:
                    results["failed_again"] += 1
                    logger.warning("Retry failed again for message %s", msg_id)
            except Exception as e:
                results["failed_again"] += 1
                results["errors"].append({
                    "msg_id": msg_id,
                    "error": str(e)[:200],
                })
                logger.error("Retry error for message %s: %s", msg_id, e)

    logger.info(
        "Retry complete: %d retried, %d succeeded, %d failed again",
        results["retried"], results["succeeded"], results["failed_again"],
    )
    return results