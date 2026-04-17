"""Dashboard endpoints — list clients, documents, and stats for a gestoría.

All endpoints require Firebase Auth (``Depends(get_current_gestoria)``).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from google.cloud import firestore
from pydantic import BaseModel, ConfigDict

from app.api.auth import get_current_gestoria
from app.api.deps import get_db as _get_db
from app.services import storage_client as _gcs
from app.services.tenant import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# Gestoría profile
# ---------------------------------------------------------------------------


class UpdateGestoriaRequest(BaseModel):
    nombre: str
    phone_number: str


class UpdateContactRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nombre_fiscal: Optional[str] = None
    nombre_comercial: Optional[str] = None
    tax_id: Optional[str] = None
    tax_country: Optional[str] = None
    tax_type: Optional[str] = None
    roles: Optional[list] = None
    direccion_fiscal: Optional[str] = None
    codigo_postal: Optional[str] = None
    email_contacto: Optional[str] = None
    telefono: Optional[str] = None
    iban: Optional[str] = None
    forma_pago_habitual: Optional[str] = None


@router.get("/gestoria")
def get_gestoria_profile(
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Return the gestoría profile for the authenticated user."""
    db = _get_db()
    doc = db.document(f"gestorias/{gestoria_id}").get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Gestoría not found")

    data = doc.to_dict()
    return {
        "gestoria_id": gestoria_id,
        "nombre": data.get("nombre", ""),
        "phone_number": data.get("phone_number", ""),
        "onboarding_complete": data.get("onboarding_complete", False),
    }


@router.patch("/gestoria")
def update_gestoria_profile(
    body: UpdateGestoriaRequest,
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Update gestoría name and WhatsApp number; marks onboarding complete."""
    db = _get_db()
    db.document(f"gestorias/{gestoria_id}").set(
        {
            "nombre": body.nombre,
            "phone_number": body.phone_number,
            "onboarding_complete": True,
        },
        merge=True,
    )
    return {
        "status": "updated",
        "gestoria_id": gestoria_id,
        "nombre": body.nombre,
        "phone_number": body.phone_number,
        "onboarding_complete": True,
    }


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

@router.get("/cuentas")
def list_clients(
    gestoria_id: str = Depends(get_current_gestoria),
):
    """List all clients for the authenticated gestoría."""
    db = _get_db()
    docs = db.collection(f"gestorias/{gestoria_id}/cuentas").get()

    clients = []
    for doc in docs:
        data = doc.to_dict()
        clients.append({
            "cuenta_id": doc.id,
            "nombre": data.get("nombre", ""),
            "phone_number": data.get("phone_number", ""),
            "tax_id": data.get("tax_id"),
            "tax_country": data.get("tax_country"),
            "tax_type": data.get("tax_type"),
            "gmail_email": data.get("gmail_email"),
            "gmail_watch_status": data.get("gmail_watch_status"),
        })

    return {"gestoria_id": gestoria_id, "cuentas": clients}


@router.get("/cuentas/{cuenta_id}")
def get_client(
    cuenta_id: str,
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Get details for a single client."""
    db = _get_db()
    doc = db.document(f"gestorias/{gestoria_id}/cuentas/{cuenta_id}").get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Client not found")

    data = doc.to_dict()
    return {
        "cuenta_id": doc.id,
        "gestoria_id": gestoria_id,
        "nombre": data.get("nombre", ""),
        "phone_number": data.get("phone_number", ""),
        "tax_id": data.get("tax_id"),
        "tax_country": data.get("tax_country"),
        "tax_type": data.get("tax_type"),
        "gmail_email": data.get("gmail_email"),
        "gmail_watch_status": data.get("gmail_watch_status"),
        "gmail_watch_state": data.get("gmail_watch_state"),
        "min_income": data.get("min_income"),
        "max_income": data.get("max_income"),
    }


class UpdateCuentaRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nombre: Optional[str] = None
    phone_number: Optional[str] = None
    tax_id: Optional[str] = None
    min_income: Optional[float] = None
    max_income: Optional[float] = None


@router.patch("/cuentas/{cuenta_id}")
def update_cuenta(
    cuenta_id: str,
    body: UpdateCuentaRequest,
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Update editable fields of a cuenta."""
    db = _get_db()
    doc_ref = db.document(f"gestorias/{gestoria_id}/cuentas/{cuenta_id}")
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"ok": True}
    doc_ref.update(updates)
    return {"ok": True}


@router.delete("/cuentas/{cuenta_id}")
def delete_cuenta(
    cuenta_id: str,
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Delete a cuenta and all its sub-collections (documentos, contactos)."""
    db = _get_db()
    doc_ref = db.document(f"gestorias/{gestoria_id}/cuentas/{cuenta_id}")
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")

    ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=cuenta_id)
    for sub in (ctx.docs_collection, ctx.contacts_collection):
        for child in db.collection(sub).get():
            db.document(f"{sub}/{child.id}").delete()
    doc_ref.delete()
    return {"ok": True, "deleted": cuenta_id}


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@router.get("/cuentas/{cuenta_id}/documentos")
def list_documents(
    cuenta_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    gestoria_id: str = Depends(get_current_gestoria),
):
    """List documents for a client, most recent first."""
    ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=cuenta_id)
    db = _get_db()

    docs = (
        db.collection(ctx.docs_collection)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .get()
    )

    documents = []
    for doc in docs:
        data = doc.to_dict()
        documents.append({
            "doc_hash": doc.id,
            "document_type": data.get("document_type"),
            "filename": data.get("file_name"),
            "created_at": data.get("created_at"),
            "normalized": data.get("normalized_data"),
            "has_original": "storage_path" in data,
        })

    return {
        "gestoria_id": gestoria_id,
        "cuenta_id": cuenta_id,
        "documentos": documents,
        "count": len(documents),
    }


@router.get("/cuentas/{cuenta_id}/documentos/{doc_hash}/original")
def download_original_document(
    cuenta_id: str,
    doc_hash: str,
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Stream the original file bytes for a document.

    Returns 404 when the document does not exist or was processed before
    original storage was enabled.
    """
    ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=cuenta_id)
    db = _get_db()

    doc = db.collection(ctx.docs_collection).document(doc_hash).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    data = doc.to_dict()
    storage_path = data.get("storage_path")
    if not storage_path:
        raise HTTPException(
            status_code=404,
            detail="Original no disponible — el documento fue procesado antes de activar el almacenamiento",
        )

    content = _gcs.download_document(storage_path)
    if content is None:
        raise HTTPException(status_code=503, detail="Error al recuperar el archivo desde el almacenamiento")

    mime_type = data.get("mime_type", "application/octet-stream")
    filename = data.get("file_name", "documento")
    return Response(
        content=content,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=300",
        },
    )


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats")
def get_stats(
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Summary stats for the authenticated gestoría.

    Performs N+1 reads (clients + docs per client).  Acceptable at low scale;
    for larger deployments, denormalise counters on the gestoría document.
    """
    db = _get_db()
    client_snapshots = list(
        db.collection(f"gestorias/{gestoria_id}/cuentas").get(),
    )

    total_clients = len(client_snapshots)
    active_watches = 0
    connected_gmail = 0
    total_documents = 0

    for snap in client_snapshots:
        data = snap.to_dict()
        if data.get("gmail_watch_status") == "active":
            active_watches += 1
        if data.get("gmail_email"):
            connected_gmail += 1

        ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=snap.id)
        total_documents += len(list(db.collection(ctx.docs_collection).get()))

    return {
        "gestoria_id": gestoria_id,
        "total_clients": total_clients,
        "connected_gmail": connected_gmail,
        "active_watches": active_watches,
        "total_documents": total_documents,
    }


# ---------------------------------------------------------------------------
# Global documents inbox (recent docs across all cuentas)
# ---------------------------------------------------------------------------

@router.get("/documentos")
def list_all_documents(
    limit: int = Query(default=50, ge=1, le=200),
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Return the most recent documents across ALL cuentas for this gestoría.

    Collects up to ``limit`` docs per client, merges, sorts by created_at
    descending, and returns the top ``limit`` results.
    """
    db = _get_db()
    client_docs = db.collection(f"gestorias/{gestoria_id}/cuentas").get()

    all_docs: list[dict] = []

    for client_doc in client_docs:
        client_data = client_doc.to_dict()
        ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=client_doc.id)

        recent = (
            db.collection(ctx.docs_collection)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .get()
        )

        for doc in recent:
            data = doc.to_dict()
            all_docs.append({
                "doc_hash": doc.id,
                "cuenta_id": client_doc.id,
                "cuenta_nombre": client_data.get("nombre", client_doc.id),
                "document_type": data.get("document_type"),
                "filename": data.get("file_name"),
                "created_at": data.get("created_at"),
                "normalized": data.get("normalized_data"),
                "has_original": "storage_path" in data,
            })

    all_docs.sort(key=lambda d: d["created_at"] or "", reverse=True)

    return {
        "gestoria_id": gestoria_id,
        "documentos": all_docs[:limit],
        "total": len(all_docs),
    }


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

@router.get("/cuentas/{cuenta_id}/contactos")
def list_contacts(
    cuenta_id: str,
    rol: Optional[str] = Query(default=None),
    gestoria_id: str = Depends(get_current_gestoria),
):
    """List contacts for a client, optionally filtered by role."""
    ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=cuenta_id)
    db = _get_db()

    col_ref = db.collection(ctx.contacts_collection)
    if rol:
        query = col_ref.where("roles", "array_contains", rol)
    else:
        query = col_ref
    docs = query.get()

    contactos = []
    for doc in docs:
        data = doc.to_dict()
        contactos.append({
            "contacto_id": doc.id,
            "nombre_fiscal": data.get("nombre_fiscal", ""),
            "tax_id": data.get("tax_id") or data.get("nif"),
            "tax_country": data.get("tax_country"),
            "tax_type": data.get("tax_type"),
            "roles": data.get("roles", []),
            "confidence": data.get("confidence", 0),
            "source": data.get("source"),
            "total_documentos": data.get("total_documentos", 0),
            "ultima_interaccion": data.get("ultima_interaccion"),
        })

    return {
        "gestoria_id": gestoria_id,
        "cuenta_id": cuenta_id,
        "contactos": contactos,
        "count": len(contactos),
    }


@router.get("/cuentas/{cuenta_id}/contactos/{contacto_id}")
def get_contact(
    cuenta_id: str,
    contacto_id: str,
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Get full details for a single contact."""
    ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=cuenta_id)
    db = _get_db()

    doc = db.document(
        f"{ctx.contacts_collection}/{contacto_id}"
    ).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Contact not found")

    data = doc.to_dict()
    # Normalize legacy "nif" field to "tax_id" for consistent API response
    if "nif" in data and "tax_id" not in data:
        data["tax_id"] = data.pop("nif")
    elif "nif" in data:
        data.pop("nif")

    _CONTACT_FIELDS = (
        "tax_id", "tax_country", "tax_type",
        "nombre_fiscal", "nombre_comercial",
        "roles", "confidence", "source", "verified_at",
        "direccion_fiscal", "codigo_postal",
        "email_contacto", "telefono", "iban",
        "forma_pago_habitual",
        "total_documentos", "total_facturado", "total_recibido",
        "ultima_interaccion",
        "created_from_document", "created_at", "updated_at",
    )
    return {
        "contacto_id": doc.id,
        "gestoria_id": gestoria_id,
        "cuenta_id": cuenta_id,
        **{k: data.get(k) for k in _CONTACT_FIELDS},
    }


@router.patch("/cuentas/{cuenta_id}/contactos/{contacto_id}")
def update_contact(
    cuenta_id: str,
    contacto_id: str,
    body: UpdateContactRequest,
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Update contact fields (user verification, role correction, enrichment)."""
    ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=cuenta_id)
    db = _get_db()

    doc_ref = db.document(f"{ctx.contacts_collection}/{contacto_id}")
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Contact not found")

    updates = body.model_dump(exclude_none=True)

    # Mark as verified (even with no field changes — verification-only is valid)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    updates["source"] = "user_verified"
    updates["confidence"] = 1.0
    updates["verified_at"] = now
    updates["updated_at"] = now

    doc_ref.update(updates)

    return {"status": "updated", "contacto_id": contacto_id, "fields_updated": list(updates.keys())}


@router.get("/cuentas/{cuenta_id}/contactos/{contacto_id}/documentos")
def list_contact_documents(
    cuenta_id: str,
    contacto_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    gestoria_id: str = Depends(get_current_gestoria),
):
    """List documents linked to a specific contact."""
    ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=cuenta_id)
    db = _get_db()

    # Query documents that reference this contact
    docs = (
        db.collection(ctx.docs_collection)
        .where("contact_refs", "array_contains_any", [
            {"contacto_id": contacto_id, "rol_en_documento": "emisor"},
            {"contacto_id": contacto_id, "rol_en_documento": "receptor"},
            {"contacto_id": contacto_id, "rol_en_documento": "parte"},
        ])
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .get()
    )

    documents = []
    for doc in docs:
        data = doc.to_dict()
        documents.append({
            "doc_hash": doc.id,
            "document_type": data.get("document_type"),
            "filename": data.get("file_name"),
            "created_at": data.get("created_at"),
            "normalized": data.get("normalized_data"),
            "contact_refs": data.get("contact_refs", []),
        })

    return {
        "gestoria_id": gestoria_id,
        "cuenta_id": cuenta_id,
        "contacto_id": contacto_id,
        "documentos": documents,
        "count": len(documents),
    }


# ---------------------------------------------------------------------------
# Fiscal summary (quarterly aggregation)
# ---------------------------------------------------------------------------

_FISCAL_DOC_TYPES = ("invoice_received", "invoice_sent", "expense_ticket")

# IVA (peninsula), IGIC (Canarias), IPSI (Ceuta/Melilla) — equivalent indirect taxes
_INDIRECT_TAX_TYPES = {"iva", "igic", "ipsi"}

_QUARTER_RANGES = {
    "T1": (1, 3),
    "T2": (4, 6),
    "T3": (7, 9),
    "T4": (10, 12),
}


def _empty_bucket() -> dict:
    return {
        "iva_soportado": 0.0,
        "iva_repercutido": 0.0,
        "irpf_retenido": 0.0,
        "total_facturado": 0.0,
    }


def _quarter_for_month(month: int) -> str:
    for label, (start, end) in _QUARTER_RANGES.items():
        if start <= month <= end:
            return label
    return "T4"  # pragma: no cover


@router.get("/cuentas/{cuenta_id}/fiscal-summary")
def get_fiscal_summary(
    cuenta_id: str,
    year: int = Query(default=None, ge=2000, le=2100),
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Aggregate IVA soportado/repercutido, IRPF retenido and total invoiced by quarter."""
    if year is None:
        year = datetime.now(timezone.utc).year

    ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=cuenta_id)
    db = _get_db()

    docs = (
        db.collection(ctx.docs_collection)
        .where("document_type", "in", list(_FISCAL_DOC_TYPES))
        .get()
    )

    quarters = {q: _empty_bucket() for q in _QUARTER_RANGES}

    for doc in docs:
        data = doc.to_dict()
        norm = data.get("normalized_data") or {}
        doc_type = data.get("document_type")

        # Resolve issue_date — Firestore Timestamp or raw string
        raw_date = norm.get("issue_date")
        if raw_date is None:
            continue
        if hasattr(raw_date, "year"):
            # Already a datetime/date-like object
            dt = raw_date
        elif isinstance(raw_date, str):
            try:
                dt = datetime.fromisoformat(raw_date)
            except (ValueError, TypeError):
                continue
        else:
            continue

        if dt.year != year:
            continue

        q = _quarter_for_month(dt.month)
        tax_lines = norm.get("tax_lines") or []

        if doc_type in ("invoice_received", "expense_ticket"):
            for line in tax_lines:
                if not isinstance(line, dict):
                    continue
                tt = line.get("tax_type", "")
                amt = line.get("amount") or 0
                if tt in _INDIRECT_TAX_TYPES:
                    quarters[q]["iva_soportado"] += float(amt)
                elif tt == "irpf" and doc_type == "invoice_received":
                    quarters[q]["irpf_retenido"] += abs(float(amt))

        elif doc_type == "invoice_sent":
            quarters[q]["total_facturado"] += float(norm.get("total_amount") or 0)
            for line in tax_lines:
                if not isinstance(line, dict):
                    continue
                tt = line.get("tax_type", "")
                amt = line.get("amount") or 0
                if tt in _INDIRECT_TAX_TYPES:
                    quarters[q]["iva_repercutido"] += float(amt)
                elif tt == "irpf":
                    quarters[q]["irpf_retenido"] += abs(float(amt))

    # Round all values to 2 decimals
    for q in quarters:
        for k in quarters[q]:
            quarters[q][k] = round(quarters[q][k], 2)

    annual = _empty_bucket()
    for q_data in quarters.values():
        for k in annual:
            annual[k] += q_data[k]
    for k in annual:
        annual[k] = round(annual[k], 2)

    return {
        "year": year,
        "quarters": quarters,
        "annual": annual,
    }


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

# Fields that must be present for a document to be considered complete.
# Each entry: (field_name, human-readable issue message in Spanish).
_ALERT_FIELDS: dict[str, list[tuple[str, str]]] = {
    "invoice_received": [
        ("issuer_nif",     "NIF del proveedor no encontrado"),
        ("invoice_number", "Número de factura no detectado"),
        ("total_amount",   "Importe total no detectado"),
        ("issue_date",     "Fecha de factura no detectada"),
    ],
    "invoice_sent": [
        ("client_nif",     "NIF del cliente no encontrado"),
        ("invoice_number", "Número de factura no detectado"),
        ("total_amount",   "Importe total no detectado"),
        ("issue_date",     "Fecha de factura no detectada"),
    ],
    "expense_ticket": [
        ("issuer_name",  "Nombre del establecimiento no encontrado"),
        ("total_amount", "Importe total no detectado"),
    ],
    "payment_receipt": [
        ("amount",       "Importe no detectado"),
        ("payment_date", "Fecha de pago no detectada"),
    ],
    "bank_document": [
        ("bank_name", "Nombre del banco no detectado"),
        ("iban",      "IBAN no detectado"),
    ],
    "contract": [
        ("contract_date", "Fecha del contrato no detectada"),
        ("parties",       "Partes firmantes no detectadas"),
    ],
    "administrative_notice": [
        ("issuer_name", "Entidad emisora no detectada"),
        ("issue_date",  "Fecha de notificación no detectada"),
    ],
}


@router.get("/alerts")
def get_alerts(
    limit: int = Query(default=20, ge=1, le=100),
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Return recent documents with missing required fields across all cuentas.

    Scans the 50 most-recent documents per client and surfaces those that are
    missing critical fields for their document type.  Results are sorted by
    ``created_at`` descending (most recent first).
    """
    db = _get_db()

    client_docs = db.collection(f"gestorias/{gestoria_id}/cuentas").get()

    alerts = []

    for client_doc in client_docs:
        client_data = client_doc.to_dict()
        ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=client_doc.id)

        recent_docs = (
            db.collection(ctx.docs_collection)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(50)
            .get()
        )

        for doc in recent_docs:
            data = doc.to_dict()
            doc_type = data.get("document_type")
            if not doc_type or doc_type not in _ALERT_FIELDS:
                continue

            norm = data.get("normalized_data") or {}
            issues = [
                {"field": field, "message": msg}
                for field, msg in _ALERT_FIELDS[doc_type]
                if not norm.get(field)
            ]

            if not issues:
                continue

            if data.get("alert_dismissed"):
                continue

            alerts.append({
                "cuenta_id":     client_doc.id,
                "cuenta_nombre": client_data.get("nombre", client_doc.id),
                "doc_hash":      doc.id,
                "document_type": doc_type,
                "filename":      data.get("file_name"),
                "created_at":    data.get("created_at"),
                "issues":        issues,
            })

    alerts.sort(key=lambda a: a["created_at"] or "", reverse=True)

    return {
        "alerts": alerts[:limit],
        "total":  len(alerts),
        "limit":  limit,
    }


class DismissAlertRequest(BaseModel):
    cuenta_id: str
    doc_hash: str


@router.post("/alerts/dismiss")
def dismiss_alert(
    body: DismissAlertRequest,
    gestoria_id: str = Depends(get_current_gestoria),
):
    """Mark a document's alert as dismissed by setting a flag on the document."""
    ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=body.cuenta_id)
    db = _get_db()
    doc_ref = db.collection(ctx.docs_collection).document(body.doc_hash)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    doc_ref.update({"alert_dismissed": True})
    return {"ok": True}
