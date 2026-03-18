"""Tests for the CSV anonymization tool."""

from __future__ import annotations

import csv
import io
import re

from rsu_tax.anonymize import AnonConfig, anonymize_realized_gains_csv

SAMPLE_CSV = """\
"Realized Gain/Loss for ...482 for 01/01/2025 to 12/31/2025 as of Sat Mar 14  09:23:17 EDT 2026","","","","","","","","","","","","","","","","","","","","","","",""
"Symbol","Name","Closed Date","Quantity","Closing Price","Cost Basis Method","Proceeds","Cost Basis (CB)","Total Gain/Loss ($)","Total Gain/Loss (%)","Long Term (LT) Gain/Loss ($)","Long Term (LT) Gain/Loss (%)","Short Term (ST) Gain/Loss ($)","Short Term (ST) Gain/Loss (%)","Wash Sale?","Disallowed Loss","Transaction Closed Date","Transaction Cost Basis","Total Transaction Gain/Loss ($)","Total Transaction Gain/Loss (%)","LT Transaction Gain/Loss ($)","LT Transaction Gain/Loss (%)","ST Transaction Gain/Loss ($)","ST Transaction Gain/Loss (%)"
"AAPL","APPLE INC","03/15/2025","45","$187.32","Specific Lots","$8,429.40","$8,312.55","$116.85","1.405717340165%","--","--","$116.85","1.405717340165214%","No","","03/15/2025","","","","","","",""
"AAPL","APPLE INC","07/10/2025","150","$195.40","FIFO","$29,310.00","$28,475.30","$834.70","2.931266417498%","--","--","$834.70","2.931266417498159%","No","","07/10/2025","","","","","","",""
"AAPL","APPLE INC","09/15/2025","62","$203.75","Specific Lots","$12,632.50","$12,841.18","-$208.68","-1.624885498498%","--","--","-$208.68","-1.624885498497621%","No","","09/15/2025","","","","","","",""
"Total","","","","","","$50,371.90","$49,629.03","$742.87","1.496841458498%","$0.00","N/A","$742.87","1.496841458498372%","","","","","","","","","",""
"""


def _parse_rows(csv_text: str) -> list[dict[str, str]]:
    """Parse anonymized CSV into list of dicts (skip title row)."""
    lines = csv_text.strip().splitlines()
    # Find header
    for i, line in enumerate(lines):
        if "Symbol" in line:
            block = "\n".join(lines[i:])
            reader = csv.DictReader(io.StringIO(block))
            return list(reader)
    return []


def _parse_currency(value: str) -> float:
    cleaned = re.sub(r"[$,\s]", "", value.strip())
    if cleaned.startswith("(") and cleaned.endswith(")"):
        return -float(cleaned[1:-1])
    return float(cleaned) if cleaned and cleaned != "--" else 0.0


class TestAnonymizeBasics:
    def test_symbol_replaced(self):
        result = anonymize_realized_gains_csv(SAMPLE_CSV, AnonConfig(seed=1))
        rows = _parse_rows(result)
        data_rows = [r for r in rows if r["Symbol"].strip() != "Total"]
        for row in data_rows:
            assert row["Symbol"].strip() != "AAPL"
            assert row["Name"].strip() != "APPLE INC"

    def test_account_number_redacted(self):
        result = anonymize_realized_gains_csv(SAMPLE_CSV, AnonConfig(seed=1))
        assert "...482" not in result
        assert "...XXX" in result

    def test_timestamp_redacted(self):
        result = anonymize_realized_gains_csv(SAMPLE_CSV, AnonConfig(seed=1))
        assert "[redacted]" in result
        assert "09:23:17" not in result

    def test_quantities_changed(self):
        result = anonymize_realized_gains_csv(SAMPLE_CSV, AnonConfig(seed=1))
        rows = _parse_rows(result)
        data_rows = [r for r in rows if r["Symbol"].strip() != "Total"]
        original_qtys = [45, 150, 62]
        for row, orig_qty in zip(data_rows, original_qtys):
            new_qty = int(row["Quantity"].strip())
            assert new_qty != orig_qty

    def test_prices_shifted(self):
        result = anonymize_realized_gains_csv(SAMPLE_CSV, AnonConfig(seed=1))
        rows = _parse_rows(result)
        data_rows = [r for r in rows if r["Symbol"].strip() != "Total"]
        original_proceeds = [8429.40, 29310.00, 12632.50]
        for row, orig in zip(data_rows, original_proceeds):
            new = _parse_currency(row["Proceeds"])
            assert new != orig


class TestAnonymizeConsistency:
    def test_gain_loss_equals_proceeds_minus_cost_basis(self):
        """Core invariant: gain/loss = proceeds - cost_basis for each row."""
        result = anonymize_realized_gains_csv(SAMPLE_CSV, AnonConfig(seed=42))
        rows = _parse_rows(result)
        data_rows = [r for r in rows if r["Symbol"].strip() != "Total"]
        for row in data_rows:
            proceeds = _parse_currency(row["Proceeds"])
            cost_basis = _parse_currency(row["Cost Basis (CB)"])
            gain_loss = _parse_currency(row["Total Gain/Loss ($)"])
            assert abs(proceeds - cost_basis - gain_loss) < 0.02, (
                f"Inconsistent: {proceeds} - {cost_basis} != {gain_loss}"
            )

    def test_total_row_sums_correctly(self):
        result = anonymize_realized_gains_csv(SAMPLE_CSV, AnonConfig(seed=42))
        rows = _parse_rows(result)
        data_rows = [r for r in rows if r["Symbol"].strip() != "Total"]
        total_rows = [r for r in rows if r["Symbol"].strip() == "Total"]

        assert len(total_rows) == 1

        sum_proceeds = sum(_parse_currency(r["Proceeds"]) for r in data_rows)
        sum_cb = sum(_parse_currency(r["Cost Basis (CB)"]) for r in data_rows)
        sum_gl = sum(_parse_currency(r["Total Gain/Loss ($)"]) for r in data_rows)

        total = total_rows[0]
        assert abs(_parse_currency(total["Proceeds"]) - sum_proceeds) < 0.02
        assert abs(_parse_currency(total["Cost Basis (CB)"]) - sum_cb) < 0.02
        assert abs(_parse_currency(total["Total Gain/Loss ($)"]) - sum_gl) < 0.02

    def test_dates_shifted_consistently(self):
        """All dates should shift by the same offset."""
        result = anonymize_realized_gains_csv(SAMPLE_CSV, AnonConfig(seed=42))
        rows = _parse_rows(result)
        data_rows = [r for r in rows if r["Symbol"].strip() != "Total"]

        original_dates = ["03/15/2025", "07/10/2025", "09/15/2025"]
        from datetime import datetime

        shifts = []
        for row, orig_str in zip(data_rows, original_dates):
            orig = datetime.strptime(orig_str, "%m/%d/%Y")
            new = datetime.strptime(row["Closed Date"].strip(), "%m/%d/%Y")
            shifts.append((new - orig).days)

        # All shifts should be the same
        assert len(set(shifts)) == 1, f"Inconsistent date shifts: {shifts}"


class TestAnonymizeReproducibility:
    def test_same_seed_same_output(self):
        r1 = anonymize_realized_gains_csv(SAMPLE_CSV, AnonConfig(seed=99))
        r2 = anonymize_realized_gains_csv(SAMPLE_CSV, AnonConfig(seed=99))
        assert r1 == r2

    def test_different_seed_different_output(self):
        r1 = anonymize_realized_gains_csv(SAMPLE_CSV, AnonConfig(seed=1))
        r2 = anonymize_realized_gains_csv(SAMPLE_CSV, AnonConfig(seed=2))
        assert r1 != r2


class TestAnonymizeRoundTrip:
    def test_parseable_by_csv_parser(self):
        """Anonymized output should still be parseable by the app's CSV parser."""
        from rsu_tax.csv_parser import parse_schwab_csv

        result = anonymize_realized_gains_csv(SAMPLE_CSV, AnonConfig(seed=42))
        parsed = parse_schwab_csv(result)

        assert len(parsed.transactions) == 3
        for t in parsed.transactions:
            assert t.symbol != "AAPL"
            assert t.proceeds_usd > 0
            assert abs(t.proceeds_usd - t.cost_basis_usd - t.gain_loss_usd) < 0.02
