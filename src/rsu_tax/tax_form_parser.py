"""Parse 1042-S PDF tax forms from Schwab.

Extracts key fields: gross income, tax withheld, withholding rate,
income code, and recipient country from IRS Form 1042-S.

The Schwab 1042-S PDF has a specific layout: form labels occupy the top portion
of each page, and field VALUES appear in a positional blob at the bottom after
the "Form 1042-S (YYYY)" marker.  This parser targets that value blob rather
than trying to match labels to adjacent values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import TaxFormData


@dataclass
class TaxFormParseResult:
    data: TaxFormData | None
    warnings: list[str] = field(default_factory=list)


def _extract_value_blob(page_text: str) -> str | None:
    """Extract the value blob that follows 'Form 1042-S (YYYY)' on a page."""
    m = re.search(r"Form\s+1042-S\s*\(\d{4}\)\s*\n(.*)", page_text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


def _find_form_pages(reader: "PdfReader") -> list[tuple[int, str, str]]:
    """Find form pages (not instruction pages) and extract their text + value blobs.

    Returns list of (page_index, full_text, value_blob).
    """
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if len(text) > 8000:
            continue  # skip instruction pages
        if "1042-S" not in text:
            continue
        blob = _extract_value_blob(text)
        if blob:
            pages.append((i, text, blob))
    return pages


def _parse_value_blob(blob: str) -> dict[str, float | str | None]:
    """Parse the positional value blob from a 1042-S form page.

    The blob has a consistent structure (values in form-field order):
    - Line 1: gross_income [spaces] other_amounts
    - Then: EIN, status codes, agent name
    - Then: country code, GIIN parts
    - Then: recipient name + country
    - Then: tax_withheld (Box 7a)
    - Then: total_withholding_credit (Box 10)
    - Then: TIN, account number
    - Then: income_code + rate + other amounts
    - Then: addresses, DOB, etc.
    """
    result: dict[str, float | str | None] = {
        "gross_income": None,
        "tax_withheld": None,
        "withholding_rate": None,
        "income_code": None,
        "recipient_country": None,
    }

    lines = blob.split("\n")
    if not lines:
        return result

    # ── Gross income: first large dollar amount on line 1 ───────────────
    first_line = lines[0].strip()
    amounts_on_first_line = re.findall(r"(\d[\d,]*\.\d{2})", first_line)
    for amt_str in amounts_on_first_line:
        val = float(amt_str.replace(",", ""))
        if val > 10:  # skip zeros and small codes
            result["gross_income"] = val
            break

    # ── Find tax withheld and rate from the blob ────────────────────────
    # Strategy: find all dollar amounts in the blob, then use position to
    # identify which is which.  Tax withheld comes AFTER the EIN/name block
    # and is typically a smaller amount than gross income.
    all_amounts: list[tuple[int, float]] = []  # (line_index, value)
    ein_line: int | None = None
    for i, line in enumerate(lines):
        # Track where EIN appears (marks the boundary)
        if re.search(r"\d{2}-\d{7,}", line):
            ein_line = i
        for m in re.finditer(r"(\d[\d,]*\.\d{2})", line):
            val = float(m.group(1).replace(",", ""))
            all_amounts.append((i, val))

    # Tax withheld: first non-zero amount appearing after the EIN line,
    # that isn't on line 0 (gross income) and is on its own line
    if ein_line is not None:
        for line_idx, val in all_amounts:
            if line_idx <= (ein_line if ein_line else 0):
                continue
            line_text = lines[line_idx].strip()
            # Tax withheld is usually on its own line or nearly so
            if re.match(r"^\d[\d,]*\.\d{2}$", line_text):
                result["tax_withheld"] = val
                break

    # ── Withholding rate: look for "NN 15" or "NN 30" or "NN15" pattern ──
    # The income code and rate often appear as "CC RR" or "CCRR..." on the
    # same line, e.g., "00 1514.63..." = code 00, rate 15%.
    for line in lines:
        # Explicit space-separated: "02 15" at start of line
        m = re.match(r"^(\d{2})\s+(15|30|14)\b", line.strip())
        if m:
            result["income_code"] = m.group(1)
            result["withholding_rate"] = int(m.group(2)) / 100.0
            break
        # Concatenated: "00 1514.63..." — code, then rate glued to next value
        m = re.match(r"^(\d{2})\s+(15|30|14)\d", line.strip())
        if m:
            result["income_code"] = m.group(1)
            result["withholding_rate"] = int(m.group(2)) / 100.0
            break

    # ── Recipient country: last 2 uppercase chars on a name-only line ───
    for line in lines:
        line_s = line.strip()
        # Skip lines with digits (EINs, amounts, TINs, etc.)
        if re.search(r"\d", line_s):
            continue
        # Skip short lines and "US" line
        if len(line_s) <= 3:
            continue
        # Pattern: uppercase letters ending with a 2-char country code
        # e.g., "MARIA GARCIAGM" → "GM", "JOHN DOEDE" → "DE"
        if line_s[-2:].isupper() and line_s[-3:-2].isalpha():
            code = line_s[-2:]
            if code not in ("US", "NO", "OK", "AN", "ON", "IN", "ER", "ED",
                            "AL", "LE", "RE", "ST", "AY", "EY", "ES", "SS"):
                result["recipient_country"] = code
                break

    return result


def parse_1042s_pdf(pdf_path: str) -> TaxFormParseResult:
    """Parse a 1042-S PDF and extract key tax fields.

    Processes all form pages, preferring Copy B (recipient's copy).
    If multiple copies have different values (as can happen with anonymized PDFs),
    uses the copy with the largest gross income.

    Returns TaxFormParseResult with parsed data or warnings.
    """
    from pypdf import PdfReader

    warnings: list[str] = []

    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        return TaxFormParseResult(
            data=None,
            warnings=[f"Could not read PDF: {e}"],
        )

    # Extract text from all pages
    full_text = ""
    for page in reader.pages:
        full_text += (page.extract_text() or "") + "\n"

    if not full_text.strip():
        return TaxFormParseResult(
            data=None,
            warnings=["Could not extract text from PDF"],
        )

    if "1042-S" not in full_text and "1042" not in full_text:
        return TaxFormParseResult(
            data=None,
            warnings=["PDF does not appear to be a 1042-S form"],
        )

    # ── Tax year ────────────────────────────────────────────────────────
    tax_year = 0
    year_m = re.search(r"Form\s+1042-S\s*\((\d{4})\)", full_text)
    if year_m:
        tax_year = int(year_m.group(1))
    else:
        year_m = re.search(r"\b(202\d)\b", full_text)
        if year_m:
            tax_year = int(year_m.group(1))

    if tax_year == 0:
        warnings.append("Could not determine tax year from 1042-S")

    # ── Find and parse form pages ───────────────────────────────────────
    form_pages = _find_form_pages(reader)
    if not form_pages:
        return TaxFormParseResult(
            data=None,
            warnings=["No form pages found in 1042-S PDF"],
        )

    # Prefer Copy B page; fall back to first form page
    best_blob: dict[str, float | str | None] | None = None
    best_gross: float = 0

    for page_idx, page_text, blob_text in form_pages:
        parsed = _parse_value_blob(blob_text)
        gross = parsed.get("gross_income")
        if gross is not None and isinstance(gross, (int, float)):
            is_copy_b = "Copy B" in page_text
            # Prefer Copy B; otherwise take the largest gross income
            if is_copy_b or gross > best_gross:
                best_blob = parsed
                best_gross = gross
                if is_copy_b:
                    break

    if best_blob is None or best_blob.get("gross_income") is None:
        return TaxFormParseResult(
            data=None,
            warnings=["Could not extract gross income from 1042-S"],
        )

    gross_income = float(best_blob["gross_income"])  # type: ignore[arg-type]
    tax_withheld = float(best_blob.get("tax_withheld") or 0)
    withholding_rate = best_blob.get("withholding_rate")
    income_code = best_blob.get("income_code")
    recipient_country = best_blob.get("recipient_country")

    # Cross-check: infer rate if not found
    if withholding_rate is None and gross_income > 0 and tax_withheld > 0:
        inferred = tax_withheld / gross_income
        if 0.05 <= inferred <= 0.50:  # only accept reasonable rates
            withholding_rate = round(inferred, 4)
            warnings.append(
                f"Withholding rate inferred as {withholding_rate:.1%} from amounts"
            )
    elif withholding_rate is not None and gross_income > 0 and tax_withheld > 0:
        expected = gross_income * withholding_rate
        if abs(expected - tax_withheld) > max(1.0, gross_income * 0.02):
            warnings.append(
                f"Tax withheld ({tax_withheld:.2f}) doesn't match "
                f"gross income ({gross_income:.2f}) x rate ({withholding_rate:.0%}) "
                f"= {expected:.2f}"
            )

    data = TaxFormData(
        tax_year=tax_year,
        gross_income_usd=gross_income,
        tax_withheld_usd=tax_withheld,
        withholding_rate=float(withholding_rate or 0),
        income_code=str(income_code) if income_code else None,
        recipient_country=str(recipient_country) if recipient_country else None,
    )

    return TaxFormParseResult(data=data, warnings=warnings)
