"""Normalizer for bank_document type."""

from typing import Any, Dict

from app.ingestion.context import NormalizationContext
from app.ingestion.helpers import (
    _clean_string,
    _track_transform,
    make_field_tracker,
    normalize_date,
    normalize_document_source,
    normalize_list_field,
    normalize_number,
)


def normalize_movement(item: Dict[str, Any], ctx: NormalizationContext, path: str = "movements") -> Dict[str, Any]:
    """Normalize a single bank movement."""
    result = {
        "date":          normalize_date(item.get("date")),
        "description":   _clean_string(item.get("description")),
        "amount":        normalize_number(item.get("amount")),
        "balance_after": normalize_number(item.get("balance_after")),
    }
    _track_transform(ctx, f"{path}.date", item.get("date"), result["date"], "normalize_date", "invalid_date")
    _track_transform(ctx, f"{path}.amount", item.get("amount"), result["amount"], "normalize_number", "invalid_amount")
    _track_transform(ctx, f"{path}.balance_after", item.get("balance_after"), result["balance_after"], "normalize_number", "invalid_balance_after")
    return result


def normalize_bank_document(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Normalize bank_document documents."""
    local_ctx = ctx or NormalizationContext()
    _t = make_field_tracker(local_ctx, raw)

    return {
        "bank_name":       _t("bank_name",       _clean_string(raw.get("bank_name")),           "clean_string"),
        "document_date":   _t("document_date",   normalize_date(raw.get("document_date")),      "normalize_date"),
        "iban":            _t("iban",            _clean_string(raw.get("iban")),                  "clean_string"),
        "movements":       normalize_list_field(raw, "movements", normalize_movement, local_ctx),
        "document_source": normalize_document_source(raw, local_ctx),
    }
