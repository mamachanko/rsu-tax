"""Parse 1042-S PDF tax forms from Schwab.

Extracts key fields: gross income, tax withheld, withholding rate,
income code, and recipient country from IRS Form 1042-S.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import TaxFormData


def _extract_dollar_amount(text: str) -> float | None:
    """Extract a dollar amount from text like '$1,234.56' or '1234.56'."""
    m = re.search(r"\$?([\d,]+\.\d{2})", text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


def _extract_percentage(text: str) -> float | None:
    """Extract a percentage like '30.00' or '15' from text."""
    m = re.search(r"(\d{1,3}(?:\.\d{1,2})?)\s*%?", text)
    if m:
        val = float(m.group(1))
        if 0 < val <= 100:
            return val / 100.0
    return None


@dataclass
class TaxFormParseResult:
    data: TaxFormData | None
    warnings: list[str] = field(default_factory=list)


def _find_box_value(text: str, box_pattern: str) -> str:
    """Find the value associated with a box label in extracted PDF text."""
    m = re.search(box_pattern, text, re.IGNORECASE)
    if m:
        # Return the rest of the line or next few characters after the match
        start = m.end()
        end = min(start + 50, len(text))
        remaining = text[start:end].strip()
        # Take until newline
        return remaining.split("\n")[0].strip()
    return ""


def parse_1042s_pdf(pdf_path: str) -> TaxFormParseResult:
    """Parse a 1042-S PDF and extract key tax fields.

    Looks for:
    - Box 2: Gross income
    - Box 7a: Federal tax withheld
    - Box 3b: Tax rate
    - Box 1: Income code
    - Box 13e/13f: Recipient country
    - Tax year from the form header

    Returns TaxFormParseResult with parsed data or warnings if parsing failed.
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
        page_text = page.extract_text() or ""
        full_text += page_text + "\n"

    if not full_text.strip():
        return TaxFormParseResult(
            data=None,
            warnings=["Could not extract text from PDF"],
        )

    # Check this is actually a 1042-S
    if "1042-S" not in full_text and "1042" not in full_text:
        return TaxFormParseResult(
            data=None,
            warnings=["PDF does not appear to be a 1042-S form"],
        )

    # ── Tax year ────────────────────────────────────────────────────────
    tax_year: int | None = None
    # Look for year patterns near "1042-S" or "tax year"
    year_m = re.search(r"(?:tax\s+year|for\s+calendar\s+year)\s*[:\s]*(\d{4})", full_text, re.IGNORECASE)
    if year_m:
        tax_year = int(year_m.group(1))
    else:
        # Try finding a 4-digit year near "1042"
        year_m = re.search(r"1042-S\s*(\d{4})", full_text)
        if year_m:
            tax_year = int(year_m.group(1))
        else:
            # Last resort: any 4-digit year in 2020-2030 range
            year_m = re.search(r"\b(202\d)\b", full_text)
            if year_m:
                tax_year = int(year_m.group(1))

    if tax_year is None:
        warnings.append("Could not determine tax year from 1042-S")
        tax_year = 0

    # ── Process only Copy B (recipient's copy) ──────────────────────────
    # The 1042-S PDF often has multiple copies. We want Copy B.
    # Split by pages and look for Copy B section
    copy_b_text = full_text  # fallback to full text
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if "Copy B" in page_text and len(page_text) < 8000:
            copy_b_text = page_text
            break

    # ── Box 2: Gross income ─────────────────────────────────────────────
    gross_income: float | None = None
    # Pattern: "2 Gross income" followed by amount
    box2_patterns = [
        r"(?:box\s*)?2[.\s]+[Gg]ross\s+[Ii]ncome[:\s]*\$?([\d,]+\.?\d*)",
        r"[Gg]ross\s+[Ii]ncome[:\s]*\$?([\d,]+\.\d{2})",
        r"2\s+\$?([\d,]+\.\d{2})",
    ]
    for pat in box2_patterns:
        m = re.search(pat, copy_b_text)
        if m:
            try:
                gross_income = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                continue

    if gross_income is None:
        # Try to find any large dollar amount in the text (likely gross income)
        amounts = re.findall(r"\$?([\d,]+\.\d{2})", copy_b_text)
        if amounts:
            parsed_amounts = []
            for a in amounts:
                try:
                    parsed_amounts.append(float(a.replace(",", "")))
                except ValueError:
                    continue
            if parsed_amounts:
                # The largest amount is likely gross income
                gross_income = max(parsed_amounts)
                warnings.append(
                    f"Gross income ({gross_income:.2f}) was inferred from largest "
                    f"amount — please verify"
                )

    # ── Box 7a: Federal tax withheld ────────────────────────────────────
    tax_withheld: float | None = None
    box7_patterns = [
        r"(?:box\s*)?7a?[.\s]+(?:[Ff]ederal\s+)?[Tt]ax\s+[Ww]ithheld[:\s]*\$?([\d,]+\.?\d*)",
        r"[Ff]ederal\s+[Tt]ax\s+[Ww]ithheld[:\s]*\$?([\d,]+\.\d{2})",
        r"7a?\s+\$?([\d,]+\.\d{2})",
    ]
    for pat in box7_patterns:
        m = re.search(pat, copy_b_text)
        if m:
            try:
                tax_withheld = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                continue

    # ── Box 3b: Tax rate ────────────────────────────────────────────────
    withholding_rate: float | None = None
    rate_patterns = [
        r"(?:box\s*)?3b?[.\s]+(?:[Rr]ate|[Tt]ax\s+[Rr]ate)[:\s]*(\d{1,3}(?:\.\d{1,2})?)\s*%?",
        r"(?:[Rr]ate\s+of\s+)?[Ww]ithholding[:\s]*(\d{1,3}(?:\.\d{1,2})?)\s*%",
        r"(\d{2}(?:\.\d{2})?)\s*%",
    ]
    for pat in rate_patterns:
        m = re.search(pat, copy_b_text)
        if m:
            val = float(m.group(1))
            if 0 < val <= 100:
                withholding_rate = val / 100.0
                break

    # ── Box 1: Income code ──────────────────────────────────────────────
    income_code: str | None = None
    code_m = re.search(r"(?:box\s*)?1[.\s]+[Ii]ncome\s+[Cc]ode[:\s]*(\d{1,2})", copy_b_text)
    if code_m:
        income_code = code_m.group(1)
    else:
        # Income code 19 = "Compensation during studying and training"
        # Income code 20 = "Compensation for independent personal services"
        # Income code 15 = "Pensions and annuities"
        # Income code 50 = "Other income"
        code_m = re.search(r"\b(1[0-9]|[2-5][0-9])\b", copy_b_text[:200])
        if code_m:
            income_code = code_m.group(1)

    # ── Recipient country ───────────────────────────────────────────────
    recipient_country: str | None = None
    country_m = re.search(
        r"(?:13[ef]|[Cc]ountry)[:\s]*(GERMANY|DE|DEUTSCHLAND|[A-Z]{2})",
        copy_b_text, re.IGNORECASE,
    )
    if country_m:
        recipient_country = country_m.group(1).upper()

    # ── Validate and build result ───────────────────────────────────────
    if gross_income is None:
        warnings.append("Could not find gross income (Box 2)")
    if tax_withheld is None:
        warnings.append("Could not find federal tax withheld (Box 7)")
        tax_withheld = 0.0

    # Cross-check: tax_withheld / gross_income should ≈ withholding_rate
    if gross_income and tax_withheld and withholding_rate:
        expected = gross_income * withholding_rate
        if abs(expected - tax_withheld) > max(1.0, gross_income * 0.01):
            warnings.append(
                f"Tax withheld ({tax_withheld:.2f}) doesn't match "
                f"gross income ({gross_income:.2f}) x rate ({withholding_rate:.0%}) "
                f"= {expected:.2f}"
            )
    elif gross_income and tax_withheld and withholding_rate is None:
        # Infer rate from amounts
        withholding_rate = tax_withheld / gross_income
        warnings.append(
            f"Withholding rate inferred as {withholding_rate:.1%} from amounts"
        )

    if gross_income is None:
        return TaxFormParseResult(data=None, warnings=warnings)

    data = TaxFormData(
        tax_year=tax_year,
        gross_income_usd=gross_income,
        tax_withheld_usd=tax_withheld or 0.0,
        withholding_rate=withholding_rate or 0.0,
        income_code=income_code,
        recipient_country=recipient_country,
    )

    return TaxFormParseResult(data=data, warnings=warnings)
