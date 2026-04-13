"""Normalization pipeline — public API, prompts, and type registrations.

Sub-modules
-----------
- ``context``              – dataclasses (TraceEntry, NormalizationContext, …)
- ``constants``            – regexes, lookup tables, tolerance values
- ``helpers``              – string / date / number / currency / tax primitives
- ``invoice``              – invoice normalizers (received + sent)
- ``bank_document``        – bank document normalizer
- ``payment_receipt``      – payment receipt normalizer
- ``administrative_notice``– administrative notice normalizer
- ``contract``             – contract normalizer
- ``expense_ticket``       – expense ticket normalizer
- ``validation``           – post-normalization validation & coherence checks
- ``firestore_dates``      – date→datetime conversion for Firestore
"""

import logging
from typing import Any, Dict

from app.models.document import (
    AdministrativeNoticeExtraction,
    BankDocumentExtraction,
    ContractExtraction,
    ExpenseTicketExtraction,
    InvoiceReceivedExtraction,
    InvoiceSentExtraction,
    PaymentReceiptExtraction,
)
from app.models.registry import (
    DOCUMENT_TYPE_REGISTRY,
    DocumentTypeConfig,
    register_document_type,
)

# --- Re-exports (backward compatibility) -----------------------------------
from app.ingestion.context import (  # noqa: F401
    NormalizationContext,
    NormalizationReport,
    TraceEntry,
    ValidationIssue,
)
from app.ingestion.helpers import (  # noqa: F401
    _clean_string,
    _detect_payment_method,
    _normalize_company_name,
    _normalize_currency,
    _normalize_single_tax_line,
    _normalize_tax_id,
    _split_invoice_series,
    _track_transform,
    infer_tax_regime,
    normalize_date,
    normalize_number,
    normalize_tax_lines,
    normalize_tax_type,
    snap_tax_rate,
)
from app.ingestion.invoice import (  # noqa: F401
    normalize_invoice_received,
    normalize_invoice_sent,
)
from app.ingestion.bank_document import (  # noqa: F401
    normalize_bank_document,
    normalize_movement,
)
from app.ingestion.payment_receipt import normalize_payment_receipt  # noqa: F401
from app.ingestion.administrative_notice import normalize_administrative_notice  # noqa: F401
from app.ingestion.contract import normalize_contract  # noqa: F401
from app.ingestion.expense_ticket import normalize_expense_ticket  # noqa: F401
from app.ingestion.validation import (  # noqa: F401
    _check_type_coherence,
    _cross_check_arithmetic,
    _finalize_validation,
    _validate_tax_lines,
)
from app.ingestion.firestore_dates import dates_to_firestore  # noqa: F401

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompts — one per document type (Gemini phase 2)
#
# No incluyen "Responde con JSON" ni "devuelve null" porque el
# response_schema + response_mime_type="application/json" lo fuerzan
# a nivel de API.
# ---------------------------------------------------------------------------

_PROMPT_INVOICE_RECEIVED = (
    "Eres un experto contable español. Analiza esta factura recibida (gasto) y extrae todos los datos disponibles. "
    "Busca: nombre y NIF/CIF del emisor, número de factura, fecha de emisión, "
    "base imponible, importe total, moneda, "
    "concepto o descripción del servicio/producto, "
    "periodo de facturación (inicio y fin) si aparece, "
    "forma de pago, y origen del documento (digital, escaneado, etc.). "
    "Para cada impuesto o retención que aparezca en la factura "
    "(IVA, recargo de equivalencia, IGIC, IPSI, IRPF u otro), "
    "extrae una línea en tax_lines con: tipo de impuesto (tax_type), "
    "porcentaje (rate), base imponible de esa línea (base_amount) y cuota (amount)."
)

_PROMPT_INVOICE_SENT = (
    "Eres un experto contable español. Analiza esta factura emitida (ingreso) y extrae todos los datos disponibles. "
    "Busca: nombre y NIF/CIF del emisor, nombre y NIF/CIF del cliente, "
    "número de factura, fecha de emisión, base imponible, importe total, moneda, "
    "estado del pago (pendiente, cobrada, etc.), forma de pago, "
    "y origen del documento. "
    "Para cada impuesto o retención que aparezca "
    "(IVA, recargo de equivalencia, IGIC, IPSI, IRPF u otro), "
    "extrae una línea en tax_lines con: tipo de impuesto (tax_type), "
    "porcentaje (rate), base imponible de esa línea (base_amount) y cuota (amount)."
)

_PROMPT_PAYMENT_RECEIPT = (
    "Eres un experto en conciliación bancaria. Analiza este justificante de pago y extrae todos los datos disponibles. "
    "Busca: fecha del pago, importe, moneda, método de pago, "
    "referencia de la operación, entidad emisora, "
    "últimos dígitos de tarjeta si aparecen, IBAN si aparece, "
    "y origen del documento. "
    "El objetivo es poder vincular este pago con una factura."
)

_PROMPT_ADMINISTRATIVE_NOTICE = (
    "Eres un experto en documentación fiscal y administrativa española. "
    "Analiza este documento y extrae: entidad emisora (AEAT, Seguridad Social, ayuntamiento, etc.), "
    "tipo de comunicación (notificación, requerimiento, resolución, liquidación, etc.), "
    "fecha de emisión, fecha límite o plazo, número de expediente, "
    "resumen del contenido, si contiene firma electrónica o PDF firmado, "
    "y origen del documento."
)

_PROMPT_BANK_DOCUMENT = (
    "Eres un experto en contabilidad bancaria. Analiza este documento bancario "
    "(extracto, aviso de movimiento, etc.) y extrae: nombre del banco, "
    "fecha del documento, IBAN de la cuenta, "
    "y la lista de movimientos con fecha, descripción, importe y saldo posterior. "
    "Indica el origen del documento."
)

_PROMPT_CONTRACT = (
    "Eres un experto en documentación legal. Analiza este contrato o documento legal "
    "y extrae: las partes firmantes (nombre y NIF de cada una), "
    "fecha del contrato, objeto o materia del contrato, "
    "duración, condiciones económicas, si está firmado, "
    "y origen del documento."
)

_PROMPT_EXPENSE_TICKET = (
    "Eres un experto contable español. Analiza este ticket o justificante de gasto "
    "y extrae: nombre del establecimiento, fecha, base imponible si aparece, "
    "importe total, moneda, concepto o descripción del gasto, "
    "forma de pago, y origen del documento. "
    "Si el ticket muestra desglose de impuestos (IVA, IGIC, recargo de equivalencia, etc.), "
    "extrae cada impuesto en tax_lines con: tipo (tax_type), porcentaje (rate), "
    "base (base_amount) y cuota (amount)."
)


# ---------------------------------------------------------------------------
# Generic fallback normalizer
# ---------------------------------------------------------------------------

def normalize_generic(raw: Dict[str, Any], ctx: NormalizationContext | None = None) -> Dict[str, Any]:
    """Fallback normalizer that preserves fields while cleaning obvious string noise."""
    local_ctx = ctx or NormalizationContext()
    out: Dict[str, Any] = {}
    for key, value in raw.items():
        cleaned = _clean_string(value) if isinstance(value, str) else value
        out[key] = cleaned
        local_ctx.record(key, value, cleaned, "normalize_generic", "normalized")
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_document_with_report(
    data: Dict[str, Any],
    document_type: str,
    *,
    strict: bool = False,
    trace: bool = False,
) -> NormalizationReport:
    """Normalize with optional strict mode and full traceability report."""
    ctx = NormalizationContext(strict=strict, trace_enabled=trace)

    if not isinstance(data, dict):
        ctx.add_issue("data", "expected_dict", "invalid", value=data)
        if strict:
            _finalize_validation(document_type, {}, ctx)
        data = {}

    config = DOCUMENT_TYPE_REGISTRY.get(document_type)
    normalizer = config.normalizer if config else normalize_generic
    normalized = normalizer(data, ctx)
    _finalize_validation(document_type, normalized, ctx)

    return NormalizationReport(
        normalized=normalized,
        trace=ctx.trace,
        issues=ctx.issues,
        document_type=document_type,
    )


def normalize_document(data: Dict[str, Any], document_type: str) -> Dict[str, Any]:
    """Backward-compatible dispatcher used by the ingestion pipeline."""
    report = normalize_document_with_report(data, document_type, strict=False, trace=False)
    return report.normalized


# ---------------------------------------------------------------------------
# Register built-in document types
# ---------------------------------------------------------------------------

register_document_type(DocumentTypeConfig(
    document_type="invoice_received",
    normalizer=normalize_invoice_received,
    schema=InvoiceReceivedExtraction,
    required_fields=["issuer_name", "invoice_number", "total_amount"],
    extraction_schema=InvoiceReceivedExtraction,
    prompt=_PROMPT_INVOICE_RECEIVED,
))
register_document_type(DocumentTypeConfig(
    document_type="invoice_sent",
    normalizer=normalize_invoice_sent,
    schema=InvoiceSentExtraction,
    required_fields=["issuer_name", "client_name", "invoice_number", "total_amount"],
    extraction_schema=InvoiceSentExtraction,
    prompt=_PROMPT_INVOICE_SENT,
))
register_document_type(DocumentTypeConfig(
    document_type="payment_receipt",
    normalizer=normalize_payment_receipt,
    schema=PaymentReceiptExtraction,
    required_fields=["amount", "payment_date"],
    extraction_schema=PaymentReceiptExtraction,
    prompt=_PROMPT_PAYMENT_RECEIPT,
))
register_document_type(DocumentTypeConfig(
    document_type="administrative_notice",
    normalizer=normalize_administrative_notice,
    schema=AdministrativeNoticeExtraction,
    required_fields=["issuer_entity", "issue_date"],
    extraction_schema=AdministrativeNoticeExtraction,
    prompt=_PROMPT_ADMINISTRATIVE_NOTICE,
))
register_document_type(DocumentTypeConfig(
    document_type="bank_document",
    normalizer=normalize_bank_document,
    schema=BankDocumentExtraction,
    required_fields=["bank_name"],
    extraction_schema=BankDocumentExtraction,
    prompt=_PROMPT_BANK_DOCUMENT,
))
register_document_type(DocumentTypeConfig(
    document_type="contract",
    normalizer=normalize_contract,
    schema=ContractExtraction,
    required_fields=["contract_date"],
    extraction_schema=ContractExtraction,
    prompt=_PROMPT_CONTRACT,
))
register_document_type(DocumentTypeConfig(
    document_type="expense_ticket",
    normalizer=normalize_expense_ticket,
    schema=ExpenseTicketExtraction,
    required_fields=["total_amount"],
    extraction_schema=ExpenseTicketExtraction,
    prompt=_PROMPT_EXPENSE_TICKET,
))
