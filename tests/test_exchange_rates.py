"""Tests for exchange rate lookup logic."""

import pytest

from rsu_tax.exchange_rates import find_rate

_RATES: dict[str, float] = {
    "2024-01-02": 0.920,
    "2024-01-03": 0.922,
    "2024-01-04": 0.919,
    "2024-01-05": 0.921,
    "2024-01-08": 0.923,  # no 6th/7th (weekend)
}


def test_exact_date_match():
    assert find_rate("2024-01-02", _RATES) == pytest.approx(0.920)


def test_weekend_fallback():
    # Saturday 2024-01-06 → falls back to Friday 2024-01-05
    assert find_rate("2024-01-06", _RATES) == pytest.approx(0.921)


def test_sunday_fallback():
    # Sunday 2024-01-07 → falls back to Friday 2024-01-05 (2 days)
    assert find_rate("2024-01-07", _RATES) == pytest.approx(0.921)


def test_no_rate_within_7_days():
    sparse: dict[str, float] = {"2024-01-01": 0.9}
    assert find_rate("2024-01-15", sparse) is None


def test_multi_day_fallback():
    # Extend gap: only 2024-01-02 available, query 2024-01-05 (3 business days later)
    partial = {"2024-01-02": 0.920}
    assert find_rate("2024-01-05", partial) == pytest.approx(0.920)
