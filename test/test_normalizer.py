# tests/test_normalizer.py

import pytest
from datetime import date
from app.ingestion.normalizer import (
    normalize_date,
    normalize_number,
    normalize_document,
    normalize_document_with_report,
    _normalize_currency,
    _normalize_company_name,
    _split_invoice_series,
    _detect_payment_method,
    _cross_check_arithmetic,
    _check_type_coherence,
    NormalizationContext,
)
from app.models.registry import DocumentTypeConfig, register_document_type


# ---------------------------------------------------------------------------
# normalize_number
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (None,      None),
    ("",        None),
    ("null",    None),
    (0,         0.0),
    (42,        42.0),
    (3.14,      3.14),
    ("100.50",  100.50),
    ("100,50",  100.50),   # coma decimal española
    ("-21.0",   -21.0),
])
def test_normalize_number(value, expected):
    result = normalize_number(value)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_normalize_number_non_numeric_string():
    assert normalize_number("abc") is None


# ---------------------------------------------------------------------------
# normalize_date
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (None,          None),
    ("",            None),
    ("null",        None),
    ("2024-01-15",  date(2024, 1, 15)),
    ("15/01/2024",  date(2024, 1, 15)),
])
def test_normalize_date(value, expected):
    assert normalize_date(value) == expected


def test_normalize_date_formato_invalido():
    assert normalize_date("01-15-2024") is None  # formato no soportado


# ---------------------------------------------------------------------------
# normalize_document — dispatch por tipo
# ---------------------------------------------------------------------------

def test_normalize_document_invoice_received():
    raw = {
        "issuer_name": "Empresa SL",
        "issue_date": "2024-01-10",
        "base_amount": "100,50",
        "tax_amount": "21.10",
        "total_amount": "121.60",
        "currency": None,
        "concept": "Servicios enero",
    }
    result = normalize_document(raw, "invoice_received")

    assert result["issuer_name"] == "Empresa SL"
    assert result["issue_date"] == date(2024, 1, 10)
    assert result["base_amount"] == pytest.approx(100.50)
    assert result["currency"] == "EUR"    # fallback cuando currency=None
    assert result["concept"] == "Servicios enero"


def test_normalize_document_invoice_sent():
    raw = {
        "client_name": "Cliente SA",
        "issuer_name": "Proveedor SL",
        "total_amount": 500,
        "currency": "USD",
    }
    result = normalize_document(raw, "invoice_sent")

    assert result["client_name"] == "Cliente SA"
    assert result["issuer_name"] == "Proveedor SL"
    assert result["total_amount"] == pytest.approx(500.0)
    assert result["currency"] == "USD"


def test_normalize_document_bank_document():
    raw = {
        "bank_name": "Banco Test",
        "iban": "ES00 0000 0000 0000 0000 0000",
        "document_date": "2024-01-15",
        "movements": [
            {"date": "2024-01-15", "description": "Pago", "amount": "200", "balance_after": "1200"},
        ],
    }
    result = normalize_document(raw, "bank_document")

    assert result["bank_name"] == "Banco Test"
    assert result["document_date"] == date(2024, 1, 15)
    assert len(result["movements"]) == 1
    assert result["movements"][0]["amount"] == pytest.approx(200.0)


def test_normalize_document_other_devuelve_raw():
    """Tipos no mapeados devuelven el raw sin modificar."""
    raw = {"campo_custom": "valor", "num": 42}
    result = normalize_document(raw, "other")
    assert result == raw


def test_normalize_document_tipo_desconocido_usa_generic():
    raw = {"x": 1}
    result = normalize_document(raw, "tipo_inventado")
    assert result == raw


# ---------------------------------------------------------------------------
# Alias de compatibilidad
# ---------------------------------------------------------------------------

def test_normalize_document_listas_vacias():
    raw = {"concept": None}
    result = normalize_document(raw, "invoice_received")
    assert result["concept"] is None


def test_normalize_document_campos_nulos():
    result = normalize_document({}, "invoice_received")
    assert result["issuer_name"] is None
    assert result["issue_date"] is None
    assert result["total_amount"] is None
    assert result["currency"] == "EUR"


# ---------------------------------------------------------------------------
# dates_to_firestore
# ---------------------------------------------------------------------------

from datetime import datetime
from app.ingestion.normalizer import dates_to_firestore


def test_dates_to_firestore_converts_date_fields():
    """date objects in known fields are converted to datetime."""
    normalized = {
        "issuer_name": "SL",
        "issue_date": date(2024, 3, 15),
        "billing_period_start": date(2024, 3, 1),
        "billing_period_end": None,
        "total_amount": 100.0,
    }
    result = dates_to_firestore(normalized)

    assert isinstance(result["issue_date"], datetime)
    assert result["issue_date"] == datetime(2024, 3, 15, 0, 0, 0)
    assert isinstance(result["billing_period_start"], datetime)
    assert result["billing_period_start"] == datetime(2024, 3, 1, 0, 0, 0)
    # None fields are left as None
    assert result["billing_period_end"] is None
    # Non-date fields are untouched
    assert result["issuer_name"] == "SL"
    assert result["total_amount"] == 100.0


def test_dates_to_firestore_normalizes_datetime_to_midnight():
    """datetime objects are normalized to midnight datetime (Firestore consistency)."""
    dt = datetime(2024, 6, 1, 12, 0, 0)
    result = dates_to_firestore({"issue_date": dt})
    # datetime is a subclass of date, so it is also normalized to midnight
    assert result["issue_date"] == datetime(2024, 6, 1, 0, 0, 0)


def test_dates_to_firestore_does_not_mutate_original():
    """The original dict is not modified."""
    original = {"issue_date": date(2024, 1, 1)}
    dates_to_firestore(original)
    assert isinstance(original["issue_date"], date)
    assert not isinstance(original["issue_date"], datetime)


def test_dates_to_firestore_ignores_unknown_fields():
    """Fields not in DATE_FIELDS are not converted."""
    data = {"custom_date": date(2024, 1, 1), "amount": 50.0}
    result = dates_to_firestore(data)
    # custom_date is not a known date field and should remain a date
    assert isinstance(result["custom_date"], date)
    assert result["amount"] == 50.0


def test_dates_to_firestore_empty_dict():
    assert dates_to_firestore({}) == {}


# ---------------------------------------------------------------------------
# Robust mode and tracing
# ---------------------------------------------------------------------------

def test_normalize_document_with_report_tolerant_collects_issues():
    raw = {
        "issuer_name": "\u200b Empresa   SL ",
        "invoice_number": None,
        "total_amount": "12,3,4",  # corrupt numeric format
    }

    report = normalize_document_with_report(raw, "invoice_received", strict=False, trace=True)

    assert report.normalized["issuer_name"] == "Empresa SL"
    assert report.normalized["total_amount"] is None
    assert len(report.issues) >= 1
    assert any(issue.kind in ("invalid", "missing") for issue in report.issues)
    assert len(report.trace) >= 1
    assert any(entry.status in ("missing", "invalid", "normalized") for entry in report.trace)


def test_normalize_document_with_report_strict_raises_on_issues():
    raw = {
        "issuer_name": "Empresa SL",
        "invoice_number": None,  # required field missing in strict mode
        "total_amount": "100,00",
    }

    with pytest.raises(ValueError, match="Normalization failed"):
        normalize_document_with_report(raw, "invoice_received", strict=True, trace=False)


def test_normalize_number_handles_eu_and_us_formats():
    assert normalize_number("1.234,56") == pytest.approx(1234.56)
    assert normalize_number("1,234.56") == pytest.approx(1234.56)


def test_normalize_date_accepts_iso_datetime_and_timestamp():
    assert normalize_date("2024-01-15T12:00:00Z") == date(2024, 1, 15)
    assert normalize_date(1705276800) == date(2024, 1, 15)


def test_registry_supports_custom_normalizer():
    def custom_normalizer(data, _ctx=None):
        return {"custom": True, "input": data.get("x")}

    register_document_type(DocumentTypeConfig(document_type="custom_doc", normalizer=custom_normalizer))
    result = normalize_document({"x": "ok"}, "custom_doc")
    assert result == {"custom": True, "input": "ok"}


# ---------------------------------------------------------------------------
# _normalize_currency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (None, "EUR"),
    ("", "EUR"),
    ("€", "EUR"),
    ("euro", "EUR"),
    ("euros", "EUR"),
    ("EUR", "EUR"),
    ("eur", "EUR"),
    ("$", "USD"),
    ("USD", "USD"),
    ("usd", "USD"),
    ("£", "GBP"),
    ("lei", "RON"),
    ("RON", "RON"),
    ("CHF", "CHF"),
    ("XYZ", "XYZ"),  # unknown 3-letter code passed through
    ("gibberish", "EUR"),  # unrecognized falls back to EUR
])
def test_normalize_currency(value, expected):
    assert _normalize_currency(value) == expected


# ---------------------------------------------------------------------------
# _normalize_company_name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (None, None),
    ("", None),
    ("Empresa SL", "Empresa SL"),  # mixed case — unchanged
    ("ACME SL", "Acme SL"),  # ALL CAPS — title case + suffix
    ("acme sl", "Acme SL"),  # all lower — title case + suffix
    ("CONSTRUCTORA S.L.", "Constructora S.L."),  # dotted suffix
    ("JOHN DOE", "John Doe"),  # no legal suffix
    ("eBay", "eBay"),  # mixed case — preserved as-is
    ("EMPRESA S. L. U.", "Empresa S.L.U."),  # spaced suffix → collapsed
])
def test_normalize_company_name(value, expected):
    assert _normalize_company_name(value) == expected


# ---------------------------------------------------------------------------
# _split_invoice_series
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("invoice_number,existing_series,expected", [
    (None, None, (None, None)),
    ("12345", None, (None, "12345")),
    ("F156862C-5742", None, ("F156862C", "5742")),
    ("FRA/001", None, ("FRA", "001")),
    ("12345", "A", ("A", "12345")),  # existing series preserved
    ("123-456", None, (None, "123-456")),  # both sides numeric — no split
])
def test_split_invoice_series(invoice_number, existing_series, expected):
    assert _split_invoice_series(invoice_number, existing_series) == expected


# ---------------------------------------------------------------------------
# _detect_payment_method
# ---------------------------------------------------------------------------

def test_detect_payment_method_finds_transfer():
    raw = {"notes": "Pago por transferencia bancaria", "issuer_name": "Acme"}
    assert _detect_payment_method(raw) == "transfer"


def test_detect_payment_method_finds_card():
    raw = {"description": "Pagado con VISA"}
    assert _detect_payment_method(raw) == "card"


def test_detect_payment_method_returns_none():
    raw = {"issuer_name": "Empresa SL", "total": "100"}
    assert _detect_payment_method(raw) is None


def test_detect_payment_method_prefers_longest_keyword():
    raw = {"notes": "transferencia bancaria confirmada"}
    # "transferencia bancaria" (longer) should match before "transferencia"
    assert _detect_payment_method(raw) == "transfer"


# ---------------------------------------------------------------------------
# _cross_check_arithmetic
# ---------------------------------------------------------------------------

def test_cross_check_arithmetic_valid():
    ctx = NormalizationContext()
    normalized = {"base_amount": 100.0, "tax_amount": 21.0, "total_amount": 121.0}
    _cross_check_arithmetic(normalized, ctx)
    assert not ctx.issues


def test_cross_check_arithmetic_mismatch():
    ctx = NormalizationContext()
    normalized = {"base_amount": 100.0, "tax_amount": 21.0, "total_amount": 200.0}
    _cross_check_arithmetic(normalized, ctx)
    assert any("arithmetic_mismatch" in issue.reason for issue in ctx.issues)


def test_cross_check_arithmetic_skips_when_null():
    ctx = NormalizationContext()
    normalized = {"base_amount": None, "tax_amount": None, "total_amount": None}
    _cross_check_arithmetic(normalized, ctx)
    assert not ctx.issues


def test_cross_check_arithmetic_tolerates_rounding():
    ctx = NormalizationContext()
    # 100.0 + 21.0 = 121.0 but total says 121.01 — within tolerance
    normalized = {"base_amount": 100.0, "tax_amount": 21.0, "total_amount": 121.01}
    _cross_check_arithmetic(normalized, ctx)
    assert not ctx.issues


# ---------------------------------------------------------------------------
# _check_type_coherence
# ---------------------------------------------------------------------------

def test_type_coherence_invoice_ok():
    ctx = NormalizationContext()
    normalized = {"invoice_number": "F-001", "total_amount": 100.0, "issuer_name": "Acme"}
    _check_type_coherence(normalized, "invoice_received", ctx)
    assert not ctx.issues


def test_type_coherence_invoice_lacks_fields():
    ctx = NormalizationContext()
    normalized = {"invoice_number": None, "total_amount": None, "issuer_name": None}
    _check_type_coherence(normalized, "invoice_received", ctx)
    assert any("type_coherence" in issue.reason for issue in ctx.issues)


def test_type_coherence_bank_document_with_invoice_number():
    ctx = NormalizationContext()
    normalized = {"invoice_number": "F-001", "bank_name": "BBVA"}
    _check_type_coherence(normalized, "bank_document", ctx)
    assert any("type_coherence" in issue.reason for issue in ctx.issues)


# ---------------------------------------------------------------------------
# Integration: end-to-end with new features
# ---------------------------------------------------------------------------

def test_invoice_currency_symbol_normalized():
    raw = {"currency": "€", "total_amount": "100"}
    result = normalize_document(raw, "invoice_received")
    assert result["currency"] == "EUR"


def test_invoice_company_name_all_caps_normalized():
    raw = {"issuer_name": "ACME CORP", "total_amount": "100"}
    result = normalize_document(raw, "invoice_received")
    assert result["issuer_name"] == "Acme CORP"


def test_arithmetic_mismatch_reported_in_report():
    raw = {
        "issuer_name": "Acme",
        "invoice_number": "001",
        "base_amount": "100",
        "tax_amount": "21",
        "total_amount": "999",  # wrong
    }
    report = normalize_document_with_report(raw, "invoice_received", strict=False)
    assert any("arithmetic_mismatch" in issue.reason for issue in report.issues)