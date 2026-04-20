import re

DATE_FIELDS = [
    "issue_date", "billing_period_start", "billing_period_end",
    "payment_date", "deadline", "document_date", "contract_date",
]

# Pre-compiled regexes for optimal performance
INVISIBLE_CHARS_RE = re.compile(r"[\u200B\u200C\u200D\u2060\uFEFF]")
NIF_CIF_RE = re.compile(r"^[A-Z0-9]{8,12}$")
WHITESPACE_RE = re.compile(r"\s+")
NON_ALPHANUMERIC_RE = re.compile(r"[^A-Za-z0-9]")
NON_NUMERIC_RE = re.compile(r"[^0-9,\.]")

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

ARITHMETIC_TOLERANCE_RATIO = 0.001  # 0.1% (stricter than before: was 0.02)
ARITHMETIC_TOLERANCE_MIN = 0.01     # €0.01 (stricter than before: was 0.05)

# ---------------------------------------------------------------------------
# Spanish tax system
# ---------------------------------------------------------------------------

TAX_TYPE_ALIASES: dict[str, str] = {
    # IVA
    "iva": "iva", "i.v.a.": "iva", "i.v.a": "iva",
    "vat": "iva", "impuesto valor añadido": "iva",
    "impuesto sobre el valor añadido": "iva",
    "impuesto sobre el valor anadido": "iva",
    # Recargo de equivalencia
    "re": "re", "r.e.": "re", "recargo": "re",
    "recargo de equivalencia": "re", "recargo equiv": "re",
    "rec. equiv.": "re", "rec equiv": "re",
    "recargo equivalencia": "re",
    # IGIC (Canarias)
    "igic": "igic", "i.g.i.c.": "igic", "i.g.i.c": "igic",
    "impuesto general indirecto canario": "igic",
    # IPSI (Ceuta y Melilla)
    "ipsi": "ipsi", "i.p.s.i.": "ipsi", "i.p.s.i": "ipsi",
    # IRPF
    "irpf": "irpf", "i.r.p.f.": "irpf", "i.r.p.f": "irpf",
    "retencion": "irpf", "retención": "irpf",
    "retención irpf": "irpf", "retencion irpf": "irpf",
    "ret. irpf": "irpf", "ret irpf": "irpf",
    "retencion a cuenta": "irpf", "retención a cuenta": "irpf",
}

ADDITIVE_TAX_TYPES: set[str] = {"iva", "re", "igic", "ipsi"}
RETENTION_TAX_TYPES: set[str] = {"irpf"}

SPANISH_TAX_RATES: dict[str, list[float]] = {
    "iva":  [0.0, 4.0, 10.0, 21.0],
    "re":   [0.0, 0.5, 1.4, 5.2],
    "igic": [0.0, 3.0, 7.0, 9.5, 15.0],
    "ipsi": [0.5, 1.0, 2.0, 4.0, 8.0, 10.0],
    "irpf": [1.0, 2.0, 7.0, 15.0, 19.0],
}

RE_IVA_PAIRS: dict[float, float] = {
    21.0: 5.2,
    10.0: 1.4,
    4.0:  0.5,
    0.0:  0.0,
}

RATE_SNAP_TOLERANCE = 0.5
