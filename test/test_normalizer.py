# tests/test_normalizer.py

from app.ingestion.normalizer import normalize_extracted_data

def test_normalize_extracted_data_basic():
    raw = {
        "issuer_name": "Empresa SL",
        "issue_date": "2024-01-10",
        "base_amount": "100,50",
        "tax_amount": "21.10",
        "total_amount": "121.60",
        "currency": None,
        "tax_breakdown": [
            {"rate": "21", "base": "100,50", "amount": "21.10"}
        ],
        "line_items": [
            {"description": "Producto", "quantity": "1", "unit_price": "100,50"}
        ]
    }

    result = normalize_extracted_data(raw)

    assert result["issuer_name"] == "Empresa SL"
    assert result["issue_date"].year == 2024
    assert result["base_amount"] == 100.50
    assert result["currency"] == "EUR"
    assert isinstance(result["tax_breakdown"], list)
    assert isinstance(result["line_items"], list)