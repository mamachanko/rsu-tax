"""Export computed transactions as CSV, PDF, or Markdown."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date

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

def export_pdf(
    transactions: list[ComputedTransaction],
    summary: TaxSummary,
    checks: list[VerificationCheck],
) -> bytes:
    """Return PDF as bytes."""
    from fpdf import FPDF  # type: ignore[import-untyped]  # lazy import to allow tests w/o fpdf

    tax_year = summary.tax_year

    class _RSUPdf(FPDF):
        def header(self) -> None:
            self.set_font("Helvetica", "B", 11)
            self.cell(0, 8, f"RSU Capital Gains - Tax Year {tax_year}", align="L")
            self.set_font("Helvetica", "", 8)
            self.cell(0, 8, f"Generated {date.today().isoformat()}", align="R", new_x="LMARGIN", new_y="NEXT")
            self.line(12, self.get_y(), self.w - 12, self.get_y())
            self.ln(3)

        def footer(self) -> None:
            self.set_y(-12)
            self.set_font("Helvetica", "I", 8)
            self.cell(0, 8, f"Page {self.page_no()}", align="C")

    pdf = _RSUPdf(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(12, 12, 12)
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

    # ── Exchange rates reference ──────────────────────────────────────────────
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Exchange Rates Used", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 7)
    pdf.multi_cell(
        0, 5,
        "Source: ECB reference rates via Frankfurter API (api.frankfurter.app). "
        "Rates for non-business days use the preceding business day's rate.",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(1)

    rate_col_defs: list[tuple[str, int, str]] = [
        ("Transaction Date", 38, "C"),
        ("ECB Rate Date", 34, "C"),
        ("USD -> EUR Rate", 34, "R"),
        ("Note", 50, "L"),
        ("Used For", 38, "L"),
    ]
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_fill_color(230, 230, 230)
    for label, w, align in rate_col_defs:
        pdf.cell(w, 5, label, border=1, align=align, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 7)
    pdf.set_fill_color(255, 255, 255)
    for row in _build_rate_rows(transactions):
        note = (
            f"Fallback from {row.transaction_date}"
            if row.transaction_date != row.effective_date
            else "Exact match"
        )
        cells = [
            (row.transaction_date, 38, "C"),
            (row.effective_date, 34, "C"),
            (f"{row.rate:.6f}", 34, "R"),
            (note, 50, "L"),
            (row.used_for, 38, "L"),
        ]
        for text, w, align in cells:
            pdf.cell(w, 5, text, border=1, align=align, fill=False)
        pdf.ln()

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


# ── Shared helpers ────────────────────────────────────────────────────────────

@dataclass
class _RateRow:
    transaction_date: str
    effective_date: str
    rate: float
    used_for: str


def _build_rate_rows(transactions: list[ComputedTransaction]) -> list[_RateRow]:
    """Collect unique (transaction_date, effective_date, rate) pairs for the reference table."""
    seen: dict[str, _RateRow] = {}

    for t in transactions:
        sold_key = f"{t.date_sold}:sold"
        if sold_key not in seen:
            seen[sold_key] = _RateRow(
                transaction_date=t.date_sold,
                effective_date=t.effective_date_sold,
                rate=t.exchange_rate_sold,
                used_for="Sale proceeds",
            )
        if t.has_acquisition_date and t.date_acquired != t.date_sold:
            acq_key = f"{t.date_acquired}:acq"
            if acq_key not in seen:
                seen[acq_key] = _RateRow(
                    transaction_date=t.date_acquired,
                    effective_date=t.effective_date_acquired,
                    rate=t.exchange_rate_acquired,
                    used_for="Cost basis",
                )

    return sorted(seen.values(), key=lambda r: r.transaction_date)


# ── Markdown ──────────────────────────────────────────────────────────────────

_ECB_SOURCE = "https://api.frankfurter.app"
_ECB_DESCRIPTION = "European Central Bank (ECB) reference rates via Frankfurter API"


def export_markdown(
    transactions: list[ComputedTransaction],
    summary: TaxSummary,
    checks: list[VerificationCheck],
) -> str:
    """Return a Markdown document capturing the full computation and audit trail."""
    lines: list[str] = []
    generated = date.today().isoformat()
    gain_sign = "+" if summary.net_gain_loss_eur >= 0 else ""

    lines += [
        f"# RSU Capital Gains Report — Tax Year {summary.tax_year}",
        "",
        "**For German Tax Declaration (Abgeltungssteuer)**",
        "",
        f"Generated: {generated}",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Total Transactions | {summary.total_transactions} |",
        f"| Voluntary Sales | {summary.voluntary_sales} |",
        f"| Sell-to-Cover Sales | {summary.sell_to_cover_sales} |",
        f"| Total Proceeds (EUR) | {summary.total_proceeds_eur:,.2f} EUR |",
        f"| Total Cost Basis (EUR) | {summary.total_cost_basis_eur:,.2f} EUR |",
        f"| **Net Capital Gain/Loss (EUR)** | **{gain_sign}{summary.net_gain_loss_eur:,.2f} EUR** |",
        f"| — from Voluntary Sales (EUR) | {summary.voluntary_gain_loss_eur:,.2f} EUR |",
        f"| — from Sell-to-Cover (EUR) | {summary.sell_to_cover_gain_loss_eur:,.2f} EUR |",
        f"| Net Gain/Loss (USD) | {summary.net_gain_loss_usd:,.2f} USD |",
        "",
        "---",
        "",
        "## Exchange Rates Used",
        "",
        f"Source: [{_ECB_DESCRIPTION}]({_ECB_SOURCE})",
        "",
        "> ECB reference rates are only published on business days.",
        "> For transaction dates falling on weekends or public holidays,",
        "> the rate from the preceding business day is used.",
        "",
        "| Transaction Date | ECB Rate Date | USD → EUR Rate | Note | Used For |",
        "|-----------------|--------------|---------------:|------|----------|",
    ]

    for row in _build_rate_rows(transactions):
        note = (
            f"Fallback from {row.transaction_date}"
            if row.transaction_date != row.effective_date
            else "Exact match"
        )
        lines.append(
            f"| {row.transaction_date} | {row.effective_date} "
            f"| {row.rate:.6f} | {note} | {row.used_for} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Verification Checks",
        "",
        "| Check | Status | Details |",
        "|-------|--------|---------|",
    ]

    status_icons = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}
    for chk in checks:
        icon = status_icons.get(chk.status, chk.status.upper())
        lines.append(f"| {chk.name} | {icon} | {chk.message} |")

    lines += [
        "",
        "---",
        "",
        "## Transaction Details",
        "",
        "Each transaction shows the full EUR conversion computation.",
        "",
    ]

    for i, t in enumerate(transactions, 1):
        acq_display = t.date_acquired if t.has_acquisition_date else "N/A (using sale date)"
        sold_rate_note = (
            f"{t.effective_date_sold} (ECB, fallback from {t.date_sold})"
            if t.effective_date_sold != t.date_sold
            else t.effective_date_sold
        )
        if t.has_acquisition_date:
            acq_rate_note = (
                f"{t.effective_date_acquired} (ECB, fallback from {t.date_acquired})"
                if t.effective_date_acquired != t.date_acquired
                else t.effective_date_acquired
            )
        else:
            acq_rate_note = f"{t.effective_date_sold} (ECB, same as sale — acquisition date not in source data)"

        type_label = "Sell-to-Cover (tax withholding at vesting)" if t.is_sell_to_cover else "Voluntary Sale"
        name_part = f" — {t.name}" if t.name else ""
        gain_sign_t = "+" if t.gain_loss_eur >= 0 else ""
        gain_sign_usd = "+" if t.gain_loss_usd >= 0 else ""

        lines += [
            f"### {i}. {t.symbol}{name_part}",
            "",
            f"**Sold:** {t.date_sold} | **Acquired:** {acq_display} "
            f"| **Qty:** {t.quantity:.4f} | **Term:** {t.term} | **Type:** {type_label}",
            "",
            "| | Amount (USD) | ECB Rate Date | Rate (USD→EUR) | Amount (EUR) |",
            "|--|-------------:|--------------|---------------:|-------------:|",
            f"| Proceeds | {t.proceeds_usd:,.2f} USD | {sold_rate_note} | {t.exchange_rate_sold:.6f} | {t.proceeds_eur:,.2f} EUR |",
            f"| Cost Basis | {t.cost_basis_usd:,.2f} USD | {acq_rate_note} | {t.exchange_rate_acquired:.6f} | {t.cost_basis_eur:,.2f} EUR |",
            f"| **Gain / Loss** | **{gain_sign_usd}{t.gain_loss_usd:,.2f} USD** | | | **{gain_sign_t}{t.gain_loss_eur:,.2f} EUR** |",
            "",
        ]

        if t.verification_notes:
            status_label = status_icons.get(t.verification_status, t.verification_status.upper())
            lines.append(f"**Verification:** {status_label}")
            for note in t.verification_notes:
                lines.append(f"- {note}")
            lines.append("")

    lines += [
        "---",
        "",
        "## Methodology",
        "",
        "### EUR Conversion",
        "",
        "All USD amounts are converted to EUR using the formula:",
        "",
        "```",
        "Proceeds (EUR)   = Proceeds (USD)   x ECB rate on date sold",
        "Cost Basis (EUR) = Cost Basis (USD)  x ECB rate on date acquired",
        "Gain/Loss (EUR)  = Proceeds (EUR) - Cost Basis (EUR)",
        "```",
        "",
        "### Exchange Rate Source",
        "",
        f"Exchange rates are ECB (European Central Bank) reference rates retrieved from the "
        f"[Frankfurter API]({_ECB_SOURCE}).",
        "The Frankfurter API mirrors the ECB's official daily reference rates.",
        "ECB rates are only published on TARGET business days (Monday-Friday, excluding ECB holidays).",
        "For dates without a published rate, the preceding business day's rate is used (maximum 7-day lookback).",
        "",
        "### Sell-to-Cover Detection",
        "",
        "Transactions are classified as *Sell-to-Cover* (tax withholding at RSU vesting) when:",
        "- The acquisition date equals the sale date, **and** the USD gain/loss is within $1.00 of zero, **or**",
        "- No acquisition date is available in the source CSV, the cost basis method is \"Specific Lots\", "
        "**and** the gain/loss is within $1.00 of zero.",
        "",
        "All other transactions are classified as *Voluntary Sales*.",
        "",
        "---",
        "",
        "*For information purposes only. This report does not constitute tax advice.*",
        "",
    ]

    return "\n".join(lines)
