"""Enrich Realized Gain/Loss transactions with lapse history data.

The key enrichment: when a transaction is missing its acquisition date,
match it to a lapse event and fill in the vest date as the acquisition date.
This enables correct EUR conversion using the vest-date ECB rate for cost basis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import LapseEvent, SchwabTransaction

# Tolerance for matching per-share cost basis against FMV per share
_PER_SHARE_TOLERANCE_PCT = 0.03  # 3%
_PER_SHARE_TOLERANCE_ABS = 2.0   # $2 absolute per share


@dataclass
class EnrichmentResult:
    transactions: list[SchwabTransaction]
    matched: int  # how many transactions were enriched with lapse data
    unmatched: int  # transactions that could have been enriched but weren't
    warnings: list[str] = field(default_factory=list)


def _per_share_matches(
    tx_cost_basis: float,
    tx_quantity: float,
    fmv_per_share: float,
) -> bool:
    """Check if a transaction's per-share cost basis matches a lapse FMV.

    Compares cost_basis/quantity against fmv_per_share. This is more robust
    than comparing totals because it's independent of lot splitting.
    """
    if tx_quantity == 0 or fmv_per_share == 0:
        return False
    per_share_cost = tx_cost_basis / tx_quantity
    diff = abs(per_share_cost - fmv_per_share)
    pct = diff / fmv_per_share
    return pct <= _PER_SHARE_TOLERANCE_PCT or diff <= _PER_SHARE_TOLERANCE_ABS


def _build_lapse_index(
    lapse_events: list[LapseEvent],
) -> dict[str, list[LapseEvent]]:
    """Index lapse events by symbol for fast lookup."""
    index: dict[str, list[LapseEvent]] = {}
    for event in lapse_events:
        index.setdefault(event.symbol, []).append(event)
    return index


def _find_matching_lapse(
    tx: SchwabTransaction,
    candidates: list[LapseEvent],
) -> LapseEvent | None:
    """Find the best matching lapse event for a transaction.

    Matching strategy — compare per-share cost basis against each lapse
    event's FMV per share.  Multiple lots from the same vest all share the
    same per-share cost, so this is independent of quantity splits.

    When the transaction already has an acquisition date, prefer lapse events
    whose lapse_date matches that date.

    Returns the best match, or None.
    """
    best: LapseEvent | None = None
    best_diff = float("inf")

    if tx.quantity == 0:
        return None

    per_share_cost = tx.cost_basis_usd / tx.quantity

    for event in candidates:
        if not _per_share_matches(tx.cost_basis_usd, tx.quantity, event.fmv_per_share_usd):
            continue

        diff = abs(per_share_cost - event.fmv_per_share_usd)

        # Prefer date-matching events when tx has an acquisition date
        if tx.has_acquisition_date and tx.date_acquired == event.lapse_date:
            return event  # exact date + per-share match — best possible

        if diff < best_diff:
            best_diff = diff
            best = event

    return best


def enrich_transactions(
    transactions: list[SchwabTransaction],
    lapse_events: list[LapseEvent],
) -> EnrichmentResult:
    """Enrich transactions with lapse event data.

    For each transaction:
    - Try to match it to a lapse event by symbol + per-share cost basis
    - If matched and acquisition date was missing, fill it in from lapse_date
    - Track match statistics for verification

    Returns an EnrichmentResult with (possibly modified) transactions.
    """
    if not lapse_events:
        return EnrichmentResult(
            transactions=transactions,
            matched=0,
            unmatched=0,
        )

    index = _build_lapse_index(lapse_events)
    warnings: list[str] = []
    matched = 0
    unmatched_missing_date = 0

    enriched: list[SchwabTransaction] = []

    for tx in transactions:
        candidates = index.get(tx.symbol, [])
        if not candidates:
            if not tx.has_acquisition_date:
                unmatched_missing_date += 1
            enriched.append(tx)
            continue

        match = _find_matching_lapse(tx, candidates)

        if match is not None:
            matched += 1
            if not tx.has_acquisition_date:
                tx = tx.model_copy(update={
                    "date_acquired": match.lapse_date,
                    "has_acquisition_date": True,
                })
            enriched.append(tx)
        else:
            if not tx.has_acquisition_date:
                unmatched_missing_date += 1
            enriched.append(tx)

    if matched > 0:
        warnings.append(
            f"Enriched {matched} transaction(s) with lapse data — "
            f"vest dates filled in for accurate EUR cost basis conversion."
        )

    if unmatched_missing_date > 0:
        # Collect available FMVs and unmatched per-share costs for diagnostics
        available_fmvs = sorted({e.fmv_per_share_usd for e in lapse_events})
        unmatched_per_share = sorted({
            round(tx.cost_basis_usd / tx.quantity, 2)
            for tx in enriched
            if not tx.has_acquisition_date and tx.quantity > 0
        })
        fmv_str = ", ".join(f"${v:.2f}" for v in available_fmvs)
        cost_str = ", ".join(f"${v:.2f}" for v in unmatched_per_share[:5])
        warnings.append(
            f"{unmatched_missing_date} transaction(s) still missing acquisition date. "
            f"Their per-share cost ({cost_str}) doesn't match any vest FMV "
            f"in the lapse file ({fmv_str}). These shares may be from older "
            f"vests — try exporting lapse history with a wider date range."
        )

    return EnrichmentResult(
        transactions=enriched,
        matched=matched,
        unmatched=unmatched_missing_date,
        warnings=warnings,
    )
