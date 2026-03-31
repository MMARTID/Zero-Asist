from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime

class ExtractedData(BaseModel):
    issuer_name: Optional[str] = None
    issuer_tax_id: Optional[str] = None
    invoice_number: Optional[str] = None
    issue_date: Optional[str] = None
    total_amount: Optional[float] = None
    raw: dict = Field(default_factory=dict)

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

class FacturaData(BaseModel):
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

class DocumentoNormalizado(BaseModel):
    id: str  # lo generaremos con uuid
    file_name: str
    file_size: int
    document_hash: str
    extracted_data: ExtractedData 
    normalized_data: FacturaData
    created_at: datetime