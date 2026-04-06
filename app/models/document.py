from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import date, datetime


class DocumentType(str, Enum):
    invoice_received = "invoice_received"
    invoice_issued = "invoice_issued"
    receipt = "receipt"
    bank_statement = "bank_statement"
    payroll = "payroll"
    social_security_form = "social_security_form"
    delivery_note = "delivery_note"
    contract = "contract"
    tax_authority_communication = "tax_authority_communication"
    other = "other"


class ExtractedData(BaseModel):
    issuer_name: Optional[str] = None
    issuer_tax_id: Optional[str] = None
    invoice_number: Optional[str] = None
    issue_date: Optional[str] = None
    total_amount: Optional[float] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


class TaxBreakdownItem(BaseModel):
    rate: Optional[float] = None
    base: Optional[float] = None
    amount: Optional[float] = None


class LineItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    base: Optional[float] = None
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None
    total: Optional[float] = None


class InvoiceReceivedData(BaseModel):
    issuer_name: Optional[str] = None
    issuer_tax_id: Optional[str] = None
    invoice_number: Optional[str] = None
    series: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    base_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: str = "EUR"
    payment_method: Optional[str] = None
    tax_breakdown: List[TaxBreakdownItem] = Field(default_factory=list)
    line_items: List[LineItem] = Field(default_factory=list)
    confidence_score: Optional[float] = None
    is_national: Optional[bool] = None
    inversion_sujeto_pasivo: Optional[bool] = None
    pasivo_intracomunitario: Optional[bool] = None
    importacion_exento: Optional[bool] = None
    recargo_equivalencia: Optional[float] = None
    bienes_inversion: Optional[bool] = None


class InvoiceIssuedData(BaseModel):
    receiver_name: Optional[str] = None
    receiver_tax_id: Optional[str] = None
    issuer_name: Optional[str] = None
    issuer_tax_id: Optional[str] = None
    invoice_number: Optional[str] = None
    series: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    base_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: str = "EUR"
    payment_method: Optional[str] = None
    tax_breakdown: List[TaxBreakdownItem] = Field(default_factory=list)
    line_items: List[LineItem] = Field(default_factory=list)
    confidence_score: Optional[float] = None
    is_national: Optional[bool] = None
    inversion_sujeto_pasivo: Optional[bool] = None
    pasivo_intracomunitario: Optional[bool] = None
    importacion_exento: Optional[bool] = None
    recargo_equivalencia: Optional[float] = None
    bienes_inversion: Optional[bool] = None


class BankTransaction(BaseModel):
    date: Optional[str] = None        # str para compatibilidad con Gemini
    description: Optional[str] = None
    amount: Optional[float] = None
    type: Optional[str] = None  # "credit" o "debit"
    balance: Optional[float] = None
    reference: Optional[str] = None
    counterparty: Optional[str] = None


class BankStatementData(BaseModel):
    bank_name: Optional[str] = None
    account_holder: Optional[str] = None
    iban: Optional[str] = None
    currency: str = "EUR"
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    transactions: List[BankTransaction] = Field(default_factory=list)


class ExtractedPayload(BaseModel):
    """
    Modelo unificado con todos los campos posibles según el tipo de documento.
    Todos los campos son opcionales; Gemini solo rellena los que aplican.
    Compatible con Gemini response_schema (sin dict ni additionalProperties).
    """
    # --- Campos comunes a facturas (invoice_received / invoice_issued) ---
    issuer_name: Optional[str] = None
    issuer_tax_id: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_tax_id: Optional[str] = None
    invoice_number: Optional[str] = None
    series: Optional[str] = None
    issue_date: Optional[str] = None       # str para máxima compatibilidad con Gemini
    due_date: Optional[str] = None
    base_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    payment_method: Optional[str] = None
    tax_breakdown: List[TaxBreakdownItem] = Field(default_factory=list)
    line_items: List[LineItem] = Field(default_factory=list)
    confidence_score: Optional[float] = None
    # --- Campos fiscales españoles (facturas) ---
    is_national: Optional[bool] = None
    inversion_sujeto_pasivo: Optional[bool] = None
    pasivo_intracomunitario: Optional[bool] = None
    importacion_exento: Optional[bool] = None
    recargo_equivalencia: Optional[float] = None
    bienes_inversion: Optional[bool] = None
    # --- Campos de bank_statement ---
    bank_name: Optional[str] = None
    account_holder: Optional[str] = None
    iban: Optional[str] = None
    period_start: Optional[str] = None    # str para máxima compatibilidad con Gemini
    period_end: Optional[str] = None
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    transactions: List[BankTransaction] = Field(default_factory=list)


class DocumentoExtraido(BaseModel):
    document_type: DocumentType
    data: ExtractedPayload = Field(default_factory=ExtractedPayload)


# Alias de compatibilidad
FacturaData = InvoiceReceivedData


class DocumentoNormalizado(BaseModel):
    id: str
    file_name: str
    file_size: int
    document_hash: str
    document_type: DocumentType
    extracted_data: ExtractedData
    normalized_data: Dict[str, Any]
    created_at: datetime