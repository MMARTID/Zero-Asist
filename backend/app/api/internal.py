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

from app.api.deps import get_db as _get_db
from app.collectors.gmail_service import get_gmail_service
from app.collectors.gmail_watch import renew_watch
from app.ingestion.normalizer import normalize_document, dates_to_firestore
from app.services.entity_resolver import resolve_and_link
from app.services.tenant import TenantContext, extract_tenant_from_doc

logger = logging.getLogger(__name__)

router = APIRouter()

_PUBSUB_TOPIC = os.environ.get("GMAIL_PUBSUB_TOPIC", "")


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

    # Collection-group query: all cuentas documents with active watches.
    docs = (
        db.collection_group("cuentas")
        .where(filter=firestore.FieldFilter("gmail_watch_status", "==", "active"))
        .get()
    )

    results = {"renewed": 0, "failed": 0, "errors": []}

    for doc in docs:
        ctx = extract_tenant_from_doc(doc)
        if not ctx:
            continue

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
        db.collection_group("cuentas")
        .where(filter=firestore.FieldFilter("gmail_watch_status", "==", "active"))
        .get()
    )

    results = {"retried": 0, "succeeded": 0, "failed_again": 0, "errors": []}

    for doc in clients:
        ctx = extract_tenant_from_doc(doc)
        if not ctx:
            continue

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


@router.post("/internal/reprocess-contacts")
def reprocess_contacts_endpoint(
    x_cloudscheduler: Optional[str] = Header(None, alias="X-CloudScheduler"),
):
    """Re-run entity resolution on all existing documents.

    Useful after code changes to the entity extractor — walks every document
    in every cuenta and calls ``resolve_and_link`` to create any missing
    contacts.  Existing contacts are matched by NIF/name so no duplicates
    are created.
    """
    db = _get_db()

    clients = (
        db.collection_group("cuentas")
        .where(filter=firestore.FieldFilter("gmail_watch_status", "==", "active"))
        .get()
    )

    results = {"documents": 0, "contacts_created": 0, "contacts_updated": 0, "errors": []}

    for client_doc in clients:
        ctx = extract_tenant_from_doc(client_doc)
        if not ctx:
            continue

        for doc in db.collection(ctx.docs_collection).stream():
            data = doc.to_dict()
            norm = data.get("normalized_data", {})
            doc_type = data.get("document_type")
            if not doc_type or not norm:
                continue

            results["documents"] += 1
            try:
                refs = resolve_and_link(db, norm, doc_type, doc_hash=doc.id, ctx=ctx)
                if refs:
                    # Update the document with new contact_refs
                    doc.reference.update({
                        "contact_refs": [ref.model_dump() for ref in refs],
                    })
                    for ref in refs:
                        results["contacts_created"] += 1
            except Exception as e:
                results["errors"].append({
                    "doc_id": doc.id,
                    "error": str(e)[:200],
                })
                logger.error("Error reprocessing contacts for doc %s: %s", doc.id, e)

    logger.info(
        "Reprocess contacts complete: %d docs, %d contacts created/updated",
        results["documents"], results["contacts_created"],
    )
    return results


@router.post("/internal/reprocess-normalizer")
def reprocess_normalizer_endpoint(
    x_cloudscheduler: Optional[str] = Header(None, alias="X-CloudScheduler"),
):
    """Re-run normalisation on all documents across all active cuentas.

    Reads each document's ``extracted_data`` and ``document_type``, runs the
    current normalizer pipeline (without calling Gemini), and overwrites
    ``normalized_data`` in Firestore.  Useful after fixing normalizer bugs
    (e.g. adding new date formats) so that already-processed documents pick
    up the corrected logic.
    """
    db = _get_db()

    clients = (
        db.collection_group("cuentas")
        .where(filter=firestore.FieldFilter("gmail_watch_status", "==", "active"))
        .get()
    )

    results = {"updated": 0, "skipped": 0, "errors": []}

    for client_doc in clients:
        ctx = extract_tenant_from_doc(client_doc)
        if not ctx:
            continue

        # Load cuenta context for normalizer enrichment
        cuenta_data = client_doc.to_dict()
        from app.ingestion.context import CuentaContext
        from app.services.tax_id import normalize_tax_id_raw
        raw_tax_id = cuenta_data.get("tax_id")
        cuenta_context = CuentaContext(
            nombre=cuenta_data.get("nombre"),
            tax_id=normalize_tax_id_raw(raw_tax_id) if raw_tax_id else None,
            tax_country=cuenta_data.get("tax_country"),
            tax_type=cuenta_data.get("tax_type"),
        )

        for doc in db.collection(ctx.docs_collection).stream():
            data = doc.to_dict()
            extracted = data.get("extracted_data")
            doc_type = data.get("document_type")
            if not doc_type or not extracted:
                results["skipped"] += 1
                continue

            try:
                new_norm = normalize_document(extracted, doc_type, cuenta_context=cuenta_context)
                new_norm_dict = dates_to_firestore(dict(new_norm))
                doc.reference.update({"normalized_data": new_norm_dict})
                results["updated"] += 1
            except Exception as e:
                results["errors"].append({
                    "doc_id": doc.id,
                    "error": str(e)[:200],
                })
                logger.error("Error re-normalizing doc %s: %s", doc.id, e)

    logger.info(
        "Reprocess normalizer complete: %d updated, %d skipped, %d errors",
        results["updated"], results["skipped"], len(results["errors"]),
    )
    return results


@router.post("/internal/reprocess-document/{gestoria_id}/{cuenta_id}/{doc_id}")
def reprocess_single_document(
    gestoria_id: str,
    cuenta_id: str,
    doc_id: str,
):
    """Re-normalise a single document by its path.

    Reads ``extracted_data`` from Firestore, re-runs the normalizer, and
    updates ``normalized_data``.  Does NOT call Gemini — zero cost.
    """
    db = _get_db()

    doc_path = f"gestorias/{gestoria_id}/cuentas/{cuenta_id}/documentos/{doc_id}"
    snap = db.document(doc_path).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Document not found")

    data = snap.to_dict()
    extracted = data.get("extracted_data")
    doc_type = data.get("document_type")
    if not extracted or not doc_type:
        raise HTTPException(status_code=400, detail="Document has no extracted_data or document_type")

    # Load cuenta context
    cuenta_snap = db.document(f"gestorias/{gestoria_id}/cuentas/{cuenta_id}").get()
    cuenta_context = None
    if cuenta_snap.exists:
        cd = cuenta_snap.to_dict()
        from app.ingestion.context import CuentaContext
        from app.services.tax_id import normalize_tax_id_raw
        raw_tax_id = cd.get("tax_id")
        cuenta_context = CuentaContext(
            nombre=cd.get("nombre"),
            tax_id=normalize_tax_id_raw(raw_tax_id) if raw_tax_id else None,
            tax_country=cd.get("tax_country"),
            tax_type=cd.get("tax_type"),
        )

    old_norm = data.get("normalized_data", {})
    new_norm = normalize_document(extracted, doc_type, cuenta_context=cuenta_context)
    new_norm_dict = dates_to_firestore(dict(new_norm))

    snap.reference.update({"normalized_data": new_norm_dict})

    # Build a diff of changed fields
    changes = {}
    all_keys = set(old_norm) | set(new_norm_dict)
    for k in sorted(all_keys):
        old_v = old_norm.get(k)
        new_v = new_norm_dict.get(k)
        if old_v != new_v:
            changes[k] = {"old": repr(old_v), "new": repr(new_v)}

    logger.info("Re-normalized doc %s: %d field(s) changed", doc_id, len(changes))

    return {
        "doc_id": doc_id,
        "document_type": doc_type,
        "changes": changes,
    }