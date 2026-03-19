"""Anonymize / randomize Schwab data exports for safe sharing and testing.

Supports:
- Realized Gain/Loss CSV
- Vesting History CSV (any column layout — auto-detected)
- 1042-S PDF (generates a new clean PDF with randomized values)
"""

from __future__ import annotations

import csv
import io
import os
import random
import re
import string
from dataclasses import dataclass
from datetime import datetime, timedelta


# ── Fake company pool ──────────────────────────────────────────────────────

_FAKE_COMPANIES = [
    ("XYZC", "EXAMPLE CORP"),
    ("ACME", "ACME INDUSTRIES"),
    ("NXRA", "NEXORA INC"),
    ("QLUX", "QUANTALUX LTD"),
    ("BRVO", "BRAVO SYSTEMS"),
    ("FNLY", "FINLEY GROUP"),
    ("ZTRN", "ZETRON HOLDINGS"),
    ("MRVL", "MARVEL DYNAMICS"),
    ("PKRA", "PAKIRA TECH"),
    ("SNVL", "SUNVALE CORP"),
]


@dataclass
class AnonConfig:
    """Controls how anonymization is applied."""

    seed: int | None = None
    price_shift_range: tuple[float, float] = (0.85, 1.15)
    quantity_shift_range: tuple[float, float] = (0.5, 2.0)
    date_shift_days: tuple[int, int] = (-90, 90)


def _make_rng(seed: int | None) -> random.Random:
    return random.Random(seed)


# ── Helpers ────────────────────────────────────────────────────────────────

_DATE_PATTERNS = [
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$"), "us"),      # MM/DD/YYYY
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), "iso"),          # YYYY-MM-DD
    (re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$"), "de"),     # DD.MM.YYYY
]


def _parse_date(value: str) -> datetime | None:
    v = value.strip()
    for pattern, fmt in _DATE_PATTERNS:
        m = pattern.match(v)
        if not m:
            continue
        if fmt == "us":
            return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        if fmt == "iso":
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if fmt == "de":
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def _format_date(dt: datetime, original: str) -> str:
    """Format a datetime back into the same format as the original string."""
    v = original.strip()
    for pattern, fmt in _DATE_PATTERNS:
        if pattern.match(v):
            if fmt == "us":
                return dt.strftime("%m/%d/%Y")
            if fmt == "iso":
                return dt.strftime("%Y-%m-%d")
            if fmt == "de":
                return dt.strftime("%d.%m.%Y")
    return dt.strftime("%m/%d/%Y")


def _parse_currency(value: str) -> float | None:
    if not value or value.strip() in ("", "--", "N/A"):
        return None
    cleaned = re.sub(r"[$,\s]", "", value.strip())
    paren = cleaned.startswith("(") and cleaned.endswith(")")
    if paren:
        cleaned = cleaned[1:-1]
    try:
        num = float(cleaned)
    except ValueError:
        return None
    return -num if paren else num


def _format_currency(amount: float, original: str) -> str:
    """Format a float back into the same currency format as the original."""
    original = original.strip()
    has_dollar = "$" in original
    is_paren_negative = original.startswith("(") or original.startswith("($")
    is_negative = amount < 0
    abs_amount = abs(amount)

    formatted = f"{abs_amount:,.2f}"
    if has_dollar:
        formatted = f"${formatted}"
    if is_negative:
        if is_paren_negative:
            if has_dollar:
                formatted = f"(${abs_amount:,.2f})"
            else:
                formatted = f"({abs_amount:,.2f})"
        else:
            formatted = f"-{formatted}"
    return formatted


def _format_percentage(value: float, original: str) -> str:
    """Format a percentage value in the same style as the original."""
    if "%" not in original:
        return str(value)
    is_paren_negative = original.strip().startswith("(") or original.strip().startswith("-")
    if value < 0 and is_paren_negative and original.strip().startswith("-"):
        return f"-{abs(value):.12f}%"
    return f"{value:.12f}%"


# ── Column detection (lightweight, just enough to find the fields) ─────────

_ANON_HEADER_HINTS: dict[str, list[str]] = {
    "symbol": ["symbol", "ticker"],
    "name": ["name", "description", "company"],
    "quantity": ["quantity", "qty", "shares", "units"],
    "date_sold": ["date sold", "sale date", "close date", "closed date"],
    "date_acquired": ["date acquired", "acquisition date", "open date", "vest date"],
    "transaction_closed_date": ["transaction closed date"],
    "proceeds": ["proceeds", "sale proceeds", "total proceeds", "gross proceeds"],
    "cost_basis": ["cost basis (cb)", "cost basis", "adjusted cost basis"],
    "gain_loss": ["total gain/loss", "gain/loss", "gain loss", "realized gain"],
    "closing_price": ["closing price", "price per share", "sale price"],
    "wash_sale": ["wash sale"],
    "disallowed": ["disallowed loss", "disallowed"],
    "st_gain_loss": ["short term (st) gain/loss", "st gain/loss", "short-term gain/loss"],
    "lt_gain_loss": ["long term (lt) gain/loss", "lt gain/loss", "long-term gain/loss"],
    "st_pct": ["short term (st) gain/loss (%)", "st gain/loss (%)"],
    "lt_pct": ["long term (lt) gain/loss (%)", "lt gain/loss (%)"],
    "total_pct": ["total gain/loss (%)", "gain/loss (%)"],
    "transaction_cost_basis": ["transaction cost basis"],
    "transaction_gain_loss": ["total transaction gain/loss", "transaction gain/loss"],
    "transaction_gain_loss_pct": ["total transaction gain/loss (%)"],
    "lt_transaction_gain_loss": ["lt transaction gain/loss ($)"],
    "lt_transaction_gain_loss_pct": ["lt transaction gain/loss (%)"],
    "st_transaction_gain_loss": ["st transaction gain/loss ($)"],
    "st_transaction_gain_loss_pct": ["st transaction gain/loss (%)"],
    "cost_basis_method": ["cost basis method", "method"],
}


def _detect_columns(headers: list[str]) -> dict[str, int]:
    """Return field → column index mapping."""
    normalized = [re.sub(r"[^a-z0-9/ ()$%-]", "", h.lower()).strip() for h in headers]
    mapping: dict[str, int] = {}
    used: set[int] = set()

    for field_name, hints in _ANON_HEADER_HINTS.items():
        for hint in hints:
            idx = next(
                (i for i, h in enumerate(normalized) if i not in used and hint in h),
                -1,
            )
            if idx != -1:
                mapping[field_name] = idx
                used.add(idx)
                break

    return mapping


# ── Core anonymization ─────────────────────────────────────────────────────

def anonymize_realized_gains_csv(csv_text: str, config: AnonConfig | None = None) -> str:
    """Anonymize a Schwab Realized Gain/Loss CSV export.

    Returns the anonymized CSV as a string.
    """
    config = config or AnonConfig()
    rng = _make_rng(config.seed)

    lines = csv_text.splitlines()

    # Find the header row
    header_idx = 0
    for i, line in enumerate(lines[:10]):
        lower = line.lower()
        if "symbol" in lower and any(k in lower for k in ("date", "proceed", "quantity")):
            header_idx = i
            break

    # Parse everything from header onward
    csv_block = "\n".join(lines[header_idx:])
    reader = csv.reader(io.StringIO(csv_block))
    all_rows = list(reader)

    if not all_rows:
        return csv_text

    headers = [h.strip() for h in all_rows[0]]
    data_rows = all_rows[1:]
    col_map = _detect_columns(headers)

    # Decide a stable date shift for this run
    date_shift = timedelta(days=rng.randint(*config.date_shift_days))

    # Build a consistent symbol mapping
    symbol_col = col_map.get("symbol")
    name_col = col_map.get("name")
    real_symbols: set[str] = set()
    if symbol_col is not None:
        for row in data_rows:
            if symbol_col < len(row):
                val = row[symbol_col].strip().strip('"')
                if val and val.lower() != "total":
                    real_symbols.add(val)

    fake_pool = list(_FAKE_COMPANIES)
    rng.shuffle(fake_pool)
    symbol_mapping: dict[str, tuple[str, str]] = {}
    for i, sym in enumerate(sorted(real_symbols)):
        symbol_mapping[sym] = fake_pool[i % len(fake_pool)]

    # Decide a stable price factor per symbol
    price_factors: dict[str, float] = {}
    for sym in real_symbols:
        price_factors[sym] = rng.uniform(*config.price_shift_range)

    # Anonymize the title row(s) above the header
    output_lines: list[str] = []
    for i in range(header_idx):
        line = lines[i]
        # Replace account numbers (e.g., "...482")
        line = re.sub(r"\.\.\.\d{3,}", "...XXX", line)
        # Shift date ranges in title (e.g., "01/01/2025 to 12/31/2025")
        def _shift_title_date(m: re.Match[str]) -> str:
            dt = _parse_date(m.group(0))
            return _format_date(dt + date_shift, m.group(0)) if dt else m.group(0)
        line = re.sub(r"\d{2}/\d{2}/\d{4}", _shift_title_date, line)
        # Replace date timestamps in title
        line = re.sub(
            r"(as of\s+)\w+ \w+ \d+ \s*\d+:\d+:\d+ \w+ \d{4}",
            r"\1[redacted]",
            line,
        )
        # Replace any real symbols/names in the title
        for real_sym, (fake_sym, fake_name) in symbol_mapping.items():
            line = line.replace(real_sym, fake_sym)
        output_lines.append(line)

    # Write header row unchanged
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
    writer.writerow(headers)
    output_lines.append(buf.getvalue().strip())

    # Anonymize each data row
    qty_col = col_map.get("quantity")
    proceeds_col = col_map.get("proceeds")
    cost_basis_col = col_map.get("cost_basis")
    gain_loss_col = col_map.get("gain_loss")
    closing_price_col = col_map.get("closing_price")
    date_sold_col = col_map.get("date_sold")
    date_acquired_col = col_map.get("date_acquired")
    st_gl_col = col_map.get("st_gain_loss")
    lt_gl_col = col_map.get("lt_gain_loss")
    st_pct_col = col_map.get("st_pct")
    lt_pct_col = col_map.get("lt_pct")
    total_pct_col = col_map.get("total_pct")
    txn_cb_col = col_map.get("transaction_cost_basis")
    txn_gl_col = col_map.get("transaction_gain_loss")
    txn_gl_pct_col = col_map.get("transaction_gain_loss_pct")
    lt_txn_gl_col = col_map.get("lt_transaction_gain_loss")
    lt_txn_gl_pct_col = col_map.get("lt_transaction_gain_loss_pct")
    st_txn_gl_col = col_map.get("st_transaction_gain_loss")
    st_txn_gl_pct_col = col_map.get("st_transaction_gain_loss_pct")

    for row in data_rows:
        if len(row) < len(headers):
            row.extend([""] * (len(headers) - len(row)))

        original_symbol = row[symbol_col].strip().strip('"') if symbol_col is not None else ""
        is_total = original_symbol.lower() == "total"

        # Replace symbol and name
        if symbol_col is not None and not is_total:
            fake_sym, fake_name = symbol_mapping.get(original_symbol, (original_symbol, ""))
            row[symbol_col] = fake_sym
            if name_col is not None:
                row[name_col] = fake_name

        # Get price factor
        pf = price_factors.get(original_symbol, 1.0)
        # Quantity factor
        qf = rng.uniform(*config.quantity_shift_range) if not is_total else 1.0

        txn_closed_date_col = col_map.get("transaction_closed_date")

        # Shift dates
        for date_col_idx in [date_sold_col, date_acquired_col, txn_closed_date_col]:
            if date_col_idx is not None and date_col_idx < len(row):
                orig = row[date_col_idx].strip()
                dt = _parse_date(orig)
                if dt:
                    row[date_col_idx] = _format_date(dt + date_shift, orig)

        # Anonymize quantity
        new_qty = None
        if qty_col is not None and not is_total:
            orig_qty = _parse_currency(row[qty_col])
            if orig_qty is not None:
                new_qty = max(1, round(orig_qty * qf))
                row[qty_col] = str(new_qty)

        # Anonymize closing price
        if closing_price_col is not None and not is_total:
            orig_price = _parse_currency(row[closing_price_col])
            if orig_price is not None:
                new_price = round(orig_price * pf, 2)
                row[closing_price_col] = _format_currency(new_price, row[closing_price_col])

        # Anonymize proceeds and cost basis, then recompute gain/loss
        new_proceeds = None
        new_cost_basis = None

        if proceeds_col is not None:
            orig_proceeds = _parse_currency(row[proceeds_col])
            if orig_proceeds is not None:
                if is_total:
                    # Will be recomputed below
                    pass
                else:
                    new_proceeds = round(orig_proceeds * pf * qf, 2)
                    row[proceeds_col] = _format_currency(new_proceeds, row[proceeds_col])

        if cost_basis_col is not None:
            orig_cb = _parse_currency(row[cost_basis_col])
            if orig_cb is not None:
                if is_total:
                    pass
                else:
                    new_cost_basis = round(orig_cb * pf * qf, 2)
                    row[cost_basis_col] = _format_currency(new_cost_basis, row[cost_basis_col])

        if gain_loss_col is not None and new_proceeds is not None and new_cost_basis is not None:
            new_gl = round(new_proceeds - new_cost_basis, 2)
            row[gain_loss_col] = _format_currency(new_gl, row[gain_loss_col])

            # Recompute percentage
            if total_pct_col is not None and new_cost_basis != 0:
                pct = (new_gl / new_cost_basis) * 100
                row[total_pct_col] = _format_percentage(pct, row[total_pct_col])

            # ST/LT gain/loss: if original had values, scale them proportionally
            for gl_col, pct_col in [(st_gl_col, st_pct_col), (lt_gl_col, lt_pct_col)]:
                if gl_col is not None:
                    orig_val = _parse_currency(row[gl_col])
                    if orig_val is not None and orig_val != 0:
                        row[gl_col] = _format_currency(new_gl, row[gl_col])
                        if pct_col is not None and new_cost_basis != 0:
                            row[pct_col] = _format_percentage(pct, row[pct_col])

        # Clear transaction-level columns (often empty, but anonymize if present)
        for col_idx in [txn_cb_col, txn_gl_col, txn_gl_pct_col,
                        lt_txn_gl_col, lt_txn_gl_pct_col,
                        st_txn_gl_col, st_txn_gl_pct_col]:
            if col_idx is not None and col_idx < len(row):
                orig = _parse_currency(row[col_idx])
                if orig is not None and orig != 0:
                    row[col_idx] = ""

        # Handle total row: recompute from scratch later (we mark it)
        if is_total:
            # We'll handle total rows in a second pass
            row[symbol_col] = "Total"
            if name_col is not None:
                row[name_col] = ""

        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
        writer.writerow(row)
        output_lines.append(buf.getvalue().strip())

    # Recompute total row(s)
    result = "\n".join(output_lines) + "\n"
    result = _recompute_totals(result, col_map, headers)
    return result


def _recompute_totals(csv_text: str, col_map: dict[str, int], headers: list[str]) -> str:
    """Recompute Total row values by summing data rows."""
    lines = csv_text.splitlines()

    # Find data rows and total rows
    total_line_indices: list[int] = []
    data_line_indices: list[int] = []
    symbol_col = col_map.get("symbol")

    if symbol_col is None:
        return csv_text

    # Find header line index in output
    header_line_idx = -1
    for i, line in enumerate(lines):
        # Parse to check
        parsed = list(csv.reader(io.StringIO(line)))
        if parsed and parsed[0] and any("Symbol" in h or "symbol" in h for h in parsed[0]):
            header_line_idx = i
            break

    if header_line_idx < 0:
        return csv_text

    for i in range(header_line_idx + 1, len(lines)):
        if not lines[i].strip():
            continue
        parsed = list(csv.reader(io.StringIO(lines[i])))
        if not parsed or not parsed[0]:
            continue
        row = parsed[0]
        if symbol_col < len(row) and row[symbol_col].strip().lower() == "total":
            total_line_indices.append(i)
        else:
            data_line_indices.append(i)

    if not total_line_indices:
        return csv_text

    # Sum monetary columns from data rows
    monetary_cols = {
        name: idx for name, idx in col_map.items()
        if name in ("proceeds", "cost_basis", "gain_loss", "st_gain_loss", "lt_gain_loss")
    }

    sums: dict[str, float] = {name: 0.0 for name in monetary_cols}
    for line_idx in data_line_indices:
        parsed = list(csv.reader(io.StringIO(lines[line_idx])))
        if not parsed or not parsed[0]:
            continue
        row = parsed[0]
        for name, col_idx in monetary_cols.items():
            if col_idx < len(row):
                val = _parse_currency(row[col_idx])
                if val is not None:
                    sums[name] += val

    # Update total rows
    for total_idx in total_line_indices:
        parsed = list(csv.reader(io.StringIO(lines[total_idx])))
        if not parsed or not parsed[0]:
            continue
        row = parsed[0]
        # Pad if needed
        while len(row) < len(headers):
            row.append("")

        for name, col_idx in monetary_cols.items():
            if col_idx < len(row):
                total_val = round(sums[name], 2)
                row[col_idx] = _format_currency(total_val, row[col_idx]) if row[col_idx].strip() else ""

        # Recompute total percentage
        total_pct_col = col_map.get("total_pct")
        cb_sum = sums.get("cost_basis", 0)
        gl_sum = sums.get("gain_loss", 0)
        if total_pct_col is not None and total_pct_col < len(row) and cb_sum != 0:
            pct = (gl_sum / cb_sum) * 100
            row[total_pct_col] = _format_percentage(pct, row[total_pct_col])

        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
        writer.writerow(row)
        lines[total_idx] = buf.getvalue().strip()

    return "\n".join(lines) + "\n"


# ── Vesting CSV anonymization ──────────────────────────────────────────────

# Column hints for vesting history exports.  We don't know Schwab's exact
# headers yet, so we cast a wide net and classify columns by content type.

_VESTING_HEADER_HINTS: dict[str, list[str]] = {
    "date": ["date", "vest date", "vesting date", "award date", "release date"],
    "event_type": ["action", "type", "event", "transaction type", "event type"],
    "symbol": ["symbol", "ticker"],
    "name": ["name", "description", "company", "security name"],
    "shares_vested": ["shares vested", "vested", "total shares"],
    "shares_delivered": ["shares delivered", "delivered", "net shares", "shares released"],
    "shares_withheld": ["shares withheld", "withheld", "shares used for taxes",
                        "tax withholding shares"],
    "fmv": ["fair market value", "fmv", "market value", "price", "vest price",
            "vest fmv", "market price"],
    "value": ["value", "total value", "market value total", "gross value", "amount"],
    "award_id": ["award id", "grant id", "award", "grant", "award number",
                 "grant number", "award name"],
    "tax_withheld": ["tax withheld", "taxes", "taxes withheld", "federal tax",
                     "tax amount"],
}


def _detect_vesting_columns(headers: list[str]) -> dict[str, int]:
    """Map vesting field types to column indices."""
    normalized = [re.sub(r"[^a-z0-9/ ()$%-]", "", h.lower()).strip() for h in headers]
    mapping: dict[str, int] = {}
    used: set[int] = set()

    for field_name, hints in _VESTING_HEADER_HINTS.items():
        for hint in hints:
            idx = next(
                (i for i, h in enumerate(normalized) if i not in used and hint in h),
                -1,
            )
            if idx != -1:
                mapping[field_name] = idx
                used.add(idx)
                break

    return mapping


def anonymize_vesting_csv(csv_text: str, config: AnonConfig | None = None) -> str:
    """Anonymize a Schwab vesting history CSV export.

    Works with any column layout — auto-detects columns by header name hints.
    Columns that aren't recognized are left as-is (safe default for non-PII
    fields like "Status" or "Plan Type").
    """
    config = config or AnonConfig()
    rng = _make_rng(config.seed)

    lines = csv_text.splitlines()

    # Find header row: look for a row containing "date" and either "shares"
    # or "vest" or "fmv" or "symbol"
    header_idx = 0
    for i, line in enumerate(lines[:10]):
        lower = line.lower()
        if "date" in lower and any(k in lower for k in ("share", "vest", "fmv",
                                                         "symbol", "action", "event")):
            header_idx = i
            break

    csv_block = "\n".join(lines[header_idx:])
    reader = csv.reader(io.StringIO(csv_block))
    all_rows = list(reader)

    if not all_rows:
        return csv_text

    headers = [h.strip() for h in all_rows[0]]
    data_rows = all_rows[1:]
    col_map = _detect_vesting_columns(headers)

    date_shift = timedelta(days=rng.randint(*config.date_shift_days))

    # Symbol mapping
    symbol_col = col_map.get("symbol")
    name_col = col_map.get("name")
    real_symbols: set[str] = set()
    if symbol_col is not None:
        for row in data_rows:
            if symbol_col < len(row):
                val = row[symbol_col].strip().strip('"')
                if val and val.lower() not in ("total", ""):
                    real_symbols.add(val)

    fake_pool = list(_FAKE_COMPANIES)
    rng.shuffle(fake_pool)
    symbol_mapping: dict[str, tuple[str, str]] = {}
    for i, sym in enumerate(sorted(real_symbols)):
        symbol_mapping[sym] = fake_pool[i % len(fake_pool)]

    price_factor = rng.uniform(*config.price_shift_range)
    qty_factor = rng.uniform(*config.quantity_shift_range)

    # Title rows above header
    output_lines: list[str] = []
    for i in range(header_idx):
        line = lines[i]
        line = re.sub(r"\.\.\.\d{3,}", "...XXX", line)
        def _shift_title_date(m: re.Match[str]) -> str:
            dt = _parse_date(m.group(0))
            return _format_date(dt + date_shift, m.group(0)) if dt else m.group(0)
        line = re.sub(r"\d{2}/\d{2}/\d{4}", _shift_title_date, line)
        line = re.sub(
            r"(as of\s+)\w+ \w+ \d+ \s*\d+:\d+:\d+ \w+ \d{4}",
            r"\1[redacted]",
            line,
        )
        for real_sym, (fake_sym, _) in symbol_mapping.items():
            line = line.replace(real_sym, fake_sym)
        output_lines.append(line)

    # Header row
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
    writer.writerow(headers)
    output_lines.append(buf.getvalue().strip())

    # Data rows
    date_col = col_map.get("date")
    shares_vested_col = col_map.get("shares_vested")
    shares_delivered_col = col_map.get("shares_delivered")
    shares_withheld_col = col_map.get("shares_withheld")
    fmv_col = col_map.get("fmv")
    value_col = col_map.get("value")
    award_id_col = col_map.get("award_id")
    tax_withheld_col = col_map.get("tax_withheld")

    for row in data_rows:
        if len(row) < len(headers):
            row.extend([""] * (len(headers) - len(row)))

        # Skip empty / total rows
        is_empty = all(not cell.strip() for cell in row)
        if is_empty:
            continue

        # Symbol + name
        if symbol_col is not None:
            orig_sym = row[symbol_col].strip().strip('"')
            if orig_sym in symbol_mapping:
                fake_sym, fake_name = symbol_mapping[orig_sym]
                row[symbol_col] = fake_sym
                if name_col is not None:
                    row[name_col] = fake_name

        # Date
        if date_col is not None and date_col < len(row):
            orig = row[date_col].strip()
            dt = _parse_date(orig)
            if dt:
                row[date_col] = _format_date(dt + date_shift, orig)

        # Shares — scale consistently
        new_vested = None
        if shares_vested_col is not None:
            orig = _parse_currency(row[shares_vested_col])
            if orig is not None and orig != 0:
                new_vested = max(1, round(orig * qty_factor))
                row[shares_vested_col] = str(new_vested)

        if shares_delivered_col is not None:
            orig = _parse_currency(row[shares_delivered_col])
            if orig is not None and orig != 0:
                row[shares_delivered_col] = str(max(1, round(orig * qty_factor)))

        if shares_withheld_col is not None:
            orig = _parse_currency(row[shares_withheld_col])
            if orig is not None and orig != 0:
                row[shares_withheld_col] = str(max(0, round(orig * qty_factor)))

        # FMV per share
        new_fmv = None
        if fmv_col is not None:
            orig = _parse_currency(row[fmv_col])
            if orig is not None and orig != 0:
                new_fmv = round(orig * price_factor, 2)
                row[fmv_col] = _format_currency(new_fmv, row[fmv_col])

        # Total value — recompute if we have both FMV and shares
        if value_col is not None:
            orig = _parse_currency(row[value_col])
            if orig is not None and orig != 0:
                if new_fmv is not None and new_vested is not None:
                    row[value_col] = _format_currency(
                        round(new_fmv * new_vested, 2), row[value_col]
                    )
                else:
                    row[value_col] = _format_currency(
                        round(orig * price_factor * qty_factor, 2), row[value_col]
                    )

        # Tax withheld
        if tax_withheld_col is not None:
            orig = _parse_currency(row[tax_withheld_col])
            if orig is not None and orig != 0:
                row[tax_withheld_col] = _format_currency(
                    round(orig * price_factor * qty_factor, 2), row[tax_withheld_col]
                )

        # Award ID — randomize
        if award_id_col is not None and row[award_id_col].strip():
            row[award_id_col] = f"AWD-{rng.randint(100000, 999999)}"

        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
        writer.writerow(row)
        output_lines.append(buf.getvalue().strip())

    return "\n".join(output_lines) + "\n"


# ── 1042-S PDF anonymization ──────────────────────────────────────────────

# Patterns that identify sensitive text in a 1042-S PDF
_SENSITIVE_PATTERNS: list[tuple[str, str]] = [
    # (pattern_name, regex) — order matters for replacement priority
    ("dollar_amount", r"\$[\d,]+\.\d{2}"),
    ("bare_amount", r"(?<!\d)[\d,]{2,}\.\d{2}(?!\d)"),  # e.g. "323.00" without $
    ("percentage", r"\d{1,3}\.\d{2}%"),
    ("tin", r"\d{2}-\d{7}"),          # EIN: XX-XXXXXXX
    ("ssn", r"\d{3}-\d{2}-\d{4}"),    # SSN
    ("date_us", r"\d{1,2}/\d{1,2}/\d{4}"),
    ("date_iso", r"\d{4}-\d{2}-\d{2}"),
    ("date_ymd_nodash", r"\d{8}"),    # YYYYMMDD in date of birth fields
    ("account_num", r"\d{4}-\d{4}"),  # Account numbers like 4563-7571
]

# Words/phrases that indicate a text fragment contains a person's name or address.
# We match by context: if a text fragment appears near "Recipient" labels in the form,
# we'll catch it via position. For standalone detection, we look for multi-word
# capitalized strings that aren't known form labels.
_FORM_LABELS = frozenset({
    "form", "1042-s", "1042", "copy", "department", "treasury", "internal",
    "revenue", "service", "income", "code", "gross", "chapter", "exemption",
    "withholding", "tax", "rate", "allowance", "federal", "withheld", "check",
    "deposited", "irs", "escrow", "procedures", "applied", "instructions",
    "occurred", "subsequent", "year", "respect", "partnership", "interest",
    "qualified", "intermediary", "foreign", "trust", "revising", "reporting",
    "report", "specific", "recipient", "agents", "overpaid", "repaid",
    "pursuant", "adjustment", "total", "credit", "combine", "boxes", "paid",
    "amounts", "not", "see", "agent", "primary", "pro-rata", "basis",
    "intermediary's", "entity", "flow-through", "country", "identification",
    "number", "global", "address", "street", "city", "town", "state",
    "province", "zip", "postal", "payer", "name", "tin", "ein", "giin",
    "status", "amended", "amendment", "unique", "form", "identifier",
    "date", "birth", "applicable", "keep", "records", "omb", "no",
    "go", "www", "irs", "gov", "for", "and", "the", "of", "to", "if",
    "a", "an", "in", "on", "or", "by", "at", "is", "it", "was", "not",
    "with", "from", "this", "that", "any", "are", "has", "had", "have",
    "been", "its", "as", "may", "box", "source", "subject", "person",
    "foreign", "information", "latest", "irs.gov/form1042s",
    "provided", "report", "records", "amounts", "shown", "needed",
    "complete", "return", "your", "copy", "instructions", "recipient",
    "form", "1042-s", "keep", "filing", "should", "use", "you",
    "will", "do", "can", "these", "those", "which", "other", "such",
    "each", "all", "both", "also", "only", "about", "than", "more",
    "some", "would", "could", "should", "shall", "must", "into",
    "through", "under", "over", "between", "after", "before", "during",
})


def _is_known_label(text: str) -> bool:
    """Check if text is a standard form label rather than personal data."""
    words = text.lower().split()
    return all(w.rstrip(".,;:()") in _FORM_LABELS or len(w) <= 2 for w in words)


@dataclass
class _TextFragment:
    """A piece of text extracted from a PDF page with its position and font size."""
    text: str
    x: float
    y: float
    font_size: float
    page_idx: int


def _extract_text_with_positions(reader: "PdfReader") -> list[_TextFragment]:
    """Extract all text fragments from a PDF with their positions."""
    from pypdf import PdfReader as _  # just for type hint

    fragments: list[_TextFragment] = []

    for page_idx, page in enumerate(reader.pages):
        def visitor(text: str, cm: list, tm: list, font_dict: dict, font_size: float,
                    _page_idx: int = page_idx) -> None:
            if text.strip():
                fragments.append(_TextFragment(
                    text=text.strip(),
                    x=tm[4],
                    y=tm[5],
                    font_size=font_size or 8.0,
                    page_idx=_page_idx,
                ))
        page.extract_text(visitor_text=visitor)

    return fragments


def _build_replacement_map(
    fragments: list[_TextFragment],
    rng: random.Random,
    price_factor: float,
    date_shift: timedelta,
) -> dict[int, list[tuple[_TextFragment, str]]]:
    """Build a per-page mapping of (original_fragment, replacement_text).

    Returns {page_idx: [(fragment, new_text), ...]}.
    """
    replacements: dict[int, list[tuple[_TextFragment, str]]] = {}

    # First pass: collect all dollar amounts to understand the value distribution
    all_amounts: list[tuple[_TextFragment, float]] = []
    for frag in fragments:
        for m in re.finditer(r"\$?([\d,]+\.\d{2})", frag.text):
            try:
                val = float(m.group(1).replace(",", ""))
                if val > 0:
                    all_amounts.append((frag, val))
            except ValueError:
                pass

    # Second pass: detect name/address fragments.
    # In 1042-S forms, names and addresses appear as standalone text fragments
    # near labeled fields.  We detect them by checking if a fragment:
    #   - Is NOT a known form label
    #   - Contains mostly alphabetic/space characters (not numbers/symbols)
    #   - Is reasonably long (names/addresses are usually >4 chars)
    _FAKE_NAMES = [
        "JOHN DOE", "JANE SMITH", "MAX MUSTERMANN", "ERIKA MUSTER",
        "ALEX JOHNSON", "MARIA GARCIA",
    ]
    _FAKE_ADDRESSES = [
        "123 EXAMPLE STRASSE", "456 MUSTER WEG", "789 DEMO ALLEE",
        "42 SAMPLE ROAD", "10 TEST BOULEVARD",
    ]
    _FAKE_CITIES = [
        "10115 BERLIN, GERMANY", "80331 MUNICH, GERMANY",
        "20095 HAMBURG, GERMANY", "50667 COLOGNE, GERMANY",
    ]

    # Track which fragments look like personal names or addresses.
    # We're conservative: only flag fragments that look like proper nouns
    # (names), street addresses, or city/postal lines — NOT general prose.
    name_address_candidates: set[int] = set()
    for i, frag in enumerate(fragments):
        text = frag.text.strip()
        # Skip very short or very long fragments (prose paragraphs)
        if len(text) < 4 or len(text) > 80:
            continue
        # Skip fragments that contain dollar amounts, percentages, or TINs —
        # those are handled by pattern-based replacement, not name heuristics
        if re.search(r"\$[\d,]+\.\d{2}|\d{2,}-\d{2,}", text):
            continue
        # Skip fragments that are mostly numbers / form field labels
        alpha_ratio = sum(1 for c in text if c.isalpha()) / max(len(text), 1)
        if alpha_ratio < 0.5:
            continue
        # Skip known form labels
        if _is_known_label(text):
            continue
        # Skip fragments that look like prose (many common English words)
        words = text.lower().split()
        common_word_count = sum(1 for w in words if w.rstrip(".,;:()") in _FORM_LABELS)
        if len(words) > 3 and common_word_count / len(words) > 0.5:
            continue
        # If it looks like a person's name or address, flag it
        name_address_candidates.add(i)

    for i, frag in enumerate(fragments):
        new_text = frag.text

        # Replace personal names and addresses (only for non-numeric fragments)
        if i in name_address_candidates:
            text = frag.text.strip()

            # Handle "Label: Value" patterns — preserve the label, replace the value
            label_match = re.match(r"^((?:Recipient|Name|Address|Agent)\s*:\s*)", text, re.IGNORECASE)
            prefix = label_match.group(1) if label_match else ""
            value_part = text[len(prefix):].strip() if prefix else text

            if any(kw in value_part.lower() for kw in ("street", "str", "weg", "allee",
                                                        "road", "way", "ave", "blvd",
                                                        "platz")):
                replacement = rng.choice(_FAKE_ADDRESSES)
            elif re.search(r"\d{4,5}\s", value_part):
                replacement = rng.choice(_FAKE_CITIES)
            else:
                replacement = rng.choice(_FAKE_NAMES)

            new_text = prefix + replacement if prefix else replacement

        # Replace dollar amounts: $X,XXX.XX
        def _replace_dollar(m: re.Match) -> str:
            try:
                val = float(m.group(0).replace("$", "").replace(",", ""))
                new_val = round(val * price_factor, 2)
                if "$" in m.group(0):
                    return f"${new_val:,.2f}"
                return f"{new_val:,.2f}"
            except ValueError:
                return m.group(0)

        new_text = re.sub(r"\$[\d,]+\.\d{2}", _replace_dollar, new_text)

        # Replace bare decimal amounts (e.g., "323.00" in form fields)
        def _replace_bare_amount(m: re.Match) -> str:
            try:
                val = float(m.group(0).replace(",", ""))
                # Don't replace small integers that might be codes (like "06", "15", "01")
                # but do replace amounts that look like money
                if val >= 10.0:
                    new_val = round(val * price_factor, 2)
                    return f"{new_val:,.2f}"
                return m.group(0)
            except ValueError:
                return m.group(0)

        new_text = re.sub(r"(?<!\d)[\d,]{2,}\.\d{2}(?!\d|%)", _replace_bare_amount, new_text)

        # Replace EIN: XX-XXXXXXX
        new_text = re.sub(r"\d{2}-\d{7}", f"{rng.randint(10,99)}-{rng.randint(1000000,9999999)}", new_text)

        # Replace SSN: XXX-XX-XXXX
        new_text = re.sub(r"\d{3}-\d{2}-\d{4}",
                          f"{rng.randint(100,999)}-{rng.randint(10,99)}-{rng.randint(1000,9999)}", new_text)

        # Replace account numbers: XXXX-XXXX
        new_text = re.sub(r"\b\d{4}-\d{4}\b",
                          f"{rng.randint(1000,9999)}-{rng.randint(1000,9999)}", new_text)

        # Replace US dates: MM/DD/YYYY
        def _replace_us_date(m: re.Match) -> str:
            dt = _parse_date(m.group(0))
            if dt:
                return _format_date(dt + date_shift, m.group(0))
            return m.group(0)

        new_text = re.sub(r"\d{1,2}/\d{1,2}/\d{4}", _replace_us_date, new_text)

        # Replace ISO dates: YYYY-MM-DD
        def _replace_iso_date(m: re.Match) -> str:
            dt = _parse_date(m.group(0))
            if dt:
                return _format_date(dt + date_shift, m.group(0))
            return m.group(0)

        new_text = re.sub(r"\d{4}-\d{2}-\d{2}", _replace_iso_date, new_text)

        # Replace 8-digit date-like sequences (YYYYMMDD) in date of birth fields
        def _replace_compact_date(m: re.Match) -> str:
            s = m.group(0)
            try:
                dt = datetime.strptime(s, "%Y%m%d")
                new_dt = dt + date_shift
                return new_dt.strftime("%Y%m%d")
            except ValueError:
                return s

        new_text = re.sub(r"\b[12]\d{3}[01]\d[0-3]\d\b", _replace_compact_date, new_text)

        # Only record if something changed
        if new_text != frag.text:
            replacements.setdefault(frag.page_idx, []).append((frag, new_text))

    return replacements


def _create_overlay_page(
    page_width: float,
    page_height: float,
    replacements: list[tuple[_TextFragment, str]],
) -> bytes:
    """Create a single-page PDF overlay with white boxes + replacement text.

    Coordinates: pypdf gives positions in PDF units (points, 1pt = 1/72 inch)
    with origin at bottom-left. fpdf uses mm with origin at top-left.
    """
    from fpdf import FPDF

    # Convert points to mm
    w_mm = page_width * 25.4 / 72
    h_mm = page_height * 25.4 / 72

    pdf = FPDF(orientation="P", unit="pt", format=(page_width, page_height))
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)

    for frag, new_text in replacements:
        font_size = frag.font_size if frag.font_size > 0 else 8.0

        # Sanitize text for fpdf's Helvetica (latin-1 only)
        safe_text = new_text.encode("latin-1", errors="replace").decode("latin-1")

        # Estimate text width for the white cover rectangle
        # Approximate: each character is ~0.6 * font_size points wide
        orig_width = len(frag.text) * font_size * 0.55
        new_width = len(safe_text) * font_size * 0.55
        cover_width = max(orig_width, new_width) + 4  # small padding

        # PDF coordinates: origin at bottom-left
        # fpdf coordinates: origin at top-left
        # Convert: fpdf_y = page_height - pdf_y
        x_pt = frag.x
        y_pt = page_height - frag.y  # convert to top-left origin

        # Draw white rectangle to cover original text
        pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(255, 255, 255)
        rect_y = y_pt - 2  # small padding above
        rect_h = font_size + 4
        pdf.rect(x_pt - 1, rect_y, cover_width, rect_h, style="F")

        # Draw replacement text
        pdf.set_font("Helvetica", "", font_size)
        pdf.set_text_color(0, 0, 0)
        pdf.text(x_pt, y_pt + font_size * 0.75, safe_text)

    return pdf.output()


def anonymize_1042s_pdf(input_path: str, output_path: str,
                        config: AnonConfig | None = None) -> None:
    """Anonymize a 1042-S PDF by overlaying replacements on the original.

    Preserves the original layout, pages, and form structure. Only sensitive
    data (amounts, names, TINs, addresses, dates) is covered with white
    rectangles and replaced with anonymized values.
    """
    from pypdf import PdfReader, PdfWriter

    config = config or AnonConfig()
    rng = _make_rng(config.seed)

    reader = PdfReader(input_path)
    price_factor = rng.uniform(*config.price_shift_range)
    date_shift = timedelta(days=rng.randint(*config.date_shift_days))

    # Extract text with positions
    fragments = _extract_text_with_positions(reader)

    # Build replacement map
    replacement_map = _build_replacement_map(fragments, rng, price_factor, date_shift)

    # Create output PDF — clone from original to preserve structure
    writer = PdfWriter(clone_from=reader)

    for page_idx in range(len(writer.pages)):
        if page_idx in replacement_map and replacement_map[page_idx]:
            page = writer.pages[page_idx]
            mediabox = page.mediabox
            page_width = float(mediabox.width)
            page_height = float(mediabox.height)

            # Create overlay
            overlay_bytes = _create_overlay_page(
                page_width, page_height,
                replacement_map[page_idx],
            )

            # Merge overlay onto the page (already attached to writer)
            overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
            page.merge_page(overlay_reader.pages[0])

    with open(output_path, "wb") as f:
        writer.write(f)


# ── File type detection & unified entry point ─────────────────────────────

def _detect_file_type(path: str, text: str | None = None) -> str:
    """Detect file type: 'realized_gains', 'vesting', or 'pdf'."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return "pdf"

    # For CSVs, peek at content to distinguish realized gains from vesting
    if text is None:
        return "csv_unknown"

    lower = text[:2000].lower()

    # Realized gains: has "proceeds" or "gain/loss" or "cost basis"
    if any(kw in lower for kw in ("proceeds", "gain/loss", "cost basis", "realized gain")):
        return "realized_gains"

    # Vesting: has "vest" or "shares delivered" or "fmv" or "fair market value"
    if any(kw in lower for kw in ("vest", "shares delivered", "fmv", "fair market value",
                                   "shares withheld")):
        return "vesting"

    # Fallback: treat as generic CSV and apply realized gains anonymizer
    # (it's the more conservative option — won't break on unknown layouts)
    return "csv_unknown"


def anonymize_file(input_path: str, output_path: str, config: AnonConfig | None = None) -> str:
    """Read a file, anonymize it, and write the result.

    Auto-detects file type (realized gains CSV, vesting CSV, or 1042-S PDF).
    Returns the detected file type as a string.
    """
    ext = os.path.splitext(input_path)[1].lower()

    if ext == ".pdf":
        anonymize_1042s_pdf(input_path, output_path, config)
        return "pdf"

    # CSV files
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            with open(input_path, encoding=encoding) as f:
                text = f.read()
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Could not decode {input_path}")

    file_type = _detect_file_type(input_path, text)

    if file_type == "vesting":
        result = anonymize_vesting_csv(text, config)
    else:
        result = anonymize_realized_gains_csv(text, config)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result)

    return file_type
