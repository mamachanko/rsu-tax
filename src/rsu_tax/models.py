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


class VerificationCheck(BaseModel):
    name: str
    status: str                 # "pass" | "warn" | "fail"
    message: str


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


class ParseWarning(BaseModel):
    message: str
