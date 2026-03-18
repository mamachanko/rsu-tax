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
| **E** | **1099-B** (US residents) | Statements → Tax Forms | PDF | Lot-level: proceeds, cost basis, gain/loss, wash sale adjustments — similar to Realized Gain/Loss but official IRS form |

### Classification: Required vs Optional

| File | Required? | Why |
|------|-----------|-----|
| **A — Realized Gain/Loss CSV** | **Required** | Core data for EUR capital gains calculation. Already supported. |
| **B — Vesting History** | **Recommended** | Fills in missing acquisition dates and provides authoritative FMV (cost basis) per share. Improves accuracy. |
| **C — Sale History** | **Optional** | Cross-verification of sale prices and proceeds. Redundant with file A but useful for sanity checks. |
| **D — 1042-S** | **Optional (beneficial)** | Enables reporting US tax withheld for foreign tax credit claims on the German return. Currently not captured at all. |
| **E — 1099-B** | **Optional** | Largely redundant with file A. Could serve as a verification source. Low priority. |

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

**Info dialog update:**
- Rewrite the "How do I get this data?" overlay to match the new multi-file structure
- Each step maps directly to a file upload section
- Add specific download instructions for each file type

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

## 6. Implementation Order

| Phase | Scope | Effort |
|-------|-------|--------|
| **Phase 1** | Frontend: multi-file upload UX + updated info dialog | Medium |
| **Phase 2** | Vesting history parser + data enrichment + matching | Medium |
| **Phase 3** | Backend: merge vesting data into calculation pipeline | Medium |
| **Phase 4** | 1042-S PDF parsing + tax withholding integration | Medium |
| **Phase 5** | Updated verification checks (#8-#10) | Small |
| **Phase 6** | Export enhancements (CSV, PDF, Markdown) | Small |
| **Phase 7** | Tests for all new parsers and enrichment logic | Medium |

### Phase 1 — Frontend (start here)
- Redesign `index.html` with multi-section upload
- Update info overlay with per-file instructions
- Modify form to send multiple files via HTMX
- Update `app.py` route to accept optional files (pass-through initially)

### Phase 2 — Vesting Parser
- Create `vesting_parser.py` with column auto-detection
- Add `VestingEvent` model
- Write tests with sample vesting CSV

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

1. **Vesting History format**: Schwab's EAC transaction export format needs to be confirmed. The user may need to provide a sample file, or we design the parser flexibly with column auto-detection (like the existing CSV parser).

2. **1042-S parsing reliability**: PDF parsing of tax forms can be fragile. Should we:
   - (a) Attempt automatic PDF parsing with fallback to manual entry, or
   - (b) Just provide 3 manual input fields (gross income, tax withheld, rate)?

3. **Sale History (File C)**: Should we include this in v1 or defer? It's mostly redundant with the Realized Gain/Loss data. Recommendation: defer to keep scope manageable.

4. **1099-B**: Same question — defer? Recommendation: defer.
