import re
from datetime import date, datetime, timezone
from typing import Any, Dict

from app.ingestion.constants import (
    CURRENCY_ALIASES,
    INVISIBLE_CHARS_RE,
    LEGAL_SUFFIXES_RE,
    NIF_CIF_RE,
    PAYMENT_KEYWORDS,
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

