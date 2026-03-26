from pydantic import BaseModel
from typing import Optional, List

class TaxBreakdownItem(BaseModel):
    rate: float
    base: float
    amount: float

class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    base: float
    tax_rate: float
    tax_amount: float
    total: float

class FacturaData(BaseModel):
    issuer_name: Optional[str] = None
    issuer_tax_id: Optional[str] = None
    invoice_number: Optional[str] = None
    series: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    base_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: str = "EUR"
    payment_method: Optional[str] = None
    tax_breakdown: List[TaxBreakdownItem] = []
    line_items: List[LineItem] = []

class DocumentoNormalizado(BaseModel):
    id: str  # lo generaremos con uuid
    file_name: str
    file_size: int
    document_hash: str
    extracted_data: FacturaData
    created_at: str