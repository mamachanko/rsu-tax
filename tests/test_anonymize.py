"""Tests for the anonymization tool (Realized G/L CSV, Vesting CSV, 1042-S PDF)."""

from __future__ import annotations

import csv
import io
import os
import re
import tempfile

from rsu_tax.anonymize import (
    AnonConfig,
    anonymize_1042s_pdf,
    anonymize_realized_gains_csv,
    anonymize_vesting_csv,
    anonymize_file,
    _detect_file_type,
)

SAMPLE_CSV = """\
"Realized Gain/Loss for ...482 for 01/01/2025 to 12/31/2025 as of Sat Mar 14  09:23:17 EDT 2026","","","","","","","","","","","","","","","","","","","","","","",""
"Symbol","Name","Closed Date","Quantity","Closing Price","Cost Basis Method","Proceeds","Cost Basis (CB)","Total Gain/Loss ($)","Total Gain/Loss (%)","Long Term (LT) Gain/Loss ($)","Long Term (LT) Gain/Loss (%)","Short Term (ST) Gain/Loss ($)","Short Term (ST) Gain/Loss (%)","Wash Sale?","Disallowed Loss","Transaction Closed Date","Transaction Cost Basis","Total Transaction Gain/Loss ($)","Total Transaction Gain/Loss (%)","LT Transaction Gain/Loss ($)","LT Transaction Gain/Loss (%)","ST Transaction Gain/Loss ($)","ST Transaction Gain/Loss (%)"
"AAPL","APPLE INC","03/15/2025","45","$187.32","Specific Lots","$8,429.40","$8,312.55","$116.85","1.405717340165%","--","--","$116.85","1.405717340165214%","No","","03/15/2025","","","","","","",""
"AAPL","APPLE INC","07/10/2025","150","$195.40","FIFO","$29,310.00","$28,475.30","$834.70","2.931266417498%","--","--","$834.70","2.931266417498159%","No","","07/10/2025","","","","","","",""
"AAPL","APPLE INC","09/15/2025","62","$203.75","Specific Lots","$12,632.50","$12,841.18","-$208.68","-1.624885498498%","--","--","-$208.68","-1.624885498497621%","No","","09/15/2025","","","","","","",""
"Total","","","","","","$50,371.90","$49,629.03","$742.87","1.496841458498%","$0.00","N/A","$742.87","1.496841458498372%","","","","","","","","","",""
"""

SAMPLE_VESTING_CSV = """\
"Date","Action","Symbol","Description","Shares Vested","Shares Delivered","Shares Withheld","Fair Market Value","Total Value","Award ID"
"02/15/2025","Vest","AAPL","APPLE INC","100","67","33","$185.50","$18,550.00","RSU-2023-0042"
"05/15/2025","Vest","AAPL","APPLE INC","100","67","33","$192.30","$19,230.00","RSU-2023-0042"
"08/15/2025","Vest","AAPL","APPLE INC","50","34","16","$201.10","$10,055.00","RSU-2024-0015"
"""


def _parse_rows(csv_text: str) -> list[dict[str, str]]:
    """Parse anonymized CSV into list of dicts (skip title row)."""
    lines = csv_text.strip().splitlines()
    for i, line in enumerate(lines):
        if "Symbol" in line or "Date" in line:
            block = "\n".join(lines[i:])
            reader = csv.DictReader(io.StringIO(block))
            return list(reader)
    return []


def _parse_currency(value: str) -> float:
    cleaned = re.sub(r"[$,\s]", "", value.strip())
    if cleaned.startswith("(") and cleaned.endswith(")"):
        return -float(cleaned[1:-1])
    return float(cleaned) if cleaned and cleaned != "--" else 0.0


# ── Realized Gain/Loss CSV tests ──────────────────────────────────────────

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


# ── Vesting CSV tests ─────────────────────────────────────────────────────

class TestVestingAnonymize:
    def test_symbol_replaced(self):
        result = anonymize_vesting_csv(SAMPLE_VESTING_CSV, AnonConfig(seed=1))
        rows = _parse_rows(result)
        for row in rows:
            assert row["Symbol"].strip() != "AAPL"
            assert row["Description"].strip() != "APPLE INC"

    def test_dates_shifted(self):
        from datetime import datetime

        result = anonymize_vesting_csv(SAMPLE_VESTING_CSV, AnonConfig(seed=42))
        rows = _parse_rows(result)

        original_dates = ["02/15/2025", "05/15/2025", "08/15/2025"]
        shifts = []
        for row, orig_str in zip(rows, original_dates):
            orig = datetime.strptime(orig_str, "%m/%d/%Y")
            new = datetime.strptime(row["Date"].strip(), "%m/%d/%Y")
            shifts.append((new - orig).days)

        assert len(set(shifts)) == 1, f"Inconsistent date shifts: {shifts}"

    def test_quantities_scaled(self):
        result = anonymize_vesting_csv(SAMPLE_VESTING_CSV, AnonConfig(seed=1))
        rows = _parse_rows(result)
        original_vested = [100, 100, 50]
        for row, orig in zip(rows, original_vested):
            new = int(row["Shares Vested"].strip())
            assert new != orig

    def test_fmv_shifted(self):
        result = anonymize_vesting_csv(SAMPLE_VESTING_CSV, AnonConfig(seed=1))
        rows = _parse_rows(result)
        original_fmv = [185.50, 192.30, 201.10]
        for row, orig in zip(rows, original_fmv):
            new = _parse_currency(row["Fair Market Value"])
            assert new != orig

    def test_award_ids_randomized(self):
        result = anonymize_vesting_csv(SAMPLE_VESTING_CSV, AnonConfig(seed=1))
        rows = _parse_rows(result)
        for row in rows:
            assert row["Award ID"].strip().startswith("AWD-")
            assert row["Award ID"].strip() != "RSU-2023-0042"
            assert row["Award ID"].strip() != "RSU-2024-0015"

    def test_total_value_consistent_with_fmv_times_shares(self):
        result = anonymize_vesting_csv(SAMPLE_VESTING_CSV, AnonConfig(seed=42))
        rows = _parse_rows(result)
        for row in rows:
            fmv = _parse_currency(row["Fair Market Value"])
            shares = int(row["Shares Vested"].strip())
            value = _parse_currency(row["Total Value"])
            assert abs(value - fmv * shares) < 0.02, (
                f"Value {value} != FMV {fmv} * shares {shares}"
            )

    def test_reproducible(self):
        r1 = anonymize_vesting_csv(SAMPLE_VESTING_CSV, AnonConfig(seed=99))
        r2 = anonymize_vesting_csv(SAMPLE_VESTING_CSV, AnonConfig(seed=99))
        assert r1 == r2


# ── 1042-S PDF tests ──────────────────────────────────────────────────────

def _make_test_1042s_pdf(
    path: str, gross: float = 75432.18, rate: float = 30.0,
    name: str = "Jane Smith", tin: str = "123-45-6789",
    address: str = "456 Real Street, Munich 80331",
    pages: int = 1,
) -> None:
    """Create a test 1042-S PDF with realistic field structure."""
    from fpdf import FPDF

    tax = round(gross * rate / 100, 2)
    pdf = FPDF()

    # Page 1: main form
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Form 1042-S  Tax Year 2025", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, f"Gross Income: ${gross:,.2f}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Tax Rate: {rate:.2f}%", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Federal Tax Withheld: ${tax:,.2f}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Withholding Agent EIN: 94-1737782", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Recipient: {name}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"TIN: {tin}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Address: {address}", new_x="LMARGIN", new_y="NEXT")

    # Additional pages if requested
    for _ in range(pages - 1):
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, "Instructions for Recipient", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 7, "Keep this form for your records.", new_x="LMARGIN", new_y="NEXT")

    pdf.output(path)


class TestPdfAnonymize:
    def test_generates_valid_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "1042s.pdf")
            dst = os.path.join(tmpdir, "1042s-anon.pdf")
            _make_test_1042s_pdf(src)
            anonymize_1042s_pdf(src, dst, AnonConfig(seed=42))

            assert os.path.isfile(dst)
            assert os.path.getsize(dst) > 100

    def test_preserves_page_count(self):
        """Overlay approach should preserve the original page count."""
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "1042s.pdf")
            dst = os.path.join(tmpdir, "1042s-anon.pdf")
            _make_test_1042s_pdf(src, pages=3)
            anonymize_1042s_pdf(src, dst, AnonConfig(seed=42))

            orig = PdfReader(src)
            anon = PdfReader(dst)
            assert len(anon.pages) == len(orig.pages) == 3

    def test_overlay_contains_replacement_amounts(self):
        """The overlay should contain new dollar amounts different from originals."""
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "1042s.pdf")
            dst = os.path.join(tmpdir, "1042s-anon.pdf")
            _make_test_1042s_pdf(src, gross=75432.18)
            anonymize_1042s_pdf(src, dst, AnonConfig(seed=42))

            reader = PdfReader(dst)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)

            # The overlay adds new amounts (pypdf shows both original + overlay)
            amounts = re.findall(r"\$([\d,]+\.\d{2})", text)
            parsed = sorted(set(float(a.replace(",", "")) for a in amounts))
            # Should have more than just the originals — overlay added new values
            assert len(parsed) > 2

    def test_overlay_replaces_tin(self):
        """TIN (SSN format) should be replaced with a different number."""
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "1042s.pdf")
            dst = os.path.join(tmpdir, "1042s-anon.pdf")
            _make_test_1042s_pdf(src, tin="123-45-6789")
            anonymize_1042s_pdf(src, dst, AnonConfig(seed=42))

            reader = PdfReader(dst)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)

            # The overlay should contain a different TIN
            tins = re.findall(r"\d{3}-\d{2}-\d{4}", text)
            assert len(tins) >= 2  # original + replacement
            assert len(set(tins)) > 1  # they should differ

    def test_overlay_replaces_ein(self):
        """Withholding agent EIN should be replaced."""
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "1042s.pdf")
            dst = os.path.join(tmpdir, "1042s-anon.pdf")
            _make_test_1042s_pdf(src)
            anonymize_1042s_pdf(src, dst, AnonConfig(seed=42))

            reader = PdfReader(dst)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)

            eins = re.findall(r"\d{2}-\d{7}", text)
            assert len(eins) >= 2  # original + replacement
            assert len(set(eins)) > 1

    def test_overlay_replaces_name(self):
        """Recipient name should be overlaid with a fake name."""
        from pypdf import PdfReader
        from rsu_tax.anonymize import _FAKE_COMPANIES

        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "1042s.pdf")
            dst = os.path.join(tmpdir, "1042s-anon.pdf")
            _make_test_1042s_pdf(src, name="Hans Mueller")
            anonymize_1042s_pdf(src, dst, AnonConfig(seed=42))

            reader = PdfReader(dst)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)

            # The overlay should contain a fake name (not the original)
            fake_names = ["JOHN DOE", "JANE SMITH", "MAX MUSTERMANN", "ERIKA MUSTER",
                          "ALEX JOHNSON", "MARIA GARCIA"]
            assert any(name in text for name in fake_names)


# ── File type detection tests ─────────────────────────────────────────────

class TestFileTypeDetection:
    def test_detects_realized_gains(self):
        assert _detect_file_type("data.csv", SAMPLE_CSV) == "realized_gains"

    def test_detects_vesting(self):
        assert _detect_file_type("vest.csv", SAMPLE_VESTING_CSV) == "vesting"

    def test_detects_pdf_by_extension(self):
        assert _detect_file_type("form.pdf") == "pdf"

    def test_unknown_csv(self):
        generic = '"Col1","Col2"\n"a","b"\n'
        assert _detect_file_type("data.csv", generic) == "csv_unknown"


# ── anonymize_file integration tests ──────────────────────────────────────

class TestAnonymizeFileIntegration:
    def test_realized_gains_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "gains.csv")
            dst = os.path.join(tmpdir, "gains-anon.csv")
            with open(src, "w") as f:
                f.write(SAMPLE_CSV)
            file_type = anonymize_file(src, dst, AnonConfig(seed=42))
            assert file_type == "realized_gains"
            assert os.path.isfile(dst)
            with open(dst) as f:
                assert "AAPL" not in f.read()

    def test_vesting_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "vest.csv")
            dst = os.path.join(tmpdir, "vest-anon.csv")
            with open(src, "w") as f:
                f.write(SAMPLE_VESTING_CSV)
            file_type = anonymize_file(src, dst, AnonConfig(seed=42))
            assert file_type == "vesting"
            assert os.path.isfile(dst)
            with open(dst) as f:
                assert "AAPL" not in f.read()

    def test_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "1042s.pdf")
            dst = os.path.join(tmpdir, "1042s-anon.pdf")
            _make_test_1042s_pdf(src)
            file_type = anonymize_file(src, dst, AnonConfig(seed=42))
            assert file_type == "pdf"
            assert os.path.isfile(dst)
