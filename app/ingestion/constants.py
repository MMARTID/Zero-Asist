import re

DATE_FIELDS = [
    "issue_date", "billing_period_start", "billing_period_end",
    "payment_date", "deadline", "document_date", "contract_date",
]

INVISIBLE_CHARS_RE = re.compile(r"[\u200B\u200C\u200D\u2060\uFEFF]")
NIF_CIF_RE = re.compile(r"^[A-Z0-9]{8,12}$")

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
