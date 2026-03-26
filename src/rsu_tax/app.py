"""FastAPI application — serves the RSU tax calculator UI."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .calculator import compute_capital_gains, compute_summary
from .csv_parser import parse_schwab_csv
from .enrichment import enrich_transactions
from .exchange_rates import rates_for_dates
from .export import export_csv, export_markdown, export_pdf
from .lapse_parser import parse_lapse_csv
from .models import ComputedTransaction, TaxSummary, VerificationCheck
from .verification import run_verification

app = FastAPI(title="RSU Tax Calculator", docs_url=None, redoc_url=None)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# In-memory session store for a single local user (keyed by session token)
_sessions: dict[str, dict] = {}


def _get_session(token: str) -> dict:
    return _sessions.setdefault(token, {})


# ── Jinja2 filters ──────────────────────────────────────────────────────────

def _fmt_eur(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.2f} €"


def _fmt_usd(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f} $"


def _gain_class(value: float) -> str:
    if value > 0:
        return "gain"
    if value < 0:
        return "loss"
    return "neutral"


templates.env.filters["fmt_eur"] = _fmt_eur
templates.env.filters["fmt_usd"] = _fmt_usd
templates.env.filters["gain_class"] = _gain_class


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    token = request.cookies.get("session", str(uuid.uuid4()))
    response = templates.TemplateResponse(
        "index.html",
        {"request": request, "token": token},
    )
    response.set_cookie("session", token, httponly=True, samesite="lax")
    return response


async def _decode_upload(upload: UploadFile) -> str:
    """Read and decode an uploaded file as text."""
    content = await upload.read()
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


@app.post("/upload", response_class=HTMLResponse)
async def upload(
    request: Request,
    file: Annotated[UploadFile, File()],
    lapse_file: Annotated[UploadFile | None, File()] = None,
) -> HTMLResponse:
    token = request.cookies.get("session", str(uuid.uuid4()))
    session = _get_session(token)

    csv_text = await _decode_upload(file)
    parse_result = parse_schwab_csv(csv_text)
    all_warnings = list(parse_result.warnings)

    if not parse_result.transactions:
        return templates.TemplateResponse(
            "partials/error.html",
            {
                "request": request,
                "message": "No transactions found in the uploaded file.",
                "warnings": all_warnings,
            },
            status_code=422,
        )

    transactions = parse_result.transactions
    enrichment = None

    # Enrich with lapse data if provided
    if lapse_file is not None and lapse_file.filename:
        lapse_text = await _decode_upload(lapse_file)
        lapse_result = parse_lapse_csv(lapse_text)
        all_warnings.extend(lapse_result.warnings)

        if lapse_result.events:
            enrichment = enrich_transactions(transactions, lapse_result.events)
            transactions = enrichment.transactions
            all_warnings.extend(enrichment.warnings)

    # Collect all dates needed for exchange rates
    all_dates = list({
        d
        for t in transactions
        for d in (t.date_sold, t.date_acquired)
        if d
    })

    try:
        rates = await rates_for_dates(all_dates)
    except Exception as exc:
        return templates.TemplateResponse(
            "partials/error.html",
            {
                "request": request,
                "message": f"Failed to fetch exchange rates: {exc}",
                "warnings": [],
            },
            status_code=502,
        )

    computed = compute_capital_gains(transactions, rates)
    summary = compute_summary(computed)
    checks = run_verification(computed, enrichment=enrichment)

    # Group transactions by tax year for the year selector
    years = sorted({int(t.date_sold[:4]) for t in computed}, reverse=True)

    session["computed"] = computed
    session["summary"] = summary
    session["checks"] = checks
    session["rates"] = rates
    session["warnings"] = all_warnings

    response = templates.TemplateResponse(
        "partials/results.html",
        {
            "request": request,
            "computed": computed,
            "summary": summary,
            "checks": checks,
            "warnings": all_warnings,
            "years": years,
            "selected_year": summary.tax_year,
        },
    )
    response.set_cookie("session", token, httponly=True, samesite="lax")
    return response


@app.post("/filter", response_class=HTMLResponse)
async def filter_year(
    request: Request,
    year: Annotated[int | None, Form()] = None,
) -> HTMLResponse:
    token = request.cookies.get("session", "")
    session = _sessions.get(token, {})
    computed: list[ComputedTransaction] = session.get("computed", [])
    rates: dict[str, float] = session.get("rates", {})
    all_warnings: list[str] = session.get("warnings", [])

    if not computed:
        raise HTTPException(status_code=404, detail="No session data. Please upload a file first.")

    filtered = (
        [t for t in computed if int(t.date_sold[:4]) == year]
        if year is not None
        else computed
    )
    summary = compute_summary(filtered, tax_year=year)
    checks = run_verification(filtered)
    years = sorted({int(t.date_sold[:4]) for t in computed}, reverse=True)

    return templates.TemplateResponse(
        "partials/results.html",
        {
            "request": request,
            "computed": filtered,
            "summary": summary,
            "checks": checks,
            "warnings": all_warnings,
            "years": years,
            "selected_year": year or summary.tax_year,
        },
    )


@app.get("/download/csv")
async def download_csv(request: Request) -> Response:
    token = request.cookies.get("session", "")
    session = _sessions.get(token, {})
    computed: list[ComputedTransaction] = session.get("computed", [])

    if not computed:
        raise HTTPException(status_code=404, detail="No data. Please upload a file first.")

    csv_content = export_csv(computed)
    year = computed[0].date_sold[:4] if computed else "unknown"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="rsu-gains-{year}.csv"'},
    )


@app.get("/download/markdown")
async def download_markdown(request: Request) -> Response:
    token = request.cookies.get("session", "")
    session = _sessions.get(token, {})
    computed: list[ComputedTransaction] = session.get("computed", [])
    summary: TaxSummary | None = session.get("summary")
    checks: list[VerificationCheck] = session.get("checks", [])

    if not computed or summary is None:
        raise HTTPException(status_code=404, detail="No data. Please upload a file first.")

    md_content = export_markdown(computed, summary, checks)
    year = computed[0].date_sold[:4] if computed else "unknown"
    return Response(
        content=md_content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="rsu-gains-{year}.md"'},
    )


@app.get("/download/pdf")
async def download_pdf(request: Request) -> Response:
    token = request.cookies.get("session", "")
    session = _sessions.get(token, {})
    computed: list[ComputedTransaction] = session.get("computed", [])
    summary: TaxSummary | None = session.get("summary")
    checks: list[VerificationCheck] = session.get("checks", [])

    if not computed or summary is None:
        raise HTTPException(status_code=404, detail="No data. Please upload a file first.")

    pdf_bytes = export_pdf(computed, summary, checks)
    year = computed[0].date_sold[:4] if computed else "unknown"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="rsu-gains-{year}.pdf"'},
    )
