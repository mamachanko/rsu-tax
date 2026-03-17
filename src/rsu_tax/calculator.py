"""Compute EUR capital gains and tax summary from Schwab transactions."""

from __future__ import annotations

from .exchange_rates import find_rate_with_date
from .models import ComputedTransaction, SchwabTransaction, TaxSummary

_SELL_TO_COVER_TOLERANCE_USD = 1.0


def _is_sell_to_cover(t: SchwabTransaction) -> bool:
    near_zero = abs(t.gain_loss_usd) <= _SELL_TO_COVER_TOLERANCE_USD
    if t.date_acquired == t.date_sold and near_zero:
        return True
    # Secondary signal: no acquisition date + Specific Lots + near-zero gain
    if (
        not t.has_acquisition_date
        and t.cost_basis_method == "Specific Lots"
        and near_zero
    ):
        return True
    return False


def _round_cents(n: float) -> float:
    return round(n, 2)


def compute_capital_gains(
    transactions: list[SchwabTransaction],
    rates: dict[str, float],
) -> list[ComputedTransaction]:
    """
    Convert all transactions to EUR using ECB rates:
    - proceeds at the sale-date rate
    - cost basis at the acquisition-date rate (falls back to sale date when unavailable)
    """
    computed: list[ComputedTransaction] = []

    for t in transactions:
        result_sold = find_rate_with_date(t.date_sold, rates)
        result_acquired = find_rate_with_date(t.date_acquired, rates)
        notes: list[str] = []
        status = "pass"

        if result_sold is None:
            notes.append(f"No exchange rate found for sale date {t.date_sold}")
            status = "fail"
        if result_acquired is None:
            notes.append(f"No exchange rate found for acquisition date {t.date_acquired}")
            status = "fail"

        if not t.has_acquisition_date:
            notes.append(
                "Using sale-date exchange rate for cost basis "
                "(acquisition date not available in CSV)"
            )
            if status == "pass":
                status = "warn"

        r_sold, eff_sold = result_sold if result_sold else (0.0, t.date_sold)
        r_acq, eff_acq = result_acquired if result_acquired else (0.0, t.date_acquired)

        proceeds_eur = _round_cents(t.proceeds_usd * r_sold)
        cost_basis_eur = _round_cents(t.cost_basis_usd * r_acq)
        gain_loss_eur = _round_cents(proceeds_eur - cost_basis_eur)

        # USD consistency check
        expected_usd = _round_cents(t.proceeds_usd - t.cost_basis_usd)
        if abs(expected_usd - t.gain_loss_usd) > 0.02:
            notes.append(
                f"USD gain/loss mismatch: expected {expected_usd:.2f}, "
                f"got {t.gain_loss_usd:.2f}"
            )
            if status == "pass":
                status = "warn"

        computed.append(
            ComputedTransaction(
                **t.model_dump(),
                exchange_rate_sold=r_sold,
                exchange_rate_acquired=r_acq,
                effective_date_sold=eff_sold,
                effective_date_acquired=eff_acq,
                proceeds_eur=proceeds_eur,
                cost_basis_eur=cost_basis_eur,
                gain_loss_eur=gain_loss_eur,
                is_sell_to_cover=_is_sell_to_cover(t),
                verification_status=status,
                verification_notes=notes,
            )
        )

    return computed


def compute_summary(
    transactions: list[ComputedTransaction],
    tax_year: int | None = None,
) -> TaxSummary:
    filtered = (
        [t for t in transactions if t.date_sold.startswith(str(tax_year))]
        if tax_year is not None
        else transactions
    )

    voluntary = [t for t in filtered if not t.is_sell_to_cover]
    sell_to_cover = [t for t in filtered if t.is_sell_to_cover]

    inferred_year = (
        tax_year
        or (int(filtered[0].date_sold[:4]) if filtered else 0)
        or 0
    )

    return TaxSummary(
        tax_year=inferred_year,
        total_transactions=len(filtered),
        voluntary_sales=len(voluntary),
        sell_to_cover_sales=len(sell_to_cover),
        total_proceeds_eur=_round_cents(sum(t.proceeds_eur for t in filtered)),
        total_cost_basis_eur=_round_cents(sum(t.cost_basis_eur for t in filtered)),
        net_gain_loss_eur=_round_cents(sum(t.gain_loss_eur for t in filtered)),
        voluntary_gain_loss_eur=_round_cents(sum(t.gain_loss_eur for t in voluntary)),
        sell_to_cover_gain_loss_eur=_round_cents(sum(t.gain_loss_eur for t in sell_to_cover)),
        total_proceeds_usd=_round_cents(sum(t.proceeds_usd for t in filtered)),
        total_cost_basis_usd=_round_cents(sum(t.cost_basis_usd for t in filtered)),
        net_gain_loss_usd=_round_cents(sum(t.gain_loss_usd for t in filtered)),
    )
