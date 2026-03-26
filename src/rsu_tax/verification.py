"""Data quality verification checks."""

from __future__ import annotations

from .enrichment import EnrichmentResult
from .models import ComputedTransaction, VerificationCheck

_RATE_MIN = 0.60
_RATE_MAX = 1.15


def run_verification(
    transactions: list[ComputedTransaction],
    enrichment: EnrichmentResult | None = None,
) -> list[VerificationCheck]:
    """Run verification checks and return a list of results."""
    if not transactions:
        return []

    checks: list[VerificationCheck] = []

    # 1. USD gain/loss consistency
    mismatches = [
        t for t in transactions
        if abs(round(t.proceeds_usd - t.cost_basis_usd, 2) - t.gain_loss_usd) > 0.02
    ]
    if mismatches:
        checks.append(VerificationCheck(
            name="USD Gain/Loss Consistency",
            status="warn",
            message=f"{len(mismatches)} transaction(s) have proceeds − cost ≠ gain/loss in USD.",
        ))
    else:
        checks.append(VerificationCheck(
            name="USD Gain/Loss Consistency",
            status="pass",
            message="All USD gain/loss values match proceeds − cost basis.",
        ))

    # 2. Exchange rate sanity
    bad_rates = [
        t for t in transactions
        if t.exchange_rate_sold != 0
        and not (_RATE_MIN <= t.exchange_rate_sold <= _RATE_MAX)
    ]
    if bad_rates:
        checks.append(VerificationCheck(
            name="Exchange Rate Sanity",
            status="warn",
            message=(
                f"{len(bad_rates)} transaction(s) have sale-date exchange rates "
                f"outside the expected range {_RATE_MIN}–{_RATE_MAX} EUR/USD."
            ),
        ))
    else:
        checks.append(VerificationCheck(
            name="Exchange Rate Sanity",
            status="pass",
            message=f"All exchange rates are within {_RATE_MIN}–{_RATE_MAX} EUR/USD.",
        ))

    # 3. EUR gain/loss consistency
    eur_mismatches = [
        t for t in transactions
        if abs(round(t.proceeds_eur - t.cost_basis_eur, 2) - t.gain_loss_eur) > 0.02
    ]
    if eur_mismatches:
        checks.append(VerificationCheck(
            name="EUR Gain/Loss Consistency",
            status="warn",
            message=f"{len(eur_mismatches)} transaction(s) have EUR proceeds − cost ≠ gain/loss.",
        ))
    else:
        checks.append(VerificationCheck(
            name="EUR Gain/Loss Consistency",
            status="pass",
            message="All EUR gain/loss values match proceeds − cost basis.",
        ))

    # 4. Sum verification
    sum_gains = round(sum(t.gain_loss_eur for t in transactions), 2)
    sum_proceeds = round(sum(t.proceeds_eur for t in transactions), 2)
    sum_cost = round(sum(t.cost_basis_eur for t in transactions), 2)
    expected_total = round(sum_proceeds - sum_cost, 2)
    if abs(sum_gains - expected_total) > 0.05:
        checks.append(VerificationCheck(
            name="EUR Sum Verification",
            status="warn",
            message=(
                f"Sum of individual gains ({sum_gains:.2f} €) differs from "
                f"total proceeds − cost ({expected_total:.2f} €)."
            ),
        ))
    else:
        checks.append(VerificationCheck(
            name="EUR Sum Verification",
            status="pass",
            message=f"Individual EUR gains sum correctly to {sum_gains:.2f} €.",
        ))

    # 5. Date ordering (acquired ≤ sold)
    date_violations = [
        t for t in transactions
        if t.has_acquisition_date and t.date_acquired > t.date_sold
    ]
    if date_violations:
        checks.append(VerificationCheck(
            name="Date Ordering",
            status="warn",
            message=f"{len(date_violations)} transaction(s) have acquisition date after sale date.",
        ))
    else:
        checks.append(VerificationCheck(
            name="Date Ordering",
            status="pass",
            message="All transactions have acquisition date ≤ sale date.",
        ))

    # 6. Exchange rate coverage
    missing_rates = [t for t in transactions if t.exchange_rate_sold == 0]
    if missing_rates:
        checks.append(VerificationCheck(
            name="Exchange Rate Coverage",
            status="fail",
            message=f"{len(missing_rates)} transaction(s) are missing exchange rates.",
        ))
    else:
        checks.append(VerificationCheck(
            name="Exchange Rate Coverage",
            status="pass",
            message="Exchange rates available for all sale dates.",
        ))

    # 7. USD totals cross-check
    usd_sum = round(sum(t.gain_loss_usd for t in transactions), 2)
    usd_expected = round(sum(t.proceeds_usd - t.cost_basis_usd for t in transactions), 2)
    if abs(usd_sum - usd_expected) > 0.05:
        checks.append(VerificationCheck(
            name="USD Total Cross-Check",
            status="warn",
            message=(
                f"Sum of USD gains ({usd_sum:.2f} $) differs from "
                f"sum of proceeds − cost ({usd_expected:.2f} $)."
            ),
        ))
    else:
        checks.append(VerificationCheck(
            name="USD Total Cross-Check",
            status="pass",
            message=f"USD totals cross-check passed ({usd_sum:.2f} $).",
        ))

    # 8. Lapse data enrichment (only when lapse file was provided)
    if enrichment is not None:
        total_enrichable = enrichment.matched + enrichment.unmatched
        if enrichment.matched > 0 and enrichment.unmatched == 0:
            checks.append(VerificationCheck(
                name="Lapse Data Enrichment",
                status="pass",
                message=(
                    f"All {enrichment.matched} transaction(s) matched to lapse events. "
                    f"Vest dates used for cost basis EUR conversion."
                ),
            ))
        elif enrichment.matched > 0 and enrichment.unmatched > 0:
            checks.append(VerificationCheck(
                name="Lapse Data Enrichment",
                status="warn",
                message=(
                    f"{enrichment.matched} of {total_enrichable} transaction(s) matched "
                    f"to lapse events. {enrichment.unmatched} still missing acquisition dates."
                ),
            ))
        else:
            checks.append(VerificationCheck(
                name="Lapse Data Enrichment",
                status="warn",
                message=(
                    f"Lapse file provided but no transactions could be matched. "
                    f"Check that symbols match between files."
                ),
            ))

    return checks
