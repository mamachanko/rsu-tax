"""Tests for the lapse data enrichment pipeline."""

from __future__ import annotations

import pytest

from rsu_tax.enrichment import EnrichmentResult, enrich_transactions
from rsu_tax.models import LapseEvent, SchwabTransaction


def _make_tx(
    symbol: str = "AVGO",
    date_sold: str = "2025-07-01",
    date_acquired: str = "2025-07-01",
    has_acquisition_date: bool = False,
    quantity: float = 30.0,
    cost_basis_usd: float = 9642.90,
    proceeds_usd: float = 9700.00,
    gain_loss_usd: float = 57.10,
) -> SchwabTransaction:
    return SchwabTransaction(
        symbol=symbol,
        quantity=quantity,
        date_acquired=date_acquired,
        date_sold=date_sold,
        proceeds_usd=proceeds_usd,
        cost_basis_usd=cost_basis_usd,
        gain_loss_usd=gain_loss_usd,
        term="Short Term",
        has_acquisition_date=has_acquisition_date,
    )


def _make_lapse(
    symbol: str = "AVGO",
    lapse_date: str = "2025-03-15",
    total_shares: float = 30.0,
    fmv_per_share_usd: float = 321.43,
    sale_price_usd: float = 322.79,
    shares_sold_for_taxes: float = 15.0,
    shares_delivered: float = 15.0,
    taxes_usd: float = 4577.97,
    award_id: str = "VM-001",
) -> LapseEvent:
    return LapseEvent(
        symbol=symbol,
        lapse_date=lapse_date,
        total_shares=total_shares,
        award_date="2023-11-22",
        award_id=award_id,
        fmv_per_share_usd=fmv_per_share_usd,
        sale_price_usd=sale_price_usd,
        shares_sold_for_taxes=shares_sold_for_taxes,
        shares_delivered=shares_delivered,
        taxes_usd=taxes_usd,
    )


# ── Basic enrichment ────────────────────────────────────────────────────

class TestBasicEnrichment:
    def test_fills_acquisition_date_from_lapse(self) -> None:
        """Transaction missing acq date gets it from matching lapse event."""
        tx = _make_tx(
            quantity=30.0,
            cost_basis_usd=321.43 * 30,  # = 9642.90
            has_acquisition_date=False,
        )
        lapse = _make_lapse(
            lapse_date="2025-03-15",
            fmv_per_share_usd=321.43,
        )
        result = enrich_transactions([tx], [lapse])
        assert result.matched == 1
        assert result.unmatched == 0
        enriched_tx = result.transactions[0]
        assert enriched_tx.date_acquired == "2025-03-15"
        assert enriched_tx.has_acquisition_date is True

    def test_no_lapse_events_is_noop(self) -> None:
        tx = _make_tx()
        result = enrich_transactions([tx], [])
        assert result.matched == 0
        assert result.unmatched == 0
        assert result.transactions[0] is tx

    def test_symbol_mismatch_no_match(self) -> None:
        tx = _make_tx(symbol="AVGO", has_acquisition_date=False)
        lapse = _make_lapse(symbol="GOOG")
        result = enrich_transactions([tx], [lapse])
        assert result.matched == 0
        assert result.unmatched == 1

    def test_cost_basis_mismatch_no_match(self) -> None:
        tx = _make_tx(
            quantity=30.0,
            cost_basis_usd=5000.00,  # doesn't match FMV * qty
            has_acquisition_date=False,
        )
        lapse = _make_lapse(fmv_per_share_usd=321.43)
        result = enrich_transactions([tx], [lapse])
        assert result.matched == 0
        assert result.unmatched == 1


# ── Multiple transactions ───────────────────────────────────────────────

class TestMultipleTransactions:
    def test_multiple_tx_same_lapse(self) -> None:
        """Multiple sell lots from the same vest event should all match."""
        fmv = 321.43
        lapse = _make_lapse(total_shares=88, fmv_per_share_usd=fmv)

        tx1 = _make_tx(quantity=42.0, cost_basis_usd=fmv * 42, has_acquisition_date=False)
        tx2 = _make_tx(quantity=46.0, cost_basis_usd=fmv * 46, has_acquisition_date=False)

        result = enrich_transactions([tx1, tx2], [lapse])
        assert result.matched == 2
        assert result.unmatched == 0
        assert result.transactions[0].date_acquired == "2025-03-15"
        assert result.transactions[1].date_acquired == "2025-03-15"

    def test_tx_with_existing_acq_date_preserved(self) -> None:
        """Transaction that already has an acquisition date keeps it."""
        tx = _make_tx(
            date_acquired="2024-06-15",
            has_acquisition_date=True,
            quantity=30.0,
            cost_basis_usd=321.43 * 30,
        )
        lapse = _make_lapse(lapse_date="2025-03-15")
        result = enrich_transactions([tx], [lapse])
        # It matches but doesn't change the existing date
        assert result.transactions[0].date_acquired == "2024-06-15"

    def test_mix_of_matched_and_unmatched(self) -> None:
        fmv = 321.43
        tx_match = _make_tx(quantity=30.0, cost_basis_usd=fmv * 30, has_acquisition_date=False)
        tx_nomatch = _make_tx(symbol="GOOG", quantity=10.0, cost_basis_usd=1000.0, has_acquisition_date=False)
        lapse = _make_lapse(fmv_per_share_usd=fmv)

        result = enrich_transactions([tx_match, tx_nomatch], [lapse])
        assert result.matched == 1
        assert result.unmatched == 1


# ── Tolerance ───────────────────────────────────────────────────────────

class TestTolerance:
    def test_slight_cost_basis_difference_still_matches(self) -> None:
        """Within 2% tolerance, the match should succeed."""
        fmv = 321.43
        # Cost basis is 1% off from FMV * quantity
        tx = _make_tx(
            quantity=30.0,
            cost_basis_usd=fmv * 30 * 1.01,  # 1% over
            has_acquisition_date=False,
        )
        lapse = _make_lapse(fmv_per_share_usd=fmv)
        result = enrich_transactions([tx], [lapse])
        assert result.matched == 1

    def test_large_cost_basis_difference_no_match(self) -> None:
        """Beyond tolerance, no match."""
        fmv = 321.43
        tx = _make_tx(
            quantity=30.0,
            cost_basis_usd=fmv * 30 * 1.10,  # 10% over
            has_acquisition_date=False,
        )
        lapse = _make_lapse(fmv_per_share_usd=fmv)
        result = enrich_transactions([tx], [lapse])
        assert result.matched == 0


# ── Warnings ────────────────────────────────────────────────────────────

class TestWarnings:
    def test_enrichment_warning_on_match(self) -> None:
        tx = _make_tx(quantity=30.0, cost_basis_usd=321.43 * 30, has_acquisition_date=False)
        lapse = _make_lapse()
        result = enrich_transactions([tx], [lapse])
        assert any("Enriched" in w for w in result.warnings)

    def test_warning_on_unmatched(self) -> None:
        tx = _make_tx(symbol="GOOG", has_acquisition_date=False)
        lapse = _make_lapse(symbol="AVGO")
        result = enrich_transactions([tx], [lapse])
        assert any("still missing" in w for w in result.warnings)

    def test_no_warnings_when_nothing_to_enrich(self) -> None:
        result = enrich_transactions([], [])
        assert len(result.warnings) == 0


# ── Original transaction unchanged ──────────────────────────────────────

class TestImmutability:
    def test_original_transaction_not_mutated(self) -> None:
        """Enrichment should create new objects, not mutate originals."""
        tx = _make_tx(quantity=30.0, cost_basis_usd=321.43 * 30, has_acquisition_date=False)
        original_date = tx.date_acquired
        lapse = _make_lapse()
        result = enrich_transactions([tx], [lapse])
        # Original unchanged
        assert tx.date_acquired == original_date
        assert tx.has_acquisition_date is False
        # Enriched is different
        assert result.transactions[0].date_acquired == "2025-03-15"
