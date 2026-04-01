import re
from datetime import datetime, date
from typing import Any, Dict, Callable, List

def normalize_date(date_str: str | None) -> date | None:
    if not date_str or date_str == "null":
        return None
    date_formats = ["%Y-%m-%d", "%d/%m/%Y"]  # Lista de formatos soportados
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None

def normalize_number(value: Any) -> float | None:
    """Convierte a float, manejando comas decimales y cadenas vacías."""
    if value in (None, "null", ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.replace(',', '.')
        value = re.sub(r'[^\d.-]', '', value)  # Limpia caracteres no numéricos
        try:
            return float(value)
        except ValueError:
            return None
    return None

def normalize_list(items: Any, normalizer: Callable[[Dict[str, Any]], Dict[str, Any]]) -> list:
    """
    Normaliza listas de elementos con un normalizador específico.

    Args:
        items: Lista de elementos a procesar.
        normalizer: Función que procesa cada elemento individual.
    """
    if not items or not isinstance(items, list):
        return []
    return [normalizer(item) for item in items if isinstance(item, dict)]

def normalize_tax_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza un único desglose de impuestos."""
    return {
        "rate": normalize_number(item.get("rate")),
        "base": normalize_number(item.get("base")),
        "amount": normalize_number(item.get("amount"))
    }

def normalize_tax_breakdown(items: Any) -> list:
    """Normaliza la lista de desglose de impuestos."""
    return normalize_list(items, normalize_tax_item)

def normalize_line_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza un único elemento de línea."""
    return {
        "description": str(item.get("description", "")).strip() or None,
        "quantity": normalize_number(item.get("quantity")),
        "unit_price": normalize_number(item.get("unit_price")),
        "base": normalize_number(item.get("base")),
        "tax_rate": normalize_number(item.get("tax_rate")),
        "tax_amount": normalize_number(item.get("tax_amount")),
        "total": normalize_number(item.get("total"))
    }

def normalize_line_items(items: Any) -> list:
    """Normaliza la lista de líneas de detalle."""
    return normalize_list(items, normalize_line_item)

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