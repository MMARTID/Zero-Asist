"""Normalizer for contract type."""

from typing import Any, Dict

from app.ingestion.context import NormalizationContext
from app.ingestion.helpers import (
    _clean_string,
    _normalize_bool,
    _normalize_company_name,
    _normalize_tax_id,
    _track_transform,
    make_field_tracker,
    normalize_date,
    normalize_document_source,
    normalize_list_field,
)


def _normalize_party(item: Dict[str, Any], ctx: NormalizationContext, path: str) -> Dict[str, Any]:
    """Normalize a single contract party."""
    name = _normalize_company_name(item.get("name"))
    nif = _normalize_tax_id(item.get("nif"))
    address = _clean_string(item.get("address"))
    phone = _clean_string(item.get("phone"))
    iban = _clean_string(item.get("iban"))
    _track_transform(ctx, f"{path}.name", item.get("name"), name, "normalize_company_name", "invalid_name")
    _track_transform(ctx, f"{path}.nif", item.get("nif"), nif, "normalize_tax_id", "invalid_nif")
    _track_transform(ctx, f"{path}.address", item.get("address"), address, "clean_string", "invalid_address")
    _track_transform(ctx, f"{path}.phone", item.get("phone"), phone, "clean_string", "invalid_phone")
    _track_transform(ctx, f"{path}.iban", item.get("iban"), iban, "clean_string", "invalid_iban")
    return {"name": name, "nif": nif, "address": address, "phone": phone, "iban": iban}


def normalize_contract(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Normalize contract documents."""
    local_ctx = ctx or NormalizationContext()
    _t = make_field_tracker(local_ctx, raw)

    parties = normalize_list_field(raw, "parties", _normalize_party, local_ctx)

    return {
        "parties":         parties,
        "contract_date":   _t("contract_date",   normalize_date(raw.get("contract_date")),   "normalize_date"),
        "subject":         _t("subject",         _clean_string(raw.get("subject")),           "clean_string"),
        "duration":        _t("duration",        _clean_string(raw.get("duration")),          "clean_string"),
        "economic_terms":  _t("economic_terms",  _clean_string(raw.get("economic_terms")),    "clean_string"),
        "signed":          _t("signed",          _normalize_bool(raw.get("signed")),          "normalize_bool"),
        "document_source": normalize_document_source(raw, local_ctx),
    }
