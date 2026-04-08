"""Document type registry.

Single source of truth for every document type supported by the ingestion
pipeline.  Each entry wires together three concerns that were previously
maintained as three separate dicts inside ``normalizer.py``:

- **normalizer** – the callable that converts raw LLM output to a clean dict.
- **schema** – the Pydantic model used for post-normalization validation.
- **required_fields** – field names that must be non-null for the document to
  be considered complete.

Adding a new document type therefore requires exactly *one* call to
``register_document_type`` — nothing else to update.

Import order
------------
This module intentionally has **no imports from** ``normalizer.py`` to keep
the dependency graph clean::

    document.py  ←  registry.py  ←  normalizer.py  ←  document_processor.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict


@dataclass
class DocumentTypeConfig:
    """Configuration bundle for a single document type."""

    document_type: str
    normalizer: Callable[[Dict[str, Any], Any], Dict[str, Any]]
    schema: type | None = None
    required_fields: list[str] = field(default_factory=list)
    extraction_schema: type | None = None
    prompt: str = ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DOCUMENT_TYPE_REGISTRY: dict[str, DocumentTypeConfig] = {}


def register_document_type(config: DocumentTypeConfig) -> None:
    """Register a document type configuration.

    Overwrites any existing entry for ``config.document_type``, so this can
    be called at module import time without ordering concerns.
    """
    DOCUMENT_TYPE_REGISTRY[config.document_type] = config


def get_document_type_config(document_type: str) -> DocumentTypeConfig | None:
    """Return the config for *document_type*, or ``None`` if unregistered."""
    return DOCUMENT_TYPE_REGISTRY.get(document_type)
