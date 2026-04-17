"""Normalizer for administrative_notice type."""

from typing import Any, Dict

from app.ingestion.context import NormalizationContext
from app.ingestion.helpers import (
    _clean_string,
    make_field_tracker,
    normalize_date,
    normalize_document_source,
)


def normalize_administrative_notice(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Normalize administrative_notice documents."""
    local_ctx = ctx or NormalizationContext()
    _t = make_field_tracker(local_ctx, raw)

    return {
        "issuer_name":      _t("issuer_name",      _clean_string(raw.get("issuer_name") or raw.get("issuer_entity")),  "clean_string"),
        "notice_type":      _t("notice_type",      _clean_string(raw.get("notice_type")),      "clean_string"),
        "issue_date":       _t("issue_date",       normalize_date(raw.get("issue_date")),      "normalize_date"),
        "deadline":         _t("deadline",         normalize_date(raw.get("deadline")),         "normalize_date"),
        "expedient_number": _t("expedient_number", _clean_string(raw.get("expedient_number")), "clean_string"),
        "summary":          _t("summary",          _clean_string(raw.get("summary")),           "clean_string"),
        "has_signed_pdf":   raw.get("has_signed_pdf"),
        "document_source":  normalize_document_source(raw, local_ctx),
    }
