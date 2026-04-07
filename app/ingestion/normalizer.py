import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict

from pydantic import ValidationError

from app.models.document import BankStatementData, InvoiceIssuedData, InvoiceReceivedData

logger = logging.getLogger(__name__)

DATE_FIELDS = ["issue_date", "due_date", "period_start", "period_end"]

INVISIBLE_CHARS_RE = re.compile(r"[\u200B\u200C\u200D\u2060\uFEFF]")
NIF_CIF_RE = re.compile(r"^[A-Z0-9]{8,12}$")


@dataclass
class TraceEntry:
    field: str
    original: Any
    transformed: Any
    rule: str
    status: str  # missing | invalid | normalized


@dataclass
class ValidationIssue:
    field: str
    reason: str
    kind: str  # missing | invalid
    value: Any = None


@dataclass
class NormalizationReport:
    normalized: Dict[str, Any]
    trace: list[TraceEntry] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    document_type: str = "other"


@dataclass
class NormalizationContext:
    strict: bool = False
    trace_enabled: bool = False
    trace: list[TraceEntry] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    def record(self, field_name: str, original: Any, transformed: Any, rule: str, status: str) -> None:
        if self.trace_enabled:
            self.trace.append(
                TraceEntry(
                    field=field_name,
                    original=original,
                    transformed=transformed,
                    rule=rule,
                    status=status,
                )
            )

    def add_issue(self, field_name: str, reason: str, kind: str, value: Any = None) -> None:
        self.issues.append(ValidationIssue(field=field_name, reason=reason, kind=kind, value=value))


SCHEMA_BY_TYPE: dict[str, type] = {
    "invoice_received": InvoiceReceivedData,
    "invoice_issued": InvoiceIssuedData,
    "bank_statement": BankStatementData,
}

REQUIRED_FIELDS_BY_TYPE: dict[str, list[str]] = {
    "invoice_received": ["issuer_name", "invoice_number", "total_amount"],
    "invoice_issued": ["issuer_name", "receiver_name", "invoice_number", "total_amount"],
    "bank_statement": ["bank_name", "period_start", "period_end"],
}

RANGE_RULES: dict[str, tuple[float, float]] = {
    "confidence_score": (0.0, 1.0),
    "tax_rate": (0.0, 100.0),
}

CURRENCY_ALIASES: dict[str, str] = {
    "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR",
    "$": "USD", "usd": "USD", "dollar": "USD", "dollars": "USD",
    "£": "GBP", "gbp": "GBP", "pound": "GBP", "pounds": "GBP",
    "¥": "JPY", "jpy": "JPY", "yen": "JPY",
    "chf": "CHF", "franc": "CHF", "francs": "CHF",
    "lei": "RON", "ron": "RON", "leu": "RON",
    "kr": "SEK", "sek": "SEK", "dkk": "DKK", "nok": "NOK",
    "zł": "PLN", "pln": "PLN",
    "kč": "CZK", "czk": "CZK",
    "ft": "HUF", "huf": "HUF",
    "лв": "BGN", "bgn": "BGN",
    "kn": "HRK", "hrk": "HRK",
}

LEGAL_SUFFIXES_RE = re.compile(
    r"\b(S\.?\s*L\.?\s*U?\.?|S\.?\s*A\.?|S\.?\s*C\.?|"
    r"S\.?\s*R\.?\s*L\.?|Ltd\.?|LLC|GmbH|AG|"
    r"B\.?\s*V\.?|N\.?\s*V\.?|Inc\.?|Corp\.?|"
    r"S\.?\s*A\.?\s*S\.?|E\.?\s*I\.?\s*R\.?\s*L\.?)\s*\.?\s*$",
    re.IGNORECASE,
)

PAYMENT_KEYWORDS: dict[str, str] = {
    "transferencia bancaria": "transfer",
    "transferencia": "transfer",
    "bank transfer": "transfer",
    "wire transfer": "transfer",
    "sepa": "transfer",
    "domiciliación": "direct_debit",
    "domiciliacion": "direct_debit",
    "direct debit": "direct_debit",
    "tarjeta de crédito": "card",
    "tarjeta": "card",
    "mastercard": "card",
    "visa": "card",
    "card": "card",
    "efectivo": "cash",
    "metálico": "cash",
    "cash": "cash",
    "cheque": "check",
    "check": "check",
    "paypal": "paypal",
    "bizum": "bizum",
    "confirming": "confirming",
    "pagaré": "promissory_note",
    "pagare": "promissory_note",
    "recibo": "receipt",
    "giro": "bank_draft",
}

ARITHMETIC_TOLERANCE_RATIO = 0.02
ARITHMETIC_TOLERANCE_MIN = 0.05


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
    """Split combined invoice number into (series, number) when series is missing.

    Returns the pair (series, invoice_number) unchanged when a series already
    exists or no splittable pattern is detected.
    """
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


def _propagate_tax_from_breakdown(
    line_items: list[Dict[str, Any]],
    tax_breakdown: list[Dict[str, Any]],
    ctx: NormalizationContext,
) -> list[Dict[str, Any]]:
    """Fill missing tax_rate in line items from a single-rate tax breakdown."""
    if not line_items or not tax_breakdown:
        return line_items
    rates = [tb["rate"] for tb in tax_breakdown if tb.get("rate") is not None]
    if len(rates) != 1:
        return line_items
    single_rate = rates[0]
    for item in line_items:
        if item.get("tax_rate") is None:
            item["tax_rate"] = single_rate
            ctx.record(
                "line_items.tax_rate", None, single_rate,
                "propagate_from_breakdown", "normalized",
            )
    return line_items


def normalize_date(date_str: Any) -> date | None:
    """Normalize date from many LLM-friendly formats.

    Supports:
    - date/datetime objects (idempotent)
    - Unix timestamp seconds/milliseconds
    - ISO8601 strings (with optional timezone and Z suffix)
    - Common locale formats: dd/mm/YYYY, dd-mm-YYYY, YYYY/mm/dd
    """
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
    """Convert numbers robustly from localized and noisy string formats.

    Returns ``None`` on malformed/ambiguous numeric values.
    """
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

    # Ambiguous values such as "12,3,4" or "1.2.3" are considered corrupt.
    if comma_count > 1 and dot_count == 0:
        return None
    if dot_count > 1 and comma_count == 0:
        return None

    if comma_count and dot_count:
        # Use the last separator as decimal separator and strip the others as thousand separators.
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


def normalize_list(items: Any, normalizer: Callable[[Dict[str, Any]], Dict[str, Any]]) -> list:
    """Normalize list items with the provided normalizer callback."""
    if not items or not isinstance(items, list):
        return []
    return [normalizer(item) for item in items if isinstance(item, dict)]


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
    if transformed is None and original not in (None, "", "null"):
        ctx.record(field_name, original, transformed, rule, "invalid")
        ctx.add_issue(field_name, invalid_reason, "invalid", value=original)
        return
    ctx.record(field_name, original, transformed, rule, "normalized")


def normalize_tax_item(item: Dict[str, Any], ctx: NormalizationContext | None = None, path: str = "tax_breakdown") -> Dict[str, Any]:
    """Normalize a tax breakdown item with optional trace support."""
    local_ctx = ctx or NormalizationContext()
    rate = normalize_number(item.get("rate"))
    base = normalize_number(item.get("base"))
    amount = normalize_number(item.get("amount"))
    _track_transform(local_ctx, f"{path}.rate", item.get("rate"), rate, "normalize_number", "invalid_number")
    _track_transform(local_ctx, f"{path}.base", item.get("base"), base, "normalize_number", "invalid_number")
    _track_transform(local_ctx, f"{path}.amount", item.get("amount"), amount, "normalize_number", "invalid_number")
    return {"rate": rate, "base": base, "amount": amount}


def normalize_tax_breakdown(items: Any, ctx: NormalizationContext | None = None, path: str = "tax_breakdown") -> list:
    """Normalize tax breakdown list."""
    local_ctx = ctx or NormalizationContext()
    if not items:
        local_ctx.record(path, items, [], "normalize_list", "missing")
        return []
    if not isinstance(items, list):
        local_ctx.record(path, items, [], "normalize_list", "invalid")
        local_ctx.add_issue(path, "expected_list", "invalid", value=items)
        return []
    result = [normalize_tax_item(item, local_ctx, f"{path}[{idx}]") for idx, item in enumerate(items) if isinstance(item, dict)]
    local_ctx.record(path, items, result, "normalize_tax_breakdown", "normalized")
    return result


def normalize_line_item(item: Dict[str, Any], ctx: NormalizationContext | None = None, path: str = "line_items") -> Dict[str, Any]:
    """Normalize a line item with optional trace support."""
    local_ctx = ctx or NormalizationContext()
    description = _clean_string(item.get("description"))
    quantity = normalize_number(item.get("quantity"))
    unit_price = normalize_number(item.get("unit_price"))
    base = normalize_number(item.get("base"))
    tax_rate = normalize_number(item.get("tax_rate"))
    tax_amount = normalize_number(item.get("tax_amount"))
    total = normalize_number(item.get("total"))

    _track_transform(local_ctx, f"{path}.description", item.get("description"), description, "clean_string", "invalid_string")
    _track_transform(local_ctx, f"{path}.quantity", item.get("quantity"), quantity, "normalize_number", "invalid_number")
    _track_transform(local_ctx, f"{path}.unit_price", item.get("unit_price"), unit_price, "normalize_number", "invalid_number")
    _track_transform(local_ctx, f"{path}.base", item.get("base"), base, "normalize_number", "invalid_number")
    _track_transform(local_ctx, f"{path}.tax_rate", item.get("tax_rate"), tax_rate, "normalize_number", "invalid_number")
    _track_transform(local_ctx, f"{path}.tax_amount", item.get("tax_amount"), tax_amount, "normalize_number", "invalid_number")
    _track_transform(local_ctx, f"{path}.total", item.get("total"), total, "normalize_number", "invalid_number")

    return {
        "description": description,
        "quantity": quantity,
        "unit_price": unit_price,
        "base": base,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total": total,
    }


def normalize_line_items(items: Any, ctx: NormalizationContext | None = None, path: str = "line_items") -> list:
    """Normalize line-item list."""
    local_ctx = ctx or NormalizationContext()
    if not items:
        local_ctx.record(path, items, [], "normalize_list", "missing")
        return []
    if not isinstance(items, list):
        local_ctx.record(path, items, [], "normalize_list", "invalid")
        local_ctx.add_issue(path, "expected_list", "invalid", value=items)
        return []
    result = [normalize_line_item(item, local_ctx, f"{path}[{idx}]") for idx, item in enumerate(items) if isinstance(item, dict)]
    local_ctx.record(path, items, result, "normalize_line_items", "normalized")
    return result


def _normalize_invoice_like(raw: Dict[str, Any], ctx: NormalizationContext, is_issued: bool) -> Dict[str, Any]:
    series, invoice_number = _split_invoice_series(
        _clean_string(raw.get("invoice_number")),
        _clean_string(raw.get("series")),
    )

    payment = _clean_string(raw.get("payment_method"))
    if not payment:
        payment = _detect_payment_method(raw)
        if payment:
            ctx.record("payment_method", None, payment, "detect_payment_method", "normalized")

    tax_breakdown = normalize_tax_breakdown(raw.get("tax_breakdown"), ctx, "tax_breakdown")
    line_items = normalize_line_items(raw.get("line_items"), ctx, "line_items")
    line_items = _propagate_tax_from_breakdown(line_items, tax_breakdown, ctx)

    result = {
        "issuer_name": _normalize_company_name(raw.get("issuer_name")),
        "issuer_tax_id": _normalize_tax_id(raw.get("issuer_tax_id")),
        "invoice_number": invoice_number,
        "series": series,
        "issue_date": normalize_date(raw.get("issue_date")),
        "due_date": normalize_date(raw.get("due_date")),
        "base_amount": normalize_number(raw.get("base_amount")),
        "tax_amount": normalize_number(raw.get("tax_amount")),
        "total_amount": normalize_number(raw.get("total_amount")),
        "currency": _normalize_currency(raw.get("currency")),
        "payment_method": payment,
        "tax_breakdown": tax_breakdown,
        "line_items": line_items,
    }

    if is_issued:
        result["receiver_name"] = _normalize_company_name(raw.get("receiver_name"))
        result["receiver_tax_id"] = _normalize_tax_id(raw.get("receiver_tax_id"))

    for key in (
        "issuer_name",
        "issuer_tax_id",
        "invoice_number",
        "series",
        "issue_date",
        "due_date",
        "base_amount",
        "tax_amount",
        "total_amount",
        "currency",
        "payment_method",
    ):
        source = raw.get(key)
        transformed = result.get(key)
        rule = "normalize_date" if key in {"issue_date", "due_date"} else "normalize_number"
        if key in {"issuer_name"}:
            rule = "normalize_company_name"
        elif key in {"series", "currency", "payment_method", "invoice_number"}:
            rule = "clean_string"
        elif key in {"issuer_tax_id", "receiver_tax_id"}:
            rule = "normalize_tax_id"
        _track_transform(ctx, key, source, transformed, rule, f"invalid_{key}")

    if is_issued:
        _track_transform(
            ctx,
            "receiver_name",
            raw.get("receiver_name"),
            result.get("receiver_name"),
            "normalize_company_name",
            "invalid_receiver_name",
        )
        _track_transform(
            ctx,
            "receiver_tax_id",
            raw.get("receiver_tax_id"),
            result.get("receiver_tax_id"),
            "normalize_tax_id",
            "invalid_receiver_tax_id",
        )

    return result


def normalize_invoice_received(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Normalize invoice_received documents."""
    return _normalize_invoice_like(raw, ctx or NormalizationContext(), is_issued=False)


def normalize_invoice_issued(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Normalize invoice_issued documents."""
    return _normalize_invoice_like(raw, ctx or NormalizationContext(), is_issued=True)


def normalize_bank_transaction(item: Dict[str, Any], ctx: NormalizationContext | None = None, path: str = "transactions") -> Dict[str, Any]:
    """Normalize a bank transaction."""
    local_ctx = ctx or NormalizationContext()
    result = {
        "date": normalize_date(item.get("date")),
        "description": _clean_string(item.get("description")),
        "amount": normalize_number(item.get("amount")),
        "type": _clean_string(item.get("type")),
        "balance": normalize_number(item.get("balance")),
        "reference": _clean_string(item.get("reference")),
        "counterparty": _clean_string(item.get("counterparty")),
    }
    _track_transform(local_ctx, f"{path}.date", item.get("date"), result["date"], "normalize_date", "invalid_date")
    _track_transform(local_ctx, f"{path}.amount", item.get("amount"), result["amount"], "normalize_number", "invalid_amount")
    _track_transform(local_ctx, f"{path}.balance", item.get("balance"), result["balance"], "normalize_number", "invalid_balance")
    return result


def normalize_bank_statement(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Normalize bank_statement documents."""
    local_ctx = ctx or NormalizationContext()
    transactions_raw = raw.get("transactions", [])
    if not isinstance(transactions_raw, list):
        local_ctx.add_issue("transactions", "expected_list", "invalid", value=transactions_raw)
        transactions_raw = []

    result = {
        "bank_name": _clean_string(raw.get("bank_name")),
        "account_holder": _normalize_company_name(raw.get("account_holder")),
        "iban": _clean_string(raw.get("iban")),
        "currency": _normalize_currency(raw.get("currency")),
        "period_start": normalize_date(raw.get("period_start")),
        "period_end": normalize_date(raw.get("period_end")),
        "opening_balance": normalize_number(raw.get("opening_balance")),
        "closing_balance": normalize_number(raw.get("closing_balance")),
        "transactions": [
            normalize_bank_transaction(item, local_ctx, f"transactions[{idx}]")
            for idx, item in enumerate(transactions_raw)
            if isinstance(item, dict)
        ],
    }

    for key in (
        "bank_name",
        "account_holder",
        "iban",
        "currency",
        "period_start",
        "period_end",
        "opening_balance",
        "closing_balance",
    ):
        source = raw.get(key)
        transformed = result.get(key)
        if key in {"period_start", "period_end"}:
            rule = "normalize_date"
        elif key in {"opening_balance", "closing_balance"}:
            rule = "normalize_number"
        else:
            rule = "clean_string"
        _track_transform(local_ctx, key, source, transformed, rule, f"invalid_{key}")

    return result


def normalize_generic(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Fallback normalizer that preserves fields while cleaning obvious string noise."""
    local_ctx = ctx or NormalizationContext()
    out: Dict[str, Any] = {}
    for key, value in raw.items():
        cleaned = _clean_string(value) if isinstance(value, str) else value
        out[key] = cleaned
        local_ctx.record(key, value, cleaned, "normalize_generic", "normalized")
    return out


NORMALIZERS: dict[str, Callable[[Dict[str, Any], NormalizationContext | None], Dict[str, Any]]] = {
    "invoice_received": normalize_invoice_received,
    "invoice_issued": normalize_invoice_issued,
    "bank_statement": normalize_bank_statement,
}


def register_normalizer(document_type: str, normalizer: Callable[[Dict[str, Any], NormalizationContext | None], Dict[str, Any]]) -> None:
    """Register a custom normalizer for a document type."""
    NORMALIZERS[document_type] = normalizer


def _validate_required_fields(normalized: Dict[str, Any], document_type: str, ctx: NormalizationContext) -> None:
    for field_name in REQUIRED_FIELDS_BY_TYPE.get(document_type, []):
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
    schema = SCHEMA_BY_TYPE.get(document_type)
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

    line_items = normalized.get("line_items", [])
    if line_items and base is not None:
        line_bases = [item.get("base") or item.get("total") or 0 for item in line_items]
        line_sum = sum(line_bases)
        if line_sum > 0:
            tolerance = max(ARITHMETIC_TOLERANCE_MIN, abs(base) * ARITHMETIC_TOLERANCE_RATIO)
            if abs(line_sum - base) > tolerance:
                ctx.add_issue(
                    "line_items",
                    f"line_items_sum_mismatch: sum({line_sum:.2f}) != base({base})",
                    "invalid",
                )


def _check_type_coherence(
    normalized: Dict[str, Any], document_type: str, ctx: NormalizationContext,
) -> None:
    """Warn when document content contradicts the declared type."""
    if document_type in ("invoice_received", "invoice_issued"):
        has_invoice_fields = any(
            normalized.get(f) for f in ("invoice_number", "total_amount", "issuer_name")
        )
        if not has_invoice_fields:
            ctx.add_issue(
                "document_type",
                f"type_coherence: {document_type} lacks key invoice fields",
                "invalid",
            )
    elif document_type == "bank_statement":
        if normalized.get("invoice_number"):
            ctx.add_issue(
                "document_type",
                "type_coherence: bank_statement has invoice_number",
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


def normalize_document_with_report(
    data: Dict[str, Any],
    document_type: str,
    *,
    strict: bool = False,
    trace: bool = False,
) -> NormalizationReport:
    """Normalize with optional strict mode and full traceability report.

    This API is production-oriented and resilient to malformed LLM output.
    Existing callers can keep using ``normalize_document``.
    """
    ctx = NormalizationContext(strict=strict, trace_enabled=trace)

    if not isinstance(data, dict):
        ctx.add_issue("data", "expected_dict", "invalid", value=data)
        if strict:
            _finalize_validation(document_type, {}, ctx)
        data = {}

    normalizer = NORMALIZERS.get(document_type, normalize_generic)
    normalized = normalizer(data, ctx)
    _finalize_validation(document_type, normalized, ctx)

    return NormalizationReport(
        normalized=normalized,
        trace=ctx.trace,
        issues=ctx.issues,
        document_type=document_type,
    )


def normalize_document(data: Dict[str, Any], document_type: str) -> Dict[str, Any]:
    """Backward-compatible dispatcher used by the ingestion pipeline.

    Default behavior is tolerant (strict=False) and without trace to preserve
    current API and avoid breaking existing callers.
    """
    report = normalize_document_with_report(data, document_type, strict=False, trace=False)
    return report.normalized


def normalize_extracted_data(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Backward-compatible alias. Prefer ``normalize_document``."""
    return normalize_invoice_received(raw)


def dates_to_firestore(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert date fields to datetime for Firestore compatibility."""
    result = dict(data)
    for field_name in DATE_FIELDS:
        value = result.get(field_name)
        if isinstance(value, datetime):
            result[field_name] = datetime.combine(value.date(), datetime.min.time())
        elif isinstance(value, date):
            result[field_name] = datetime.combine(value, datetime.min.time())
    return result