"""Tests for app.services.tax_id — classification and matching."""

import pytest
from app.services.tax_id import classify_tax_id, tax_ids_match, normalize_tax_id_raw


# ── classify_tax_id ──────────────────────────────────────────────

class TestClassifyTaxId:
    """Verifies classify_tax_id recognises all valid Spanish CIF prefixes."""

    @pytest.mark.parametrize("nif,expected_type", [
        ("B12345678", "company"),   # S.L. / S.R.L.
        ("A87654321", "company"),   # S.A.
        ("Z59886272", "company"),   # S.A.T. / A.I.E.
        ("T41937135", "company"),   # U.T.E.
        ("G12345678", "company"),   # Asociación
        ("Q2461591H", "company"),   # Organismo público
    ])
    def test_spanish_company_prefixes(self, nif, expected_type):
        result = classify_tax_id(nif)
        assert result is not None, f"{nif} should be classified"
        assert result.tax_type == expected_type
        assert result.tax_country == "ES"

    def test_spanish_nif_persona(self):
        result = classify_tax_id("12345678Z")
        assert result is not None
        assert result.tax_type == "person"
        assert result.tax_country == "ES"

    def test_spanish_nie(self):
        result = classify_tax_id("X1234567L")
        assert result is not None
        assert result.tax_type == "nie"
        assert result.tax_country == "ES"

    def test_eu_vat_strips_es_prefix(self):
        result = classify_tax_id("ESB12345678")
        assert result is not None
        assert result.tax_id == "B12345678"
        assert result.tax_type == "company"

    @pytest.mark.parametrize("nif", [
        "ESZ59886272",
        "EST41937135",
    ])
    def test_eu_vat_es_prefix_with_z_t(self, nif):
        result = classify_tax_id(nif)
        assert result is not None
        assert result.tax_type == "company"
        assert result.tax_country == "ES"

    def test_unrecognisable_returns_none(self):
        assert classify_tax_id("") is None
        assert classify_tax_id("INVALID") is None


# ── tax_ids_match ────────────────────────────────────────────────

class TestTaxIdsMatch:

    def test_direct_match(self):
        assert tax_ids_match("B12345678", "B12345678")

    def test_es_prefix_match(self):
        assert tax_ids_match("Z59886272", "ESZ59886272")
        assert tax_ids_match("T41937135", "EST41937135")

    def test_suffix_containment(self):
        assert tax_ids_match("NIFQ24615910", "Q24615910")

    def test_different_ids_no_match(self):
        assert not tax_ids_match("B12345678", "A87654321")


# ── normalize_tax_id_raw ────────────────────────────────────────

class TestNormalizeTaxIdRaw:

    def test_strips_whitespace_and_punctuation(self):
        assert normalize_tax_id_raw("  b-123.456/78 ") == "B12345678"
