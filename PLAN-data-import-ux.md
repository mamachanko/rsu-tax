# Plan: Multi-File Data Import UX Redesign

## Context

Currently the app accepts a **single file**: the Schwab "Realized Gain/Loss" CSV. The info dialog tells users to also look up vesting data, sale details, and tax forms — but none of that can be imported. This plan redesigns the app to accept all the data a user would actually download from Schwab, enriching calculations and the final tax report.

---

## 1. What Files Does Schwab Provide?

When a user follows all the steps in the current info dialog, they end up with:

| # | File / Data | Source in Schwab | Format | What's in it |
|---|-------------|------------------|--------|-------------|
| **A** | **Realized Gain/Loss** | EAC → Realized Gain/Loss → Export | CSV | Per-lot: symbol, sale date, acquisition date (sometimes missing), proceeds, cost basis, gain/loss, term, wash sale, cost basis method |
| **B** | **Transaction History (Vesting Events)** | EAC → History → Transactions → filter "Vest" → Export | CSV / JSON / screen scrape | Per-vest: vest date, shares vested, shares delivered (after withholding), FMV per share on vest date, share withholding count |
| **C** | **Transaction History (Sales)** | EAC → History → Transactions → filter "Sale" → Export | CSV / JSON / screen scrape | Per-sale: sale date, shares sold, gross sale price per share, net proceeds |
| **D** | **1042-S** (non-US residents) | Statements → Tax Forms | PDF | US-source income from RSU vesting, US tax withheld (rate, amount), treaty info |

> **Note:** The 1099-B is a US-resident-only form. As German tax residents, we will never receive one. It is excluded from this plan entirely.

### Classification: Required vs Optional

| File | Required? | Why |
|------|-----------|-----|
| **A — Realized Gain/Loss CSV** | **Required** | Core data for EUR capital gains calculation. Already supported. |
| **B — Vesting History** | **Recommended** | Fills in missing acquisition dates and provides authoritative FMV (cost basis) per share. Improves accuracy. |
| **C — Sale History** | **Optional (defer)** | Cross-verification of sale prices and proceeds. Redundant with file A. Deferred from v1. |
| **D — 1042-S** | **Optional (beneficial)** | Enables reporting US tax withheld for foreign tax credit claims on the German return (Anlage AUS). |

---

## 2. What New Data Would We Gain?

### From Vesting History (File B):
- **Authoritative vest date** → currently often missing from Realized Gain/Loss
- **FMV per share on vest date** → the true cost basis per share (can cross-check file A)
- **Shares withheld for taxes** → enables calculating the share withholding ratio
- **Total shares vested vs delivered** → full picture of the RSU event

### From 1042-S (File D):
- **US tax withheld amount** (USD)
- **Withholding rate** (typically 30% or treaty-reduced 15%)
- **Gross income from RSU vesting** (USD)
- Enables: foreign tax credit calculation for German Anlage AUS

### From Sale History (File C):
- **Per-share sale price** → cross-verify with Realized Gain/Loss proceeds
- **Net vs gross proceeds** → detect commission/fee deductions

---

## 3. Frontend UX Redesign

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
│  │ 2. Vesting History                RECOMMENDED │  │
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

The current info dialog is vague ("look up vesting data"). The new dialog should create a clear mental model: "here's exactly what you'll download, and here's what you'll end up with."

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
│  ── File 2: Vesting History (RECOMMENDED) ──────────────── │
│                                                             │
│  This gives us authoritative vest dates and the fair market │
│  value per share — improving accuracy of your EUR cost      │
│  basis calculation.                                         │
│                                                             │
│  Where to get it:                                           │
│  1. In Equity Award Center, click "History"                 │
│  2. Go to "Transactions" tab                                │
│  3. Filter by event type: "Vest"                            │
│  4. Set date range to cover your tax year                   │
│  5. Click "Export" → CSV                                    │
│                                                             │
│  What you'll get:                                           │
│  A CSV with one row per vesting event — vest date, shares   │
│  vested, shares delivered, shares withheld, FMV per share.  │
│                                                             │
│  ── File 3: 1042-S Tax Form (OPTIONAL) ────────────────── │
│                                                             │
│  If you want to claim a foreign tax credit on your German   │
│  return (Anlage AUS), this form has the US tax withheld.    │
│                                                             │
│  Where to get it:                                           │
│  1. Go to Accounts → Statements                            │
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
│  ✓ vesting-history.csv ............... RECOMMENDED          │
│  ○ 1042-S.pdf ........................ OPTIONAL             │
│                                                             │
│  Upload them above and click Calculate.                     │
└─────────────────────────────────────────────────────────────┘
```

**Key improvement:** The dialog ends with a concrete "file checklist" so the user knows exactly which files they should have on disk before proceeding.

---

## 4. Backend Changes

### 4a. New Parser: Vesting History CSV (`vesting_parser.py`)

Parse Schwab EAC transaction history filtered to vesting events.

**Expected columns** (with auto-detection like existing parser):
- Date, Event Type ("Vest"), Symbol
- Shares Vested, Shares Delivered, Shares Withheld
- FMV / Fair Market Value per share (USD)
- Award ID / Grant ID (optional, for matching)

**Output model** — new `VestingEvent`:
```python
class VestingEvent(BaseModel):
    symbol: str
    vest_date: str           # YYYY-MM-DD
    shares_vested: float
    shares_delivered: float
    shares_withheld: float
    fmv_per_share_usd: float  # Fair Market Value on vest date
    award_id: str | None = None
```

### 4b. New Parser: 1042-S PDF (`tax_form_parser.py`)

Extract key fields from the 1042-S PDF. This is simpler — just a few numbers:

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

**Implementation note:** PDF parsing can use `pdfplumber` or similar. If parsing is unreliable, fall back to manual entry fields for the 3 key numbers (gross income, tax withheld, rate).

### 4c. Data Enrichment Pipeline

Modify `calculator.py` to merge data sources:

```
Realized Gain/Loss (required)
        │
        ├── + Vesting History (if provided)
        │     → Fill in missing acquisition dates
        │     → Cross-verify cost basis (FMV × shares = cost_basis_usd)
        │     → Add shares_withheld info
        │
        ├── + 1042-S (if provided)
        │     → Attach US tax withheld to summary
        │     → Calculate foreign tax credit eligibility
        │
        └── → Compute EUR gains (existing logic, unchanged)
```

**Matching logic (Vesting → Realized Gain/Loss):**
- Match by symbol + acquisition date = vest date
- If acquisition date is missing in Realized G/L, match by cost_basis_usd ≈ FMV × quantity
- Add verification check: "Vesting data cross-check" (pass/warn)

### 4d. Updated Route: `/upload`

Accept multiple files in the form:
```python
@app.post("/upload")
async def upload(
    file: UploadFile,                          # Required: Realized Gain/Loss CSV
    vesting_file: UploadFile | None = None,    # Optional: Vesting History CSV
    tax_form_file: UploadFile | None = None,   # Optional: 1042-S PDF
):
```

### 4e. Enhanced Models

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
# New fields (optional, only populated if vesting data provided)
fmv_per_share_usd: float | None = None
shares_withheld: float | None = None
vesting_data_matched: bool = False
```

### 4f. New Verification Checks

Add to the existing 7 checks:
- **#8 — Vesting Data Cross-Check**: If vesting file provided, verify cost basis matches FMV × quantity (within tolerance)
- **#9 — Acquisition Date Enrichment**: Report how many transactions had missing dates filled in from vesting data
- **#10 — 1042-S Consistency**: If 1042-S provided, check that gross income ≈ sum of cost bases for the same tax year

---

## 5. Export Enhancements

### CSV Export
- Add columns: `FMV/Share (USD)`, `Shares Withheld`, `Vesting Matched`
- Add US tax withheld row in summary section (if available)

### PDF Export
- Add "US Tax Withholding" section if 1042-S data present:
  - Gross vesting income, withholding rate, tax withheld (USD + EUR)
  - Note about Anlage AUS foreign tax credit

### Markdown Export
- Add corresponding sections
- Add "Data Sources Used" section listing which files were imported

---

## 6. Anonymization / Randomization Tool

A CLI tool (or web UI button) that takes real Schwab files and produces randomized versions safe for use as test data, demo data, or sharing with AI assistants.

### What it anonymizes:

| Field | Strategy |
|-------|----------|
| Symbol / Company name | Replace with fake ticker + name (e.g., `XYZC` / `EXAMPLE CORP`) |
| Account numbers | Strip or replace with `...XXX` |
| Quantities | Multiply by random factor (0.5–2.0), round to whole shares |
| Prices / Proceeds / Cost basis | Shift by random ±5–15%, keep internal consistency (proceeds = price × qty) |
| Dates | Shift all dates by same random offset (±30–90 days) to preserve relative ordering |
| Gain/Loss | Recompute from randomized proceeds − cost basis |
| Names / Addresses (in 1042-S) | Replace with placeholder text |
| Award IDs / Grant IDs | Randomize |

### Key properties preserved:
- **Internal consistency**: gain/loss = proceeds − cost basis still holds
- **Relative date ordering**: acquisition before sale, vesting before sale
- **Realistic ranges**: prices stay in plausible stock price territory
- **File format**: output is valid CSV/PDF that the app can still parse

### Implementation:

```
src/rsu_tax/anonymize.py     — core anonymization logic
src/rsu_tax/cli.py            — CLI entry point: `rsu-tax anonymize <file> [--output <dir>]`
```

- Works on all supported file types (Realized G/L CSV, Vesting CSV, 1042-S PDF)
- Applies a random seed (optionally user-provided for reproducibility)
- Outputs anonymized files to a specified directory (default: `./anonymized/`)
- Also usable from the web UI: a small "Anonymize my files" utility page

---

## 7. Implementation Order

| Phase | Scope | Effort |
|-------|-------|--------|
| **Phase 0** | Anonymization tool (unblocks everything else — produces test data) | Medium |
| **Phase 1** | Frontend: multi-file upload UX + updated info dialog | Medium |
| **Phase 2** | Vesting history parser + data enrichment + matching | Medium |
| **Phase 3** | Backend: merge vesting data into calculation pipeline | Medium |
| **Phase 4** | 1042-S PDF parsing + tax withholding integration | Medium |
| **Phase 5** | Updated verification checks (#8-#10) | Small |
| **Phase 6** | Export enhancements (CSV, PDF, Markdown) | Small |
| **Phase 7** | Tests for all new parsers and enrichment logic | Medium |

### Phase 0 — Anonymization Tool (start here)
- Create `anonymize.py` with randomization logic for CSV files
- Add CLI entry point (`rsu-tax anonymize`)
- User runs this on their real files → produces safe test data for `test-data/`
- This unblocks all other phases by providing realistic sample files

### Phase 1 — Frontend
- Redesign `index.html` with multi-section upload
- Update info overlay with detailed per-file download instructions and file checklist
- Modify form to send multiple files via HTMX
- Update `app.py` route to accept optional files (pass-through initially)

### Phase 2 — Vesting Parser
- Create `vesting_parser.py` with column auto-detection
- Add `VestingEvent` model
- Write tests with anonymized sample vesting CSV

### Phase 3 — Data Enrichment
- Add matching logic in `calculator.py`
- Fill missing acquisition dates from vesting data
- Cross-verify cost basis
- Update `ComputedTransaction` model

### Phase 4 — 1042-S
- Add PDF parsing (or manual fallback fields)
- Create `TaxFormData` model
- Integrate into summary

### Phase 5 — Verification
- Add checks #8-#10
- Update verification UI

### Phase 6 — Exports
- Update all three export formats

### Phase 7 — Tests
- Parser tests (vesting CSV, 1042-S)
- Enrichment/matching tests
- Integration tests with multi-file upload

---

## 7. Open Questions / Decisions Needed

1. **Vesting History format**: Schwab's EAC transaction export format needs to be confirmed. The user should run the anonymization tool on a real export so we can see the actual column names. We design the parser flexibly with column auto-detection (like the existing CSV parser).

2. **1042-S parsing reliability**: PDF parsing of tax forms can be fragile. Should we:
   - (a) Attempt automatic PDF parsing with fallback to manual entry, or
   - (b) Just provide 3 manual input fields (gross income, tax withheld, rate)?

3. **Sale History (File C)**: Deferred from v1 — mostly redundant with Realized Gain/Loss data.

### Decisions already made

- **1099-B**: Excluded entirely. As German tax residents we never receive this US-only form.
- **Anonymization tool**: Phase 0 — build first to unblock test data for all other phases.
- **Info dialog**: Full rewrite with per-file download instructions and a file checklist summary.
