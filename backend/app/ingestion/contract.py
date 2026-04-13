"""Normalizer for contract type."""

from typing import Any, Dict

from app.ingestion.context import NormalizationContext
from app.ingestion.helpers import (
    _clean_string,
    _normalize_company_name,
    _normalize_tax_id,
    _track_transform,
    normalize_date,
)


def _normalize_party(item: Dict[str, Any], ctx: NormalizationContext, path: str) -> Dict[str, Any]:
    """Normalize a single contract party."""
    name = _normalize_company_name(item.get("name"))
    nif = _normalize_tax_id(item.get("nif"))
    _track_transform(ctx, f"{path}.name", item.get("name"), name, "normalize_company_name", "invalid_name")
    _track_transform(ctx, f"{path}.nif", item.get("nif"), nif, "normalize_tax_id", "invalid_nif")
    return {"name": name, "nif": nif}


def normalize_contract(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Normalize contract documents."""
    local_ctx = ctx or NormalizationContext()

    parties_raw = raw.get("parties", [])
    if not isinstance(parties_raw, list):
        local_ctx.add_issue("parties", "expected_list", "invalid", value=parties_raw)
        parties_raw = []

    parties = [
        _normalize_party(p, local_ctx, f"parties[{i}]")
        for i, p in enumerate(parties_raw)
        if isinstance(p, dict)
    ]

    def _t(key: str, value: Any, rule: str) -> Any:
        _track_transform(local_ctx, key, raw.get(key), value, rule, f"invalid_{key}")
        return value

    return {
        "parties":         parties,
        "contract_date":   _t("contract_date",   normalize_date(raw.get("contract_date")),   "normalize_date"),
        "subject":         _t("subject",         _clean_string(raw.get("subject")),           "clean_string"),
        "duration":        _t("duration",        _clean_string(raw.get("duration")),          "clean_string"),
        "economic_terms":  _t("economic_terms",  _clean_string(raw.get("economic_terms")),    "clean_string"),
        "signed":          raw.get("signed"),
        "document_source": _t("document_source", _clean_string(raw.get("document_source")),  "clean_string"),
    }
