"""Enrich Realized Gain/Loss transactions with lapse history data.

The key enrichment: when a transaction is missing its acquisition date,
match it to a lapse event and fill in the vest date as the acquisition date.
This enables correct EUR conversion using the vest-date ECB rate for cost basis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import LapseEvent, SchwabTransaction

# Tolerance for matching cost basis: FMV × quantity vs CSV cost_basis_usd
_COST_BASIS_TOLERANCE_PCT = 0.02  # 2%
_COST_BASIS_TOLERANCE_ABS = 5.0   # $5 absolute


@dataclass
class EnrichmentResult:
    transactions: list[SchwabTransaction]
    matched: int  # how many transactions were enriched with lapse data
    unmatched: int  # transactions that could have been enriched but weren't
    warnings: list[str] = field(default_factory=list)


def _cost_basis_matches(
    tx_cost_basis: float,
    fmv_per_share: float,
    quantity: float,
) -> bool:
    """Check if a transaction's cost basis ≈ FMV × quantity."""
    expected = fmv_per_share * quantity
    if expected == 0:
        return False
    diff = abs(tx_cost_basis - expected)
    pct = diff / expected
    return pct <= _COST_BASIS_TOLERANCE_PCT or diff <= _COST_BASIS_TOLERANCE_ABS


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
    used: set[tuple[str, str, str]],
) -> LapseEvent | None:
    """Find the best matching lapse event for a transaction.

    Matching strategy:
    1. If tx has acquisition date: match by symbol + date_acquired == lapse_date
    2. If tx has no acquisition date: match by symbol + cost_basis ≈ FMV × quantity

    Returns the best match, or None.
    """
    best: LapseEvent | None = None

    for event in candidates:
        key = (event.symbol, event.lapse_date, event.award_id or "")

        # Match by acquisition date if available
        if tx.has_acquisition_date and tx.date_acquired == event.lapse_date:
            if _cost_basis_matches(tx.cost_basis_usd, event.fmv_per_share_usd, tx.quantity):
                if key not in used:
                    best = event
                    break

        # Match by cost basis when acquisition date is missing
        if not tx.has_acquisition_date:
            if _cost_basis_matches(tx.cost_basis_usd, event.fmv_per_share_usd, tx.quantity):
                if key not in used:
                    best = event
                    break

    return best


def enrich_transactions(
    transactions: list[SchwabTransaction],
    lapse_events: list[LapseEvent],
) -> EnrichmentResult:
    """Enrich transactions with lapse event data.

    For each transaction:
    - Try to match it to a lapse event by symbol + cost basis
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

    # Track which lapse events have been used (for one-to-many matching,
    # a single lapse event can match multiple sell lots)
    enriched: list[SchwabTransaction] = []

    for tx in transactions:
        candidates = index.get(tx.symbol, [])
        if not candidates:
            if not tx.has_acquisition_date:
                unmatched_missing_date += 1
            enriched.append(tx)
            continue

        # For lapse matching, we don't mark events as "used" because
        # one lapse event produces multiple sell lots (sell-to-cover +
        # potentially later voluntary sales from delivered shares).
        match = _find_matching_lapse(tx, candidates, set())

        if match is not None:
            matched += 1
            if not tx.has_acquisition_date:
                # Fill in the acquisition date from the lapse event
                tx = tx.model_copy(update={
                    "date_acquired": match.lapse_date,
                    "has_acquisition_date": True,
                })
            enriched.append(tx)
        else:
            if not tx.has_acquisition_date:
                unmatched_missing_date += 1
            enriched.append(tx)

    if unmatched_missing_date > 0:
        warnings.append(
            f"{unmatched_missing_date} transaction(s) still missing acquisition date "
            f"after lapse matching"
        )

    if matched > 0:
        warnings.append(
            f"Enriched {matched} transaction(s) with lapse data "
            f"(vest dates filled in for EUR conversion)"
        )

    return EnrichmentResult(
        transactions=enriched,
        matched=matched,
        unmatched=unmatched_missing_date,
        warnings=warnings,
    )
