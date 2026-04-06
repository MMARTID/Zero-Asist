# tests/test_normalizer.py

import pytest
from datetime import date
from app.ingestion.normalizer import (
    normalize_date,
    normalize_number,
    normalize_document,
    normalize_extracted_data,
)


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
        "tax_breakdown": [{"rate": "21", "base": "100,50", "amount": "21.10"}],
        "line_items": [{"description": "Producto", "quantity": "1", "unit_price": "100,50"}],
    }
    result = normalize_document(raw, "invoice_received")

    assert result["issuer_name"] == "Empresa SL"
    assert result["issue_date"] == date(2024, 1, 10)
    assert result["base_amount"] == pytest.approx(100.50)
    assert result["currency"] == "EUR"    # fallback cuando currency=None
    assert len(result["tax_breakdown"]) == 1
    assert result["tax_breakdown"][0]["rate"] == pytest.approx(21.0)
    assert len(result["line_items"]) == 1


def test_normalize_document_invoice_issued():
    raw = {
        "receiver_name": "Cliente SA",
        "issuer_name": "Proveedor SL",
        "total_amount": 500,
        "currency": "USD",
    }
    result = normalize_document(raw, "invoice_issued")

    assert result["receiver_name"] == "Cliente SA"
    assert result["issuer_name"] == "Proveedor SL"
    assert result["total_amount"] == pytest.approx(500.0)
    assert result["currency"] == "USD"


def test_normalize_document_bank_statement():
    raw = {
        "bank_name": "Banco Test",
        "iban": "ES00 0000 0000 0000 0000 0000",
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "opening_balance": "1000",
        "closing_balance": "1200",
        "transactions": [
            {"date": "2024-01-15", "description": "Pago", "amount": "200", "type": "credit"},
        ],
    }
    result = normalize_document(raw, "bank_statement")

    assert result["bank_name"] == "Banco Test"
    assert result["period_start"] == date(2024, 1, 1)
    assert result["opening_balance"] == pytest.approx(1000.0)
    assert len(result["transactions"]) == 1
    assert result["transactions"][0]["amount"] == pytest.approx(200.0)


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

def test_normalize_extracted_data_basic():
    raw = {
        "issuer_name": "Empresa SL",
        "issue_date": "2024-01-10",
        "base_amount": "100,50",
        "tax_amount": "21.10",
        "total_amount": "121.60",
        "currency": None,
        "tax_breakdown": [{"rate": "21", "base": "100,50", "amount": "21.10"}],
        "line_items": [{"description": "Producto", "quantity": "1", "unit_price": "100,50"}],
    }
    result = normalize_extracted_data(raw)

    assert result["issuer_name"] == "Empresa SL"
    assert result["issue_date"].year == 2024
    assert result["base_amount"] == pytest.approx(100.50)
    assert result["currency"] == "EUR"
    assert isinstance(result["tax_breakdown"], list)
    assert isinstance(result["line_items"], list)


def test_normalize_document_listas_vacias():
    raw = {"tax_breakdown": [], "line_items": None}
    result = normalize_document(raw, "invoice_received")
    assert result["tax_breakdown"] == []
    assert result["line_items"] == []


def test_normalize_document_campos_nulos():
    result = normalize_document({}, "invoice_received")
    assert result["issuer_name"] is None
    assert result["issue_date"] is None
    assert result["total_amount"] is None
    assert result["currency"] == "EUR"