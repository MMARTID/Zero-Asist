"""Normalizers for invoice_received and invoice_sent document types."""

from typing import Any, Dict

from app.ingestion.constants import ADDITIVE_TAX_TYPES, RETENTION_TAX_TYPES
from app.ingestion.context import NormalizationContext
from app.ingestion.helpers import (
    _clean_string,
    _normalize_company_name,
    _normalize_currency,
    _normalize_tax_id,
    _track_transform,
    infer_tax_regime,
    normalize_date,
    normalize_number,
    normalize_tax_lines,
)


def _fill_amount_gaps(
    base: float | None,
    total: float | None,
    tax_lines: list[dict],
    ctx: NormalizationContext,
) -> tuple[float | None, float | None]:
    """Attempt to recover base_amount or total_amount from available data."""
    if not tax_lines:
        return base, total

    sum_additive = sum(
        tl["amount"] for tl in tax_lines
        if tl.get("amount") is not None and tl.get("tax_type") in ADDITIVE_TAX_TYPES
    )
    sum_retention = sum(
        tl["amount"] for tl in tax_lines
        if tl.get("amount") is not None and tl.get("tax_type") in RETENTION_TAX_TYPES
    )

    if base is None and total is not None:
        base = round(total - sum_additive + sum_retention, 2)
        ctx.record("base_amount", None, base, "computed_from_total_and_taxes", "normalized")

    if total is None and base is not None:
        total = round(base + sum_additive - sum_retention, 2)
        ctx.record("total_amount", None, total, "computed_from_base_and_taxes", "normalized")

    return base, total


def _normalize_invoice_like(raw: Dict[str, Any], ctx: NormalizationContext, is_sent: bool) -> Dict[str, Any]:
    def _t(key: str, value: Any, rule: str) -> Any:
        _track_transform(ctx, key, raw.get(key), value, rule, f"invalid_{key}")
        return value

    base_amount = normalize_number(raw.get("base_amount"))
    total_amount = normalize_number(raw.get("total_amount"))

    _track_transform(ctx, "base_amount", raw.get("base_amount"), base_amount, "normalize_number", "invalid_base_amount")
    _track_transform(ctx, "total_amount", raw.get("total_amount"), total_amount, "normalize_number", "invalid_total_amount")

    tax_lines = normalize_tax_lines(raw.get("tax_lines"), base_amount, ctx)
    base_amount, total_amount = _fill_amount_gaps(base_amount, total_amount, tax_lines, ctx)

    result: Dict[str, Any] = {
        "issuer_name":    _t("issuer_name",    _normalize_company_name(raw.get("issuer_name")),  "normalize_company_name"),
        "issuer_nif":     _t("issuer_nif",     _normalize_tax_id(raw.get("issuer_nif")),         "normalize_tax_id"),
        "invoice_number": _t("invoice_number", _clean_string(raw.get("invoice_number")),         "clean_string"),
        "issue_date":     _t("issue_date",     normalize_date(raw.get("issue_date")),            "normalize_date"),
        "base_amount":    base_amount,
        "total_amount":   total_amount,
        "tax_lines":      tax_lines,
        "tax_regime":     infer_tax_regime(tax_lines),
        "currency":       _t("currency",       _normalize_currency(raw.get("currency")),         "normalize_currency"),
        "payment_method": _t("payment_method", _clean_string(raw.get("payment_method")),         "clean_string"),
        "document_source": _t("document_source", _clean_string(raw.get("document_source")),      "clean_string"),
    }

    if is_sent:
        result["client_name"]    = _t("client_name",    _normalize_company_name(raw.get("client_name")),  "normalize_company_name")
        result["client_nif"]     = _t("client_nif",     _normalize_tax_id(raw.get("client_nif")),         "normalize_tax_id")
        result["payment_status"] = _t("payment_status", _clean_string(raw.get("payment_status")),         "clean_string")
    else:
        result["concept"]              = _t("concept",              _clean_string(raw.get("concept")),                      "clean_string")
        result["billing_period_start"] = _t("billing_period_start", normalize_date(raw.get("billing_period_start")),        "normalize_date")
        result["billing_period_end"]   = _t("billing_period_end",   normalize_date(raw.get("billing_period_end")),          "normalize_date")

    return result


def normalize_invoice_received(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Normalize invoice_received documents."""
    return _normalize_invoice_like(raw, ctx or NormalizationContext(), is_sent=False)


def normalize_invoice_sent(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Normalize invoice_sent documents."""
    return _normalize_invoice_like(raw, ctx or NormalizationContext(), is_sent=True)
