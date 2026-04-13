# tests/test_gmail_reader.py

import base64
import pytest
from unittest.mock import MagicMock
from app.collectors.gmail_reader import (
    is_invoice_candidate,
    list_candidate_messages,
    get_attachments,
)


# ---------------------------------------------------------------------------
# is_invoice_candidate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("subject,snippet", [
    ("Factura 2024-001", ""),
    ("", "Adjuntamos invoice de enero"),
    ("Re: Fra. servicio", ""),
    ("Nota de cargo", "importe pendiente"),
    ("Pago recibido", ""),
    ("", "total iva irpf"),
    ("Recibo de pago", ""),
    ("Albarán de entrega", ""),
])
def test_is_invoice_candidate_match(subject, snippet):
    assert is_invoice_candidate(subject, snippet) is True


@pytest.mark.parametrize("subject,snippet", [
    ("Reunión de equipo", "Nos vemos el lunes"),
    ("Newsletter semanal", "Novedades del sector"),
    ("Confirmación de vuelo", "Su reserva está confirmada"),
    ("", ""),
])
def test_is_invoice_candidate_no_match(subject, snippet):
    assert is_invoice_candidate(subject, snippet) is False


def test_is_invoice_candidate_case_insensitive():
    """Las keywords deben matchear independientemente de mayúsculas."""
    assert is_invoice_candidate("FACTURA RECIBIDA", "") is True
    assert is_invoice_candidate("", "INVOICE ATTACHED") is True


# ---------------------------------------------------------------------------
# list_candidate_messages
# ---------------------------------------------------------------------------

def _make_service(messages: list[dict], details: list[dict]) -> MagicMock:
    """Construye un mock del servicio Gmail con list() y get() configurados."""
    service = MagicMock()
    list_exec = MagicMock()
    list_exec.execute.return_value = {"messages": messages}
    service.users().messages().list.return_value = list_exec

    get_executions = [MagicMock() for _ in details]
    for mock, detail in zip(get_executions, details):
        mock.execute.return_value = detail
    service.users().messages().get.side_effect = get_executions

    return service


def test_list_candidate_messages_returns_candidates():
    messages = [{"id": "msg1", "threadId": "thread1"}]
    detail = {
        "snippet": "Factura adjunta",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Factura enero"},
                {"name": "From", "value": "proveedor@ejemplo.com"},
            ]
        },
    }
    service = _make_service(messages, [detail])
    candidates = list_candidate_messages(service, max_results=10)

    assert len(candidates) == 1
    assert candidates[0]["id"] == "msg1"
    assert candidates[0]["thread_id"] == "thread1"
    assert candidates[0]["subject"] == "Factura enero"
    assert candidates[0]["from"] == "proveedor@ejemplo.com"
    assert candidates[0]["snippet"] == "Factura adjunta"


def test_list_candidate_messages_no_messages():
    service = MagicMock()
    service.users().messages().list.return_value.execute.return_value = {"messages": []}
    assert list_candidate_messages(service) == []


def test_list_candidate_messages_missing_messages_key():
    service = MagicMock()
    service.users().messages().list.return_value.execute.return_value = {}
    assert list_candidate_messages(service) == []


# ---------------------------------------------------------------------------
# get_attachments
# ---------------------------------------------------------------------------

def _make_full_service(payload: dict) -> MagicMock:
    service = MagicMock()
    service.users().messages().get.return_value.execute.return_value = {"payload": payload}
    return service


def test_get_attachments_pdf_via_attachment_id():
    """Adjunto PDF con attachmentId → se descarga y devuelve bytes."""
    pdf_data = base64.urlsafe_b64encode(b"%PDF fake content").decode()
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "application/pdf",
                "filename": "factura.pdf",
                "body": {"attachmentId": "att123", "size": 100},
            }
        ],
    }
    service = _make_full_service(payload)
    service.users().messages().attachments().get.return_value.execute.return_value = {
        "data": pdf_data
    }

    attachments = get_attachments(service, "msg1")
    assert len(attachments) == 1
    assert attachments[0]["filename"] == "factura.pdf"
    assert attachments[0]["mime_type"] == "application/pdf"
    assert attachments[0]["data"] == b"%PDF fake content"


def test_get_attachments_inline_data():
    """Adjunto con datos inline (sin attachmentId) → se decodifica directamente."""
    raw = b"inline image bytes"
    inline_b64 = base64.urlsafe_b64encode(raw).decode()
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "image/png",
                "filename": "img.png",
                "body": {"data": inline_b64, "size": len(raw)},
            }
        ],
    }
    service = _make_full_service(payload)
    attachments = get_attachments(service, "msg2")
    assert len(attachments) == 1
    assert attachments[0]["data"] == raw


def test_get_attachments_ignores_unsupported_mime():
    """Adjuntos con mime no permitido (ej. .docx) deben ignorarse."""
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "filename": "contrato.docx",
                "body": {"attachmentId": "att_docx"},
            }
        ],
    }
    service = _make_full_service(payload)
    attachments = get_attachments(service, "msg3")
    assert attachments == []


def test_get_attachments_nested_parts():
    """Partes MIME anidadas (multipart/alternative → attachment) se recorren recursivamente."""
    raw = b"xml content"
    xml_b64 = base64.urlsafe_b64encode(raw).decode()
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "application/xml",
                        "filename": "factura.xml",
                        "body": {"data": xml_b64},
                    }
                ],
            }
        ],
    }
    service = _make_full_service(payload)
    attachments = get_attachments(service, "msg4")
    assert len(attachments) == 1
    assert attachments[0]["mime_type"] == "application/xml"


def test_get_attachments_attachment_download_error():
    """Si la descarga del adjunto falla, se omite sin propagar excepción."""
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "application/pdf",
                "filename": "fallo.pdf",
                "body": {"attachmentId": "att_bad"},
            }
        ],
    }
    service = _make_full_service(payload)
    service.users().messages().attachments().get.return_value.execute.side_effect = Exception("API error")

    attachments = get_attachments(service, "msg5")
    assert attachments == []
