"""Normalizer for expense_ticket type."""

from typing import Any, Dict

from app.ingestion.context import NormalizationContext
from app.ingestion.helpers import (
    _clean_string,
    _normalize_company_name,
    _normalize_currency,
    _track_transform,
    make_field_tracker,
    normalize_date,
    normalize_document_source,
    normalize_number,
    normalize_tax_block,
)


def normalize_expense_ticket(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Normalize expense_ticket documents."""
    local_ctx = ctx or NormalizationContext()
    _t = make_field_tracker(local_ctx, raw)

    base_amount = normalize_number(raw.get("base_amount"))
    total_amount = normalize_number(raw.get("total_amount"))

    _track_transform(local_ctx, "base_amount", raw.get("base_amount"), base_amount, "normalize_number", "invalid_base_amount")
    _track_transform(local_ctx, "total_amount", raw.get("total_amount"), total_amount, "normalize_number", "invalid_total_amount")

    tax_lines, tax_regime = normalize_tax_block(raw, base_amount, local_ctx)

    return {
        "issuer_name":     _t("issuer_name",     _normalize_company_name(raw.get("issuer_name")),  "normalize_company_name"),
        "issue_date":      _t("issue_date",      normalize_date(raw.get("issue_date")),            "normalize_date"),
        "base_amount":     base_amount,
        "total_amount":    total_amount,
        "tax_lines":       tax_lines,
        "tax_regime":      tax_regime,
        "vat_included":    True,
        "currency":        _t("currency",        _normalize_currency(raw.get("currency")),         "normalize_currency"),
        "concept":         _t("concept",         _clean_string(raw.get("concept")),                "clean_string"),
        "payment_method":  _t("payment_method",  _clean_string(raw.get("payment_method")),         "clean_string"),
        "document_source": normalize_document_source(raw, local_ctx),
    }
