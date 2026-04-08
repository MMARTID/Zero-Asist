"""Structured pipeline error type.

All layers in the processing pipeline raise ``PipelineError`` (never raw
exceptions) so that upper layers — and Firestore — only ever see clean,
classified codes, not raw API payloads.

Usage pattern:
  - The layer *closest* to the external call (e.g. ``gemini_client``) is
    responsible for catching raw API exceptions and re-raising as
    ``PipelineError``.
  - Upper layers may let ``PipelineError`` propagate unchanged, or catch it
    to add context before re-raising.
  - The outermost layer (poller / HTTP handler) catches ``PipelineError`` and
    uses ``.code`` directly — no string parsing needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ErrorCode = Literal[
    "UNAVAILABLE",   # 503 / service temporarily down
    "RATE_LIMIT",    # 429 / quota exceeded
    "TIMEOUT",       # deadline exceeded
    "INVALID_MIME",  # unsupported file type
    "VALIDATION",    # Pydantic / schema validation failure
    "UNKNOWN",       # anything else
]


@dataclass
class PipelineError(Exception):
    """Normalised, Firestore-safe pipeline error.

    Attributes:
        code:    Short machine-readable error category (see ``ErrorCode``).
        message: Human-readable description, safe to store in Firestore.
                 Does NOT contain raw API payloads or full stack traces.
    """

    code: ErrorCode
    message: str
    # Internal-only: keep the original exception for logging without exposing
    # it to upper layers or Firestore.
    _original: Exception | None = field(default=None, repr=False, compare=False)

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    @classmethod
    def from_exception(cls, e: Exception) -> "PipelineError":
        """Classify an arbitrary exception and return a ``PipelineError``.

        Inspects ``str(e)`` for known patterns.  Any unrecognised exception
        becomes ``UNKNOWN`` — the raw message is deliberately discarded so it
        cannot leak into Firestore.
        """
        msg = str(e)
        msg_upper = msg.upper()

        if "503" in msg or "UNAVAILABLE" in msg_upper:
            return cls(
                code="UNAVAILABLE",
                message="El servicio externo no está disponible temporalmente (503).",
                _original=e,
            )
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg_upper:
            return cls(
                code="RATE_LIMIT",
                message="Límite de peticiones alcanzado (429). Reintentar más tarde.",
                _original=e,
            )
        if "timeout" in msg.lower() or "DEADLINE_EXCEEDED" in msg_upper:
            return cls(
                code="TIMEOUT",
                message="La petición al servicio externo superó el tiempo límite.",
                _original=e,
            )
        if "validation" in msg.lower() or "validationerror" in type(e).__name__.lower():
            return cls(
                code="VALIDATION",
                message="La respuesta del servicio externo no tiene el formato esperado.",
                _original=e,
            )
        return cls(
            code="UNKNOWN",
            message="Error inesperado durante el procesamiento.",
            _original=e,
        )
