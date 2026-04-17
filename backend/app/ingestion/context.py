from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class CuentaContext:
    """Identity of the cuenta processing the document."""
    nombre: str | None = None
    tax_id: str | None = None
    tax_country: str | None = None
    tax_type: str | None = None


@dataclass
class TraceEntry:
    field: str
    original: Any
    transformed: Any
    rule: str
    status: str  # missing | invalid | normalized


@dataclass
class ValidationIssue:
    field: str
    reason: str
    kind: str  # missing | invalid
    value: Any = None


@dataclass
class NormalizationReport:
    normalized: Dict[str, Any]
    trace: list[TraceEntry] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    document_type: str = "other"


@dataclass
class NormalizationContext:
    strict: bool = False
    trace_enabled: bool = False
    trace: list[TraceEntry] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    cuenta: Optional[CuentaContext] = None

    def record(self, field_name: str, original: Any, transformed: Any, rule: str, status: str) -> None:
        if self.trace_enabled:
            self.trace.append(
                TraceEntry(
                    field=field_name,
                    original=original,
                    transformed=transformed,
                    rule=rule,
                    status=status,
                )
            )

    def add_issue(self, field_name: str, reason: str, kind: str, value: Any = None) -> None:
        self.issues.append(ValidationIssue(field=field_name, reason=reason, kind=kind, value=value))
