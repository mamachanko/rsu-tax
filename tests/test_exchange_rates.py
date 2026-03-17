"""Tests for exchange rate lookup logic."""

import pytest

from rsu_tax.exchange_rates import find_rate, find_rate_with_date

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


# ── find_rate_with_date ───────────────────────────────────────────────────────

def test_find_rate_with_date_exact():
    result = find_rate_with_date("2024-01-02", _RATES)
    assert result is not None
    rate, eff_date = result
    assert rate == pytest.approx(0.920)
    assert eff_date == "2024-01-02"


def test_find_rate_with_date_fallback_returns_effective_date():
    # Saturday 2024-01-06 → should fall back to Friday 2024-01-05
    result = find_rate_with_date("2024-01-06", _RATES)
    assert result is not None
    rate, eff_date = result
    assert rate == pytest.approx(0.921)
    assert eff_date == "2024-01-05"  # actual ECB publication date


def test_find_rate_with_date_none_when_not_found():
    sparse: dict[str, float] = {"2024-01-01": 0.9}
    assert find_rate_with_date("2024-01-15", sparse) is None
