"""Webhook endpoint for Gmail → Pub/Sub push notifications.

Google Pub/Sub sends a POST with a base64-encoded JSON payload containing
``emailAddress`` and ``historyId``.  This endpoint:

1. Verifies the Pub/Sub JWT (audience = Cloud Run URL).
2. Decodes the notification.
3. Looks up the tenant by email address in Firestore.
4. Uses ``gmail_watch.get_new_messages()`` (atomic historyId) to fetch new messages.
5. Processes each message through the existing pipeline.
6. Optionally renews the watch if it's expiring within 24 h.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from google.auth.transport import requests as google_requests
from google.cloud import firestore
from google.oauth2 import id_token

from app.collectors.gmail_reader import get_attachments, is_invoice_candidate
from app.collectors.gmail_service import get_gmail_service
from app.collectors.gmail_watch import (
    get_new_messages,
    is_watch_expiring_soon,
    renew_watch,
)
from app.services.document_processor import process_document
from app.services.errors import PipelineError
from app.api.deps import get_db as _get_db
from app.services.firestore_client import (
    is_message_processed,
    mark_message_processed,
)
from app.services.tenant import TenantContext, extract_tenant_from_doc

logger = logging.getLogger(__name__)

router = APIRouter()

# The Cloud Run service URL — used as the expected JWT audience.
_CLOUD_RUN_URL = os.environ.get("CLOUD_RUN_URL", "")

# Pub/Sub topic used to renew watches opportunistically.
_PUBSUB_TOPIC = os.environ.get(
    "GMAIL_PUBSUB_TOPIC",
    "",
)


# ---------------------------------------------------------------------------
# JWT verification
# ---------------------------------------------------------------------------

def _verify_pubsub_token(auth_header: Optional[str]) -> dict:
    """Verify the Pub/Sub push JWT and return its claims.

    Raises ``HTTPException(403)`` on failure.
    """
    if not _CLOUD_RUN_URL:
        # In local dev / testing we skip verification.
        logger.warning("CLOUD_RUN_URL not set — skipping JWT verification")
        return {}

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="Missing or malformed Authorization header")

    token = auth_header[len("Bearer "):]

    # Pub/Sub sets the OIDC audience to the full push endpoint URL.
    # Try both the full path and the base URL to be safe.
    audiences = [
        _CLOUD_RUN_URL.rstrip("/") + "/webhook/gmail",
        _CLOUD_RUN_URL.rstrip("/"),
    ]
    last_exc: Exception | None = None
    for audience in audiences:
        try:
            claims = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                audience=audience,
            )
            return claims
        except Exception as e:
            last_exc = e

    logger.warning("JWT verification failed: %s", last_exc)
    raise HTTPException(status_code=403, detail="Invalid Pub/Sub token") from last_exc


# ---------------------------------------------------------------------------
# Tenant lookup by email
# ---------------------------------------------------------------------------

def _find_tenant_by_email(email: str) -> Optional[TenantContext]:
    """Search Firestore for a client whose gmail_email matches *email*.

    Queries ``gestorias/*/cuentas/*`` using a collection-group query.
    Returns ``None`` if no match.
    """
    db = _get_db()
    docs = (
        db.collection_group("cuentas")
        .where(filter=firestore.FieldFilter("gmail_email", "==", email))
        .limit(1)
        .get()
    )
    for doc in docs:
        ctx = extract_tenant_from_doc(doc)
        if ctx:
            return ctx
    return None


# ---------------------------------------------------------------------------
# Message processing (reuses poller logic)
# ---------------------------------------------------------------------------

def _process_single_message(
    service,
    msg_id: str,
    ctx: TenantContext,
) -> dict:
    """Fetch metadata + attachments for a single message and process them.

    Returns a summary dict.
    """
    summary: dict = {
        "msg_id": msg_id,
        "procesados": 0,
        "duplicados": 0,
        "errores": 0,
        "descartados": False,
    }

    if is_message_processed(msg_id, include_errors=False, ctx=ctx):
        return summary

    # Fetch message metadata for heuristic check
    try:
        detail = service.users().messages().get(
            userId="me",
            id=msg_id,
            format="metadata",
            metadataHeaders=["Subject", "From"],
        ).execute()
    except Exception as e:
        logger.error("Failed to fetch message %s: %s", msg_id, e)
        return summary

    headers = {
        h["name"]: h["value"]
        for h in detail.get("payload", {}).get("headers", [])
    }
    subject = headers.get("Subject", "")
    from_addr = headers.get("From", "")
    snippet = detail.get("snippet", "")
    thread_id = detail.get("threadId", "")

    if not is_invoice_candidate(subject, snippet):
        mark_message_processed(
            msg_id, "discarded", subject,
            reason="heuristica", thread_id=thread_id, from_addr=from_addr,
            ctx=ctx,
        )
        summary["descartados"] = True
        return summary

    attachments = get_attachments(service, msg_id)
    if not attachments:
        mark_message_processed(
            msg_id, "discarded", subject,
            reason="sin_adjuntos", thread_id=thread_id, from_addr=from_addr,
            ctx=ctx,
        )
        summary["descartados"] = True
        return summary

    categories: list[str] = []
    msg_hashes: list[str] = []
    error_reason: str | None = None

    for att in attachments:
        filename = att["filename"]
        try:
            result = process_document(
                file_bytes=att["data"],
                mime_type=att["mime_type"],
                filename=filename,
                file_size=len(att["data"]),
                extra={
                    "source": "gmail_watch",
                    "gmail_message_id": msg_id,
                    "gmail_subject": subject,
                    "gmail_from": from_addr,
                },
                ctx=ctx,
            )
            if result.status == "duplicate":
                categories.append("duplicados")
                summary["duplicados"] += 1
                if result.doc_hash:
                    msg_hashes.append(result.doc_hash)
            else:
                categories.append("procesados")
                summary["procesados"] += 1
                if result.doc_hash:
                    msg_hashes.append(result.doc_hash)
        except PipelineError as e:
            orig = getattr(e, '_original', None)
            if orig:
                logger.error(
                    "Pipeline error on %s: %s | original: %s: %s",
                    filename, e, type(orig).__name__, orig,
                )
            else:
                logger.error("Pipeline error on %s: %s", filename, e)
            categories.append("errores")
            summary["errores"] += 1
            if error_reason is None or e.code != "UNKNOWN":
                error_reason = e.code
        except Exception as e:
            pe = PipelineError.from_exception(e)
            logger.exception("Unexpected error processing %s: %s", filename, e)
            categories.append("errores")
            summary["errores"] += 1
            if error_reason is None or pe.code != "UNKNOWN":
                error_reason = pe.code

    # Derive final status
    has_processed = "procesados" in categories
    has_error = "errores" in categories
    if has_error:
        final_status = "error"
    elif has_processed:
        final_status = "processed"
    else:
        final_status = "duplicate"

    mark_message_processed(
        msg_id, final_status, subject,
        reason=error_reason if final_status == "error" else None,
        document_hashes=msg_hashes,
        thread_id=thread_id,
        from_addr=from_addr,
        ctx=ctx,
    )

    return summary


# ---------------------------------------------------------------------------
# Background processing (runs after 200 is returned to Pub/Sub)
# ---------------------------------------------------------------------------

def _process_notification(email_address: str) -> None:
    """Heavy lifting: find tenant, fetch messages, run Gemini pipeline.

    Called via ``asyncio.to_thread()`` from the async webhook handler so
    concurrent notifications for different cuentas run in parallel without
    blocking the event loop.
    """
    ctx = _find_tenant_by_email(email_address)
    if ctx is None:
        logger.warning("No tenant found for email %s — ignoring", email_address)
        return

    service = get_gmail_service(ctx=ctx)

    new_messages = get_new_messages(service, ctx)
    logger.info(
        "Found %d new message(s) for %s/%s",
        len(new_messages), ctx.gestoria_id, ctx.cliente_id,
    )

    total = {"procesados": 0, "duplicados": 0, "errores": 0, "descartados": 0}
    for msg in new_messages:
        msg_id = msg.get("id")
        if not msg_id:
            continue
        result = _process_single_message(service, msg_id, ctx)
        total["procesados"] += result["procesados"]
        total["duplicados"] += result["duplicados"]
        total["errores"] += result["errores"]
        if result["descartados"]:
            total["descartados"] += 1

    logger.info("Processing complete for %s: %s", email_address, total)

    if _PUBSUB_TOPIC and is_watch_expiring_soon(ctx):
        try:
            renew_watch(service, _PUBSUB_TOPIC, ctx)
            logger.info("Watch renewed for %s/%s", ctx.gestoria_id, ctx.cliente_id)
        except Exception as e:
            logger.error("Failed to renew watch for %s/%s: %s", ctx.gestoria_id, ctx.cliente_id, e)


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

@router.post("/webhook/gmail")
async def gmail_webhook(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Receive a Pub/Sub push notification from Gmail Watch API."""

    # 1. Verify JWT
    _verify_pubsub_token(authorization)

    # 2. Decode Pub/Sub envelope
    body = await request.json()
    message = body.get("message", {})
    data_b64 = message.get("data", "")
    if not data_b64:
        raise HTTPException(status_code=400, detail="No data in Pub/Sub message")

    try:
        payload = json.loads(base64.b64decode(data_b64))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Pub/Sub payload")

    email_address = payload.get("emailAddress", "")
    if not email_address:
        raise HTTPException(status_code=400, detail="Missing emailAddress in notification")

    logger.info("Gmail push notification for %s — processing", email_address)

    # 3. Offload blocking I/O (Gmail API, Firestore, Gemini) to a thread
    #    so concurrent webhook calls don't block each other on the event loop.
    #    We still return 200 even on processing errors to prevent Pub/Sub
    #    infinite retries — idempotency is handled by is_message_processed().
    try:
        await asyncio.to_thread(_process_notification, email_address)
    except Exception as e:
        logger.exception("Error processing notification for %s: %s", email_address, e)

    return {"status": "accepted"}
