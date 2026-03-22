"""Parse Schwab Equity Award Lapse History CSV exports.

The Schwab lapse export uses a two-row-per-event structure:
  Row 1 (header): Date, Action, Symbol, Description, Quantity
  Row 2 (detail): AwardDate, AwardId, FairMarketValuePrice, SalePrice,
                  SharesSoldWithheldForTaxes, NetSharesDeposited, Taxes

This parser pairs each header row with its following detail row to produce
a list of LapseEvent objects.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any

from .models import LapseEvent


def _parse_currency(value: Any) -> float:
    """Parse a currency string like '$1,234.56' to a float."""
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

    return cleaned


@dataclass
class LapseParseResult:
    events: list[LapseEvent]
    warnings: list[str] = field(default_factory=list)


def _find_header_row(lines: list[str]) -> int:
    """Find the CSV header row by looking for lapse-specific column names."""
    for i, line in enumerate(lines[:10]):
        lower = line.lower()
        if "fairmv" in lower or "fairmarketvalue" in lower or (
            "date" in lower and "awardid" in lower.replace(" ", "")
        ):
            return i
    return 0


def _is_header_row(row: dict[str, str]) -> bool:
    """Detect a lapse header row (row 1 of a pair).

    Header rows have Date, Action, Symbol, Quantity filled in,
    but AwardDate/FairMarketValuePrice are empty.
    """
    date_val = row.get("Date", "").strip()
    action_val = row.get("Action", "").strip()
    fmv_val = row.get("FairMarketValuePrice", "").strip()
    return bool(date_val) and bool(action_val) and not fmv_val


def _is_detail_row(row: dict[str, str]) -> bool:
    """Detect a lapse detail row (row 2 of a pair).

    Detail rows have AwardDate and FairMarketValuePrice filled in,
    but Date/Action are empty.
    """
    date_val = row.get("Date", "").strip()
    fmv_val = row.get("FairMarketValuePrice", "").strip()
    return not date_val and bool(fmv_val)


def parse_lapse_csv(csv_text: str) -> LapseParseResult:
    """Parse a Schwab Equity Award Lapse History CSV export.

    Returns a LapseParseResult with parsed LapseEvent objects and any warnings.
    """
    warnings: list[str] = []
    lines = csv_text.splitlines()

    if not lines:
        return LapseParseResult(events=[], warnings=["Empty CSV file"])

    header_idx = _find_header_row(lines)
    csv_block = "\n".join(lines[header_idx:])

    reader = csv.DictReader(
        io.StringIO(csv_block),
        skipinitialspace=True,
    )
    reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]
    rows = list(reader)

    # Validate that this looks like a lapse CSV
    headers = set(reader.fieldnames or [])
    expected = {"Date", "Action", "FairMarketValuePrice"}
    if not expected.issubset(headers):
        missing = expected - headers
        return LapseParseResult(
            events=[],
            warnings=[f"Not a lapse CSV: missing columns {missing}"],
        )

    events: list[LapseEvent] = []
    i = 0
    while i < len(rows):
        row = rows[i]

        if _is_header_row(row):
            # Expect the next row to be the detail row
            if i + 1 >= len(rows):
                warnings.append(
                    f"Row {i + 1}: lapse header without detail row at end of file"
                )
                break

            detail = rows[i + 1]
            if not _is_detail_row(detail):
                warnings.append(
                    f"Row {i + 1}: expected detail row after header, "
                    f"got another header or unrecognized row"
                )
                i += 1
                continue

            lapse_date = _parse_date(row.get("Date", ""))
            symbol = row.get("Symbol", "").strip()
            total_shares = _parse_currency(row.get("Quantity", ""))

            award_date_raw = detail.get("AwardDate", "").strip()
            award_date = _parse_date(award_date_raw) if award_date_raw else None
            award_id = detail.get("AwardId", "").strip() or None

            fmv = _parse_currency(detail.get("FairMarketValuePrice", ""))
            sale_price = _parse_currency(detail.get("SalePrice", ""))
            shares_sold = _parse_currency(
                detail.get("SharesSoldWithheldForTaxes", "")
            )
            shares_delivered = _parse_currency(
                detail.get("NetSharesDeposited", "")
            )
            taxes = _parse_currency(detail.get("Taxes", ""))

            if not lapse_date or not symbol:
                warnings.append(
                    f"Row {i + 1}: missing date or symbol — skipping"
                )
                i += 2
                continue

            if fmv == 0:
                warnings.append(
                    f"Row {i + 1}: FairMarketValuePrice is zero or missing"
                )

            events.append(
                LapseEvent(
                    symbol=symbol,
                    lapse_date=lapse_date,
                    total_shares=total_shares,
                    award_date=award_date,
                    award_id=award_id,
                    fmv_per_share_usd=fmv,
                    sale_price_usd=sale_price,
                    shares_sold_for_taxes=shares_sold,
                    shares_delivered=shares_delivered,
                    taxes_usd=taxes,
                )
            )
            i += 2
        else:
            # Skip unrecognized rows (e.g. standalone detail rows, empty rows)
            i += 1

    if not events:
        warnings.append("No lapse events found in the CSV")

    return LapseParseResult(events=events, warnings=warnings)
