# tests/test_gmail_poller.py

import hashlib
import pytest
from unittest.mock import MagicMock, call, patch
from app.collectors.gmail_poller import poll_gmail


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


@pytest.fixture
def base_mocks(monkeypatch):
    """Prepara todos los mocks externos del poller. Devuelve un namespace para ajustar."""
    mocks = MagicMock()

    # Gmail service (no hace nada real)
    monkeypatch.setattr("app.collectors.gmail_poller.get_gmail_service", lambda: mocks.service)

    # Por defecto: un candidato que pasa la heurística con un adjunto PDF
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

    # Gemini
    monkeypatch.setattr(
        "app.collectors.gmail_poller.extract_from_file",
        lambda *a, **kw: {"document_type": "invoice_received", "data": {"issuer_name": "Proveedor"}},
    )
    # Normalizer
    monkeypatch.setattr(
        "app.collectors.gmail_poller.normalize_document",
        lambda data, dtype: data,
    )

    # Firestore db
    fake_snapshot = MagicMock()
    fake_snapshot.exists = False
    fake_doc_ref = MagicMock()
    fake_doc_ref.get.return_value = fake_snapshot
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value = fake_doc_ref
    fake_db.transaction.return_value = MagicMock()
    monkeypatch.setattr("app.collectors.gmail_poller.db", fake_db)
    mocks.db = fake_db
    mocks.doc_ref = fake_doc_ref
    mocks.snapshot = fake_snapshot

    # guardar_si_no_existe
    monkeypatch.setattr("app.collectors.gmail_poller.guardar_si_no_existe", lambda *a, **kw: None)

    # historial
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

    # Verificar que se registró en historial con status correcto
    base_mocks.mark.assert_called_once()
    call_kwargs = base_mocks.mark.call_args
    assert call_kwargs.args[1] == "processed"


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

    # No debe aparecer en ninguna categoría del summary
    assert all(len(v) == 0 for v in summary.values())
    # No debe llamar a mark_message_processed (ya estaba marcado)
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


def test_poll_gmail_adjunto_duplicado_por_hash(base_mocks):
    """Adjunto cuyo hash ya existe en Firestore → contado como duplicado."""
    base_mocks.snapshot.exists = True  # doc ya existe

    summary = poll_gmail()

    assert len(summary["duplicados"]) == 1
    assert len(summary["procesados"]) == 0

    base_mocks.mark.assert_called_once()
    assert base_mocks.mark.call_args.args[1] == "duplicate"


def test_poll_gmail_error_en_gemini(base_mocks, monkeypatch):
    """Error en Gemini → adjunto en errores, mensaje marcado como 'error'."""
    monkeypatch.setattr(
        "app.collectors.gmail_poller.extract_from_file",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("Gemini timeout")),
    )

    summary = poll_gmail()

    assert len(summary["errores"]) == 1
    assert "Gemini timeout" in summary["errores"][0]["reason"]
    assert base_mocks.mark.call_args.args[1] == "error"


def test_poll_gmail_error_check_duplicado(base_mocks, monkeypatch):
    """Error al consultar Firestore para check duplicado → error en summary."""
    base_mocks.doc_ref.get.side_effect = Exception("Firestore unavailable")

    summary = poll_gmail()

    assert len(summary["errores"]) == 1
    assert "error_check_duplicado" in summary["errores"][0]["reason"]
    assert base_mocks.mark.call_args.args[1] == "error"


def test_poll_gmail_multiples_adjuntos_uno_procesado_uno_duplicado(base_mocks, monkeypatch):
    """Mensaje con 2 adjuntos: uno nuevo y uno duplicado → status final 'processed'."""
    content_new = b"PDF nuevo"
    content_dup = b"PDF duplicado"

    def fake_attachments(*a, **kw):
        return [
            _make_attachment(filename="nuevo.pdf", content=content_new),
            _make_attachment(filename="dup.pdf", content=content_dup),
        ]

    monkeypatch.setattr("app.collectors.gmail_poller.get_attachments", fake_attachments)

    # El primer adjunto no existe, el segundo sí
    hash_new = hashlib.sha256(content_new).hexdigest()
    hash_dup = hashlib.sha256(content_dup).hexdigest()

    def fake_doc_get(self=None):
        # Acceder al hash desde el document mock es difícil; usamos call count
        return MagicMock(exists=False)

    call_count = {"n": 0}

    def fake_exists_check():
        call_count["n"] += 1
        snap = MagicMock()
        snap.exists = call_count["n"] > 1  # segundo adjunto es duplicado
        return snap

    base_mocks.doc_ref.get.side_effect = lambda: fake_exists_check()

    summary = poll_gmail()

    assert len(summary["procesados"]) == 1
    assert len(summary["duplicados"]) == 1
    # Status final optimista → processed
    assert base_mocks.mark.call_args.args[1] == "processed"


def test_poll_gmail_duplicado_en_transaccion(base_mocks, monkeypatch):
    """guardar_si_no_existe lanza ValueError (race condition) → duplicado."""
    def _raise(*a, **kw):
        raise ValueError("Documento duplicado")

    monkeypatch.setattr("app.collectors.gmail_poller.guardar_si_no_existe", _raise)

    summary = poll_gmail()

    assert len(summary["duplicados"]) == 1
    assert base_mocks.mark.call_args.args[1] == "duplicate"


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
