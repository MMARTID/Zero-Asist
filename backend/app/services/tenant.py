"""Multi-tenant context propagated through the processing pipeline.

Every function that touches Firestore or builds a Gmail service receives a
``TenantContext``.  When *ctx* is ``None`` the legacy flat collections are
used, keeping backward compatibility during the migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.constants import COLLECTION_DOCS, COLLECTION_GMAIL


@dataclass(frozen=True)
class TenantContext:
    """Identifies a gestoría + cliente pair.

    Properties compute the Firestore collection paths for that tenant.
    """

    gestoria_id: str
    cliente_id: str

    @property
    def docs_collection(self) -> str:
        return f"gestorias/{self.gestoria_id}/clientes/{self.cliente_id}/documentos"

    @property
    def gmail_collection(self) -> str:
        return f"gestorias/{self.gestoria_id}/clientes/{self.cliente_id}/gmail_processed"


def resolve_docs_collection(ctx: Optional[TenantContext] = None) -> str:
    """Return the Firestore collection path for documents."""
    return ctx.docs_collection if ctx else COLLECTION_DOCS


def resolve_gmail_collection(ctx: Optional[TenantContext] = None) -> str:
    """Return the Firestore collection path for processed Gmail messages."""
    return ctx.gmail_collection if ctx else COLLECTION_GMAIL
