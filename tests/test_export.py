"""Tests for CSV/PDF/Markdown export."""

import csv
import io

import pytest

from rsu_tax.calculator import compute_capital_gains, compute_summary
from rsu_tax.export import export_csv, export_markdown, export_pdf
from rsu_tax.models import SchwabTransaction
from rsu_tax.verification import run_verification

_RATES = {
    "2023-01-10": 0.920,
    "2023-06-15": 0.910,
}

_T = SchwabTransaction(
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


def _computed():
    return compute_capital_gains([_T], _RATES)


def test_csv_has_headers():
    content = export_csv(_computed())
    reader = csv.reader(io.StringIO(content))
    headers = next(reader)
    assert "Symbol" in headers
    assert "Gain/Loss (EUR)" in headers
    assert "Type" in headers


def test_csv_values():
    computed = _computed()
    content = export_csv(computed)
    rows = list(csv.DictReader(io.StringIO(content)))
    assert len(rows) == 1
    assert rows[0]["Symbol"] == "GOOG"
    assert float(rows[0]["Gain/Loss (EUR)"]) == pytest.approx(computed[0].gain_loss_eur)


def test_csv_no_acquisition_date():
    t_no_acq = _T.model_copy(update={"has_acquisition_date": False})
    computed = compute_capital_gains([t_no_acq], _RATES)
    content = export_csv(computed)
    rows = list(csv.DictReader(io.StringIO(content)))
    assert rows[0]["Date Acquired"] == ""


def test_pdf_returns_bytes():
    computed = _computed()
    summary = compute_summary(computed)
    checks = run_verification(computed)
    pdf = export_pdf(computed, summary, checks)
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"


# ── Markdown export ───────────────────────────────────────────────────────────

def test_markdown_contains_tax_year():
    computed = _computed()
    summary = compute_summary(computed)
    checks = run_verification(computed)
    md = export_markdown(computed, summary, checks)
    assert "Tax Year 2023" in md


def test_markdown_contains_net_gain():
    computed = _computed()
    summary = compute_summary(computed)
    checks = run_verification(computed)
    md = export_markdown(computed, summary, checks)
    assert "Net Capital Gain/Loss (EUR)" in md
    # Proceeds: 15000 * 0.910 = 13650, Cost: 12000 * 0.920 = 11040, Gain = 2610
    assert "2,610.00 EUR" in md


def test_markdown_exchange_rates_section():
    computed = _computed()
    summary = compute_summary(computed)
    checks = run_verification(computed)
    md = export_markdown(computed, summary, checks)
    assert "Exchange Rates Used" in md
    assert "api.frankfurter.app" in md
    assert "2023-01-10" in md  # acquisition date
    assert "2023-06-15" in md  # sale date


def test_markdown_exact_match_note():
    computed = _computed()
    summary = compute_summary(computed)
    checks = run_verification(computed)
    md = export_markdown(computed, summary, checks)
    assert "Exact match" in md


def test_markdown_fallback_note():
    # Use a weekend date so the rate falls back to the prior Friday
    rates_with_weekend = {
        "2023-01-10": 0.920,
        "2023-06-16": 0.912,  # Friday (sale was "Saturday" 2023-06-17)
    }
    t_weekend = SchwabTransaction(
        symbol="MSFT",
        quantity=5,
        date_acquired="2023-01-10",
        date_sold="2023-06-17",  # Saturday
        proceeds_usd=5_000.0,
        cost_basis_usd=4_000.0,
        gain_loss_usd=1_000.0,
        term="Long Term",
        has_acquisition_date=True,
    )
    computed = compute_capital_gains([t_weekend], rates_with_weekend)
    summary = compute_summary(computed)
    checks = run_verification(computed)
    md = export_markdown(computed, summary, checks)
    assert "Fallback from 2023-06-17" in md
    assert "2023-06-16" in md  # effective ECB date


def test_markdown_verification_checks():
    computed = _computed()
    summary = compute_summary(computed)
    checks = run_verification(computed)
    md = export_markdown(computed, summary, checks)
    assert "Verification Checks" in md
    assert "OK" in md or "WARN" in md or "FAIL" in md


def test_markdown_methodology_section():
    computed = _computed()
    summary = compute_summary(computed)
    checks = run_verification(computed)
    md = export_markdown(computed, summary, checks)
    assert "Methodology" in md
    assert "Sell-to-Cover Detection" in md


def test_markdown_transaction_details():
    computed = _computed()
    summary = compute_summary(computed)
    checks = run_verification(computed)
    md = export_markdown(computed, summary, checks)
    assert "Transaction Details" in md
    assert "GOOG" in md
    assert "15,000.00 USD" in md


# ── effective_date fields in calculator ──────────────────────────────────────

def test_effective_dates_exact_match():
    computed = _computed()
    assert computed[0].effective_date_sold == "2023-06-15"
    assert computed[0].effective_date_acquired == "2023-01-10"


def test_effective_date_fallback():
    rates_with_gap = {"2023-01-10": 0.920, "2023-06-16": 0.912}
    t = _T.model_copy(update={"date_sold": "2023-06-17"})  # Saturday
    computed = compute_capital_gains([t], rates_with_gap)
    assert computed[0].effective_date_sold == "2023-06-16"
    assert computed[0].effective_date_acquired == "2023-01-10"
