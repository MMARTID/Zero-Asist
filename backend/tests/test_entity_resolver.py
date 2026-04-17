"""Tests for app.services.entity_resolver — entity extraction, matching, and linking."""

from unittest.mock import MagicMock, patch
import pytest

from app.models.contact import ContactRef, ContactRole, ContactSource
from app.services.entity_resolver import (
    EntityCandidate,
    _assign_roles,
    _is_cuenta_entity,
    _merge_roles,
    _enrich_contact,
    _normalize_name_for_matching,
    _name_similarity,
    extract_entities,
    find_matching_contact,
    resolve_and_link,
)
from app.services.tax_id import tax_ids_match
from app.services.tenant import TenantContext


# ---------------------------------------------------------------------------
# extract_entities
# ---------------------------------------------------------------------------

class TestExtractEntities:
    def test_invoice_received_extracts_provider(self):
        data = {"issuer_name": "Acme S.L.", "issuer_nif": "B12345678", "total_amount": 121.0}
        candidates = extract_entities(data, "invoice_received")
        assert len(candidates) == 1
        assert candidates[0].name == "Acme S.L."
        assert candidates[0].nif == "B12345678"
        assert candidates[0].role is None  # assigned later by _assign_roles
        assert candidates[0].document_role == "emisor"
        assert candidates[0].confidence == 0.9
        assert candidates[0].amount == 121.0

    def test_invoice_received_extracts_both_parties(self):
        data = {
            "issuer_name": "Acme S.L.", "issuer_nif": "B12345678",
            "client_name": "Mi Empresa", "client_nif": "A99999999",
            "total_amount": 121.0,
        }
        candidates = extract_entities(data, "invoice_received")
        assert len(candidates) == 2
        assert candidates[0].role is None
        assert candidates[0].document_role == "emisor"
        assert candidates[1].role is None
        assert candidates[1].document_role == "receptor"

    def test_invoice_received_carries_extra_payment_method(self):
        data = {
            "issuer_name": "Acme", "issuer_nif": "B12345678",
            "total_amount": 100.0, "payment_method": "Transferencia bancaria",
        }
        candidates = extract_entities(data, "invoice_received")
        assert candidates[0].extra["payment_method"] == "Transferencia bancaria"

    def test_invoice_sent_carries_amount_and_extra(self):
        data = {
            "client_name": "Client", "client_nif": "A99999999",
            "total_amount": 500.0, "payment_method": "Domiciliación",
        }
        candidates = extract_entities(data, "invoice_sent")
        assert len(candidates) == 1
        assert candidates[0].amount == 500.0
        assert candidates[0].extra["payment_method"] == "Domiciliación"

    def test_invoice_received_without_nif_lower_confidence(self):
        data = {"issuer_name": "Acme S.L.", "total_amount": 121.0}
        candidates = extract_entities(data, "invoice_received")
        assert len(candidates) == 1
        assert candidates[0].confidence == 0.6

    def test_invoice_received_no_issuer_returns_empty(self):
        data = {"total_amount": 121.0}
        assert extract_entities(data, "invoice_received") == []

    def test_invoice_sent_extracts_customer(self):
        data = {"client_name": "Cliente Corp", "client_nif": "A87654321"}
        candidates = extract_entities(data, "invoice_sent")
        assert len(candidates) == 1
        assert candidates[0].name == "Cliente Corp"
        assert candidates[0].role is None  # assigned later
        assert candidates[0].document_role == "receptor"

    def test_invoice_sent_extracts_both_parties(self):
        data = {
            "issuer_name": "Mi Empresa S.L.", "issuer_nif": "B11111111",
            "client_name": "Cliente Corp", "client_nif": "A87654321",
        }
        candidates = extract_entities(data, "invoice_sent")
        assert len(candidates) == 2
        assert candidates[0].role is None
        assert candidates[0].document_role == "emisor"
        assert candidates[1].role is None
        assert candidates[1].document_role == "receptor"

    def test_invoice_sent_no_client_returns_empty(self):
        data = {}
        assert extract_entities(data, "invoice_sent") == []

    def test_expense_ticket_extracts_provider(self):
        data = {"issuer_name": "Restaurante El Buen Comer", "total_amount": 25.5}
        candidates = extract_entities(data, "expense_ticket")
        assert len(candidates) == 1
        assert candidates[0].role == ContactRole.proveedor
        assert candidates[0].confidence == 0.4

    def test_expense_ticket_no_issuer_returns_empty(self):
        data = {"total_amount": 25.5}
        assert extract_entities(data, "expense_ticket") == []

    def test_contract_extracts_all_parties(self):
        data = {"parties": [
            {"name": "Parte A S.L.", "nif": "B11111111"},
            {"name": "Parte B S.A.", "nif": "A22222222"},
        ]}
        candidates = extract_entities(data, "contract")
        assert len(candidates) == 2
        assert candidates[0].document_role == "parte"
        assert candidates[1].document_role == "parte"

    def test_contract_skips_parties_without_name(self):
        data = {"parties": [{"nif": "B11111111"}, {"name": "Valid"}]}
        candidates = extract_entities(data, "contract")
        assert len(candidates) == 1
        assert candidates[0].name == "Valid"

    def test_payment_receipt_returns_empty(self):
        data = {"amount": 100, "issuer_name": "CaixaBank"}
        assert extract_entities(data, "payment_receipt") == []

    def test_administrative_notice_returns_empty(self):
        data = {"issuer_name": "AEAT", "issue_date": "2024-01-01"}
        assert extract_entities(data, "administrative_notice") == []

    def test_bank_document_returns_empty(self):
        data = {"bank_name": "BBVA", "iban": "ES1234"}
        assert extract_entities(data, "bank_document") == []

    def test_unknown_type_returns_empty(self):
        data = {"issuer_name": "Test"}
        assert extract_entities(data, "other") == []


# ---------------------------------------------------------------------------
# _normalize_name_for_matching
# ---------------------------------------------------------------------------

class TestNormalizeNameForMatching:
    def test_strips_legal_suffix(self):
        assert "acme" == _normalize_name_for_matching("Acme S.L.")

    def test_case_insensitive(self):
        assert _normalize_name_for_matching("ACME") == _normalize_name_for_matching("acme")

    def test_strips_accents(self):
        assert "companiaespanola" == _normalize_name_for_matching("Compañía Española")

    def test_removes_punctuation(self):
        assert _normalize_name_for_matching("A.C.M.E") == _normalize_name_for_matching("ACME")

    def test_sa_suffix_removed(self):
        assert "empresa" == _normalize_name_for_matching("Empresa S.A.")

    def test_empty_string(self):
        assert "" == _normalize_name_for_matching("")


# ---------------------------------------------------------------------------
# _name_similarity
# ---------------------------------------------------------------------------

class TestNameSimilarity:
    def test_identical_names(self):
        assert _name_similarity("acme", "acme") == 1.0

    def test_empty_names(self):
        assert _name_similarity("", "acme") == 0.0
        assert _name_similarity("acme", "") == 0.0

    def test_similar_names_high_score(self):
        score = _name_similarity("acmecorporation", "acmecorp")
        assert score > 0.4

    def test_different_names_low_score(self):
        score = _name_similarity("acme", "xyz")
        assert score < 0.3


# ---------------------------------------------------------------------------
# _merge_roles
# ---------------------------------------------------------------------------

class TestMergeRoles:
    def test_adds_new_role(self):
        result = _merge_roles(["proveedor"], ContactRole.cliente)
        assert "cliente" in result
        assert "proveedor" in result

    def test_does_not_duplicate(self):
        result = _merge_roles(["proveedor"], ContactRole.proveedor)
        assert result == ["proveedor"]

    def test_empty_existing(self):
        result = _merge_roles([], ContactRole.proveedor)
        assert result == ["proveedor"]


# ---------------------------------------------------------------------------
# _is_cuenta_entity
# ---------------------------------------------------------------------------

class TestIsCuentaEntity:
    def test_matching_nif(self):
        assert _is_cuenta_entity("B12345678", "B12345678") is True

    def test_case_insensitive(self):
        assert _is_cuenta_entity("b12345678", "B12345678") is True

    def test_no_match(self):
        assert _is_cuenta_entity("A99999999", "B12345678") is False

    def test_none_candidate(self):
        assert _is_cuenta_entity(None, "B12345678") is False

    def test_none_cuenta(self):
        assert _is_cuenta_entity("B12345678", None) is False

    def test_es_prefix_on_candidate(self):
        """Gemini may extract 'ESB12345678' while cuenta stores 'B12345678'."""
        assert _is_cuenta_entity("ESB12345678", "B12345678") is True

    def test_es_prefix_on_cuenta(self):
        assert _is_cuenta_entity("B12345678", "ESB12345678") is True

    def test_es_prefix_with_dashes(self):
        assert _is_cuenta_entity("ES-B12.345.678", "B12345678") is True

    def test_nif_prefix_junk(self):
        """Gemini/OCR may extract 'NIF Q24615910' → normalizes to 'NIFQ24615910'."""
        assert _is_cuenta_entity("NIFQ24615910", "Q24615910") is True

    def test_cif_prefix_junk(self):
        assert _is_cuenta_entity("CIFQ24615910", "Q24615910") is True

    def test_nif_prefix_no_false_positive(self):
        """Suffix match must not trigger for unrelated IDs that happen to share a substring."""
        assert _is_cuenta_entity("NIFB12345678", "Q24615910") is False


# ---------------------------------------------------------------------------
# _assign_roles
# ---------------------------------------------------------------------------

class TestAssignRoles:
    def test_invoice_received_skips_cuenta_assigns_proveedor(self):
        """For invoice_received, the non-cuenta entity should be assigned proveedor."""
        candidates = [
            EntityCandidate("Proveedor S.L.", "B12345678", None, "emisor", 0.9),
            EntityCandidate("Mi Empresa", "A99999999", None, "receptor", 0.9),
        ]
        result = _assign_roles(candidates, "invoice_received", "A99999999")
        assert len(result) == 1
        assert result[0].name == "Proveedor S.L."
        assert result[0].role == ContactRole.proveedor

    def test_invoice_sent_skips_cuenta_assigns_cliente(self):
        """For invoice_sent, the non-cuenta entity should be assigned cliente."""
        candidates = [
            EntityCandidate("Mi Empresa", "B11111111", None, "emisor", 0.9),
            EntityCandidate("Cliente Corp", "A87654321", None, "receptor", 0.9),
        ]
        result = _assign_roles(candidates, "invoice_sent", "B11111111")
        assert len(result) == 1
        assert result[0].name == "Cliente Corp"
        assert result[0].role == ContactRole.cliente

    def test_no_cuenta_tax_id_uses_positional_fallback(self):
        """Without a cuenta tax_id, positional fallback skips the cuenta-position entity."""
        candidates = [
            EntityCandidate("Issuer", "B12345678", None, "emisor", 0.9),
            EntityCandidate("Client", "A99999999", None, "receptor", 0.9),
        ]
        result = _assign_roles(candidates, "invoice_received", None)
        # receptor is the cuenta position for invoice_received → skipped
        assert len(result) == 1
        assert result[0].name == "Issuer"
        assert result[0].role == ContactRole.proveedor

    def test_no_cuenta_tax_id_invoice_sent_positional(self):
        """For invoice_sent without cuenta tax_id, emisor (us) is skipped."""
        candidates = [
            EntityCandidate("Mi Empresa", "B12345678", None, "emisor", 0.9),
            EntityCandidate("Cliente Corp", "A87654321", None, "receptor", 0.9),
        ]
        result = _assign_roles(candidates, "invoice_sent", None)
        # emisor is the cuenta position for invoice_sent → skipped
        assert len(result) == 1
        assert result[0].name == "Cliente Corp"
        assert result[0].role == ContactRole.cliente

    def test_nif_match_overrides_positional(self):
        """When NIF matches, positional fallback is NOT used (NIF is primary)."""
        candidates = [
            EntityCandidate("Proveedor S.L.", "B12345678", None, "emisor", 0.9),
            EntityCandidate("Mi Empresa", "A99999999", None, "receptor", 0.9),
        ]
        result = _assign_roles(candidates, "invoice_received", "A99999999")
        # NIF matched "Mi Empresa" → skipped. Positional NOT applied (NIF found match).
        assert len(result) == 1
        assert result[0].name == "Proveedor S.L."

    def test_es_prefix_nif_filtering(self):
        """Entity with ES-prefixed NIF matching the cuenta should be filtered."""
        candidates = [
            EntityCandidate("Proveedor S.L.", "X1234567L", None, "emisor", 0.9),
            EntityCandidate("Mi Empresa", "ESB12345678", None, "receptor", 0.9),
        ]
        result = _assign_roles(candidates, "invoice_received", "B12345678")
        assert len(result) == 1
        assert result[0].name == "Proveedor S.L."
        assert result[0].role == ContactRole.proveedor

    def test_non_invoice_types_unchanged(self):
        """expense_ticket and contract types pass through unchanged."""
        c = EntityCandidate("Shop", None, ContactRole.proveedor, "emisor", 0.4)
        result = _assign_roles([c], "expense_ticket", "B12345678")
        assert len(result) == 1
        assert result[0].role == ContactRole.proveedor


# ---------------------------------------------------------------------------
# _enrich_contact
# ---------------------------------------------------------------------------

class TestEnrichContact:
    def test_adds_missing_tax_id(self):
        existing = {"tax_id": None, "roles": ["proveedor"], "confidence": 0.5, "total_documentos": 1}
        candidate = EntityCandidate("Test", "B12345678", ContactRole.proveedor, "emisor", 0.9)
        updates = _enrich_contact(existing, candidate)
        assert updates["tax_id"] == "B12345678"
        assert updates["tax_country"] == "ES"
        assert updates["tax_type"] == "company"

    def test_does_not_overwrite_existing_tax_id(self):
        existing = {"tax_id": "A99999999", "roles": ["proveedor"], "confidence": 0.9, "total_documentos": 1}
        candidate = EntityCandidate("Test", "B12345678", ContactRole.proveedor, "emisor", 0.5)
        updates = _enrich_contact(existing, candidate)
        assert "tax_id" not in updates

    def test_adds_new_role(self):
        existing = {"tax_id": "B12345678", "roles": ["proveedor"], "confidence": 0.9, "total_documentos": 1}
        candidate = EntityCandidate("Test", "B12345678", ContactRole.cliente, "receptor", 0.9)
        updates = _enrich_contact(existing, candidate)
        assert "cliente" in updates["roles"]
        assert "proveedor" in updates["roles"]

    def test_increments_total_documentos(self):
        existing = {"roles": ["proveedor"], "confidence": 0.5, "total_documentos": 5}
        candidate = EntityCandidate("Test", None, ContactRole.proveedor, "emisor", 0.3)
        updates = _enrich_contact(existing, candidate)
        assert updates["total_documentos"] == 6

    def test_updates_confidence_only_if_higher(self):
        existing = {"roles": ["proveedor"], "confidence": 0.9, "total_documentos": 1}
        candidate = EntityCandidate("Test", None, ContactRole.proveedor, "emisor", 0.5)
        updates = _enrich_contact(existing, candidate)
        assert "confidence" not in updates

    def test_accumulates_total_recibido_for_proveedor(self):
        existing = {"roles": ["proveedor"], "confidence": 0.9, "total_documentos": 3, "total_recibido": 100.0}
        candidate = EntityCandidate("Test", None, ContactRole.proveedor, "emisor", 0.5, amount=50.5)
        updates = _enrich_contact(existing, candidate)
        assert updates["total_recibido"] == 150.5

    def test_accumulates_total_facturado_for_cliente(self):
        existing = {"roles": ["cliente"], "confidence": 0.9, "total_documentos": 1, "total_facturado": 200.0}
        candidate = EntityCandidate("Test", None, ContactRole.cliente, "receptor", 0.5, amount=300.0)
        updates = _enrich_contact(existing, candidate)
        assert updates["total_facturado"] == 500.0

    def test_accumulates_total_from_zero(self):
        existing = {"roles": ["proveedor"], "confidence": 0.9, "total_documentos": 0}
        candidate = EntityCandidate("Test", None, ContactRole.proveedor, "emisor", 0.5, amount=75.0)
        updates = _enrich_contact(existing, candidate)
        assert updates["total_recibido"] == 75.0

    def test_no_amount_does_not_set_totals(self):
        existing = {"roles": ["proveedor"], "confidence": 0.9, "total_documentos": 1}
        candidate = EntityCandidate("Test", None, ContactRole.proveedor, "emisor", 0.5)
        updates = _enrich_contact(existing, candidate)
        assert "total_recibido" not in updates
        assert "total_facturado" not in updates

    def test_propagates_payment_method(self):
        existing = {"roles": ["proveedor"], "confidence": 0.9, "total_documentos": 1, "forma_pago_habitual": None}
        candidate = EntityCandidate("Test", None, ContactRole.proveedor, "emisor", 0.5, extra={"payment_method": "Transferencia"})
        updates = _enrich_contact(existing, candidate)
        assert updates["forma_pago_habitual"] == "Transferencia"

    def test_does_not_overwrite_existing_payment_method(self):
        existing = {"roles": ["proveedor"], "confidence": 0.9, "total_documentos": 1, "forma_pago_habitual": "Domiciliación"}
        candidate = EntityCandidate("Test", None, ContactRole.proveedor, "emisor", 0.5, extra={"payment_method": "Transferencia"})
        updates = _enrich_contact(existing, candidate)
        assert "forma_pago_habitual" not in updates


# ---------------------------------------------------------------------------
# find_matching_contact
# ---------------------------------------------------------------------------

class TestFindMatchingContact:
    def test_nif_exact_match(self):
        mock_doc = MagicMock()
        mock_doc.id = "contact-1"
        mock_doc.to_dict.return_value = {"nombre_fiscal": "Acme", "tax_id": "B12345678", "roles": ["proveedor"]}

        mock_db = MagicMock()
        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = [mock_doc]

        candidate = EntityCandidate("Acme S.L.", "B12345678", ContactRole.proveedor, "emisor")
        result = find_matching_contact(mock_db, candidate)
        assert result is not None
        assert result[0] == "contact-1"

    def test_no_nif_falls_back_to_name(self):
        mock_doc = MagicMock()
        mock_doc.id = "contact-2"
        mock_doc.to_dict.return_value = {"nombre_fiscal": "Acme Corp", "tax_id": None, "roles": ["proveedor"]}

        mock_db = MagicMock()
        # NIF query returns nothing (no NIF on candidate)
        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
        mock_db.collection.return_value.get.return_value = [mock_doc]

        candidate = EntityCandidate("Acme Corp", None, ContactRole.proveedor, "emisor")
        result = find_matching_contact(mock_db, candidate)
        assert result is not None
        assert result[0] == "contact-2"

    def test_no_match_returns_none(self):
        mock_db = MagicMock()
        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
        mock_db.collection.return_value.get.return_value = []

        candidate = EntityCandidate("Unknown Company", None, ContactRole.proveedor, "emisor")
        result = find_matching_contact(mock_db, candidate)
        assert result is None

    def test_name_match_skipped_when_nifs_differ(self):
        """Candidate with NIF N36841196 must NOT match contact with NIF B65176411
        even if company names are similar (e.g. 'X y asociados S.Coop.')."""
        existing_contact = MagicMock()
        existing_contact.id = "existing-contact"
        existing_contact.to_dict.return_value = {
            "nombre_fiscal": "Cano y asociados S.Coop.",
            "tax_id": "B65176411",
            "roles": ["cliente"],
        }

        mock_db = MagicMock()
        # NIF query returns nothing (different NIF)
        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
        # Name scan returns the existing contact
        mock_db.collection.return_value.get.return_value = [existing_contact]

        candidate = EntityCandidate(
            "Patiño y asociados S.Coop.", "N36841196", ContactRole.cliente, "receptor",
        )
        result = find_matching_contact(mock_db, candidate)
        assert result is None, "Should not match a contact with a different NIF"

    def test_name_match_allowed_when_contact_has_no_nif(self):
        """If the existing contact has no NIF, name matching should still work."""
        existing_contact = MagicMock()
        existing_contact.id = "no-nif-contact"
        existing_contact.to_dict.return_value = {
            "nombre_fiscal": "Acme Corp",
            "tax_id": None,
            "roles": ["proveedor"],
        }

        mock_db = MagicMock()
        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
        mock_db.collection.return_value.get.return_value = [existing_contact]

        candidate = EntityCandidate("Acme Corp", "B11111111", ContactRole.proveedor, "emisor")
        result = find_matching_contact(mock_db, candidate)
        assert result is not None
        assert result[0] == "no-nif-contact"


# ---------------------------------------------------------------------------
# resolve_and_link
# ---------------------------------------------------------------------------

class TestResolveAndLink:
    def _mock_cuenta_doc(self, mock_db, tax_id="A00000000"):
        """Configure mock_db to return a cuenta document with the given tax_id."""
        cuenta_doc = MagicMock()
        cuenta_doc.exists = True
        cuenta_doc.to_dict.return_value = {"tax_id": tax_id, "nombre": "Mi Empresa"}
        mock_db.document.return_value.get.return_value = cuenta_doc

    def test_creates_contact_for_new_entity(self):
        mock_db = MagicMock()
        self._mock_cuenta_doc(mock_db, tax_id="A00000000")
        # find_matching_contact returns no matches
        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
        mock_db.collection.return_value.get.return_value = []
        # New doc ref
        mock_ref = MagicMock()
        mock_ref.id = "new-contact-id"
        mock_db.collection.return_value.document.return_value = mock_ref

        data = {"issuer_name": "NewCorp S.L.", "issuer_nif": "B99999999", "total_amount": 100}
        ctx = TenantContext(gestoria_id="g1", cliente_id="c1")

        refs = resolve_and_link(mock_db, data, "invoice_received", "hash123", ctx)

        assert len(refs) == 1
        assert refs[0].contacto_id == "new-contact-id"
        assert refs[0].rol_en_documento == "emisor"
        # Verify set was called (new contact created)
        mock_ref.set.assert_called_once()

    def test_new_contact_has_all_fields(self):
        """New contacts must have ALL model fields initialized (including enrichable ones)."""
        mock_db = MagicMock()
        self._mock_cuenta_doc(mock_db, tax_id="A00000000")
        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
        mock_db.collection.return_value.get.return_value = []
        mock_ref = MagicMock()
        mock_ref.id = "full-contact"
        mock_db.collection.return_value.document.return_value = mock_ref

        data = {
            "issuer_name": "Corp S.L.", "issuer_nif": "B12345678",
            "total_amount": 242.0, "payment_method": "Transferencia bancaria",
        }
        ctx = TenantContext(gestoria_id="g1", cliente_id="c1")
        resolve_and_link(mock_db, data, "invoice_received", "h1", ctx)

        contact_data = mock_ref.set.call_args[0][0]
        # Core fields
        assert contact_data["tax_id"] == "B12345678"
        assert contact_data["nombre_fiscal"] is not None
        assert contact_data["roles"] == ["proveedor"]
        # Enrichable fields initialized (not missing from dict)
        assert "direccion_fiscal" in contact_data
        assert "email_contacto" in contact_data
        assert "telefono" in contact_data
        assert "iban" in contact_data
        # payment_method propagated to forma_pago_habitual
        assert contact_data["forma_pago_habitual"] == "Transferencia bancaria"
        # Totals: proveedor → total_recibido set
        assert contact_data["total_recibido"] == 242.0
        assert contact_data["total_facturado"] is None

    def test_new_contact_cliente_sets_total_facturado(self):
        """For invoice_sent, the client contact should get total_facturado."""
        mock_db = MagicMock()
        self._mock_cuenta_doc(mock_db, tax_id="B11111111")
        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
        mock_db.collection.return_value.get.return_value = []
        mock_ref = MagicMock()
        mock_ref.id = "client-contact"
        mock_db.collection.return_value.document.return_value = mock_ref

        data = {
            "issuer_name": "Mi Empresa", "issuer_nif": "B11111111",
            "client_name": "Client Corp", "client_nif": "A87654321",
            "total_amount": 500.0,
        }
        ctx = TenantContext(gestoria_id="g1", cliente_id="c1")
        resolve_and_link(mock_db, data, "invoice_sent", "h2", ctx)

        contact_data = mock_ref.set.call_args[0][0]
        assert contact_data["roles"] == ["cliente"]
        assert contact_data["total_facturado"] == 500.0
        assert contact_data["total_recibido"] is None

    def test_skip_cuenta_entity_invoice_received(self):
        """When issuer matches cuenta tax_id and client doesn't, only client contact is created as proveedor."""
        mock_db = MagicMock()
        self._mock_cuenta_doc(mock_db, tax_id="A99999999")
        # No existing contacts
        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
        mock_db.collection.return_value.get.return_value = []
        mock_ref = MagicMock()
        mock_ref.id = "other-party-id"
        mock_db.collection.return_value.document.return_value = mock_ref

        data = {
            "issuer_name": "Proveedor S.L.", "issuer_nif": "B12345678",
            "client_name": "Mi Empresa", "client_nif": "A99999999",
        }
        ctx = TenantContext(gestoria_id="g1", cliente_id="c1")

        refs = resolve_and_link(mock_db, data, "invoice_received", "hash-skip", ctx)

        # Only one contact created (the issuer = proveedor), "Mi Empresa" was skipped
        assert len(refs) == 1
        assert refs[0].rol_en_documento == "emisor"
        # The created contact should have role=proveedor
        call_args = mock_ref.set.call_args[0][0]
        assert call_args["roles"] == ["proveedor"]

    def test_skip_cuenta_entity_invoice_sent(self):
        """When issuer matches cuenta tax_id, only the client contact is created as cliente."""
        mock_db = MagicMock()
        self._mock_cuenta_doc(mock_db, tax_id="B11111111")
        # No existing contacts
        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
        mock_db.collection.return_value.get.return_value = []
        mock_ref = MagicMock()
        mock_ref.id = "client-contact-id"
        mock_db.collection.return_value.document.return_value = mock_ref

        data = {
            "issuer_name": "Mi Empresa S.L.", "issuer_nif": "B11111111",
            "client_name": "Cliente Corp", "client_nif": "A87654321",
        }
        ctx = TenantContext(gestoria_id="g1", cliente_id="c1")

        refs = resolve_and_link(mock_db, data, "invoice_sent", "hash-sent", ctx)

        assert len(refs) == 1
        assert refs[0].rol_en_documento == "receptor"
        call_args = mock_ref.set.call_args[0][0]
        assert call_args["roles"] == ["cliente"]

    def test_updates_existing_contact(self):
        mock_db = MagicMock()
        self._mock_cuenta_doc(mock_db, tax_id="A00000000")

        existing_doc = MagicMock()
        existing_doc.id = "existing-id"
        existing_doc.to_dict.return_value = {
            "nombre_fiscal": "Acme",
            "tax_id": "B12345678",
            "roles": ["proveedor"],
            "confidence": 0.5,
            "total_documentos": 3,
        }

        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = [existing_doc]

        data = {"issuer_name": "Acme S.L.", "issuer_nif": "B12345678", "total_amount": 200}
        ctx = TenantContext(gestoria_id="g1", cliente_id="c1")

        refs = resolve_and_link(mock_db, data, "invoice_received", "hash456", ctx)

        assert len(refs) == 1
        assert refs[0].contacto_id == "existing-id"
        # Verify update was called
        mock_db.collection.return_value.document.return_value.update.assert_called_once()

    def test_no_entities_returns_empty(self):
        mock_db = MagicMock()
        data = {"amount": 100, "payment_date": "2024-01-01"}

        refs = resolve_and_link(mock_db, data, "payment_receipt", "hash789")
        assert refs == []

    def test_role_accumulation_on_same_contact(self):
        """If a contact exists as proveedor and we process an invoice_sent to them, role becomes both."""
        mock_db = MagicMock()
        self._mock_cuenta_doc(mock_db, tax_id="X00000000")

        existing_doc = MagicMock()
        existing_doc.id = "dual-role-id"
        existing_doc.to_dict.return_value = {
            "nombre_fiscal": "DualCorp",
            "tax_id": "A11111111",
            "roles": ["proveedor"],
            "confidence": 0.9,
            "total_documentos": 5,
        }

        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = [existing_doc]

        data = {"client_name": "DualCorp", "client_nif": "A11111111"}
        ctx = TenantContext(gestoria_id="g1", cliente_id="c1")

        refs = resolve_and_link(mock_db, data, "invoice_sent", "hash-dual", ctx)

        assert len(refs) == 1
        # Verify the update includes the new role
        call_args = mock_db.collection.return_value.document.return_value.update.call_args
        updates = call_args[0][0]
        assert "proveedor" in updates["roles"]
        assert "cliente" in updates["roles"]

    def test_contract_extracts_multiple_parties(self):
        mock_db = MagicMock()
        # No cuenta doc needed for contracts (roles are assigned during extraction)
        cuenta_doc = MagicMock()
        cuenta_doc.exists = False
        mock_db.document.return_value.get.return_value = cuenta_doc

        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
        mock_db.collection.return_value.get.return_value = []
        mock_ref = MagicMock()
        mock_ref.id = "party-id"
        mock_db.collection.return_value.document.return_value = mock_ref

        data = {"parties": [
            {"name": "Parte A", "nif": "B11111111"},
            {"name": "Parte B", "nif": "A22222222"},
        ]}

        refs = resolve_and_link(mock_db, data, "contract", "hash-contract")
        assert len(refs) == 2
        assert all(r.rol_en_documento == "parte" for r in refs)

    def test_exception_in_one_entity_does_not_block_others(self):
        """If resolving one entity fails, continue with the rest."""
        mock_db = MagicMock()
        # Contract — no cuenta matching needed
        cuenta_doc = MagicMock()
        cuenta_doc.exists = False
        mock_db.document.return_value.get.return_value = cuenta_doc

        # First entity: tax_id query raises → whole entity caught by except.
        # Second entity: tax_id query returns [], nif fallback returns [].
        mock_db.collection.return_value.where.return_value.limit.return_value.get.side_effect = [
            Exception("Firestore error"),  # party 1 tax_id query (caught → skip)
            [],  # party 2 tax_id query
            [],  # party 2 nif fallback
        ]
        mock_db.collection.return_value.get.return_value = []
        mock_ref = MagicMock()
        mock_ref.id = "party-2"
        mock_db.collection.return_value.document.return_value = mock_ref

        data = {"parties": [
            {"name": "Failing Party", "nif": "X00000000"},
            {"name": "Working Party", "nif": "B99999999"},
        ]}

        refs = resolve_and_link(mock_db, data, "contract", "hash-err")
        # At least one should succeed (the second one)
        assert len(refs) >= 1

    def test_guardrail_blocks_cuenta_nif_contact(self):
        """Even if _assign_roles fails to filter the cuenta entity,
        the guardrail in resolve_and_link must block it from being persisted."""
        mock_db = MagicMock()
        self._mock_cuenta_doc(mock_db, tax_id="Q24615910")
        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
        mock_db.collection.return_value.get.return_value = []
        mock_ref = MagicMock()
        mock_ref.id = "should-not-exist"
        mock_db.collection.return_value.document.return_value = mock_ref

        # Both entities have NIFs — one matches the cuenta
        data = {
            "issuer_name": "Mi Empresa", "issuer_nif": "Q24615910",
            "client_name": "Proveedor SL", "client_nif": "B99999999",
        }
        ctx = TenantContext(gestoria_id="g1", cliente_id="c1")
        refs = resolve_and_link(mock_db, data, "invoice_received", "h-guard", ctx)

        # Only 1 contact (proveedor), cuenta entity blocked
        assert len(refs) == 1
        # issuer was the cuenta (Q24615910) → skipped. Client (receptor) remains.
        assert refs[0].rol_en_documento == "receptor"
        # Verify only 1 set call (not 2)
        assert mock_ref.set.call_count == 1
        contact_data = mock_ref.set.call_args[0][0]
        assert contact_data["tax_id"] != "Q24615910"

    def test_guardrail_blocks_junk_prefix_nif(self):
        """Cuenta NIF with junk prefix (NIFQ24615910) must still be blocked."""
        mock_db = MagicMock()
        self._mock_cuenta_doc(mock_db, tax_id="Q24615910")
        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
        mock_db.collection.return_value.get.return_value = []
        mock_ref = MagicMock()
        mock_ref.id = "blocked"
        mock_db.collection.return_value.document.return_value = mock_ref

        data = {
            "issuer_name": "Mi Empresa", "issuer_nif": "NIFQ24615910",
            "client_name": "Otro SL", "client_nif": "B88888888",
        }
        ctx = TenantContext(gestoria_id="g1", cliente_id="c1")
        refs = resolve_and_link(mock_db, data, "invoice_received", "h-junk", ctx)

        assert len(refs) == 1
        assert mock_ref.set.call_count == 1
        contact_data = mock_ref.set.call_args[0][0]
        assert contact_data["tax_id"] != "Q24615910"

    def test_guardrail_blocks_update_of_existing_cuenta_contact(self):
        """If an existing contact already has the cuenta's NIF (created before
        the guardrail was added), the update path must also block it.

        Scenario: expense_ticket has no NIF, so it passes all NIF-based guards.
        find_matching_contact finds the bad self-contact via name similarity.
        The update-path guardrail must block the update.
        """
        mock_db = MagicMock()
        self._mock_cuenta_doc(mock_db, tax_id="A29183164")

        # Simulate find_matching_contact returning the bad self-contact via
        # name-based scanning (no NIF on expense_ticket candidate)
        existing_contact_doc = MagicMock()
        existing_contact_doc.id = "bad-self-contact-id"
        existing_contact_doc.to_dict.return_value = {
            "tax_id": "A29183164",
            "nombre_fiscal": "Mi Empresa SA",
            "roles": ["proveedor"],
            "total_documentos": 21,
        }
        # No NIF query (expense_ticket has no NIF); all-contacts scan returns the bad doc
        mock_db.collection.return_value.where.return_value.limit.return_value.get.return_value = []
        mock_db.collection.return_value.get.return_value = [existing_contact_doc]

        # expense_ticket: only issuer_name extracted, NIF=None
        data = {"issuer_name": "Mi Empresa SA"}
        ctx = TenantContext(gestoria_id="g1", cliente_id="c1")

        refs = resolve_and_link(mock_db, data, "expense_ticket", "h-self", ctx)

        # The candidate matched the bad contact but was blocked → no refs, no update
        assert len(refs) == 0
        # Verify the bad contact was NOT updated
        mock_db.collection.return_value.document.return_value.update.assert_not_called()


# ---------------------------------------------------------------------------
# tax_ids_match (cross-module helper)
# ---------------------------------------------------------------------------

class TestTaxIdsMatch:
    def test_identical(self):
        assert tax_ids_match("B12345678", "B12345678") is True

    def test_es_prefix_left(self):
        assert tax_ids_match("ESB12345678", "B12345678") is True

    def test_es_prefix_right(self):
        assert tax_ids_match("B12345678", "ESB12345678") is True

    def test_both_es_prefix(self):
        assert tax_ids_match("ESB12345678", "ESB12345678") is True

    def test_dashes_and_dots(self):
        assert tax_ids_match("ES-B12.345.678", "B12345678") is True

    def test_different_ids(self):
        assert tax_ids_match("A99999999", "B12345678") is False

    def test_nie_with_prefix(self):
        assert tax_ids_match("ESX1234567L", "X1234567L") is True

    def test_persona_fisica(self):
        assert tax_ids_match("ES12345678Z", "12345678Z") is True

    def test_nif_junk_prefix(self):
        """'NIF Q24615910' → 'NIFQ24615910' must match 'Q24615910'."""
        assert tax_ids_match("NIFQ24615910", "Q24615910") is True

    def test_cif_junk_prefix(self):
        assert tax_ids_match("CIFB12345678", "B12345678") is True

    def test_suffix_no_false_positive(self):
        """Unrelated IDs must not match even with suffix logic."""
        assert tax_ids_match("NIFB12345678", "Q24615910") is False
