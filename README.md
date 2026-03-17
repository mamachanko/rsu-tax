# RSU Tax Calculator

A local web application for calculating capital gains from RSU (Restricted Stock Unit) sales for German tax reporting (*Abgeltungssteuer*).

Upload a Schwab "Realized Gain/Loss" CSV export and the app will:

- Convert USD amounts to EUR using official ECB exchange rates (via [Frankfurter API](https://www.frankfurter.app/))
- Separate voluntary sales from sell-to-cover (tax withholding) transactions
- Run verification checks on the computed data
- Export results as a CSV or PDF for your tax filing

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

```bash
git clone https://github.com/mamachanko/rsu-tax.git
cd rsu-tax
uv sync
```

## Usage

```bash
uv run rsu-tax
```

This starts the server at `http://127.0.0.1:8765` and opens the app in your browser. Press `Ctrl+C` to stop.

### What to upload

Export a **Realized Gain/Loss** report from the Schwab website as a CSV file. The app auto-detects column headers and handles common variations in the Schwab export format.

### Tax year filtering

After uploading, use the year selector to filter transactions by tax year. The summary and verification checks update accordingly.

### Exports

- **CSV**: Full transaction detail table with EUR conversions
- **PDF**: Formatted report with summary, verification results, and transaction table (landscape A4)

## Development

Install with dev dependencies:

```bash
uv sync --extra dev
```

Run tests:

```bash
uv run pytest
```

## Project structure

```
src/rsu_tax/        Python package (FastAPI app)
  app.py            Route handlers
  calculator.py     EUR conversion and gain computation
  csv_parser.py     Schwab CSV parsing with auto-detection
  exchange_rates.py ECB exchange rate fetching (Frankfurter API)
  export.py         CSV and PDF export
  models.py         Pydantic data models
  verification.py   Data integrity checks
  templates/        Jinja2 HTML templates
tests/              pytest test suite
test-data/          Sample Schwab CSV for manual testing
```

## How it works

1. **CSV parsing** — Reads Schwab Realized Gain/Loss exports, detects column layout, parses dates and currency values, infers short/long term from gain/loss columns when not explicit.

2. **Exchange rates** — Fetches EUR/USD rates from the Frankfurter API (ECB data) for all relevant dates. Falls back up to 7 days for weekends and holidays.

3. **Gain computation** — Converts proceeds at the sale-date rate and cost basis at the acquisition-date rate. Detects sell-to-cover transactions (same acquisition and sale date with near-zero gain/loss).

4. **Verification** — Runs 7 checks: USD gain consistency, EUR gain consistency, exchange rate sanity, EUR sum, date ordering, rate coverage, and USD totals cross-check.

5. **Export** — Generates a CSV or PDF report suitable for attaching to your German tax return.

## License

MIT
