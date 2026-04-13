"""Normalizer for administrative_notice type."""

from typing import Any, Dict

from app.ingestion.context import NormalizationContext
from app.ingestion.helpers import (
    _clean_string,
    _track_transform,
    normalize_date,
)


def normalize_administrative_notice(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Normalize administrative_notice documents."""
    local_ctx = ctx or NormalizationContext()

    def _t(key: str, value: Any, rule: str) -> Any:
        _track_transform(local_ctx, key, raw.get(key), value, rule, f"invalid_{key}")
        return value

    return {
        "issuer_entity":    _t("issuer_entity",    _clean_string(raw.get("issuer_entity")),    "clean_string"),
        "notice_type":      _t("notice_type",      _clean_string(raw.get("notice_type")),      "clean_string"),
        "issue_date":       _t("issue_date",       normalize_date(raw.get("issue_date")),      "normalize_date"),
        "deadline":         _t("deadline",         normalize_date(raw.get("deadline")),         "normalize_date"),
        "expedient_number": _t("expedient_number", _clean_string(raw.get("expedient_number")), "clean_string"),
        "summary":          _t("summary",          _clean_string(raw.get("summary")),           "clean_string"),
        "has_signed_pdf":   raw.get("has_signed_pdf"),
        "document_source":  _t("document_source",  _clean_string(raw.get("document_source")),  "clean_string"),
    }
