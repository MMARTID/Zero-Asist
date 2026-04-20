"""Tests for the document review workflow endpoints."""

import pytest
from datetime import datetime, timezone
from app.services.tenant import TenantContext


@pytest.fixture
def review_doc(db, gestoria_id, cuenta_id):
    """Create a test document for review testing."""
    ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=cuenta_id)
    doc_data = {
        "document_hash": "test_doc_hash_123",
        "file_name": "invoice.pdf",
        "file_size": 50000,
        "document_type": "invoice_received",
        "normalized_data": {
            "issuer_name": "Proveedor S.L.",
            "issuer_nif": "B12345678",
            "client_name": "Test Client",
            "client_nif": "B87654321",
            "invoice_number": "INV-001",
            "total_amount": 1500.00,
        },
        "extracted_data": {},
        "created_at": datetime.now(timezone.utc),
        "review_status": "pending",
    }
    db.collection(ctx.docs_collection).document("test_doc_hash_123").set(doc_data)
    return "test_doc_hash_123"


def test_get_single_document(client, gestoria_id, cuenta_id, review_doc, auth_headers):
    """Test fetching a single document detail."""
    response = client.get(
        f"/dashboard/cuentas/{cuenta_id}/documentos/{review_doc}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["doc_hash"] == review_doc
    assert data["document_type"] == "invoice_received"
    assert data["review_status"] == "pending"
    assert data["normalized_data"]["issuer_name"] == "Proveedor S.L."


def test_get_nonexistent_document(client, gestoria_id, cuenta_id, auth_headers):
    """Test fetching a nonexistent document returns 404."""
    response = client.get(
        f"/dashboard/cuentas/{cuenta_id}/documentos/nonexistent_hash",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_update_document_normalized_data(client, gestoria_id, cuenta_id, review_doc, auth_headers):
    """Test updating document normalized_data."""
    response = client.patch(
        f"/dashboard/cuentas/{cuenta_id}/documentos/{review_doc}",
        headers=auth_headers,
        json={
            "normalized_data": {
                "issuer_name": "Updated Proveedor S.L.",
                "issuer_nif": "B12345678",
                "client_name": "Updated Client",
                "client_nif": "B87654321",
                "invoice_number": "INV-001",
                "total_amount": 2000.00,
            }
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["normalized_data"]["issuer_name"] == "Updated Proveedor S.L."
    assert data["normalized_data"]["total_amount"] == 2000.00


def test_update_document_type(client, gestoria_id, cuenta_id, review_doc, auth_headers):
    """Test updating document type."""
    response = client.patch(
        f"/dashboard/cuentas/{cuenta_id}/documentos/{review_doc}",
        headers=auth_headers,
        json={"document_type": "invoice_sent"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_type"] == "invoice_sent"


def test_update_nonexistent_document(client, gestoria_id, cuenta_id, auth_headers):
    """Test updating a nonexistent document returns 404."""
    response = client.patch(
        f"/dashboard/cuentas/{cuenta_id}/documentos/nonexistent_hash",
        headers=auth_headers,
        json={"normalized_data": {}},
    )
    assert response.status_code == 404


def test_review_document(client, gestoria_id, cuenta_id, review_doc, auth_headers, db):
    """Test marking a document as reviewed."""
    response = client.post(
        f"/dashboard/cuentas/{cuenta_id}/documentos/{review_doc}/review",
        headers=auth_headers,
        json={"changes": {}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    
    # Verify document status was updated
    ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=cuenta_id)
    doc = db.collection(ctx.docs_collection).document(review_doc).get()
    assert doc.to_dict()["review_status"] == "reviewed"
    assert doc.to_dict()["reviewed_at"] is not None
    assert doc.to_dict()["reviewed_by"] is not None


def test_review_document_creates_audit_record(client, gestoria_id, cuenta_id, review_doc, auth_headers, db):
    """Test that reviewing a document creates an audit record."""
    response = client.post(
        f"/dashboard/cuentas/{cuenta_id}/documentos/{review_doc}/review",
        headers=auth_headers,
        json={"changes": {"total_amount": {"old": 1500, "new": 2000}}},
    )
    assert response.status_code == 200
    
    # Verify audit record was created
    reviews = db.collection(f"gestorias/{gestoria_id}/reviews").get()
    audit_records = [r.to_dict() for r in reviews if r.to_dict().get("doc_hash") == review_doc]
    assert len(audit_records) > 0
    audit = audit_records[0]
    assert audit["action"] == "reviewed"
    assert audit["changes"] == {"total_amount": {"old": 1500, "new": 2000}}


def test_review_document_nonexistent(client, gestoria_id, cuenta_id, auth_headers):
    """Test reviewing a nonexistent document returns 404."""
    response = client.post(
        f"/dashboard/cuentas/{cuenta_id}/documentos/nonexistent_hash/review",
        headers=auth_headers,
        json={},
    )
    assert response.status_code == 404


def test_get_review_queue_empty(client, gestoria_id, auth_headers):
    """Test getting review queue when empty."""
    response = client.get(
        "/dashboard/review-queue",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["queue"] == []


def test_get_review_queue_with_pending_docs(client, gestoria_id, cuenta_id, review_doc, auth_headers):
    """Test getting review queue with pending documents."""
    response = client.get(
        "/dashboard/review-queue",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    queue_items = [item for item in data["queue"] if item["doc_hash"] == review_doc]
    assert len(queue_items) == 1
    assert queue_items[0]["cuenta_id"] == cuenta_id
    assert queue_items[0]["review_status"] != "reviewed"


def test_review_queue_excludes_reviewed_docs(client, gestoria_id, cuenta_id, review_doc, auth_headers, db):
    """Test that review queue excludes documents marked as reviewed."""
    # First mark as reviewed
    client.post(
        f"/dashboard/cuentas/{cuenta_id}/documentos/{review_doc}/review",
        headers=auth_headers,
        json={},
    )
    
    # Now check queue doesn't include it
    response = client.get(
        "/dashboard/review-queue",
        headers=auth_headers,
    )
    data = response.json()
    queue_items = [item for item in data["queue"] if item["doc_hash"] == review_doc]
    assert len(queue_items) == 0


def test_review_document_returns_next_pending(client, gestoria_id, cuenta_id, review_doc, auth_headers, db):
    """Test that review endpoint returns next pending document info."""
    response = client.post(
        f"/dashboard/cuentas/{cuenta_id}/documentos/{review_doc}/review",
        headers=auth_headers,
        json={},
    )
    assert response.status_code == 200
    data = response.json()
    assert "next" in data
    # next can be None if no more pending docs


def test_list_documents_includes_review_status(client, gestoria_id, cuenta_id, review_doc, auth_headers):
    """Test that list documents endpoint includes review_status."""
    response = client.get(
        f"/dashboard/cuentas/{cuenta_id}/documentos",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    docs = [d for d in data["documentos"] if d["doc_hash"] == review_doc]
    assert len(docs) > 0
    assert "review_status" in docs[0]
    assert docs[0]["review_status"] == "pending"
