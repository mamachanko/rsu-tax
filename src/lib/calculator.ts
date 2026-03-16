import type { SchwabTransaction, ComputedTransaction, TaxSummary } from '../types';
import { findRate } from './exchange-rates';

const SELL_TO_COVER_TOLERANCE = 1.0; // USD — if gain/loss is within $1 of zero

/**
 * Detect if a transaction is likely a sell-to-cover (tax withholding at vesting).
 * Heuristic: same acquisition and sale date, and gain/loss near zero.
 * Also consider "Specific Lots" cost basis method as a secondary signal.
 */
function isSellToCover(t: SchwabTransaction): boolean {
  if (t.dateAcquired === t.dateSold && Math.abs(t.gainLossUsd) <= SELL_TO_COVER_TOLERANCE) {
    return true;
  }
  // When we don't have the acquisition date, fall back to cost basis method + small gain
  if (!t.hasAcquisitionDate && t.costBasisMethod === 'Specific Lots' && Math.abs(t.gainLossUsd) <= SELL_TO_COVER_TOLERANCE) {
    return true;
  }
  return false;
}

/**
 * Compute EUR capital gains for all transactions.
 * For German tax (Abgeltungssteuer):
 * - Convert proceeds using EUR/USD rate on date sold
 * - Convert cost basis using EUR/USD rate on date acquired (or date sold if unavailable)
 * - Gain/loss in EUR = proceeds(EUR) - cost basis(EUR)
 */
export function computeCapitalGains(
  transactions: SchwabTransaction[],
  rates: Map<string, number>
): ComputedTransaction[] {
  return transactions.map((t) => {
    const rateSold = findRate(t.dateSold, rates);
    // When no acquisition date is available, dateAcquired was set to dateSold by the parser
    // so findRate will return the same rate for both
    const rateAcquired = findRate(t.dateAcquired, rates);
    const notes: string[] = [];
    let status: ComputedTransaction['verificationStatus'] = 'pass';

    if (rateSold === null) {
      notes.push(`No exchange rate found for sale date ${t.dateSold}`);
      status = 'fail';
    }
    if (rateAcquired === null) {
      notes.push(`No exchange rate found for acquisition date ${t.dateAcquired}`);
      status = 'fail';
    }

    if (!t.hasAcquisitionDate) {
      notes.push('Using sale date exchange rate for cost basis (acquisition date not available in CSV)');
      if (status === 'pass') status = 'warn';
    }

    const exchangeRateSold = rateSold ?? 0;
    const exchangeRateAcquired = rateAcquired ?? 0;

    // Convert: USD amount * (EUR per USD) = EUR amount
    const proceedsEur = roundCents(t.proceedsUsd * exchangeRateSold);
    const costBasisEur = roundCents(t.costBasisUsd * exchangeRateAcquired);
    const gainLossEur = roundCents(proceedsEur - costBasisEur);

    // Verify USD gain/loss consistency
    const expectedGainUsd = roundCents(t.proceedsUsd - t.costBasisUsd);
    if (Math.abs(expectedGainUsd - t.gainLossUsd) > 0.02) {
      notes.push(`USD gain/loss mismatch: expected ${expectedGainUsd}, got ${t.gainLossUsd}`);
      if (status === 'pass') status = 'warn';
    }

    return {
      ...t,
      exchangeRateSold,
      exchangeRateAcquired,
      proceedsEur,
      costBasisEur,
      gainLossEur,
      isSellToCover: isSellToCover(t),
      verificationStatus: status,
      verificationNotes: notes,
    };
  });
}

/**
 * Compute summary totals for a tax year.
 */
export function computeSummary(computed: ComputedTransaction[], taxYear?: number): TaxSummary {
  const filtered = taxYear
    ? computed.filter((t) => t.dateSold.startsWith(String(taxYear)))
    : computed;

  const voluntary = filtered.filter((t) => !t.isSellToCover);
  const sellToCover = filtered.filter((t) => t.isSellToCover);

  return {
    taxYear: taxYear ?? (filtered.length > 0 ? parseInt(filtered[0].dateSold.slice(0, 4)) : new Date().getFullYear()),
    totalTransactions: filtered.length,
    voluntarySales: voluntary.length,
    sellToCoverSales: sellToCover.length,
    totalProceedsEur: roundCents(filtered.reduce((s, t) => s + t.proceedsEur, 0)),
    totalCostBasisEur: roundCents(filtered.reduce((s, t) => s + t.costBasisEur, 0)),
    netGainLossEur: roundCents(filtered.reduce((s, t) => s + t.gainLossEur, 0)),
    voluntaryGainLossEur: roundCents(voluntary.reduce((s, t) => s + t.gainLossEur, 0)),
    sellToCoverGainLossEur: roundCents(sellToCover.reduce((s, t) => s + t.gainLossEur, 0)),
    totalProceedsUsd: roundCents(filtered.reduce((s, t) => s + t.proceedsUsd, 0)),
    totalCostBasisUsd: roundCents(filtered.reduce((s, t) => s + t.costBasisUsd, 0)),
    netGainLossUsd: roundCents(filtered.reduce((s, t) => s + t.gainLossUsd, 0)),
  };
}

function roundCents(n: number): number {
  return Math.round(n * 100) / 100;
}
