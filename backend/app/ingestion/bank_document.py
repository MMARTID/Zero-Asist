"""Normalizer for bank_document type."""

from typing import Any, Dict

from app.ingestion.context import NormalizationContext
from app.ingestion.helpers import (
    _clean_string,
    _track_transform,
    normalize_date,
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

    movements_raw = raw.get("movements", [])
    if not isinstance(movements_raw, list):
        local_ctx.add_issue("movements", "expected_list", "invalid", value=movements_raw)
        movements_raw = []

    def _t(key: str, value: Any, rule: str) -> Any:
        _track_transform(local_ctx, key, raw.get(key), value, rule, f"invalid_{key}")
        return value

    return {
        "bank_name":       _t("bank_name",       _clean_string(raw.get("bank_name")),           "clean_string"),
        "document_date":   _t("document_date",   normalize_date(raw.get("document_date")),      "normalize_date"),
        "iban":            _t("iban",            _clean_string(raw.get("iban")),                  "clean_string"),
        "movements": [
            normalize_movement(item, local_ctx, f"movements[{idx}]")
            for idx, item in enumerate(movements_raw)
            if isinstance(item, dict)
        ],
        "document_source": _t("document_source", _clean_string(raw.get("document_source")),     "clean_string"),
    }
