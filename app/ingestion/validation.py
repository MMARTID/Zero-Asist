import logging
from typing import Any, Dict

from pydantic import ValidationError

from app.ingestion.constants import ARITHMETIC_TOLERANCE_MIN, ARITHMETIC_TOLERANCE_RATIO, RANGE_RULES
from app.ingestion.context import NormalizationContext
from app.models.registry import DOCUMENT_TYPE_REGISTRY

logger = logging.getLogger(__name__)


def _validate_required_fields(normalized: Dict[str, Any], document_type: str, ctx: NormalizationContext) -> None:
    config = DOCUMENT_TYPE_REGISTRY.get(document_type)
    required = config.required_fields if config else []
    for field_name in required:
        if normalized.get(field_name) in (None, "", []):
            ctx.add_issue(field_name, "required_field_missing", "missing")
            ctx.record(field_name, None, normalized.get(field_name), "required_field_check", "missing")


def _validate_ranges(normalized: Dict[str, Any], ctx: NormalizationContext) -> None:
    for field_name, (min_value, max_value) in RANGE_RULES.items():
        value = normalized.get(field_name)
        if value is None:
            continue
        if not isinstance(value, (int, float)):
            ctx.add_issue(field_name, "range_check_non_numeric", "invalid", value=value)
            ctx.record(field_name, value, value, "range_check", "invalid")
            continue
        if value < min_value or value > max_value:
            ctx.add_issue(field_name, f"out_of_range[{min_value},{max_value}]", "invalid", value=value)
            ctx.record(field_name, value, value, "range_check", "invalid")


def _validate_schema(normalized: Dict[str, Any], document_type: str, ctx: NormalizationContext) -> None:
    config = DOCUMENT_TYPE_REGISTRY.get(document_type)
    schema = config.schema if config else None
    if not schema:
        return
    try:
        schema.model_validate(normalized)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", [])) or "unknown"
            msg = err.get("msg", "validation_error")
            ctx.add_issue(loc, msg, "invalid", value=normalized.get(loc))
            ctx.record(loc, normalized.get(loc), normalized.get(loc), "schema_validation", "invalid")


def _cross_check_arithmetic(normalized: Dict[str, Any], ctx: NormalizationContext) -> None:
    """Validate arithmetic consistency: base + tax ≈ total."""
    base = normalized.get("base_amount")
    tax = normalized.get("tax_amount")
    total = normalized.get("total_amount")

    if base is not None and tax is not None and total is not None:
        expected = base + tax
        tolerance = max(ARITHMETIC_TOLERANCE_MIN, abs(total) * ARITHMETIC_TOLERANCE_RATIO)
        if abs(expected - total) > tolerance:
            ctx.add_issue(
                "total_amount",
                f"arithmetic_mismatch: base({base}) + tax({tax}) = {expected:.2f} != total({total})",
                "invalid",
                value=total,
            )


def _check_type_coherence(
    normalized: Dict[str, Any], document_type: str, ctx: NormalizationContext,
) -> None:
    """Warn when document content contradicts the declared type."""
    if document_type in ("invoice_received", "invoice_sent"):
        has_invoice_fields = any(
            normalized.get(f) for f in ("invoice_number", "total_amount", "issuer_name")
        )
        if not has_invoice_fields:
            ctx.add_issue(
                "document_type",
                f"type_coherence: {document_type} lacks key invoice fields",
                "invalid",
            )
    elif document_type == "bank_document":
        if normalized.get("invoice_number"):
            ctx.add_issue(
                "document_type",
                "type_coherence: bank_document has invoice_number",
                "invalid",
            )


def _finalize_validation(document_type: str, normalized: Dict[str, Any], ctx: NormalizationContext) -> None:
    _validate_required_fields(normalized, document_type, ctx)
    _validate_ranges(normalized, ctx)
    _validate_schema(normalized, document_type, ctx)
    _cross_check_arithmetic(normalized, ctx)
    _check_type_coherence(normalized, document_type, ctx)

    if ctx.issues:
        logger.warning(
            "normalization_issues",
            extra={
                "document_type": document_type,
                "strict": ctx.strict,
                "issue_count": len(ctx.issues),
                "issues": [issue.__dict__ for issue in ctx.issues],
            },
        )

    if ctx.strict and ctx.issues:
        raise ValueError(
            f"Normalization failed for {document_type}: "
            f"{'; '.join(f'{issue.field}:{issue.reason}' for issue in ctx.issues)}"
        )
