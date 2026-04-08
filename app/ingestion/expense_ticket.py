"""Normalizer for expense_ticket type."""

from typing import Any, Dict

from app.ingestion.context import NormalizationContext
from app.ingestion.helpers import (
    _clean_string,
    _normalize_company_name,
    _normalize_currency,
    _track_transform,
    normalize_date,
    normalize_number,
)


def normalize_expense_ticket(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Normalize expense_ticket documents."""
    local_ctx = ctx or NormalizationContext()

    def _t(key: str, value: Any, rule: str) -> Any:
        _track_transform(local_ctx, key, raw.get(key), value, rule, f"invalid_{key}")
        return value

    return {
        "issuer_name":     _t("issuer_name",     _normalize_company_name(raw.get("issuer_name")),  "normalize_company_name"),
        "issue_date":      _t("issue_date",      normalize_date(raw.get("issue_date")),            "normalize_date"),
        "total_amount":    _t("total_amount",    normalize_number(raw.get("total_amount")),        "normalize_number"),
        "currency":        _t("currency",        _normalize_currency(raw.get("currency")),         "normalize_currency"),
        "vat_included":    raw.get("vat_included"),
        "concept":         _t("concept",         _clean_string(raw.get("concept")),                "clean_string"),
        "payment_method":  _t("payment_method",  _clean_string(raw.get("payment_method")),         "clean_string"),
        "document_source": _t("document_source", _clean_string(raw.get("document_source")),        "clean_string"),
    }
