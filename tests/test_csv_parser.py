"""Tests for Schwab CSV parsing."""

import textwrap

import pytest

from rsu_tax.csv_parser import detect_column_mapping, parse_schwab_csv

# ── Column detection ──────────────────────────────────────────────────────────

def test_detect_standard_headers():
    headers = ["Symbol", "Date Acquired", "Date Sold", "Quantity", "Proceeds", "Cost Basis", "Gain/Loss"]
    mapping = detect_column_mapping(headers)
    assert mapping["symbol"] == "Symbol"
    assert mapping["date_acquired"] == "Date Acquired"
    assert mapping["date_sold"] == "Date Sold"
    assert mapping["proceeds"] == "Proceeds"
    assert mapping["cost_basis"] == "Cost Basis"
    assert mapping["gain_loss"] == "Gain/Loss"


def test_detect_schwab_realized_gain_headers():
    headers = [
        "Symbol", "Description", "Quantity", "Date Acquired", "Date Sold",
        "Proceeds", "Cost Basis (CB)", "Short Term (ST) Gain/Loss ($)",
        "Long Term (LT) Gain/Loss ($)", "Total Gain/Loss ($)", "Wash Sale?",
    ]
    mapping = detect_column_mapping(headers)
    assert mapping["symbol"] == "Symbol"
    assert mapping["cost_basis"] == "Cost Basis (CB)"
    assert mapping["gain_loss"] == "Total Gain/Loss ($)"
    assert mapping["st_gain_loss"] == "Short Term (ST) Gain/Loss ($)"
    assert mapping["lt_gain_loss"] == "Long Term (LT) Gain/Loss ($)"
    assert mapping["wash_sale"] == "Wash Sale?"


def test_detect_alternative_headers():
    headers = ["Ticker", "Sale Date", "Total Proceeds", "Adjusted Cost Basis", "Realized Gain"]
    mapping = detect_column_mapping(headers)
    assert mapping["symbol"] == "Ticker"
    assert mapping["date_sold"] == "Sale Date"
    assert mapping["proceeds"] == "Total Proceeds"
    assert mapping["cost_basis"] == "Adjusted Cost Basis"
    assert mapping["gain_loss"] == "Realized Gain"


# ── Full CSV parsing ──────────────────────────────────────────────────────────

_BASIC_CSV = textwrap.dedent("""\
    Symbol,Date Acquired,Date Sold,Quantity,Proceeds,Cost Basis,Gain/Loss
    GOOG,01/10/2023,06/15/2023,10,"$15,000.00","$12,000.00","$3,000.00"
    GOOG,02/20/2023,06/15/2023,5,"$7,500.00","$6,500.00","$1,000.00"
""")


def test_parse_basic_csv():
    result = parse_schwab_csv(_BASIC_CSV)
    assert len(result.transactions) == 2
    t = result.transactions[0]
    assert t.symbol == "GOOG"
    assert t.date_acquired == "2023-01-10"
    assert t.date_sold == "2023-06-15"
    assert t.proceeds_usd == pytest.approx(15_000.0)
    assert t.cost_basis_usd == pytest.approx(12_000.0)
    assert t.gain_loss_usd == pytest.approx(3_000.0)
    assert t.has_acquisition_date is True


def test_parse_negative_gain_parentheses():
    csv = textwrap.dedent("""\
        Symbol,Date Acquired,Date Sold,Quantity,Proceeds,Cost Basis,Gain/Loss
        AMZN,03/01/2023,09/01/2023,2,"$1,800.00","$2,000.00","($200.00)"
    """)
    result = parse_schwab_csv(csv)
    assert result.transactions[0].gain_loss_usd == pytest.approx(-200.0)


def test_parse_term_from_st_lt_columns():
    csv = textwrap.dedent("""\
        Symbol,Date Acquired,Date Sold,Quantity,Proceeds,Cost Basis,Short Term (ST) Gain/Loss ($),Long Term (LT) Gain/Loss ($),Total Gain/Loss ($)
        MSFT,01/01/2022,05/01/2022,3,"$900.00","$800.00","$100.00","--","$100.00"
        MSFT,01/01/2020,05/01/2023,2,"$600.00","$500.00","--","$100.00","$100.00"
    """)
    result = parse_schwab_csv(csv)
    assert result.transactions[0].term == "Short Term"
    assert result.transactions[1].term == "Long Term"


def test_skip_total_rows():
    csv = textwrap.dedent("""\
        Symbol,Date Acquired,Date Sold,Quantity,Proceeds,Cost Basis,Gain/Loss
        GOOG,01/10/2023,06/15/2023,10,"$15,000.00","$12,000.00","$3,000.00"
        Total,,,,"$15,000.00","$12,000.00","$3,000.00"
    """)
    result = parse_schwab_csv(csv)
    assert len(result.transactions) == 1
    assert result.transactions[0].symbol == "GOOG"


def test_schwab_header_footer_noise():
    csv = textwrap.dedent("""\
        "Realized Gain/Loss for Account XXXX1234"
        Symbol,Date Acquired,Date Sold,Quantity,Proceeds,Cost Basis,Gain/Loss
        AAPL,01/01/2023,07/01/2023,5,"$5,000.00","$4,000.00","$1,000.00"
        "***End of file***"
    """)
    result = parse_schwab_csv(csv)
    assert len(result.transactions) == 1
    assert result.transactions[0].symbol == "AAPL"


def test_no_date_acquired_warning():
    csv = textwrap.dedent("""\
        Symbol,Date Sold,Quantity,Proceeds,Cost Basis,Gain/Loss
        GOOG,06/15/2023,10,"$15,000.00","$12,000.00","$3,000.00"
    """)
    result = parse_schwab_csv(csv)
    assert result.transactions[0].has_acquisition_date is False
    assert result.transactions[0].date_acquired == result.transactions[0].date_sold
    assert any("Date Acquired" in w or "date" in w.lower() for w in result.warnings)
