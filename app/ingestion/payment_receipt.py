"""Normalizer for payment_receipt type."""

from typing import Any, Dict

from app.ingestion.context import NormalizationContext
from app.ingestion.helpers import (
    _clean_string,
    _normalize_currency,
    _track_transform,
    normalize_date,
    normalize_number,
)


def normalize_payment_receipt(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Normalize payment_receipt documents."""
    local_ctx = ctx or NormalizationContext()

    def _t(key: str, value: Any, rule: str) -> Any:
        _track_transform(local_ctx, key, raw.get(key), value, rule, f"invalid_{key}")
        return value

    return {
        "payment_date":        _t("payment_date",        normalize_date(raw.get("payment_date")),            "normalize_date"),
        "amount":              _t("amount",              normalize_number(raw.get("amount")),                "normalize_number"),
        "currency":            _t("currency",            _normalize_currency(raw.get("currency")),           "normalize_currency"),
        "payment_method":      _t("payment_method",      _clean_string(raw.get("payment_method")),           "clean_string"),
        "operation_reference": _t("operation_reference", _clean_string(raw.get("operation_reference")),      "clean_string"),
        "issuer_entity":       _t("issuer_entity",       _clean_string(raw.get("issuer_entity")),            "clean_string"),
        "card_last_digits":    _t("card_last_digits",    _clean_string(raw.get("card_last_digits")),         "clean_string"),
        "iban":                _t("iban",                _clean_string(raw.get("iban")),                      "clean_string"),
        "document_source":     _t("document_source",     _clean_string(raw.get("document_source")),          "clean_string"),
    }
