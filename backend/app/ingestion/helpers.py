import re
from datetime import date, datetime, timezone
from typing import Any, Dict

from app.ingestion.constants import (
    ADDITIVE_TAX_TYPES,
    CURRENCY_ALIASES,
    INVISIBLE_CHARS_RE,
    LEGAL_SUFFIXES_RE,
    NIF_CIF_RE,
    WHITESPACE_RE,
    NON_ALPHANUMERIC_RE,
    NON_NUMERIC_RE,
    PAYMENT_KEYWORDS,
    RATE_SNAP_TOLERANCE,
    RETENTION_TAX_TYPES,
    SPANISH_TAX_RATES,
    TAX_TYPE_ALIASES,
)
from app.ingestion.context import NormalizationContext


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = INVISIBLE_CHARS_RE.sub("", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    if not text or text.lower() == "null":
        return None
    return text


def _normalize_tax_id(value: Any) -> str | None:
    text = _clean_string(value)
    if not text:
        return None
    compact = NON_ALPHANUMERIC_RE.sub("", text).upper()
    if not NIF_CIF_RE.match(compact):
        return None
    return compact


def _normalize_currency(value: Any) -> str:
    """Normalize currency symbols and text to ISO 4217 codes."""
    text = _clean_string(value)
    if not text:
        return "EUR"
    lookup = text.lower().strip()
    if lookup in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[lookup]
    if re.match(r"^[A-Za-z]{3}$", text):
        return text.upper()
    return "EUR"


def _normalize_bool(value: Any, default: bool | None = None) -> bool | None:
    """Normalize boolean values from various sources (Gemini, strings, etc.).
    
    Handles:
    - Python bool: True/False
    - String variations: "true", "false", "yes", "no", "1", "0"
    - None → default parameter
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.lower().strip()
        if text in ("true", "yes", "1", "incluido", "included"):
            return True
        if text in ("false", "no", "0", "no incluido", "not included"):
            return False
    if isinstance(value, int):
        return bool(value)
    return default


def _normalize_company_name(value: Any) -> str | None:
    """Normalize company names: fix ALL-CAPS from OCR, standardize legal suffixes."""
    text = _clean_string(value)
    if not text:
        return None
    if text != text.upper() and text != text.lower():
        return text
    suffix_match = LEGAL_SUFFIXES_RE.search(text)
    if suffix_match:
        base = text[: suffix_match.start()].strip().title()
        suffix = re.sub(r"\s+", "", suffix_match.group(0)).upper()
        return f"{base} {suffix}"
    return text.title()


def _split_invoice_series(
    invoice_number: str | None, existing_series: str | None
) -> tuple[str | None, str | None]:
    """Split combined invoice number into (series, number) when series is missing."""
    if existing_series or not invoice_number:
        return existing_series, invoice_number
    for sep in ("-", "/"):
        if sep in invoice_number:
            parts = invoice_number.rsplit(sep, 1)
            if (
                len(parts) == 2
                and parts[1].strip().isdigit()
                and not parts[0].strip().isdigit()
            ):
                return parts[0].strip(), parts[1].strip()
    return None, invoice_number


def _detect_payment_method(raw: Dict[str, Any]) -> str | None:
    """Search all string values in raw data for payment method indicators."""
    text_pool = " ".join(
        str(v).lower() for v in raw.values() if isinstance(v, str) and v
    )
    for keyword, method in sorted(
        PAYMENT_KEYWORDS.items(), key=lambda x: -len(x[0])
    ):
        if keyword in text_pool:
            return method
    return None


def normalize_date(date_str: Any) -> date | None:
    """Normalize date from many LLM-friendly formats."""
    if date_str is None:
        return None

    if isinstance(date_str, datetime):
        return date_str.date()

    if isinstance(date_str, date):
        return date_str

    if isinstance(date_str, (int, float)):
        ts = float(date_str)
        if ts > 10_000_000_000:
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).date()
        except (OverflowError, OSError, ValueError):
            return None

    raw = _clean_string(date_str)
    if not raw:
        return None

    iso_candidate = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_candidate).date()
    except ValueError:
        pass

    date_formats = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        # Dot-separated — common in German, Swiss, Austrian, and many EU invoices
        "%d.%m.%Y",
        "%Y.%m.%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%d/%m/%Y %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
    )
    for fmt in date_formats:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def normalize_number(value: Any) -> float | None:
    """Convert numbers robustly from localized and noisy string formats."""
    if value in (None, "", "null"):
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        return None

    raw = _clean_string(value)
    if raw is None:
        return None

    sign = ""
    if raw.startswith(("-", "+")):
        sign = raw[0]
        raw = raw[1:]

    compact = raw.replace(" ", "")
    compact = NON_NUMERIC_RE.sub("", compact)

    if not compact:
        return None

    comma_count = compact.count(",")
    dot_count = compact.count(".")

    if comma_count > 1 and dot_count == 0:
        return None
    if dot_count > 1 and comma_count == 0:
        return None

    if comma_count and dot_count:
        if compact.rfind(",") > compact.rfind("."):
            compact = compact.replace(".", "")
            compact = compact.replace(",", ".")
        else:
            compact = compact.replace(",", "")
    elif comma_count == 1 and dot_count == 0:
        compact = compact.replace(",", ".")

    try:
        return float(f"{sign}{compact}")
    except ValueError:
        return None


def _track_transform(
    ctx: NormalizationContext,
    field_name: str,
    original: Any,
    transformed: Any,
    rule: str,
    invalid_reason: str,
) -> None:
    if original in (None, "", "null"):
        ctx.record(field_name, original, transformed, rule, "missing")
        return

    if transformed is None:
        ctx.record(field_name, original, transformed, rule, "invalid")
        ctx.add_issue(field_name, invalid_reason, "invalid", value=original)
        return

    ctx.record(field_name, original, transformed, rule, "normalized")


# ---------------------------------------------------------------------------
# Tax normalization helpers
# ---------------------------------------------------------------------------

def normalize_tax_type(value: Any) -> str | None:
    """Normalize tax type labels to canonical identifiers (iva, re, igic, ipsi, irpf)."""
    text = _clean_string(value)
    if not text:
        return None
    lookup = text.lower().strip()
    if lookup in TAX_TYPE_ALIASES:
        return TAX_TYPE_ALIASES[lookup]
    for alias, canonical in TAX_TYPE_ALIASES.items():
        if alias in lookup or lookup in alias:
            return canonical
    return lookup


def snap_tax_rate(rate: float, tax_type: str) -> float:
    """Snap a rate to the nearest legal Spanish rate if within tolerance."""
    legal_rates = SPANISH_TAX_RATES.get(tax_type)
    if not legal_rates:
        return rate
    for legal in legal_rates:
        if abs(rate - legal) <= RATE_SNAP_TOLERANCE:
            return legal
    return rate


def _normalize_single_tax_line(
    raw_line: dict,
    base_amount_fallback: float | None,
    ctx: NormalizationContext,
    path: str,
) -> dict | None:
    """Normalize a single tax line dict."""
    if not isinstance(raw_line, dict):
        return None

    tax_type = normalize_tax_type(raw_line.get("tax_type"))
    rate = normalize_number(raw_line.get("rate"))
    base = normalize_number(raw_line.get("base_amount"))
    amount = normalize_number(raw_line.get("amount"))

    if base is None and base_amount_fallback is not None:
        base = base_amount_fallback

    if amount is not None and amount < 0:
        amount = abs(amount)

    if rate is None and base is not None and base > 0 and amount is not None:
        computed = round(amount / base * 100, 2)
        rate = snap_tax_rate(computed, tax_type) if tax_type else computed
        ctx.record(f"{path}.rate", None, rate, "computed_from_amount_base", "normalized")

    if amount is None and base is not None and rate is not None:
        amount = round(base * rate / 100, 2)
        ctx.record(f"{path}.amount", None, amount, "computed_from_base_rate", "normalized")

    if rate is not None and tax_type:
        snapped = snap_tax_rate(rate, tax_type)
        if snapped != rate:
            ctx.record(f"{path}.rate", rate, snapped, "snap_to_legal_rate", "normalized")
            rate = snapped

    if tax_type:
        ctx.record(f"{path}.tax_type", raw_line.get("tax_type"), tax_type, "normalize_tax_type", "normalized")

    return {
        "tax_type": tax_type,
        "rate": rate,
        "base_amount": base,
        "amount": amount,
    }


def normalize_tax_lines(
    raw_lines: list | None,
    base_amount: float | None,
    ctx: NormalizationContext,
) -> list[dict]:
    """Normalize a list of tax lines."""
    if not raw_lines or not isinstance(raw_lines, list):
        return []
    result = []
    for idx, raw_line in enumerate(raw_lines):
        normalized = _normalize_single_tax_line(
            raw_line, base_amount, ctx, f"tax_lines[{idx}]",
        )
        if normalized:
            result.append(normalized)
    return result


def infer_tax_regime(tax_lines: list[dict]) -> str:
    """Determine fiscal regime from extracted tax types."""
    types = {tl.get("tax_type") for tl in tax_lines if tl.get("tax_type")}
    if "igic" in types:
        return "canarias"
    if "ipsi" in types:
        return "ceuta_melilla"
    if types & ADDITIVE_TAX_TYPES:
        return "peninsular"
    return "unknown"


# ---------------------------------------------------------------------------
# DRY helpers for normalizers
# ---------------------------------------------------------------------------

def make_field_tracker(ctx: NormalizationContext, raw: Dict[str, Any]):
    """Return a _t(key, value, rule) closure for tracking field transforms."""
    def _t(key: str, value: Any, rule: str) -> Any:
        _track_transform(ctx, key, raw.get(key), value, rule, f"invalid_{key}")
        return value
    return _t


def normalize_list_field(
    raw: Dict[str, Any],
    key: str,
    item_fn,
    ctx: NormalizationContext,
) -> list:
    """Validate that raw[key] is a list, normalize each dict item via item_fn."""
    items_raw = raw.get(key, [])
    if not isinstance(items_raw, list):
        ctx.add_issue(key, "expected_list", "invalid", value=items_raw)
        items_raw = []
    return [
        item_fn(item, ctx, f"{key}[{idx}]")
        for idx, item in enumerate(items_raw)
        if isinstance(item, dict)
    ]


def normalize_document_source(raw: Dict[str, Any], ctx: NormalizationContext) -> str | None:
    """Normalize the document_source field common to all document types."""
    value = _clean_string(raw.get("document_source"))
    _track_transform(ctx, "document_source", raw.get("document_source"), value, "clean_string", "invalid_document_source")
    return value


def normalize_tax_block(
    raw: Dict[str, Any],
    base_amount: float | None,
    ctx: NormalizationContext,
) -> tuple[list[dict], str]:
    """Normalize tax_lines and derive tax_regime — shared by invoice & expense_ticket."""
    tax_lines = normalize_tax_lines(raw.get("tax_lines"), base_amount, ctx)
    tax_regime = infer_tax_regime(tax_lines)
    return tax_lines, tax_regime


# ---------------------------------------------------------------------------
# VAT and IRPF inference helpers
# ---------------------------------------------------------------------------

def infer_vat_included_from_arithmetic(
    base_amount: float | None,
    total_amount: float | None,
    tax_lines: list[dict] | None,
) -> bool | None:
    """Infer vat_included from arithmetic: base + taxes - retentions ≈ total means FALSE; total=base means FALSE.
    
    Returns:
        True if taxes are included in total, False if not, None if cannot determine.
    """
    if not base_amount or not total_amount or not tax_lines:
        return None
    
    # If base_amount ≈ total_amount (no taxes), return None as undeterminable
    if abs(base_amount - total_amount) < 0.01:
        return None
    
    sum_additive = sum(
        tl.get("amount", 0) for tl in tax_lines
        if isinstance(tl, dict) and tl.get("tax_type") in ADDITIVE_TAX_TYPES
    )
    sum_retention = sum(
        tl.get("amount", 0) for tl in tax_lines
        if isinstance(tl, dict) and tl.get("tax_type") in RETENTION_TAX_TYPES
    )
    
    # If vat_included=False: expected = base + taxes - retentions
    expected_if_excluded = base_amount + sum_additive - sum_retention
    # If vat_included=True: expected = total (base already includes taxes)
    expected_if_included = base_amount + sum_retention  # Only subtract retentions
    
    tolerance = max(0.01, abs(total_amount) * 0.001)  # 0.1% tolerance
    
    if abs(expected_if_excluded - total_amount) < tolerance:
        return False  # Taxes excluded: base + taxes = total
    elif abs(base_amount + sum_retention - total_amount) < tolerance:
        return True   # Taxes included: base (which includes taxes) + retentions = total
    
    return None


def infer_missing_irpf(
    issuer_nif: str | None,
    client_nif: str | None,
    base_amount: float | None,
    total_amount: float | None,
    tax_lines: list[dict] | None,
    ctx: NormalizationContext | None = None,
) -> dict | None:
    """Auto-detect missing IRPF line for B2B invoices from natural persons.
    
    Spanish tax rule: B2B freelancers (DNI+CIF) must have 15% IRPF retention.
    Detects: issuer=person, client=company, but no IRPF line → infer it.
    
    Returns:
        A normalized tax_line dict for IRPF, or None if not applicable.
    """
    from app.ingestion.constants import NIF_CIF_RE
    
    if not issuer_nif or not client_nif or not base_amount or not total_amount:
        return None
    
    tax_lines = tax_lines or []
    
    # Check if IRPF already exists
    if any(tl.get("tax_type") == "irpf" for tl in tax_lines if isinstance(tl, dict)):
        return None
    
    # Check: issuer is natural person (DNI-like: 8 digits + letter), client is company (CIF-like)
    issuer_clean = issuer_nif.replace("-", "").upper()
    client_clean = client_nif.replace("-", "").upper()
    
    # Simple heuristic: DNI is 8 digits + letter at end; CIF is letter + 7-8 digits
    is_issuer_person = (
        len(issuer_clean) == 9 and issuer_clean[:8].isdigit() and issuer_clean[8].isalpha()
    )
    is_client_company = (
        len(client_clean) >= 8 and client_clean[0].isalpha() and client_clean[1:].replace("0", "").isalnum()
    )
    
    if not (is_issuer_person and is_client_company):
        return None
    
    # Detect descuadre: base + IVA - IRPF = total
    # If descuadre ≈ base × 15%, infer IRPF
    sum_iva = sum(
        tl.get("amount", 0) for tl in tax_lines
        if isinstance(tl, dict) and tl.get("tax_type") == "iva"
    )
    
    expected_with_irpf_15 = base_amount + sum_iva - (base_amount * 0.15)
    tolerance = max(0.01, abs(base_amount) * 0.01)
    
    if abs(expected_with_irpf_15 - total_amount) < tolerance:
        irpf_amount = round(base_amount * 0.15, 2)
        inferred_line = {
            "tax_type": "irpf",
            "rate": 15.0,
            "base_amount": base_amount,
            "amount": irpf_amount,
        }
        if ctx:
            ctx.record(
                "tax_lines[inferred_irpf]",
                None,
                inferred_line,
                "infer_missing_irpf",
                "normalized",
            )
        return inferred_line
    
    return None
