"""Tax ID classification and normalization.

Supports:
- Spanish NIF persona física (8 digits + letter)
- Spanish NIF empresa (letter + 7 digits + control)
- Spanish NIE (X/Y/Z + 7 digits + letter)
- EU VAT numbers (2-letter country prefix + digits)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TaxId:
    """Structured representation of a fiscal identifier."""
    tax_id: str        # Normalized ID (e.g. "B12345678")
    tax_country: str   # ISO 3166-1 alpha-2 (e.g. "ES")
    tax_type: str      # "person" | "company" | "nie" | "vat_eu"


# Spanish CIF letters indicating company type
# Z = S.A.T. / A.I.E., T = Uniones Temporales de Empresas
_ES_COMPANY_PREFIXES = set("ABCDEFGHJNPQRSUVWZT")

# EU VAT country prefixes (2-letter ISO codes with known VAT systems)
_EU_VAT_COUNTRIES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK", "XI",
}

# Regex patterns
_RE_ES_NIF_PERSONA = re.compile(r"^\d{8}[A-Z]$")
_RE_ES_CIF = re.compile(r"^[A-Z]\d{7}[A-Z0-9]$")
_RE_ES_NIE = re.compile(r"^[XYZ]\d{7}[A-Z]$")
_RE_EU_VAT = re.compile(r"^([A-Z]{2})(\w{2,13})$")


def normalize_tax_id_raw(value: str) -> str:
    """Strip whitespace, dashes, dots, and uppercase."""
    return re.sub(r"[\s\-./]", "", value).upper()


def classify_tax_id(raw: str) -> Optional[TaxId]:
    """Classify a raw tax identifier string.

    Returns a TaxId with country and type, or None if unrecognizable.
    """
    clean = normalize_tax_id_raw(raw)
    if not clean:
        return None

    # 1. Spanish NIF persona física: 8 digits + letter (e.g. "12345678Z")
    if _RE_ES_NIF_PERSONA.match(clean):
        return TaxId(tax_id=clean, tax_country="ES", tax_type="person")

    # 2. Spanish NIE: X/Y/Z + 7 digits + letter (e.g. "X1234567L")
    if _RE_ES_NIE.match(clean):
        return TaxId(tax_id=clean, tax_country="ES", tax_type="nie")

    # 3. Spanish CIF/NIF empresa: letter + 7 digits + control (e.g. "B12345678")
    if _RE_ES_CIF.match(clean) and clean[0] in _ES_COMPANY_PREFIXES:
        return TaxId(tax_id=clean, tax_country="ES", tax_type="company")

    # 4. EU VAT: 2-letter country + alphanumeric (e.g. "FR12345678901")
    m = _RE_EU_VAT.match(clean)
    if m:
        country = m.group(1)
        if country in _EU_VAT_COUNTRIES:
            # If it starts with "ES" followed by a valid NIF/CIF, it's Spanish VAT
            rest = m.group(2)
            if country == "ES":
                inner = classify_tax_id(rest)
                if inner:
                    return TaxId(tax_id=rest, tax_country="ES", tax_type=inner.tax_type)
            return TaxId(tax_id=clean, tax_country=country, tax_type="vat_eu")

    # 5. Fallback: if it looks like a Spanish CIF with a valid letter but didn't match
    #    strict pattern (e.g. 9-char B + 8 digits), try relaxed match
    if len(clean) == 9 and clean[0] in _ES_COMPANY_PREFIXES and clean[1:].isdigit():
        return TaxId(tax_id=clean, tax_country="ES", tax_type="company")

    return None


def tax_ids_match(a: str, b: str) -> bool:
    """Return True if two tax identifiers refer to the same entity.

    Comparison layers (returns True on first hit):
    1. Direct match after stripping whitespace/punctuation.
    2. Match after stripping country prefix via ``classify_tax_id``
       (e.g. ``"ESB12345678"`` vs ``"B12345678"``).
    3. Suffix containment — one cleaned value ends with the other's
       canonical ID.  Covers junk prefixes from OCR/Gemini
       (e.g. ``"NIFQ24615910"`` contains ``"Q24615910"``).
    """
    norm_a = normalize_tax_id_raw(a)
    norm_b = normalize_tax_id_raw(b)
    if norm_a == norm_b:
        return True
    # Layer 2: strip country prefix via classification
    cls_a = classify_tax_id(norm_a)
    cls_b = classify_tax_id(norm_b)
    id_a = cls_a.tax_id if cls_a else norm_a
    id_b = cls_b.tax_id if cls_b else norm_b
    if id_a == id_b:
        return True
    # Layer 3: suffix containment — covers "NIF", "CIF", or other
    # junk prefixes that classify_tax_id doesn't recognize.
    return norm_a.endswith(id_b) or norm_b.endswith(id_a)
