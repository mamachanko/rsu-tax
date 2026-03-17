"""Tests for verification checks."""

import pytest

from rsu_tax.calculator import compute_capital_gains
from rsu_tax.models import SchwabTransaction
from rsu_tax.verification import run_verification

_RATES = {
    "2023-01-10": 0.920,
    "2023-06-15": 0.910,
}


def _make_transaction(**overrides) -> SchwabTransaction:
    defaults = dict(
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
    defaults.update(overrides)
    return SchwabTransaction(**defaults)


def test_all_pass():
    txns = compute_capital_gains([_make_transaction()], _RATES)
    checks = run_verification(txns)
    assert all(c.status == "pass" for c in checks), [c for c in checks if c.status != "pass"]


def test_usd_consistency_fail():
    t = _make_transaction(gain_loss_usd=99999.0)  # deliberately wrong
    txns = compute_capital_gains([t], _RATES)
    checks = {c.name: c for c in run_verification(txns)}
    assert checks["USD Gain/Loss Consistency"].status == "warn"


def test_exchange_rate_sanity_warn():
    bad_rates = {"2023-01-10": 2.5, "2023-06-15": 2.5}
    txns = compute_capital_gains([_make_transaction()], bad_rates)
    checks = {c.name: c for c in run_verification(txns)}
    assert checks["Exchange Rate Sanity"].status == "warn"


def test_exchange_rate_coverage_fail():
    txns = compute_capital_gains([_make_transaction()], {})
    checks = {c.name: c for c in run_verification(txns)}
    assert checks["Exchange Rate Coverage"].status == "fail"


def test_date_ordering_warn():
    t = _make_transaction(date_acquired="2024-01-01", date_sold="2023-06-15")
    txns = compute_capital_gains([t], _RATES)
    checks = {c.name: c for c in run_verification(txns)}
    assert checks["Date Ordering"].status == "warn"


def test_no_date_ordering_check_without_acq_date():
    t = _make_transaction(date_acquired="2023-06-15", date_sold="2023-06-15", has_acquisition_date=False)
    txns = compute_capital_gains([t], _RATES)
    checks = {c.name: c for c in run_verification(txns)}
    assert checks["Date Ordering"].status == "pass"
