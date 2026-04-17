"""Entity resolution service — extract, match, and manage contacts from documents.

This module bridges the gap between raw document extraction (where entity
names and NIFs are buried inside ``normalized_data``) and the Contact model.

The cuenta's own ``tax_id`` (set at onboarding) is the anchor: the entity
whose tax ID matches the cuenta is "us" and is **skipped** — we only create
contacts for "the other party".  The business role is inferred from the
document type:

* ``invoice_received`` → the *other* entity is a **proveedor**
* ``invoice_sent``     → the *other* entity is a **cliente**
* ``expense_ticket``   → always a **proveedor** (no cuenta matching)
* ``contract``         → all named parties get a default role

Flow (called after normalization, before save):
    1. Extract entity candidates from the normalized document.
    2. Compare each candidate's tax ID against the cuenta's own tax ID.
    3. Skip candidates that match the cuenta ("us").
    4. Assign role based on document type.
    5. For each remaining candidate, find or create a contact.
    6. Return ``ContactRef`` list to be stored in the document record.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.cloud.firestore import Client as FirestoreClient

from app.ingestion.helpers import _normalize_company_name, _normalize_tax_id
from app.models.contact import ContactRef, ContactRole, ContactSource
from app.services.tax_id import TaxId, classify_tax_id, normalize_tax_id_raw, tax_ids_match
from app.services.tenant import TenantContext, resolve_contacts_collection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entity candidate — intermediate representation
# ---------------------------------------------------------------------------

class EntityCandidate:
    """An entity extracted from a document, before matching to a Contact.

    ``role`` is initially ``None`` when extracted from invoices — it gets
    assigned later in ``_assign_roles`` based on cuenta tax_id comparison.
    For non-invoice types (expense_ticket, contract) the role is set during
    extraction.

    ``amount`` carries the document's total_amount for accumulating
    total_facturado / total_recibido on the contact.

    ``extra`` carries additional fields from the document that can be
    propagated to the contact (e.g. payment_method → forma_pago_habitual).
    """

    __slots__ = ("name", "nif", "role", "document_role", "confidence", "amount", "extra")

    def __init__(
        self,
        name: str,
        nif: Optional[str],
        role: Optional[ContactRole],
        document_role: str,
        confidence: float = 0.5,
        amount: Optional[float] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.nif = nif
        self.role = role
        self.document_role = document_role  # "emisor", "receptor", "parte"
        self.confidence = confidence
        self.amount = amount
        self.extra = extra or {}


# ---------------------------------------------------------------------------
# Cuenta tax_id helper
# ---------------------------------------------------------------------------

# Maps extra fields from EntityCandidate to contact field names.
_EXTRA_FIELD_MAP: dict[str, str] = {
    "payment_method": "forma_pago_habitual",
    "address": "direccion_fiscal",
    "phone": "telefono",
    "iban": "iban",
}

def _load_cuenta_tax_id(
    db: FirestoreClient,
    ctx: Optional[TenantContext],
) -> Optional[str]:
    """Load the cuenta's normalized tax_id from Firestore. Returns None when unavailable."""
    if ctx is None:
        logger.debug("_load_cuenta_tax_id: ctx is None — cannot load cuenta tax_id")
        return None
    path = f"gestorias/{ctx.gestoria_id}/cuentas/{ctx.cliente_id}"
    doc = db.document(path).get()
    if not doc.exists:
        logger.warning("_load_cuenta_tax_id: document %s does not exist", path)
        return None
    raw = doc.to_dict().get("tax_id")
    if not raw:
        logger.warning("_load_cuenta_tax_id: tax_id field is empty in %s", path)
        return None
    result = normalize_tax_id_raw(raw)
    logger.debug("_load_cuenta_tax_id: loaded cuenta tax_id from %s", path)
    return result


def _is_cuenta_entity(candidate_nif: Optional[str], cuenta_tax_id: Optional[str]) -> bool:
    """Return True if the candidate's NIF matches the cuenta's own tax_id.

    Uses ``tax_ids_match`` which handles country-prefix differences
    (e.g. ``"ESB12345678"`` vs ``"B12345678"``), plus a suffix fallback
    for junk prefixes (e.g. ``"NIFQ24615910"`` contains ``"Q24615910"``).
    """
    if not candidate_nif or not cuenta_tax_id:
        return False
    return tax_ids_match(candidate_nif, cuenta_tax_id)


# ---------------------------------------------------------------------------
# 1. Extract entity candidates from normalized data
# ---------------------------------------------------------------------------

_EXTRACTORS: dict[str, Any] = {}


def _register_extractor(doc_type: str):
    def decorator(fn):
        _EXTRACTORS[doc_type] = fn
        return fn
    return decorator


@_register_extractor("invoice_received")
def _extract_invoice_received(data: Dict[str, Any]) -> List[EntityCandidate]:
    """Extract issuer + client from a received invoice.

    Roles are **not assigned** here — they will be set by ``_assign_roles``
    after comparing against the cuenta's tax_id.
    """
    candidates: List[EntityCandidate] = []
    total = data.get("total_amount")
    extra = {}
    if data.get("payment_method"):
        extra["payment_method"] = data["payment_method"]

    issuer_name = data.get("issuer_name")
    if issuer_name:
        issuer_extra = dict(extra)
        if data.get("issuer_address"):
            issuer_extra["address"] = data["issuer_address"]
        if data.get("issuer_phone"):
            issuer_extra["phone"] = data["issuer_phone"]
        if data.get("issuer_iban"):
            issuer_extra["iban"] = data["issuer_iban"]
        candidates.append(EntityCandidate(
            name=issuer_name,
            nif=data.get("issuer_nif"),
            role=None,  # assigned later
            document_role="emisor",
            confidence=0.9 if data.get("issuer_nif") else 0.6,
            amount=total,
            extra=issuer_extra,
        ))
    client_name = data.get("client_name")
    if client_name:
        client_extra = dict(extra)
        if data.get("client_address"):
            client_extra["address"] = data["client_address"]
        if data.get("client_phone"):
            client_extra["phone"] = data["client_phone"]
        if data.get("client_iban"):
            client_extra["iban"] = data["client_iban"]
        candidates.append(EntityCandidate(
            name=client_name,
            nif=data.get("client_nif"),
            role=None,  # assigned later
            document_role="receptor",
            confidence=0.9 if data.get("client_nif") else 0.6,
            amount=total,
            extra=client_extra,
        ))
    return candidates


@_register_extractor("invoice_sent")
def _extract_invoice_sent(data: Dict[str, Any]) -> List[EntityCandidate]:
    """Extract issuer + client from a sent invoice.

    Roles are **not assigned** here — they will be set by ``_assign_roles``.
    """
    candidates: List[EntityCandidate] = []
    total = data.get("total_amount")
    extra = {}
    if data.get("payment_method"):
        extra["payment_method"] = data["payment_method"]

    issuer_name = data.get("issuer_name")
    if issuer_name:
        issuer_extra = dict(extra)
        if data.get("issuer_address"):
            issuer_extra["address"] = data["issuer_address"]
        if data.get("issuer_phone"):
            issuer_extra["phone"] = data["issuer_phone"]
        if data.get("issuer_iban"):
            issuer_extra["iban"] = data["issuer_iban"]
        candidates.append(EntityCandidate(
            name=issuer_name,
            nif=data.get("issuer_nif"),
            role=None,
            document_role="emisor",
            confidence=0.9 if data.get("issuer_nif") else 0.6,
            amount=total,
            extra=issuer_extra,
        ))
    client_name = data.get("client_name")
    if client_name:
        client_extra = dict(extra)
        if data.get("client_address"):
            client_extra["address"] = data["client_address"]
        if data.get("client_phone"):
            client_extra["phone"] = data["client_phone"]
        if data.get("client_iban"):
            client_extra["iban"] = data["client_iban"]
        candidates.append(EntityCandidate(
            name=client_name,
            nif=data.get("client_nif"),
            role=None,
            document_role="receptor",
            confidence=0.9 if data.get("client_nif") else 0.6,
            amount=total,
            extra=client_extra,
        ))
    return candidates


@_register_extractor("expense_ticket")
def _extract_expense_ticket(data: Dict[str, Any]) -> List[EntityCandidate]:
    name = data.get("issuer_name")
    if not name:
        return []
    return [EntityCandidate(
        name=name,
        nif=None,
        role=ContactRole.proveedor,
        document_role="emisor",
        confidence=0.4,
    )]


@_register_extractor("contract")
def _extract_contract(data: Dict[str, Any]) -> List[EntityCandidate]:
    parties = data.get("parties", [])
    candidates = []
    for party in parties:
        if isinstance(party, dict):
            name = party.get("name")
            if name:
                extra: Dict[str, Any] = {}
                if party.get("address"):
                    extra["address"] = party["address"]
                if party.get("phone"):
                    extra["phone"] = party["phone"]
                if party.get("iban"):
                    extra["iban"] = party["iban"]
                candidates.append(EntityCandidate(
                    name=name,
                    nif=party.get("nif"),
                    role=ContactRole.cliente,  # default; will be refined
                    document_role="parte",
                    confidence=0.4,
                    extra=extra,
                ))
    return candidates


def extract_entities(
    normalized_data: Dict[str, Any],
    document_type: str,
) -> List[EntityCandidate]:
    """Extract entity candidates from normalized document data."""
    extractor = _EXTRACTORS.get(document_type)
    if not extractor:
        return []
    return extractor(normalized_data)


# ---------------------------------------------------------------------------
# 1b. Assign roles based on cuenta tax_id comparison
# ---------------------------------------------------------------------------

# Maps (document_type) → role assigned to the *other* party (i.e. not the cuenta)
_OTHER_PARTY_ROLE: dict[str, ContactRole] = {
    "invoice_received": ContactRole.proveedor,
    "invoice_sent": ContactRole.cliente,
}

# The document_role that corresponds to "us" (the cuenta) for each invoice type.
# invoice_received → the cuenta is the receptor (we received the invoice).
# invoice_sent → the cuenta is the emisor (we issued the invoice).
_CUENTA_DOC_ROLE: dict[str, str] = {
    "invoice_received": "receptor",
    "invoice_sent": "emisor",
}


def _assign_roles(
    candidates: List[EntityCandidate],
    document_type: str,
    cuenta_tax_id: Optional[str],
) -> List[EntityCandidate]:
    """Filter out the cuenta's own entity and assign roles to the rest.

    For invoice types:
    1. If a candidate's NIF matches the cuenta's tax_id → skip ("us").
    2. If no NIF match was found, fall back to **positional filtering**:
       the entity in the cuenta's expected position (receptor for
       ``invoice_received``, emisor for ``invoice_sent``) is skipped.
    3. Remaining candidates receive the role from ``_OTHER_PARTY_ROLE``.

    For non-invoice types (expense_ticket, contract):
    - Roles are already assigned during extraction → return as-is.
    """
    other_role = _OTHER_PARTY_ROLE.get(document_type)
    if other_role is None:
        # Non-invoice: roles already assigned by extractor
        return candidates

    cuenta_doc_role = _CUENTA_DOC_ROLE.get(document_type)

    # Phase 1: check if any candidate matches by NIF
    nif_matched = any(_is_cuenta_entity(c.nif, cuenta_tax_id) for c in candidates)

    result: List[EntityCandidate] = []
    for c in candidates:
        if _is_cuenta_entity(c.nif, cuenta_tax_id):
            logger.debug(
                "Skipping entity '%s' — matches cuenta tax_id",
                c.name,
            )
            continue
        # Positional fallback: skip the cuenta-position entity when NIF
        # matching didn't identify anyone (avoids assigning both entities
        # the same role).
        if not nif_matched and cuenta_doc_role and c.document_role == cuenta_doc_role:
            logger.info(
                "Skipping entity '%s' (role=%s) — positional fallback for %s",
                c.name, c.document_role, document_type,
            )
            continue
        c.role = other_role
        result.append(c)
    return result


# ---------------------------------------------------------------------------
# 2. Normalize name for matching
# ---------------------------------------------------------------------------

_LEGAL_SUFFIX_RE = re.compile(
    r"\b(s\.?l\.?u?\.?|s\.?a\.?|s\.?l\.?l\.?|s\.?c\.?|ltd\.?|gmbh|inc\.?|ag)\b",
    re.IGNORECASE,
)


def _normalize_name_for_matching(name: str) -> str:
    """Produce a canonical form of a company name for fuzzy matching."""
    # Lowercase + strip accents
    text = unicodedata.normalize("NFKD", name.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Remove legal suffixes
    text = _LEGAL_SUFFIX_RE.sub("", text)
    # Remove non-alphanumeric
    text = re.sub(r"[^a-z0-9]", "", text)
    return text.strip()


def _name_similarity(a: str, b: str) -> float:
    """Simple ratio similarity between two normalized names. 0..1."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Longest common subsequence ratio (simple but effective)
    len_a, len_b = len(a), len(b)
    if len_a == 0 or len_b == 0:
        return 0.0
    # Use set-based similarity (Jaccard on character trigrams)
    trigrams_a = {a[i:i + 3] for i in range(max(1, len_a - 2))}
    trigrams_b = {b[i:i + 3] for i in range(max(1, len_b - 2))}
    if not trigrams_a or not trigrams_b:
        return 0.0
    intersection = len(trigrams_a & trigrams_b)
    union = len(trigrams_a | trigrams_b)
    return intersection / union if union else 0.0


# ---------------------------------------------------------------------------
# 3. Match against existing contacts
# ---------------------------------------------------------------------------

_NAME_MATCH_THRESHOLD = 0.7


def find_matching_contact(
    db: FirestoreClient,
    candidate: EntityCandidate,
    ctx: Optional[TenantContext] = None,
) -> Optional[tuple[str, dict]]:
    """Find an existing contact matching the candidate.

    Strategy (by priority):
    a) Exact tax_id match — O(1) with Firestore index.
    b) Normalized name similarity above threshold.

    Returns (contact_id, contact_data) or None.
    """
    collection_path = resolve_contacts_collection(ctx)
    col_ref = db.collection(collection_path)

    # a) tax_id exact match (check both "tax_id" and legacy "nif" field)
    normalized_nif = _normalize_tax_id(candidate.nif) if candidate.nif else None
    if normalized_nif:
        nif_docs = col_ref.where("tax_id", "==", normalized_nif).limit(1).get()
        for doc in nif_docs:
            return (doc.id, doc.to_dict())
        # Legacy field name fallback
        nif_docs = col_ref.where("nif", "==", normalized_nif).limit(1).get()
        for doc in nif_docs:
            return (doc.id, doc.to_dict())

    # b) Name-based fuzzy match (scan contacts — acceptable at low-medium scale)
    candidate_norm = _normalize_name_for_matching(candidate.name)
    if not candidate_norm:
        return None

    all_contacts = col_ref.get()
    best_match: Optional[tuple[str, dict, float]] = None

    for doc in all_contacts:
        data = doc.to_dict()
        # If both the candidate and the existing contact have a NIF and they
        # differ, they are distinct entities — skip regardless of name similarity.
        contact_nif = data.get("tax_id") or data.get("nif")
        if normalized_nif and contact_nif and not tax_ids_match(normalized_nif, contact_nif):
            continue
        contact_norm = _normalize_name_for_matching(data.get("nombre_fiscal", ""))
        similarity = _name_similarity(candidate_norm, contact_norm)
        if similarity >= _NAME_MATCH_THRESHOLD:
            if best_match is None or similarity > best_match[2]:
                best_match = (doc.id, data, similarity)

    if best_match:
        return (best_match[0], best_match[1])

    return None


# ---------------------------------------------------------------------------
# 4. Create or update contact
# ---------------------------------------------------------------------------

def _merge_roles(existing_roles: list, new_role: ContactRole) -> list:
    """Add a role to the list if not already present."""
    role_values = [r if isinstance(r, str) else r.value for r in existing_roles]
    if new_role.value not in role_values:
        role_values.append(new_role.value)
    return role_values


def _enrich_contact(existing: dict, candidate: EntityCandidate) -> dict:
    """Return fields to update on an existing contact (only fill blanks)."""
    updates: dict = {}

    # Add role if new
    current_roles = existing.get("roles", [])
    merged = _merge_roles(current_roles, candidate.role)
    if merged != current_roles:
        updates["roles"] = merged

    # Enrich tax_id fields if missing
    if not (existing.get("tax_id") or existing.get("nif")) and candidate.nif:
        normalized_nif = _normalize_tax_id(candidate.nif)
        if normalized_nif:
            updates["tax_id"] = normalized_nif
            classified = classify_tax_id(normalized_nif)
            if classified:
                updates["tax_country"] = classified.tax_country
                updates["tax_type"] = classified.tax_type

    # Propagate extra fields (only fill blanks)
    for src_key, dest_key in _EXTRA_FIELD_MAP.items():
        if not existing.get(dest_key) and candidate.extra.get(src_key):
            updates[dest_key] = candidate.extra[src_key]

    # Update confidence only if higher
    if candidate.confidence > existing.get("confidence", 0):
        updates["confidence"] = candidate.confidence

    # Accumulate totals from document amount
    if candidate.amount is not None and candidate.role:
        if candidate.role == ContactRole.proveedor:
            current = existing.get("total_recibido") or 0
            updates["total_recibido"] = round(current + candidate.amount, 2)
        elif candidate.role == ContactRole.cliente:
            current = existing.get("total_facturado") or 0
            updates["total_facturado"] = round(current + candidate.amount, 2)

    # Always update interaction stats
    now = datetime.now(timezone.utc).isoformat()
    updates["total_documentos"] = existing.get("total_documentos", 0) + 1
    updates["ultima_interaccion"] = now
    updates["updated_at"] = now

    return updates


def resolve_and_link(
    db: FirestoreClient,
    normalized_data: Dict[str, Any],
    document_type: str,
    doc_hash: str,
    ctx: Optional[TenantContext] = None,
) -> List[ContactRef]:
    """Full entity resolution pipeline for a document.

    1. Extract entity candidates from normalized data.
    2. Load cuenta tax_id, filter out "us", assign roles.
    3. For each remaining candidate, find or create a contact.
    4. Return ContactRef list to store in the document record.
    """
    candidates = extract_entities(normalized_data, document_type)
    if not candidates:
        return []

    # Load cuenta's own tax_id for role assignment
    cuenta_tax_id = _load_cuenta_tax_id(db, ctx)
    candidates = _assign_roles(candidates, document_type, cuenta_tax_id)

    # ── Defence-in-depth: drop any candidate whose NIF still matches ──
    if cuenta_tax_id:
        before = len(candidates)
        candidates = [
            c for c in candidates
            if not _is_cuenta_entity(c.nif, cuenta_tax_id)
        ]
        dropped = before - len(candidates)
        if dropped:
            logger.warning(
                "Guardrail dropped %d candidate(s) matching cuenta tax_id "
                "after _assign_roles (doc=%s)",
                dropped, doc_hash,
            )

    if not candidates:
        return []

    collection_path = resolve_contacts_collection(ctx)
    refs: List[ContactRef] = []

    for candidate in candidates:
        try:
            match = find_matching_contact(db, candidate, ctx)

            if match:
                contact_id, contact_data = match
                # ── Guardrail: never update a contact that IS the cuenta ──
                matched_nif = contact_data.get("tax_id") or contact_data.get("nif")
                if matched_nif and cuenta_tax_id and tax_ids_match(matched_nif, cuenta_tax_id):
                    logger.warning(
                        "Guardrail (update path): skipping contact %s — "
                        "matches cuenta tax_id (doc=%s)",
                        contact_id, doc_hash,
                    )
                    continue
                updates = _enrich_contact(contact_data, candidate)
                if updates:
                    db.collection(collection_path).document(contact_id).update(updates)
                    logger.info(
                        "Updated contact %s with role=%s from doc=%s",
                        contact_id, candidate.role.value, doc_hash,
                    )
            else:
                # Create new contact
                normalized_name = _normalize_company_name(candidate.name) or candidate.name
                normalized_nif = _normalize_tax_id(candidate.nif) if candidate.nif else None

                # Classify the tax_id
                tax_country = None
                tax_type = None
                if normalized_nif:
                    classified = classify_tax_id(normalized_nif)
                    if classified:
                        tax_country = classified.tax_country
                        tax_type = classified.tax_type

                # ── Final guardrail: never persist a contact with the
                #    cuenta's own tax_id. ──
                if normalized_nif and cuenta_tax_id and tax_ids_match(normalized_nif, cuenta_tax_id):
                    logger.warning(
                        "Final guardrail: skipping contact '%s' — "
                        "matches cuenta tax_id (doc=%s)",
                        normalized_name, doc_hash,
                    )
                    continue

                now = datetime.now(timezone.utc)
                contact_data = {
                    "tax_id": normalized_nif,
                    "tax_country": tax_country,
                    "tax_type": tax_type,
                    "nombre_fiscal": normalized_name,
                    "nombre_comercial": None,
                    "roles": [candidate.role.value],
                    "confidence": candidate.confidence,
                    "source": ContactSource.ai_extracted.value,
                    "verified_at": None,
                    "direccion_fiscal": None,
                    "codigo_postal": None,
                    "email_contacto": None,
                    "telefono": None,
                    "iban": None,
                    "forma_pago_habitual": candidate.extra.get("payment_method"),
                    "total_documentos": 1,
                    "total_facturado": (
                        round(candidate.amount, 2)
                        if candidate.amount is not None and candidate.role == ContactRole.cliente
                        else None
                    ),
                    "total_recibido": (
                        round(candidate.amount, 2)
                        if candidate.amount is not None and candidate.role == ContactRole.proveedor
                        else None
                    ),
                    "ultima_interaccion": now.isoformat(),
                    "created_from_document": doc_hash,
                    "created_at": now,
                    "updated_at": now.isoformat(),
                }
                doc_ref = db.collection(collection_path).document()
                doc_ref.set(contact_data)
                contact_id = doc_ref.id
                logger.info(
                    "Created contact %s (%s) role=%s from doc=%s",
                    contact_id, normalized_name, candidate.role.value, doc_hash,
                )

            refs.append(ContactRef(
                contacto_id=contact_id,
                rol_en_documento=candidate.document_role,
            ))
        except Exception:
            logger.exception(
                "Failed to resolve entity '%s' from doc=%s",
                candidate.name, doc_hash,
            )

    return refs
