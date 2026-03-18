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

def anonymize_1042s_pdf(input_path: str, output_path: str,
                        config: AnonConfig | None = None) -> None:
    """Anonymize a 1042-S PDF by extracting key data and generating a new PDF.

    Since editing PDFs in-place is unreliable, we:
    1. Extract text from the original to identify monetary amounts and the tax year
    2. Generate a clean new PDF with randomized values in the 1042-S structure
    """
    from fpdf import FPDF
    from pypdf import PdfReader

    config = config or AnonConfig()
    rng = _make_rng(config.seed)

    reader = PdfReader(input_path)
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    # Extract the tax year
    tax_year_match = re.search(r"20[0-9]{2}", full_text)
    tax_year = int(tax_year_match.group()) if tax_year_match else 2025

    date_shift = timedelta(days=rng.randint(*config.date_shift_days))
    price_factor = rng.uniform(*config.price_shift_range)

    # Try to extract monetary amounts from the PDF text
    # 1042-S key fields: gross income (Box 2), tax rate (Box 3b),
    # federal tax withheld (Box 7)
    amounts = re.findall(r"\$?([\d,]+\.\d{2})\b", full_text)
    parsed_amounts = []
    for a in amounts:
        try:
            parsed_amounts.append(float(a.replace(",", "")))
        except ValueError:
            pass

    # Heuristic: largest amount is likely gross income, second largest is tax withheld
    parsed_amounts.sort(reverse=True)
    orig_gross = parsed_amounts[0] if len(parsed_amounts) >= 1 else 50000.00
    orig_tax = parsed_amounts[1] if len(parsed_amounts) >= 2 else orig_gross * 0.30

    # Try to find withholding rate
    rate_match = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%", full_text)
    withholding_rate = float(rate_match.group(1)) if rate_match else 30.0

    # Randomize
    new_gross = round(orig_gross * price_factor, 2)
    new_tax = round(new_gross * withholding_rate / 100, 2)

    # Generate clean PDF
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Title
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Form 1042-S", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Foreign Person's U.S. Source Income Subject to Withholding",
             new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Tax Year {tax_year}  [ANONYMIZED]",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Box layout
    def _box(label: str, value: str) -> None:
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(90, 5, label, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(90, 7, value, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    _box("Box 1 - Income Code", "15 (Compensation for personal services)")
    _box("Box 2 - Gross Income", f"${new_gross:,.2f}")
    _box("Box 3 - Chapter 3 Tax Rate", f"{withholding_rate:.2f}%")
    _box("Box 4a - Exemption Code", "")
    _box("Box 7 - Federal Tax Withheld", f"${new_tax:,.2f}")
    _box("Box 7a - Check if federal tax withheld was not deposited with the IRS", "")
    _box("Box 12a - Withholding Agent's EIN", "XX-XXXXXXX")
    _box("Box 12b - Withholding Agent's Name", "CHARLES SCHWAB & CO., INC.")

    pdf.ln(5)
    _box("Box 13a - Recipient's TIN", "XXX-XX-XXXX")
    _box("Box 13b - Recipient's Name", "JOHN DOE")
    _box("Box 13c - Recipient's Address", "123 EXAMPLE STRASSE, 10115 BERLIN, GERMANY")
    _box("Box 13d - Recipient's Country Code", "DE")

    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5,
             "This is an anonymized version of a 1042-S form generated for testing purposes.",
             new_x="LMARGIN", new_y="NEXT")

    pdf.output(output_path)


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
