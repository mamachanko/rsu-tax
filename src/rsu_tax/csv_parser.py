"""Parse Schwab brokerage CSV exports (Realized Gain/Loss format)."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any

from .models import SchwabTransaction

# Known header variants for each field (most-specific first to avoid collisions)
_HEADER_VARIANTS: dict[str, list[str]] = {
    "cost_basis_method": ["cost basis method", "method", "lot method"],
    "st_gain_loss": ["short term (st) gain/loss ($)", "st gain/loss ($)", "short-term gain/loss"],
    "lt_gain_loss": ["long term (lt) gain/loss ($)", "lt gain/loss ($)", "long-term gain/loss"],
    "wash_sale": ["wash sale?", "wash sale", "wash sale loss disallowed", "wash sale adjustment", "wash"],
    "cost_basis": ["cost basis (cb)", "cost basis", "adjusted cost basis", "cost", "basis", "purchase price", "total cost"],
    "gain_loss": ["total gain/loss ($)", "gain/loss", "gain loss", "gain(loss)", "realized gain/loss", "realized gain", "gain/loss ($)"],
    "date_acquired": ["date acquired", "acquisition date", "open date", "vest date", "acquired"],
    "date_sold": ["date sold", "sale date", "close date", "closed date", "sold", "date of sale", "transaction closed date"],
    "symbol": ["symbol", "ticker", "security"],
    "name": ["name", "description", "company"],
    "quantity": ["quantity", "qty", "shares", "number of shares", "units"],
    "proceeds": ["proceeds", "sale proceeds", "total proceeds", "gross proceeds", "amount"],
    "term": ["term", "type", "holding period", "short/long"],
}

_REQUIRED_FIELDS = ("symbol", "date_sold", "proceeds", "cost_basis", "gain_loss")
_NONE_SENTINEL = "__none__"


def _normalize(header: str) -> str:
    return re.sub(r"[^a-z0-9/ ()$%-]", "", header.lower()).strip()


def detect_column_mapping(headers: list[str]) -> dict[str, str]:
    """Map logical field names to actual CSV column headers."""
    mapping: dict[str, str] = {}
    normalized = [_normalize(h) for h in headers]
    used: set[int] = set()

    for field_name, variants in _HEADER_VARIANTS.items():
        for variant in variants:
            # Exact match first, then substring
            idx = next(
                (i for i, h in enumerate(normalized) if i not in used and h == variant),
                -1,
            )
            if idx == -1:
                idx = next(
                    (i for i, h in enumerate(normalized) if i not in used and variant in h),
                    -1,
                )
            if idx != -1:
                mapping[field_name] = headers[idx]
                used.add(idx)
                break

    # Fill optional fields with sentinel
    for opt in ("wash_sale", "term", "name", "cost_basis_method", "st_gain_loss", "lt_gain_loss", "date_acquired"):
        mapping.setdefault(opt, _NONE_SENTINEL)

    return mapping


def _parse_currency(value: Any) -> float:
    """Parse a currency string like '$1,234.56' or '($50.00)' to a float."""
    if value is None or value == "" or value == "--":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[$,\s]", "", str(value))
    paren_negative = cleaned.startswith("(") and cleaned.endswith(")")
    if paren_negative:
        cleaned = cleaned[1:-1]
    try:
        num = float(cleaned)
    except ValueError:
        return 0.0
    return -num if paren_negative else num


def _parse_date(value: str | None) -> str:
    """Normalise a date string to YYYY-MM-DD."""
    if not value:
        return ""
    cleaned = str(value).strip()

    # MM/DD/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", cleaned)
    if m:
        return f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"

    # Already YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", cleaned):
        return cleaned

    # DD.MM.YYYY (German)
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", cleaned)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"

    return cleaned  # return as-is if unrecognised


def _detect_term(row: dict[str, str], mapping: dict[str, str]) -> str:
    """Determine Short Term / Long Term from available columns."""
    if mapping["term"] != _NONE_SENTINEL:
        term_val = row.get(mapping["term"], "").lower()
        if "long" in term_val:
            return "Long Term"
        if "short" in term_val:
            return "Short Term"

    st_col = mapping["st_gain_loss"]
    lt_col = mapping["lt_gain_loss"]
    if st_col != _NONE_SENTINEL or lt_col != _NONE_SENTINEL:
        st_raw = row.get(st_col, "--") if st_col != _NONE_SENTINEL else "--"
        lt_raw = row.get(lt_col, "--") if lt_col != _NONE_SENTINEL else "--"
        st_empty = not st_raw or st_raw.strip() in ("--", "")
        lt_empty = not lt_raw or lt_raw.strip() in ("--", "")
        if not st_empty and lt_empty:
            return "Short Term"
        if st_empty and not lt_empty:
            return "Long Term"
        if not st_empty and not lt_empty:
            st_num = _parse_currency(st_raw)
            lt_num = _parse_currency(lt_raw)
            if st_num != 0 and lt_num == 0:
                return "Short Term"
            if lt_num != 0 and st_num == 0:
                return "Long Term"

    return "Unknown"


def _parse_wash_sale(row: dict[str, str], mapping: dict[str, str]) -> float:
    if mapping["wash_sale"] == _NONE_SENTINEL:
        return 0.0
    val = row.get(mapping["wash_sale"], "")
    if not val:
        return 0.0
    lower = val.strip().lower()
    if lower == "yes":
        # Look for a disallowed loss column
        for key, raw in row.items():
            if "disallowed loss" in _normalize(key):
                amount = _parse_currency(raw)
                if amount != 0:
                    return amount
        return 1.0
    if lower == "no":
        return 0.0
    return _parse_currency(val)


@dataclass
class ParseResult:
    transactions: list[SchwabTransaction]
    warnings: list[str] = field(default_factory=list)


def parse_schwab_csv(csv_text: str) -> ParseResult:
    """Parse a Schwab Realized Gain/Loss CSV export."""
    warnings: list[str] = []
    lines = csv_text.splitlines()

    # Find the header row (contains 'symbol' and 'date' or 'proceed' or 'quantity')
    data_start = 0
    for i, line in enumerate(lines[:10]):
        lower = line.lower()
        if "symbol" in lower and any(k in lower for k in ("date", "proceed", "quantity")):
            data_start = i
            break

    # Strip trailing summary / empty rows
    data_end = len(lines)
    for i in range(len(lines) - 1, data_start, -1):
        stripped = lines[i].strip()
        if (
            stripped == ""
            or stripped.lower().startswith('"total')
            or stripped.lower().startswith("total")
            or stripped.startswith("***")
        ):
            data_end = i
        else:
            break

    csv_block = "\n".join(lines[data_start:data_end])
    reader = csv.DictReader(
        io.StringIO(csv_block),
        skipinitialspace=True,
    )
    # Strip whitespace from headers
    reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]

    rows: list[dict[str, str]] = list(reader)
    headers: list[str] = list(reader.fieldnames or [])
    mapping = detect_column_mapping(headers)

    for req in _REQUIRED_FIELDS:
        if mapping.get(req, _NONE_SENTINEL) == _NONE_SENTINEL:
            warnings.append(
                f'Could not auto-detect column for "{req}". '
                f"Available headers: {', '.join(headers)}"
            )

    has_acquisition_date = mapping["date_acquired"] != _NONE_SENTINEL
    if not has_acquisition_date:
        warnings.append(
            "No \"Date Acquired\" column found in Realized Gain/Loss CSV. "
            "Upload the Lapse History CSV to fill in vest dates automatically."
        )

    transactions: list[SchwabTransaction] = []
    for i, row in enumerate(rows):
        symbol_val = row.get(mapping.get("symbol", ""), "").strip()
        if not symbol_val or symbol_val.lower() == "total":
            continue

        date_sold = _parse_date(row.get(mapping.get("date_sold", ""), ""))
        if not date_sold:
            warnings.append(f"Row {i + 1}: missing sale date — skipping")
            continue

        date_acquired_raw = (
            row.get(mapping["date_acquired"], "") if has_acquisition_date else ""
        )
        date_acquired = _parse_date(date_acquired_raw) if date_acquired_raw else date_sold

        transactions.append(
            SchwabTransaction(
                symbol=symbol_val,
                name=row.get(mapping.get("name", _NONE_SENTINEL), "").strip() or None
                if mapping.get("name") != _NONE_SENTINEL
                else None,
                quantity=_parse_currency(row.get(mapping.get("quantity", ""), "")),
                date_acquired=date_acquired,
                date_sold=date_sold,
                proceeds_usd=_parse_currency(row.get(mapping.get("proceeds", ""), "")),
                cost_basis_usd=_parse_currency(row.get(mapping.get("cost_basis", ""), "")),
                gain_loss_usd=_parse_currency(row.get(mapping.get("gain_loss", ""), "")),
                term=_detect_term(row, mapping),
                wash_sale=_parse_wash_sale(row, mapping),
                cost_basis_method=row.get(mapping.get("cost_basis_method", _NONE_SENTINEL), "").strip() or None
                if mapping.get("cost_basis_method") != _NONE_SENTINEL
                else None,
                has_acquisition_date=has_acquisition_date,
            )
        )

    return ParseResult(transactions=transactions, warnings=warnings)
