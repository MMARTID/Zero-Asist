import re
from datetime import datetime, date
from typing import Any, Dict, Callable, List

DATE_FIELDS = ["issue_date", "due_date", "period_start", "period_end"]

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

def normalize_invoice_received(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza una factura recibida."""
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

def normalize_invoice_issued(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza una factura emitida."""
    return {
        "receiver_name": raw.get("receiver_name") or None,
        "receiver_tax_id": raw.get("receiver_tax_id") or None,
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

def normalize_bank_transaction(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza una transacción bancaria."""
    return {
        "date": normalize_date(item.get("date")),
        "description": str(item.get("description", "")).strip() or None,
        "amount": normalize_number(item.get("amount")),
        "type": item.get("type") or None,
        "balance": normalize_number(item.get("balance")),
        "reference": str(item.get("reference", "")).strip() or None,
        "counterparty": str(item.get("counterparty", "")).strip() or None,
    }

def normalize_bank_statement(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza un extracto bancario."""
    return {
        "bank_name": raw.get("bank_name") or None,
        "account_holder": raw.get("account_holder") or None,
        "iban": raw.get("iban") or None,
        "currency": raw.get("currency", "EUR") or "EUR",
        "period_start": normalize_date(raw.get("period_start")),
        "period_end": normalize_date(raw.get("period_end")),
        "opening_balance": normalize_number(raw.get("opening_balance")),
        "closing_balance": normalize_number(raw.get("closing_balance")),
        "transactions": normalize_list(raw.get("transactions", []), normalize_bank_transaction),
    }

def normalize_generic(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback: devuelve los datos tal cual, aplicando normalización básica de números y fechas."""
    return {k: v for k, v in raw.items()}

def normalize_document(data: Dict[str, Any], document_type: str) -> Dict[str, Any]:
    """Dispatcher principal: redirige al normalizador específico según el tipo de documento."""
    if document_type == "invoice_received":
        return normalize_invoice_received(data)
    elif document_type == "invoice_issued":
        return normalize_invoice_issued(data)
    elif document_type == "bank_statement":
        return normalize_bank_statement(data)
    else:
        return normalize_generic(data)

def normalize_extracted_data(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Alias de compatibilidad. Usar normalize_document en su lugar."""
    return normalize_invoice_received(raw)


def dates_to_firestore(data: Dict[str, Any]) -> Dict[str, Any]:
    """Converts date objects in known date fields to datetime for Firestore compatibility.

    Firestore does not accept plain ``date`` objects — they must be ``datetime``.
    This function converts any ``date`` (or ``datetime``) value found in the
    standard date fields to a ``datetime`` with midnight time (UTC midnight).

    Args:
        data: Normalized document dict (mutated copy is returned; original unchanged).

    Returns:
        A new dict with date fields converted to ``datetime`` where applicable.
    """
    result = dict(data)
    for field in DATE_FIELDS:
        val = result.get(field)
        if val is not None and hasattr(val, "year"):
            result[field] = datetime.combine(val, datetime.min.time())
    return result