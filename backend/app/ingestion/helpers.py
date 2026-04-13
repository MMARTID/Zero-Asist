import re
from datetime import date, datetime, timezone
from typing import Any, Dict

from app.ingestion.constants import (
    ADDITIVE_TAX_TYPES,
    CURRENCY_ALIASES,
    INVISIBLE_CHARS_RE,
    LEGAL_SUFFIXES_RE,
    NIF_CIF_RE,
    PAYMENT_KEYWORDS,
    RATE_SNAP_TOLERANCE,
    SPANISH_TAX_RATES,
    TAX_TYPE_ALIASES,
)
from app.ingestion.context import NormalizationContext


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = INVISIBLE_CHARS_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or text.lower() == "null":
        return None
    return text


def _normalize_tax_id(value: Any) -> str | None:
    text = _clean_string(value)
    if not text:
        return None
    compact = re.sub(r"[^A-Za-z0-9]", "", text).upper()
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
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%d/%m/%Y %H:%M:%S",
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
    compact = re.sub(r"[^0-9,\.]", "", compact)

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
