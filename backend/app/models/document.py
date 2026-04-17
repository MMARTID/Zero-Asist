from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List


class DocumentType(str, Enum):
    invoice_received = "invoice_received"
    invoice_sent = "invoice_sent"
    payment_receipt = "payment_receipt"
    administrative_notice = "administrative_notice"
    bank_document = "bank_document"
    contract = "contract"
    expense_ticket = "expense_ticket"
    other = "other"


# ---------------------------------------------------------------------------
# Classification (Gemini phase 1)
# ---------------------------------------------------------------------------

class ClassificationResult(BaseModel):
    document_type: DocumentType


# ---------------------------------------------------------------------------
# Extraction schemas (Gemini phase 2) — one per document type
#
# Cada schema es plano (sin Union/anyOf) para cumplir la restricción de
# Gemini response_schema.  Todas las fechas son str para máxima
# compatibilidad.  Los normalizadores convierten a date después.
#
# Las líneas fiscales (tax_lines) modelan todos los impuestos españoles:
# IVA, recargo de equivalencia, IGIC, IPSI, IRPF.
# ---------------------------------------------------------------------------


class TaxLine(BaseModel):
    """Single tax/retention line extracted from a document."""
    tax_type: Optional[str] = None
    rate: Optional[float] = None
    base_amount: Optional[float] = None
    amount: Optional[float] = None


class InvoiceReceivedExtraction(BaseModel):
    issuer_name: Optional[str] = None
    issuer_nif: Optional[str] = None
    issuer_address: Optional[str] = None
    issuer_phone: Optional[str] = None
    issuer_iban: Optional[str] = None
    client_name: Optional[str] = None
    client_nif: Optional[str] = None
    client_address: Optional[str] = None
    client_phone: Optional[str] = None
    client_iban: Optional[str] = None
    invoice_number: Optional[str] = None
    issue_date: Optional[str] = None
    base_amount: Optional[float] = None
    total_amount: Optional[float] = None
    tax_lines: List[TaxLine] = Field(default_factory=list)
    currency: Optional[str] = None
    concept: Optional[str] = None
    billing_period_start: Optional[str] = None
    billing_period_end: Optional[str] = None
    payment_method: Optional[str] = None
    tax_regime: Optional[str] = None
    vat_included: Optional[bool] = None
    document_source: Optional[str] = None


class InvoiceSentExtraction(BaseModel):
    issuer_name: Optional[str] = None
    issuer_nif: Optional[str] = None
    issuer_address: Optional[str] = None
    issuer_phone: Optional[str] = None
    issuer_iban: Optional[str] = None
    client_name: Optional[str] = None
    client_nif: Optional[str] = None
    client_address: Optional[str] = None
    client_phone: Optional[str] = None
    client_iban: Optional[str] = None
    invoice_number: Optional[str] = None
    issue_date: Optional[str] = None
    base_amount: Optional[float] = None
    total_amount: Optional[float] = None
    tax_lines: List[TaxLine] = Field(default_factory=list)
    currency: Optional[str] = None
    payment_status: Optional[str] = None
    payment_method: Optional[str] = None
    tax_regime: Optional[str] = None
    vat_included: Optional[bool] = None
    document_source: Optional[str] = None


class PaymentReceiptExtraction(BaseModel):
    payment_date: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    payment_method: Optional[str] = None
    operation_reference: Optional[str] = None
    issuer_name: Optional[str] = None
    card_last_digits: Optional[str] = None
    iban: Optional[str] = None
    document_source: Optional[str] = None


class AdministrativeNoticeExtraction(BaseModel):
    issuer_name: Optional[str] = None
    notice_type: Optional[str] = None
    issue_date: Optional[str] = None
    deadline: Optional[str] = None
    expedient_number: Optional[str] = None
    summary: Optional[str] = None
    has_signed_pdf: Optional[bool] = None
    document_source: Optional[str] = None


class Movement(BaseModel):
    date: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    balance_after: Optional[float] = None


class BankDocumentExtraction(BaseModel):
    bank_name: Optional[str] = None
    document_date: Optional[str] = None
    iban: Optional[str] = None
    movements: List[Movement] = Field(default_factory=list)
    document_source: Optional[str] = None


class ContractParty(BaseModel):
    name: Optional[str] = None
    nif: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    iban: Optional[str] = None


class ContractExtraction(BaseModel):
    parties: List[ContractParty] = Field(default_factory=list)
    contract_date: Optional[str] = None
    subject: Optional[str] = None
    duration: Optional[str] = None
    economic_terms: Optional[str] = None
    signed: Optional[bool] = None
    document_source: Optional[str] = None


class ExpenseTicketExtraction(BaseModel):
    issuer_name: Optional[str] = None
    issue_date: Optional[str] = None
    base_amount: Optional[float] = None
    total_amount: Optional[float] = None
    tax_lines: List[TaxLine] = Field(default_factory=list)
    currency: Optional[str] = None
    concept: Optional[str] = None
    payment_method: Optional[str] = None
    tax_regime: Optional[str] = None
    vat_included: Optional[bool] = None
    document_source: Optional[str] = None



