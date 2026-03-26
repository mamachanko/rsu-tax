"""Pydantic data models for the RSU tax calculator."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class SchwabTransaction(BaseModel):
    symbol: str
    name: str | None = None
    quantity: float
    date_acquired: str          # YYYY-MM-DD; may equal date_sold when not in CSV
    date_sold: str              # YYYY-MM-DD
    proceeds_usd: float
    cost_basis_usd: float
    gain_loss_usd: float
    term: str                   # "Short Term" | "Long Term" | "Unknown"
    wash_sale: float = 0.0
    cost_basis_method: str | None = None
    has_acquisition_date: bool  # False when dateAcquired was inferred from dateSold

    @field_validator("term")
    @classmethod
    def validate_term(cls, v: str) -> str:
        allowed = {"Short Term", "Long Term", "Unknown"}
        return v if v in allowed else "Unknown"


class ComputedTransaction(SchwabTransaction):
    exchange_rate_sold: float
    exchange_rate_acquired: float
    # Actual ECB publication date for each rate (may differ from transaction date on weekends/holidays)
    effective_date_sold: str
    effective_date_acquired: str
    proceeds_eur: float
    cost_basis_eur: float
    gain_loss_eur: float
    is_sell_to_cover: bool
    verification_status: str    # "pass" | "warn" | "fail"
    verification_notes: list[str] = []


class LapseEvent(BaseModel):
    """A single RSU vest/lapse event parsed from Schwab's Lapse History CSV."""

    symbol: str
    lapse_date: str  # YYYY-MM-DD — the vest/lapse date
    total_shares: float  # from row 1 Quantity
    award_date: str | None = None  # YYYY-MM-DD — original grant date
    award_id: str | None = None
    fmv_per_share_usd: float  # FairMarketValuePrice — acquisition cost per share
    sale_price_usd: float  # SalePrice — sell-to-cover price
    shares_sold_for_taxes: float  # SharesSoldWithheldForTaxes
    shares_delivered: float  # NetSharesDeposited
    taxes_usd: float  # Taxes — US tax withheld at vest


class VerificationCheck(BaseModel):
    name: str
    status: str                 # "pass" | "warn" | "fail"
    message: str


class TaxFormData(BaseModel):
    """Parsed data from a 1042-S tax form."""

    tax_year: int
    gross_income_usd: float       # Box 2: Gross income
    tax_withheld_usd: float       # Box 7: Federal tax withheld
    withholding_rate: float       # Box 3b: Tax rate (e.g., 0.30 for 30%)
    income_code: str | None = None  # Box 1: Income code
    recipient_country: str | None = None


class TaxSummary(BaseModel):
    tax_year: int
    total_transactions: int
    voluntary_sales: int
    sell_to_cover_sales: int
    total_proceeds_eur: float
    total_cost_basis_eur: float
    net_gain_loss_eur: float
    voluntary_gain_loss_eur: float
    sell_to_cover_gain_loss_eur: float
    total_proceeds_usd: float
    total_cost_basis_usd: float
    net_gain_loss_usd: float
    # Optional: populated when 1042-S is provided
    us_tax_withheld_usd: float | None = None
    us_tax_withheld_eur: float | None = None
    withholding_rate: float | None = None
    gross_vesting_income_usd: float | None = None


class ParseWarning(BaseModel):
    message: str
