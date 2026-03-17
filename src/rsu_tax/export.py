"""Export computed transactions as CSV or PDF."""

from __future__ import annotations

import csv
import io
from datetime import date

from fpdf import FPDF  # type: ignore[import-untyped]

from .models import ComputedTransaction, TaxSummary, VerificationCheck

# fpdf2 core fonts (Helvetica) only support ISO-8859-1.
_UNICODE_REPLACEMENTS = str.maketrans({
    "\u2014": "-",   # em dash
    "\u2013": "-",   # en dash
    "\u2212": "-",   # minus sign
    "\u2264": "<=",  # ≤
    "\u2265": ">=",  # ≥
    "\u2248": "~",   # ≈
    "\u20ac": "EUR", # €
    "\u00d7": "x",   # ×
    "\u00f7": "/",   # ÷
    "\u2260": "!=",  # ≠
})


def _pdf_safe(text: str) -> str:
    """Strip/replace characters unsupported by fpdf2 core (ISO-8859-1) fonts."""
    return text.translate(_UNICODE_REPLACEMENTS)


# ── CSV ──────────────────────────────────────────────────────────────────────

_CSV_HEADERS = [
    "Symbol",
    "Name",
    "Quantity",
    "Date Acquired",
    "Date Sold",
    "Term",
    "Type",
    "Proceeds (USD)",
    "Cost Basis (USD)",
    "Gain/Loss (USD)",
    "Exchange Rate (Sale)",
    "Exchange Rate (Acq.)",
    "Proceeds (EUR)",
    "Cost Basis (EUR)",
    "Gain/Loss (EUR)",
    "Wash Sale",
    "Verification",
    "Notes",
]


def export_csv(transactions: list[ComputedTransaction]) -> str:
    """Return CSV content as a string."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_CSV_HEADERS)

    for t in transactions:
        writer.writerow([
            t.symbol,
            t.name or "",
            t.quantity,
            t.date_acquired if t.has_acquisition_date else "",
            t.date_sold,
            t.term,
            "Sell-to-Cover" if t.is_sell_to_cover else "Voluntary",
            f"{t.proceeds_usd:.2f}",
            f"{t.cost_basis_usd:.2f}",
            f"{t.gain_loss_usd:.2f}",
            f"{t.exchange_rate_sold:.6f}",
            f"{t.exchange_rate_acquired:.6f}",
            f"{t.proceeds_eur:.2f}",
            f"{t.cost_basis_eur:.2f}",
            f"{t.gain_loss_eur:.2f}",
            f"{t.wash_sale:.2f}" if t.wash_sale else "",
            t.verification_status,
            "; ".join(t.verification_notes),
        ])

    return buf.getvalue()


# ── PDF ──────────────────────────────────────────────────────────────────────

class _RSUPdf(FPDF):
    def __init__(self, tax_year: int) -> None:
        super().__init__(orientation="L", unit="mm", format="A4")
        self.tax_year = tax_year
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(12, 12, 12)

    def header(self) -> None:
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, f"RSU Capital Gains - Tax Year {self.tax_year}", align="L")
        self.set_font("Helvetica", "", 8)
        self.cell(0, 8, f"Generated {date.today().isoformat()}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(12, self.get_y(), self.w - 12, self.get_y())
        self.ln(3)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")


def export_pdf(
    transactions: list[ComputedTransaction],
    summary: TaxSummary,
    checks: list[VerificationCheck],
) -> bytes:
    """Return PDF as bytes."""
    pdf = _RSUPdf(tax_year=summary.tax_year)
    pdf.add_page()

    # ── Summary section ──────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)

    gain_sign = "+" if summary.net_gain_loss_eur >= 0 else ""
    rows = [
        ("Tax year", str(summary.tax_year)),
        ("Total transactions", str(summary.total_transactions)),
        ("  Voluntary sales", str(summary.voluntary_sales)),
        ("  Sell-to-cover", str(summary.sell_to_cover_sales)),
        ("Net gain/loss (EUR)", f"{gain_sign}{summary.net_gain_loss_eur:,.2f} EUR"),
        ("  of which voluntary", f"{summary.voluntary_gain_loss_eur:,.2f} EUR"),
        ("  of which sell-to-cover", f"{summary.sell_to_cover_gain_loss_eur:,.2f} EUR"),
        ("Total proceeds (EUR)", f"{summary.total_proceeds_eur:,.2f} EUR"),
        ("Total cost basis (EUR)", f"{summary.total_cost_basis_eur:,.2f} EUR"),
        ("Net gain/loss (USD)", f"{summary.net_gain_loss_usd:,.2f} USD"),
    ]
    col_w = [80, 60]
    for label, val in rows:
        pdf.cell(col_w[0], 6, label)
        pdf.cell(col_w[1], 6, val, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)

    # ── Verification ─────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Verification", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    status_symbols = {"pass": "[OK]", "warn": "[!]", "fail": "[X]"}
    for chk in checks:
        sym = status_symbols.get(chk.status, "?")
        pdf.cell(6, 5, sym)
        pdf.cell(60, 5, _pdf_safe(chk.name))
        pdf.multi_cell(0, 5, _pdf_safe(chk.message), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)

    # ── Transactions table ───────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Transactions", new_x="LMARGIN", new_y="NEXT")

    col_defs: list[tuple[str, int, str]] = [
        ("Symbol", 18, "L"),
        ("Date Sold", 22, "C"),
        ("Date Acq.", 22, "C"),
        ("Term", 20, "C"),
        ("Type", 22, "C"),
        ("Proceeds $", 26, "R"),
        ("Cost $", 26, "R"),
        ("G/L $", 22, "R"),
        ("Rate", 16, "R"),
        ("Proceeds EUR", 28, "R"),
        ("Cost EUR", 26, "R"),
        ("G/L EUR", 22, "R"),
        ("St.", 10, "C"),
    ]

    # Header row
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_fill_color(230, 230, 230)
    for label, w, align in col_defs:
        pdf.cell(w, 5, label, border=1, align=align, fill=True)
    pdf.ln()

    # Data rows
    pdf.set_font("Helvetica", "", 7)
    for t in transactions:
        fill = t.is_sell_to_cover
        if fill:
            pdf.set_fill_color(248, 248, 248)
        else:
            pdf.set_fill_color(255, 255, 255)

        cells = [
            (t.symbol, 18, "L"),
            (t.date_sold, 22, "C"),
            (t.date_acquired if t.has_acquisition_date else "-", 22, "C"),
            (t.term[:5], 20, "C"),
            ("S2C" if t.is_sell_to_cover else "Vol.", 22, "C"),
            (f"{t.proceeds_usd:,.2f}", 26, "R"),
            (f"{t.cost_basis_usd:,.2f}", 26, "R"),
            (f"{t.gain_loss_usd:+,.2f}", 22, "R"),
            (f"{t.exchange_rate_sold:.4f}", 16, "R"),
            (f"{t.proceeds_eur:,.2f}", 26, "R"),
            (f"{t.cost_basis_eur:,.2f}", 26, "R"),
            (f"{t.gain_loss_eur:+,.2f}", 22, "R"),
            (t.verification_status[:1].upper(), 10, "C"),
        ]
        for text, w, align in cells:
            pdf.cell(w, 5, text, border=1, align=align, fill=fill)
        pdf.ln()

    return bytes(pdf.output())
