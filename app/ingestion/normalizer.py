# normalizer.py
import re
from datetime import datetime, date
from typing import Any, Dict

def normalize_date(date_str: str | None) -> date | None:
    if not date_str or date_str == "null":
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(date_str, "%d/%m/%Y").date()
    except ValueError:
        return None

def normalize_number(value: Any) -> float | None:
    """Convierte a float, manejando comas decimales y cadenas vacías."""
    if value is None or value == "null":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Reemplazar coma decimal por punto
        value = value.replace(',', '.')
        # Eliminar espacios y separadores de miles (puntos, comas, etc.)
        value = re.sub(r'[^\d.-]', '', value)
        try:
            return float(value)
        except ValueError:
            return None
    return None

def normalize_tax_breakdown(items: Any) -> list:
    """Normaliza la lista de desglose de impuestos."""
    if not items:
        return []
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized.append({
            "rate": normalize_number(item.get("rate")),
            "base": normalize_number(item.get("base")),
            "amount": normalize_number(item.get("amount"))
        })
    return normalized

def normalize_line_items(items: Any) -> list:
    """Normaliza la lista de líneas de detalle."""
    if not items:
        return []
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized.append({
            "description": str(item.get("description", "")).strip() or None,
            "quantity": normalize_number(item.get("quantity")),
            "unit_price": normalize_number(item.get("unit_price")),
            "base": normalize_number(item.get("base")),
            "tax_rate": normalize_number(item.get("tax_rate")),
            "tax_amount": normalize_number(item.get("tax_amount")),
            "total": normalize_number(item.get("total"))
        })
    return normalized

def normalize_extracted_data(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica todas las normalizaciones al diccionario extraído."""
    return {
        "issuer_name": raw.get("issuer_name") or None,
        "issuer_tax_id": raw.get("issuer_tax_id") or None,
        "invoice_number": raw.get("invoice_number") or None,
        "series": raw.get("series") or None,
        "issue_date": normalize_date(raw.get("issue_date")),
        "due_date": normalize_date(raw.get("due_date")),
        "base_amount": normalize_number(raw.get("base_amount")),
        "tax_amount": normalize_number(raw.get("tax_amount")),
        "total_amount": normalize_number(raw.get("total_amount")),
        "currency": raw.get("currency", "EUR") or "EUR",
        "payment_method": raw.get("payment_method") or None,
        "tax_breakdown": normalize_tax_breakdown(raw.get("tax_breakdown")),
        "line_items": normalize_line_items(raw.get("line_items"))
    }