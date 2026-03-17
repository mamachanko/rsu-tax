"""Tests for capital gains computation."""

import pytest

from rsu_tax.calculator import compute_capital_gains, compute_summary
from rsu_tax.models import SchwabTransaction

_RATES = {
    "2023-01-10": 0.920,
    "2023-06-15": 0.910,
}

_T1 = SchwabTransaction(
    symbol="GOOG",
    quantity=10,
    date_acquired="2023-01-10",
    date_sold="2023-06-15",
    proceeds_usd=15_000.0,
    cost_basis_usd=12_000.0,
    gain_loss_usd=3_000.0,
    term="Long Term",
    has_acquisition_date=True,
)

_T2 = SchwabTransaction(
    symbol="GOOG",
    quantity=5,
    date_acquired="2023-06-15",
    date_sold="2023-06-15",
    proceeds_usd=7_500.0,
    cost_basis_usd=7_499.50,
    gain_loss_usd=0.50,
    term="Short Term",
    has_acquisition_date=True,
)


def test_eur_conversion():
    computed = compute_capital_gains([_T1], _RATES)
    assert len(computed) == 1
    c = computed[0]
    # proceeds: 15000 * 0.910 = 13650.00
    assert c.proceeds_eur == pytest.approx(13_650.0)
    # cost: 12000 * 0.920 = 11040.00
    assert c.cost_basis_eur == pytest.approx(11_040.0)
    assert c.gain_loss_eur == pytest.approx(13_650.0 - 11_040.0)


def test_sell_to_cover_detection():
    computed = compute_capital_gains([_T2], _RATES)
    assert computed[0].is_sell_to_cover is True


def test_voluntary_not_sell_to_cover():
    computed = compute_capital_gains([_T1], _RATES)
    assert computed[0].is_sell_to_cover is False


def test_missing_rate_status():
    computed = compute_capital_gains(
        [_T1],
        {"2023-01-10": 0.920},  # missing 2023-06-15
    )
    assert computed[0].verification_status == "fail"


def test_no_acquisition_date_warn():
    t = SchwabTransaction(
        symbol="MSFT",
        quantity=3,
        date_acquired="2023-06-15",  # same as sold (inferred)
        date_sold="2023-06-15",
        proceeds_usd=1_000.0,
        cost_basis_usd=900.0,
        gain_loss_usd=100.0,
        term="Short Term",
        has_acquisition_date=False,  # <-- no acq. date in CSV
    )
    computed = compute_capital_gains([t], _RATES)
    assert computed[0].verification_status == "warn"
    assert any("sale-date" in n or "acquisition date" in n for n in computed[0].verification_notes)


def test_summary_separates_types():
    computed = compute_capital_gains([_T1, _T2], _RATES)
    summary = compute_summary(computed)
    assert summary.voluntary_sales == 1
    assert summary.sell_to_cover_sales == 1
    assert summary.total_transactions == 2
