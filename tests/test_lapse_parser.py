"""Tests for the lapse history CSV parser."""

from __future__ import annotations

import textwrap

import pytest

from rsu_tax.lapse_parser import LapseParseResult, parse_lapse_csv
from rsu_tax.models import LapseEvent

# ── Minimal valid lapse CSV ─────────────────────────────────────────────

MINIMAL_CSV = textwrap.dedent("""\
    "Date","Action","Symbol","Description","Quantity","FeesAndCommissions","DisbursementElection","Amount","AwardDate","AwardId","FairMarketValuePrice","SalePrice","SharesSoldWithheldForTaxes","NetSharesDeposited","Taxes"
    "03/15/2026","Lapse","AVGO","Restricted Stock Lapse","30","","","","","","","","","",""
    "","","","","","","","","11/22/2023","VM-00225234","$321.43","$322.79","15","15","$4,577.97"
""")


def test_parse_single_event() -> None:
    result = parse_lapse_csv(MINIMAL_CSV)
    assert len(result.events) == 1
    e = result.events[0]
    assert e.symbol == "AVGO"
    assert e.lapse_date == "2026-03-15"
    assert e.total_shares == 30.0
    assert e.award_date == "2023-11-22"
    assert e.award_id == "VM-00225234"
    assert e.fmv_per_share_usd == 321.43
    assert e.sale_price_usd == 322.79
    assert e.shares_sold_for_taxes == 15.0
    assert e.shares_delivered == 15.0
    assert e.taxes_usd == 4577.97


# ── Multiple events ─────────────────────────────────────────────────────

MULTI_CSV = textwrap.dedent("""\
    "Date","Action","Symbol","Description","Quantity","FeesAndCommissions","DisbursementElection","Amount","AwardDate","AwardId","FairMarketValuePrice","SalePrice","SharesSoldWithheldForTaxes","NetSharesDeposited","Taxes"
    "03/15/2026","Lapse","AVGO","Restricted Stock Lapse","30","","","","","","","","","",""
    "","","","","","","","","11/22/2023","VM-001","$321.43","$322.79","15","15","$4,577.97"
    "03/15/2026","Lapse","AVGO","Restricted Stock Lapse","88","","","","","","","","","",""
    "","","","","","","","","03/15/2025","VM-002","$321.43","$322.79","42","46","$13,428.70"
    "12/31/2025","Lapse","AVGO","Restricted Stock Lapse","49","","","","","","","","","",""
    "","","","","","","","","12/08/2023","VM-003","$336.11","$331.46","25","25","$7,843.54"
""")


def test_parse_multiple_events() -> None:
    result = parse_lapse_csv(MULTI_CSV)
    assert len(result.events) == 3
    assert result.events[0].total_shares == 30.0
    assert result.events[1].total_shares == 88.0
    assert result.events[2].total_shares == 49.0
    assert result.events[2].lapse_date == "2025-12-31"


def test_different_lapse_dates() -> None:
    result = parse_lapse_csv(MULTI_CSV)
    dates = {e.lapse_date for e in result.events}
    assert dates == {"2026-03-15", "2025-12-31"}


# ── Real anonymized test data ──────────────────────────────────────────

def test_parse_real_anonymized_file() -> None:
    with open("test-data/lapses-anonymized.csv") as f:
        csv_text = f.read()
    result = parse_lapse_csv(csv_text)
    assert len(result.warnings) == 0
    assert len(result.events) == 6
    # Check all events have valid data
    for e in result.events:
        assert e.symbol == "ACME"
        assert e.fmv_per_share_usd > 0
        assert e.sale_price_usd > 0
        assert e.taxes_usd > 0
        assert e.shares_sold_for_taxes > 0
        assert e.shares_delivered > 0


def test_shares_roughly_add_up() -> None:
    """shares_sold + shares_delivered should be close to total_shares.

    May not be exact due to anonymization rounding.
    """
    with open("test-data/lapses-anonymized.csv") as f:
        csv_text = f.read()
    result = parse_lapse_csv(csv_text)
    for e in result.events:
        assert abs(
            e.shares_sold_for_taxes + e.shares_delivered - e.total_shares
        ) <= 2  # allow small rounding from anonymization


# ── Edge cases ──────────────────────────────────────────────────────────

def test_empty_csv() -> None:
    result = parse_lapse_csv("")
    assert len(result.events) == 0
    assert any("Empty" in w for w in result.warnings)


def test_wrong_file_type() -> None:
    csv_text = '"Symbol","Name","Closed Date","Quantity"\n"AVGO","BROADCOM","03/17/2026","61"\n'
    result = parse_lapse_csv(csv_text)
    assert len(result.events) == 0
    assert any("Not a lapse CSV" in w for w in result.warnings)


def test_header_without_detail_at_eof() -> None:
    """A header row at the end of file without a following detail row."""
    csv_text = textwrap.dedent("""\
        "Date","Action","Symbol","Description","Quantity","FeesAndCommissions","DisbursementElection","Amount","AwardDate","AwardId","FairMarketValuePrice","SalePrice","SharesSoldWithheldForTaxes","NetSharesDeposited","Taxes"
        "03/15/2026","Lapse","AVGO","Restricted Stock Lapse","30","","","","","","","","","",""
    """)
    result = parse_lapse_csv(csv_text)
    assert len(result.events) == 0
    assert any("without detail" in w for w in result.warnings)


def test_lapse_event_model_fields() -> None:
    """Verify LapseEvent model can be constructed with all fields."""
    e = LapseEvent(
        symbol="TEST",
        lapse_date="2025-01-01",
        total_shares=100,
        award_date="2023-06-15",
        award_id="AWD-123",
        fmv_per_share_usd=250.00,
        sale_price_usd=251.50,
        shares_sold_for_taxes=48,
        shares_delivered=52,
        taxes_usd=12000.00,
    )
    assert e.fmv_per_share_usd * e.total_shares == 25000.00
