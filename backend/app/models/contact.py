"""Contact model — unified representation of fiscal entities.

A Contact represents any fiscal entity (provider, customer, or both) that
a *cuenta* interacts with.  Contacts are identified primarily by tax_id within
a given account, and accumulate roles dynamically as documents are processed.

Firestore path:
    ``gestorias/{gestoria_id}/cuentas/{cuenta_id}/contactos/{contacto_id}``
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field


class ContactRole(str, Enum):
    """Roles a contact can have — accumulative, never auto-removed."""
    proveedor = "proveedor"
    cliente = "cliente"


class ContactSource(str, Enum):
    """How the contact was created."""
    ai_extracted = "ai_extracted"
    user_verified = "user_verified"
    manual = "manual"


class ContactRef(BaseModel):
    """Reference stored inside a document linking it to a contact.

    ``rol_en_documento`` describes the contact's *positional* role within that
    specific document (emisor / receptor / parte), which is distinct from the
    contact's *business* role (proveedor / cliente) stored in ``Contact.roles``.
    """
    contacto_id: str
    rol_en_documento: str  # "emisor", "receptor", "parte"


class Contact(BaseModel):
    """Pydantic model for a Contact document in Firestore."""
    # Identity — structured tax identifier
    tax_id: Optional[str] = None         # e.g. "B12345678"
    tax_country: Optional[str] = None    # ISO 3166-1 alpha-2 e.g. "ES"
    tax_type: Optional[str] = None       # "person" | "company" | "nie" | "vat_eu"
    nombre_fiscal: str
    nombre_comercial: Optional[str] = None

    # Roles (accumulative)
    roles: List[ContactRole] = Field(default_factory=list)

    # Confidence & provenance
    confidence: float = 0.5
    source: ContactSource = ContactSource.ai_extracted
    verified_at: Optional[str] = None

    # Enrichable fiscal data
    direccion_fiscal: Optional[str] = None
    codigo_postal: Optional[str] = None
    email_contacto: Optional[str] = None
    telefono: Optional[str] = None
    iban: Optional[str] = None
    forma_pago_habitual: Optional[str] = None

    # Denormalized stats
    total_documentos: int = 0
    total_facturado: Optional[float] = None
    total_recibido: Optional[float] = None
    ultima_interaccion: Optional[str] = None

    # Provenance
    created_from_document: Optional[str] = None
    updated_at: Optional[str] = None
