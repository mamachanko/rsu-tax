"""Tests for CSV/PDF export."""

import csv
import io

import pytest

from rsu_tax.calculator import compute_capital_gains, compute_summary
from rsu_tax.export import export_csv, export_pdf
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
