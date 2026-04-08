# tests/test_gmail_poller.py
"""Tests for app.collectors.gmail_poller.

poll_gmail() delegates document processing to process_document(), so tests
mock process_document() at the poller's module level and focus on:
  - Gmail-level filtering (heuristics, attachment presence, already-processed)
  - Correct routing of ProcessingResult.status values into the summary
  - PipelineError → clean error_code / error_message in summary + Firestore
  - mark_message_processed called with the right arguments
"""

import pytest
from unittest.mock import MagicMock
from app.collectors.gmail_poller import poll_gmail
from app.services.document_processor import ProcessingResult
from app.services.errors import PipelineError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_msg(msg_id="msg1", subject="Factura enero", snippet="factura adjunta",
              thread_id="thread1", from_addr="proveedor@test.com"):
    return {
        "id": msg_id,
        "thread_id": thread_id,
        "subject": subject,
        "snippet": snippet,
        "from": from_addr,
    }


def _make_attachment(filename="factura.pdf", mime_type="application/pdf", content=b"PDF content"):
    return {"filename": filename, "mime_type": mime_type, "data": content}


def _processed_result(doc_hash="abc123", document_type="invoice_received"):
    return ProcessingResult(
        status="processed",
        doc_hash=doc_hash,
        document_type=document_type,
        normalized_data={"issuer_name": "Proveedor"},
        extracted_data={"issuer_name": "Proveedor"},
    )


def _duplicate_result(doc_hash="abc123"):
    return ProcessingResult(
        status="duplicate",
        doc_hash=doc_hash,
        document_type=None,
        normalized_data=None,
        extracted_data=None,
    )


@pytest.fixture
def base_mocks(monkeypatch):
    """Sets up all external mocks for the poller. Returns a namespace to adjust."""
    mocks = MagicMock()

    monkeypatch.setattr("app.collectors.gmail_poller.get_gmail_service", lambda: mocks.service)
    monkeypatch.setattr(
        "app.collectors.gmail_poller.list_candidate_messages",
        lambda *a, **kw: [_make_msg()],
    )
    monkeypatch.setattr(
        "app.collectors.gmail_poller.is_invoice_candidate",
        lambda subject, snippet: True,
    )
    monkeypatch.setattr(
        "app.collectors.gmail_poller.get_attachments",
        lambda *a, **kw: [_make_attachment()],
    )

    # Default: process_document succeeds
    mocks.process = MagicMock(return_value=_processed_result())
    monkeypatch.setattr("app.collectors.gmail_poller.process_document", mocks.process)

    monkeypatch.setattr("app.collectors.gmail_poller.is_message_processed", lambda *a, **kw: False)
    mocks.mark = MagicMock()
    monkeypatch.setattr("app.collectors.gmail_poller.mark_message_processed", mocks.mark)

    return mocks


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_poll_gmail_happy_path(base_mocks):
    """Mensaje nuevo con adjunto → procesado y marcado como 'processed'."""
    summary = poll_gmail()

    assert len(summary["procesados"]) == 1
    assert summary["procesados"][0]["document_type"] == "invoice_received"
    assert len(summary["errores"]) == 0
    assert len(summary["duplicados"]) == 0
    assert len(summary["descartados"]) == 0

    base_mocks.mark.assert_called_once()
    assert base_mocks.mark.call_args.args[1] == "processed"


def test_poll_gmail_mensaje_ya_procesado_skip(monkeypatch):
    """Si is_message_processed devuelve True, el mensaje se salta por completo."""
    monkeypatch.setattr("app.collectors.gmail_poller.get_gmail_service", lambda: MagicMock())
    monkeypatch.setattr(
        "app.collectors.gmail_poller.list_candidate_messages",
        lambda *a, **kw: [_make_msg()],
    )
    monkeypatch.setattr("app.collectors.gmail_poller.is_message_processed", lambda *a, **kw: True)
    mark = MagicMock()
    monkeypatch.setattr("app.collectors.gmail_poller.mark_message_processed", mark)

    summary = poll_gmail()

    assert all(len(v) == 0 for v in summary.values())
    mark.assert_not_called()


def test_poll_gmail_descartado_por_heuristica(monkeypatch):
    """Mensaje que no pasa la heurística → descartado y marcado como 'discarded'."""
    monkeypatch.setattr("app.collectors.gmail_poller.get_gmail_service", lambda: MagicMock())
    monkeypatch.setattr(
        "app.collectors.gmail_poller.list_candidate_messages",
        lambda *a, **kw: [_make_msg(subject="Newsletter", snippet="novedades")],
    )
    monkeypatch.setattr("app.collectors.gmail_poller.is_message_processed", lambda *a, **kw: False)
    monkeypatch.setattr(
        "app.collectors.gmail_poller.is_invoice_candidate",
        lambda subject, snippet: False,
    )
    mark = MagicMock()
    monkeypatch.setattr("app.collectors.gmail_poller.mark_message_processed", mark)

    summary = poll_gmail()

    assert len(summary["descartados"]) == 1
    assert summary["descartados"][0]["reason"] == "heuristica"
    mark.assert_called_once()
    assert mark.call_args.args[1] == "discarded"
    assert mark.call_args.kwargs.get("reason") == "heuristica"


def test_poll_gmail_descartado_sin_adjuntos(monkeypatch):
    """Mensaje sin adjuntos válidos → descartado y marcado como 'discarded'."""
    monkeypatch.setattr("app.collectors.gmail_poller.get_gmail_service", lambda: MagicMock())
    monkeypatch.setattr(
        "app.collectors.gmail_poller.list_candidate_messages",
        lambda *a, **kw: [_make_msg()],
    )
    monkeypatch.setattr("app.collectors.gmail_poller.is_message_processed", lambda *a, **kw: False)
    monkeypatch.setattr(
        "app.collectors.gmail_poller.is_invoice_candidate", lambda *a, **kw: True
    )
    monkeypatch.setattr(
        "app.collectors.gmail_poller.get_attachments", lambda *a, **kw: []
    )
    mark = MagicMock()
    monkeypatch.setattr("app.collectors.gmail_poller.mark_message_processed", mark)

    summary = poll_gmail()

    assert len(summary["descartados"]) == 1
    assert summary["descartados"][0]["reason"] == "sin_adjuntos"
    assert mark.call_args.kwargs.get("reason") == "sin_adjuntos"


def test_poll_gmail_adjunto_duplicado(base_mocks):
    """process_document devuelve 'duplicate' → contado como duplicado."""
    base_mocks.process.return_value = _duplicate_result()

    summary = poll_gmail()

    assert len(summary["duplicados"]) == 1
    assert len(summary["procesados"]) == 0
    assert base_mocks.mark.call_args.args[1] == "duplicate"


def test_poll_gmail_pipeline_error_unavailable(base_mocks):
    """PipelineError(UNAVAILABLE) → error_code limpio en summary y Firestore."""
    base_mocks.process.side_effect = PipelineError(
        code="UNAVAILABLE",
        message="El servicio externo no está disponible temporalmente (503).",
    )

    summary = poll_gmail()

    assert len(summary["errores"]) == 1
    err = summary["errores"][0]
    assert err["error_code"] == "UNAVAILABLE"
    assert "503" in err["error_message"] or "disponible" in err["error_message"]
    assert base_mocks.mark.call_args.args[1] == "error"
    assert base_mocks.mark.call_args.kwargs.get("reason") == "UNAVAILABLE"


def test_poll_gmail_error_inesperado_wrapped(base_mocks):
    """Excepción inesperada (no PipelineError) → envuelta; nunca el error crudo en Firestore."""
    base_mocks.process.side_effect = RuntimeError("raw internal crash with long payload xyz")

    summary = poll_gmail()

    assert len(summary["errores"]) == 1
    err = summary["errores"][0]
    # error_code must be a clean category — raw message must NOT leak
    assert err["error_code"] in {"UNAVAILABLE", "RATE_LIMIT", "TIMEOUT", "VALIDATION", "UNKNOWN"}
    assert "raw internal crash" not in err["error_code"]
    assert "raw internal crash" not in err["error_message"]
    reason = base_mocks.mark.call_args.kwargs.get("reason")
    assert reason in {"UNAVAILABLE", "RATE_LIMIT", "TIMEOUT", "VALIDATION", "UNKNOWN"}


def test_poll_gmail_multiples_adjuntos_uno_procesado_uno_duplicado(base_mocks, monkeypatch):
    """2 adjuntos: uno nuevo + uno duplicado → status final 'processed'."""
    monkeypatch.setattr(
        "app.collectors.gmail_poller.get_attachments",
        lambda *a, **kw: [
            _make_attachment(filename="nuevo.pdf"),
            _make_attachment(filename="dup.pdf"),
        ],
    )
    base_mocks.process.side_effect = [
        _processed_result(doc_hash="hash1"),
        _duplicate_result(doc_hash="hash2"),
    ]

    summary = poll_gmail()

    assert len(summary["procesados"]) == 1
    assert len(summary["duplicados"]) == 1
    assert base_mocks.mark.call_args.args[1] == "processed"


def test_poll_gmail_multiples_adjuntos_todos_error(base_mocks, monkeypatch):
    """2 adjuntos con error → status final 'error', reason limpio."""
    monkeypatch.setattr(
        "app.collectors.gmail_poller.get_attachments",
        lambda *a, **kw: [
            _make_attachment(filename="a.pdf"),
            _make_attachment(filename="b.pdf"),
        ],
    )
    base_mocks.process.side_effect = [
        PipelineError(code="RATE_LIMIT", message="Límite alcanzado."),
        PipelineError(code="UNAVAILABLE", message="Servicio caído."),
    ]

    summary = poll_gmail()

    assert len(summary["errores"]) == 2
    assert base_mocks.mark.call_args.args[1] == "error"
    reason = base_mocks.mark.call_args.kwargs.get("reason")
    assert reason in {"RATE_LIMIT", "UNAVAILABLE"}


def test_poll_gmail_sin_candidatos(monkeypatch):
    """Sin candidatos de Gmail → summary vacío, sin llamadas a mark."""
    monkeypatch.setattr("app.collectors.gmail_poller.get_gmail_service", lambda: MagicMock())
    monkeypatch.setattr(
        "app.collectors.gmail_poller.list_candidate_messages", lambda *a, **kw: []
    )
    mark = MagicMock()
    monkeypatch.setattr("app.collectors.gmail_poller.mark_message_processed", mark)

    summary = poll_gmail()

    assert all(len(v) == 0 for v in summary.values())
    mark.assert_not_called()


def test_poll_gmail_mark_incluye_thread_id_y_from(base_mocks, monkeypatch):
    """Verificar que mark_message_processed recibe thread_id y from_addr correctos."""
    monkeypatch.setattr(
        "app.collectors.gmail_poller.list_candidate_messages",
        lambda *a, **kw: [_make_msg(thread_id="t99", from_addr="vendedor@shop.com")],
    )

    poll_gmail()

    call_kwargs = base_mocks.mark.call_args.kwargs
    assert call_kwargs.get("thread_id") == "t99"
    assert call_kwargs.get("from_addr") == "vendedor@shop.com"
