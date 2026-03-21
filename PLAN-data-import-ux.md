# Plan: Multi-File Data Import UX Redesign

## Context

Currently the app accepts a **single file**: the Schwab "Realized Gain/Loss" CSV. The info dialog tells users to also look up vesting data, sale details, and tax forms — but none of that can be imported. This plan redesigns the app to accept all the data a user would actually download from Schwab, enriching calculations and the final tax report.

---

## 1. What Files Does Schwab Provide?

A user with RSUs at Schwab has **two separate account views**:

1. **Equity Award Center (EAC)** — the RSU/award management portal
2. **Individual Brokerage Account** — the regular trading account where delivered shares land

### The three files we need

| # | File | Where in Schwab | Format | What's in it |
|---|------|-----------------|--------|-------------|
| **A** | **Realized Gain/Loss** | EAC → "Realized Gain/Loss" view → Export | CSV | Per-lot: symbol, sale date, acquisition date (often missing), proceeds, cost basis, gain/loss, term, wash sale, cost basis method |
| **B** | **Equity Award Lapse History** | EAC → filter by "Lapse" → Export | CSV | Per-vest event: lapse date, shares vested, shares withheld for taxes, shares delivered, FMV per share, sale price, award ID |
| **C** | **1042-S** (non-US residents) | Schwab → Statements → Tax Forms | PDF | US-source income from RSU vesting, US tax withheld (rate, amount), treaty info |

### What we do NOT need

| File | Why excluded |
|------|-------------|
| **Individual Account Trade History** | Shows the same sells from the brokerage side, but without cost basis or gain/loss. Fully redundant with file A. |
| **1099-B** | US-resident-only form. German tax residents never receive it. |

### Classification: Required vs Optional

| File | Required? | Why |
|------|-----------|-----|
| **A — Realized Gain/Loss CSV** | **Required** | Core data for EUR capital gains calculation. Already supported. |
| **B — Equity Award Lapse CSV** | **Recommended** | Fills missing acquisition dates and provides authoritative FMV (= cost basis per share) on vest date. Critical for correct EUR conversion. |
| **C — 1042-S** | **Optional** | Enables reporting US tax withheld for foreign tax credit (Anlage AUS). |

---

## 2. Actual File Structures (from real Schwab exports)

### File A: Realized Gain/Loss CSV (already supported)

Exported from: EAC → Realized Gain/Loss → Export

```csv
"Symbol","Name","Date Sold","Date Acquired","Quantity","Proceeds","Cost Basis (CB)","Total Gain/Loss","..."
"AVGO","BROADCOM INC","03/17/2026","12/15/2024","61","$19,690.08","$19,607.18","$82.90","..."
```

### File B: Equity Award Lapse History CSV (NEW)

Exported from: EAC → filter transactions by "Lapse" → Export

**Key insight:** This file uses a **two-row-per-event** structure. The first row has the lapse-level data (date, action, symbol, total quantity). The second row has the per-award detail (award date, award ID, FMV, sale price, shares withheld, shares delivered, taxes).

```csv
"Date","Action","Symbol","Description","Quantity","FeesAndCommissions","DisbursementElection","Amount","AwardDate","AwardId","FairMarketValuePrice","SalePrice","SharesSoldWithheldForTaxes","NetSharesDeposited","Taxes"
"03/15/2026","Lapse","AVGO","Restricted Stock Lapse","30","","","","","","","","","",""
"","","","","","","","","11/22/2023","VM-00225234","$321.43","$322.79","15","15","$4,577.97"
"03/15/2026","Lapse","AVGO","Restricted Stock Lapse","88","","","","","","","","","",""
"","","","","","","","","03/15/2025","422361","$321.43","$322.79","42","46","$13,428.70"
```

**Fields:**
- Row 1 (lapse header): `Date` (vest/lapse date), `Action` ("Lapse"), `Symbol`, `Description`, `Quantity` (total shares in this lapse)
- Row 2 (award detail): `AwardDate`, `AwardId`, `FairMarketValuePrice` (FMV per share at vest), `SalePrice` (sell-to-cover sale price), `SharesSoldWithheldForTaxes`, `NetSharesDeposited`, `Taxes` (USD tax withheld)

**What this gives us:**
- `Date` = the **vest date** (= acquisition date for German tax purposes)
- `FairMarketValuePrice` = the **FMV per share** (= acquisition cost per share)
- `SalePrice` = the **sell-to-cover price** (should match proceeds in file A)
- `SharesSoldWithheldForTaxes` + `NetSharesDeposited` = `Quantity` (total shares)
- `Taxes` = US tax withheld per event (can cross-verify with 1042-S)

### File C: 1042-S PDF (already supported for anonymization)

IRS form showing US-source income and tax withheld. Key boxes:
- Box 2: Gross income (USD)
- Box 7: Federal tax withheld (USD)
- Box 3b: Tax rate (e.g., 30% or treaty 15%)

---

## 3. How the Files Fit Together

For German RSU tax (Abgeltungssteuer), the core calculation per lot is:

```
Gain/Loss (EUR) = Proceeds (EUR) − Cost Basis (EUR)

where:
  Proceeds (EUR)   = proceeds_usd × ECB_rate(sell_date)
  Cost Basis (EUR) = cost_basis_usd × ECB_rate(acquisition_date)
```

The **critical insight**: proceeds and cost basis are each converted at **different ECB rates** — the sell date rate and the acquisition (vest) date rate respectively. Getting the acquisition date wrong means using the wrong exchange rate, which changes the taxable gain.

### Data flow

```
File A: Realized Gain/Loss CSV    →  sell transactions (date, proceeds, cost basis USD)
         │                              ↓
         │  Problem: acquisition date often MISSING
         │                              ↓
File B: Lapse History CSV          →  fills in vest date + verifies FMV per share
         │                              = correct ECB rate for cost basis
         │
File C: 1042-S PDF (optional)     →  US tax withheld for Anlage AUS
```

Without File B, the app falls back to using the **sell date** ECB rate for cost basis conversion — which is wrong and produces inaccurate EUR gains.

---

## 4. Frontend UX Redesign

### Current UX
Single drop zone → upload CSV → results.

### New UX: Stepped File Import

Replace the single upload with a **multi-section file import** interface:

```
┌─────────────────────────────────────────────────────┐
│  RSU Tax Calculator                                 │
│  Import your Schwab data for EUR capital gains      │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │ 1. Realized Gain/Loss CSV          REQUIRED   │  │
│  │    [  Drop CSV here or click to browse     ]  │  │
│  │    Your main transaction data from Schwab     │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │ 2. Lapse History CSV            RECOMMENDED   │  │
│  │    [  Drop CSV here or click to browse     ]  │  │
│  │    Adds vest dates & FMV per share            │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │ 3. 1042-S Tax Form                  OPTIONAL  │  │
│  │    [  Drop PDF here or click to browse     ]  │  │
│  │    US tax withheld for foreign tax credit     │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  [ Calculate ]                                      │
└─────────────────────────────────────────────────────┘
```

**Design principles:**
- The required file (Realized Gain/Loss) stays prominent at the top
- Optional sections are visually de-emphasized (lighter border, collapsed by default on mobile)
- Each section has a badge: `REQUIRED`, `RECOMMENDED`, `OPTIONAL`
- Each section has a small "?" link explaining how to get that specific file
- The Calculate button enables as soon as the required file is provided
- Optional files just enhance the results — they're never blocking

**Info dialog redesign — "Your Schwab Files" guide:**

The current info dialog is vague. The new dialog should create a clear mental model: "here's exactly what you'll download, and here's what you'll end up with."

Structure:

```
┌─────────────────────────────────────────────────────────────┐
│  Your Schwab Files                                          │
│                                                             │
│  You'll download up to 3 files from Schwab. Here's where   │
│  to find each one and what it contains.                     │
│                                                             │
│  ── File 1: Realized Gain/Loss (REQUIRED) ──────────────── │
│                                                             │
│  This is your main transaction data — every lot you sold.   │
│                                                             │
│  Where to get it:                                           │
│  1. Log in to schwab.com                                    │
│  2. Go to Accounts → Equity Award Center                   │
│  3. Click "Realized Gain/Loss" in the left sidebar          │
│  4. Set the date range to cover your tax year               │
│  5. Click "Export" (top right) → CSV                        │
│                                                             │
│  What you'll get:                                           │
│  A CSV file with one row per lot sold — symbol, dates,      │
│  proceeds, cost basis, and gain/loss in USD.                │
│                                                             │
│  ── File 2: Lapse History (RECOMMENDED) ────────────────── │
│                                                             │
│  This gives us the vest date and fair market value per      │
│  share — so we can convert your cost basis at the correct   │
│  EUR exchange rate (which is often different from the sell   │
│  date rate).                                                │
│                                                             │
│  Where to get it:                                           │
│  1. In Equity Award Center, go to your transaction history  │
│  2. Filter by transaction type: "Lapse"                     │
│  3. Set date range to cover your tax year                   │
│  4. Click "Export" → CSV                                    │
│                                                             │
│  What you'll get:                                           │
│  A CSV with one entry per vesting event — vest date,        │
│  shares vested/withheld/delivered, FMV per share, and the   │
│  sell-to-cover sale price.                                  │
│                                                             │
│  ── File 3: 1042-S Tax Form (OPTIONAL) ─────────────────── │
│                                                             │
│  If you want to claim a foreign tax credit on your German   │
│  return (Anlage AUS), this form has the US tax withheld.    │
│                                                             │
│  Where to get it:                                           │
│  1. On schwab.com, go to Accounts → Statements             │
│  2. Click "Tax Forms" tab                                   │
│  3. Find your 1042-S for the relevant tax year              │
│  4. Download PDF                                            │
│                                                             │
│  What you'll get:                                           │
│  A PDF showing gross RSU income, withholding rate, and      │
│  total US federal tax withheld.                             │
│                                                             │
│  ── Summary: Your file checklist ───────────────────────── │
│                                                             │
│  After following these steps you should have:               │
│                                                             │
│  ✓ realized-gain-loss.csv ............ REQUIRED             │
│  ✓ lapse-history.csv ................. RECOMMENDED          │
│  ○ 1042-S.pdf ........................ OPTIONAL             │
│                                                             │
│  Upload them above and click Calculate.                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Backend Changes

### 5a. New Parser: Lapse History CSV (`lapse_parser.py`)

Parse Schwab EAC transaction history filtered to "Lapse" events.

**Two-row structure:** Each lapse event spans two CSV rows:
- Row 1: `Date`, `Action`, `Symbol`, `Description`, `Quantity` (lapse-level)
- Row 2: `AwardDate`, `AwardId`, `FairMarketValuePrice`, `SalePrice`, `SharesSoldWithheldForTaxes`, `NetSharesDeposited`, `Taxes` (award-level)

**Output model** — new `LapseEvent`:
```python
class LapseEvent(BaseModel):
    symbol: str
    lapse_date: str                    # YYYY-MM-DD — the vest/lapse date
    total_shares: float                # from row 1 Quantity
    award_date: str | None = None      # YYYY-MM-DD — original grant date
    award_id: str | None = None
    fmv_per_share_usd: float           # FairMarketValuePrice — acquisition cost
    sale_price_usd: float              # SalePrice — sell-to-cover price
    shares_sold_for_taxes: float       # SharesSoldWithheldForTaxes
    shares_delivered: float            # NetSharesDeposited
    taxes_usd: float                   # Taxes — US tax withheld
```

### 5b. New Parser: 1042-S PDF (`tax_form_parser.py`)

Extract key fields from the 1042-S PDF.

**Output model** — new `TaxFormData`:
```python
class TaxFormData(BaseModel):
    tax_year: int
    gross_income_usd: float       # Box 2: Gross income
    tax_withheld_usd: float       # Box 7: Federal tax withheld
    withholding_rate: float       # Box 3b: Tax rate (e.g., 0.30)
    income_code: str | None = None  # Box 1: Income code
    recipient_country: str | None = None
```

**Implementation note:** PDF parsing can use `pypdf` (already a dependency). If parsing is unreliable, fall back to manual entry fields for the 3 key numbers.

### 5c. Data Enrichment Pipeline

Modify `calculator.py` to merge data sources:

```
Realized Gain/Loss (required)
        │
        ├── + Lapse History (if provided)
        │     → Fill in missing acquisition dates (lapse_date = vest date)
        │     → Cross-verify cost basis: FMV_per_share × shares = cost_basis_usd
        │     → Record sell-to-cover price for verification
        │     → Add shares_withheld info
        │
        ├── + 1042-S (if provided)
        │     → Attach US tax withheld to summary
        │     → Calculate foreign tax credit eligibility
        │
        └── → Compute EUR gains (existing logic, unchanged)
```

**Matching logic (Lapse → Realized Gain/Loss):**
- Primary: match by `symbol` + `quantity` + `lapse_date ≈ date_acquired`
- Fallback: match by `cost_basis_usd ≈ FMV × quantity` (when acquisition date is missing in file A)
- Verification: `sale_price × shares_sold_for_taxes ≈ proceeds` in matching sell-to-cover lots
- Add verification check: "Lapse data cross-check" (pass/warn)

### 5d. Updated Route: `/upload`

Accept multiple files in the form:
```python
@app.post("/upload")
async def upload(
    file: UploadFile,                          # Required: Realized Gain/Loss CSV
    lapse_file: UploadFile | None = None,      # Optional: Lapse History CSV
    tax_form_file: UploadFile | None = None,   # Optional: 1042-S PDF
):
```

### 5e. Enhanced Models

Add to `TaxSummary`:
```python
# New fields (optional, only populated if 1042-S provided)
us_tax_withheld_usd: float | None = None
us_tax_withheld_eur: float | None = None
withholding_rate: float | None = None
gross_vesting_income_usd: float | None = None
```

Add to `ComputedTransaction`:
```python
# New fields (optional, only populated if lapse data provided)
fmv_per_share_usd: float | None = None
shares_withheld: float | None = None
lapse_data_matched: bool = False
```

### 5f. New Verification Checks

Add to the existing checks:
- **Lapse Data Cross-Check**: If lapse file provided, verify cost basis matches FMV × quantity (within tolerance)
- **Acquisition Date Enrichment**: Report how many transactions had missing dates filled in from lapse data
- **1042-S Consistency**: If 1042-S provided, check that gross income ≈ sum of cost bases for the same tax year

---

## 6. Export Enhancements

### CSV Export
- Add columns: `FMV/Share (USD)`, `Shares Withheld`, `Lapse Matched`
- Add US tax withheld row in summary section (if available)

### PDF Export
- Add "US Tax Withholding" section if 1042-S data present:
  - Gross vesting income, withholding rate, tax withheld (USD + EUR)
  - Note about Anlage AUS foreign tax credit

### Markdown Export
- Add corresponding sections
- Add "Data Sources Used" section listing which files were imported

---

## 7. Anonymization Tool

A CLI tool that takes real Schwab files and produces randomized versions safe for use as test data, demo data, or sharing with AI assistants.

### Supported file types:
- Realized Gain/Loss CSV ✅ (implemented)
- Lapse History CSV — needs new anonymizer for two-row structure
- 1042-S PDF ✅ (implemented)

### What it anonymizes:

| Field | Strategy |
|-------|----------|
| Symbol / Company name | Replace with fake ticker + name |
| Account numbers | Strip or replace with `...XXX` |
| Quantities | Multiply by random factor (0.5–2.0), round to whole shares |
| Prices / Proceeds / Cost basis | Shift by random ±5–15%, keep internal consistency |
| Dates | Shift all dates by same random offset (±30–90 days) |
| Gain/Loss / Taxes | Recompute from randomized values |
| Names / Addresses (in 1042-S) | Replace with placeholder text |
| Award IDs | Randomize |
| Foreign tax IDs / TINs / GIINs | Randomize (preserving format) |

---

## 8. Implementation Order

| Phase | Scope | Status |
|-------|-------|--------|
| **Phase 0** | Anonymization tool | ✅ Done (CSV + PDF anonymizers) |
| **Phase 0b** | Add Lapse CSV anonymizer (two-row structure) | Pending |
| **Phase 1** | Frontend: multi-file upload UX + updated info dialog | Pending |
| **Phase 2** | Lapse history parser + `LapseEvent` model | Pending |
| **Phase 3** | Data enrichment: merge lapse data into calculation pipeline | Pending |
| **Phase 4** | 1042-S PDF parsing + tax withholding integration | Pending |
| **Phase 5** | Updated verification checks | Pending |
| **Phase 6** | Export enhancements (CSV, PDF, Markdown) | Pending |
| **Phase 7** | Tests for all new parsers and enrichment logic | Pending |

---

## 9. Open Questions / Decisions Needed

1. **Lapse CSV quirks**: The two-row-per-event structure is unusual. Need to confirm whether multiple award IDs can appear under a single lapse date (the sample data suggests yes — e.g., 03/15/2026 has 3 lapse events for different awards).

2. **1042-S parsing reliability**: PDF parsing of tax forms can be fragile. Should we:
   - (a) Attempt automatic PDF parsing with fallback to manual entry, or
   - (b) Just provide 3 manual input fields (gross income, tax withheld, rate)?

3. **Matching edge cases**: What if a sell-to-cover in file A doesn't exactly match a lapse event in file B (due to rounding, partial lots, etc.)? Need tolerance strategy.

### Decisions already made

- **1099-B**: Excluded entirely. German tax residents never receive this.
- **Individual Account Trade History**: Excluded — redundant with Realized Gain/Loss.
- **Anonymization tool**: Phase 0 — built first to unblock test data.
- **Info dialog**: Full rewrite with per-file download instructions and file checklist.
