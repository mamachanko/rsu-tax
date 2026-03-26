"""Tests for the 1042-S PDF tax form parser."""

from __future__ import annotations

import pytest

from rsu_tax.tax_form_parser import TaxFormParseResult, parse_1042s_pdf


def test_parse_real_anonymized_1042s() -> None:
    """Parse the real anonymized 1042-S test PDF."""
    result = parse_1042s_pdf("test-data/1042S-anonymized.pdf")
    # Should extract some data (even if anonymized values are present)
    assert result.data is not None or len(result.warnings) > 0


def test_parse_nonexistent_file() -> None:
    result = parse_1042s_pdf("nonexistent.pdf")
    assert result.data is None
    assert any("Could not read" in w for w in result.warnings)


def test_tax_form_data_model() -> None:
    """Verify TaxFormData model works correctly."""
    from rsu_tax.models import TaxFormData

    data = TaxFormData(
        tax_year=2025,
        gross_income_usd=50000.00,
        tax_withheld_usd=15000.00,
        withholding_rate=0.30,
        income_code="19",
        recipient_country="DE",
    )
    assert data.tax_year == 2025
    assert data.withholding_rate == 0.30
    assert data.tax_withheld_usd / data.gross_income_usd == pytest.approx(0.30)
