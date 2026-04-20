import logging
from typing import Any, Dict

from pydantic import ValidationError

from app.ingestion.constants import (
    ADDITIVE_TAX_TYPES,
    ARITHMETIC_TOLERANCE_MIN,
    ARITHMETIC_TOLERANCE_RATIO,
    RE_IVA_PAIRS,
    RETENTION_TAX_TYPES,
    SPANISH_TAX_RATES,
)
from app.ingestion.context import NormalizationContext, ValidationIssue
from app.models.registry import DOCUMENT_TYPE_REGISTRY

logger = logging.getLogger(__name__)


def _validate_required_fields(normalized: Dict[str, Any], document_type: str, ctx: NormalizationContext) -> None:
    config = DOCUMENT_TYPE_REGISTRY.get(document_type)
    required = config.required_fields if config else []
    for field_name in required:
        if normalized.get(field_name) in (None, "", []):
            ctx.add_issue(field_name, "required_field_missing", "missing")
            ctx.record(field_name, None, normalized.get(field_name), "required_field_check", "missing")


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
    """Validate arithmetic consistency: base + additive_taxes - retentions ≈ total."""
    base = normalized.get("base_amount")
    total = normalized.get("total_amount")
    tax_lines = normalized.get("tax_lines")

    if not tax_lines or not isinstance(tax_lines, list):
        return
    if base is None or total is None:
        return

    sum_additive = sum(
        tl["amount"] for tl in tax_lines
        if isinstance(tl, dict) and tl.get("amount") is not None
        and tl.get("tax_type") in ADDITIVE_TAX_TYPES
    )
    sum_retention = sum(
        tl["amount"] for tl in tax_lines
        if isinstance(tl, dict) and tl.get("amount") is not None
        and tl.get("tax_type") in RETENTION_TAX_TYPES
    )

    expected = base + sum_additive - sum_retention
    tolerance = max(ARITHMETIC_TOLERANCE_MIN, abs(total) * ARITHMETIC_TOLERANCE_RATIO)

    if abs(expected - total) > tolerance:
        ctx.add_issue(
            "total_amount",
            f"arithmetic_mismatch: base({base}) + taxes({sum_additive}) - retentions({sum_retention}) = {expected:.2f} != total({total})",
            "invalid",
            value=total,
        )


def _validate_tax_lines(normalized: Dict[str, Any], ctx: NormalizationContext) -> None:
    """Validate individual tax lines and inter-line coherence."""
    tax_lines = normalized.get("tax_lines")
    if not tax_lines or not isinstance(tax_lines, list):
        return

    types_seen: set[str] = set()
    iva_rates_seen: set[float] = set()
    re_rates_seen: set[float] = set()

    for idx, tl in enumerate(tax_lines):
        if not isinstance(tl, dict):
            continue

        tax_type = tl.get("tax_type")
        rate = tl.get("rate")
        base = tl.get("base_amount")
        amount = tl.get("amount")
        path = f"tax_lines[{idx}]"

        if tax_type:
            types_seen.add(tax_type)
        if tax_type == "iva" and rate is not None:
            iva_rates_seen.add(rate)
        elif tax_type == "re" and rate is not None:
            re_rates_seen.add(rate)

        # Per-line: base × rate / 100 ≈ amount
        if base is not None and rate is not None and amount is not None and base > 0:
            expected = round(base * rate / 100, 2)
            tolerance = max(ARITHMETIC_TOLERANCE_MIN, abs(amount) * ARITHMETIC_TOLERANCE_RATIO)
            if abs(expected - amount) > tolerance:
                ctx.add_issue(
                    path,
                    f"tax_line_mismatch: {base} × {rate}% = {expected:.2f} != {amount}",
                    "invalid",
                    value=amount,
                )

        # Rate belongs to legal set
        if tax_type and rate is not None:
            legal_rates = SPANISH_TAX_RATES.get(tax_type)
            if legal_rates and rate not in legal_rates:
                ctx.add_issue(
                    f"{path}.rate",
                    f"non_standard_rate: {rate}% not in legal rates for {tax_type}",
                    "invalid",
                    value=rate,
                )

    # Mutual exclusion: IVA, IGIC, IPSI cannot coexist
    indirect = types_seen & {"iva", "igic", "ipsi"}
    if len(indirect) > 1:
        ctx.add_issue(
            "tax_lines",
            f"mutually_exclusive_taxes: {', '.join(sorted(indirect))} cannot coexist",
            "invalid",
        )

    # RE requires IVA
    if "re" in types_seen and "iva" not in types_seen:
        ctx.add_issue(
            "tax_lines",
            "re_without_iva: recargo de equivalencia requires IVA",
            "invalid",
        )

    # RE ↔ IVA rate pairs
    if "re" in types_seen and "iva" in types_seen:
        for re_rate in re_rates_seen:
            expected_iva = None
            for iva_r, re_r in RE_IVA_PAIRS.items():
                if re_r == re_rate:
                    expected_iva = iva_r
                    break
            if expected_iva is not None and expected_iva not in iva_rates_seen:
                ctx.add_issue(
                    "tax_lines",
                    f"re_iva_pair_mismatch: RE {re_rate}% expects IVA {expected_iva}%",
                    "invalid",
                )


def _check_vat_included_coherence(normalized: Dict[str, Any], ctx: NormalizationContext) -> None:
    """Validate that vat_included is coherent with base_amount and total_amount."""
    vat_included = normalized.get("vat_included")
    base_amount = normalized.get("base_amount")
    total_amount = normalized.get("total_amount")
    tax_lines = normalized.get("tax_lines") or []
    
    if vat_included is None or base_amount is None or total_amount is None:
        return
    
    # If vat_included=False: base ≠ total (when taxes exist)
    if vat_included is False:
        if tax_lines and abs(base_amount - total_amount) < 0.01:
            ctx.add_issue(
                "vat_included",
                "incoherent_arithmetic_vat_false: base_amount equals total_amount but vat_included=False",
                "invalid",
                value=vat_included,
            )
    
    # If vat_included=True: base < total (or base ≈ total if no taxes)
    elif vat_included is True:
        if tax_lines and base_amount >= total_amount:
            ctx.add_issue(
                "vat_included",
                "incoherent_arithmetic_vat_true: base_amount >= total_amount but vat_included=True",
                "invalid",
                value=vat_included,
            )


def _sanitize_issue_for_logging(issue: ValidationIssue) -> dict:
    """Redact PII from validation issues before logging."""
    pii_fields = {"issuer_nif", "client_nif", "iban", "phone", "card_last_digits", "operation_reference"}
    
    if any(pii_field in issue.field for pii_field in pii_fields):
        return {
            "field": issue.field,
            "reason": issue.reason,
            "kind": issue.kind,
            "value": "[REDACTED]",
        }
    
    return issue.__dict__


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
    _validate_schema(normalized, document_type, ctx)
    _validate_tax_lines(normalized, ctx)
    _cross_check_arithmetic(normalized, ctx)
    _check_vat_included_coherence(normalized, ctx)
    _check_type_coherence(normalized, document_type, ctx)

    if ctx.issues:
        # Sanitize issues before logging (redact PII)
        sanitized_issues = [_sanitize_issue_for_logging(issue) for issue in ctx.issues]
        
        logger.warning(
            "normalization_issues",
            extra={
                "document_type": document_type,
                "strict": ctx.strict,
                "issue_count": len(ctx.issues),
                "issues": sanitized_issues,
            },
        )

    if ctx.strict and ctx.issues:
        raise ValueError(
            f"Normalization failed for {document_type}: "
            f"{'; '.join(f'{issue.field}:{issue.reason}' for issue in ctx.issues)}"
        )
