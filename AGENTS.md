# Agent guidance

## Repository overview

This is a Python web application (`src/rsu_tax/`) built with FastAPI. It parses Schwab brokerage CSV exports and computes EUR capital gains for German tax reporting. Tests live in `tests/` and use pytest.

## Commands

```bash
# Install dependencies (including dev)
uv sync --extra dev

# Run the application
uv run rsu-tax

# Run tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run a single test file
uv run pytest tests/test_calculator.py
```

## Code layout

| Path | Purpose |
|------|---------|
| `src/rsu_tax/app.py` | FastAPI routes — upload, filter, download |
| `src/rsu_tax/calculator.py` | EUR conversion and sell-to-cover detection |
| `src/rsu_tax/csv_parser.py` | Schwab CSV parsing with column auto-detection |
| `src/rsu_tax/exchange_rates.py` | Frankfurter API (ECB) rate fetching |
| `src/rsu_tax/export.py` | CSV and PDF export (fpdf2) |
| `src/rsu_tax/models.py` | Pydantic data models |
| `src/rsu_tax/verification.py` | 7 data integrity checks |
| `src/rsu_tax/templates/` | Jinja2 HTML templates |
| `tests/` | pytest tests mirroring the module structure |
| `test-data/` | Sample Schwab CSV for manual/integration testing |

## Key design decisions

- **Single-user local app**: session state is held in an in-memory dict keyed by a cookie token. No database.
- **Sell-to-cover detection**: heuristic — same acquisition and sale date, gain/loss ≤ $1.
- **Exchange rate fallback**: if no rate exists for a date (weekend/holiday), the lookup walks back up to 7 days.
- **EUR conversion**: proceeds converted at sale-date rate; cost basis converted at acquisition-date rate.

## Testing notes

- Tests use `pytest-asyncio` with `asyncio_mode = "auto"` (configured in `pyproject.toml`).
- Exchange rate tests mock HTTP responses via `httpx` transport overrides.
- The sample CSV in `test-data/` is used in several parser tests.

## What to avoid

- Do not add Node.js, TypeScript, or frontend build tooling — this project is Python-only.
- Do not introduce a database; the in-memory session store is intentional for a local tool.
- Do not expose the app on a public interface; it is designed for `127.0.0.1` only.
