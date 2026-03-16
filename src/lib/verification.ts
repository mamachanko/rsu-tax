import type { ComputedTransaction, VerificationCheck } from '../types';

function roundCents(n: number): number {
  return Math.round(n * 100) / 100;
}

/**
 * Run all verification checks on computed transactions.
 */
export function runVerification(transactions: ComputedTransaction[]): VerificationCheck[] {
  const checks: VerificationCheck[] = [];

  // 1. USD consistency — proceeds - cost basis ≈ gain/loss for each row
  {
    let failures = 0;
    for (const t of transactions) {
      const expected = roundCents(t.proceedsUsd - t.costBasisUsd);
      if (Math.abs(expected - t.gainLossUsd) > 0.02) {
        failures++;
      }
    }
    checks.push({
      name: 'USD Gain/Loss Consistency',
      status: failures === 0 ? 'pass' : failures <= 2 ? 'warn' : 'fail',
      message: failures === 0
        ? 'All transactions: proceeds - cost basis = reported gain/loss'
        : `${failures} transaction(s) have USD gain/loss mismatches (may include wash sale adjustments)`,
    });
  }

  // 2. Exchange rate sanity — rates in reasonable range
  {
    let outOfRange = 0;
    const MIN_RATE = 0.60;
    const MAX_RATE = 1.15;
    for (const t of transactions) {
      if (t.exchangeRateSold < MIN_RATE || t.exchangeRateSold > MAX_RATE) outOfRange++;
      if (t.exchangeRateAcquired < MIN_RATE || t.exchangeRateAcquired > MAX_RATE) outOfRange++;
    }
    checks.push({
      name: 'Exchange Rate Sanity',
      status: outOfRange === 0 ? 'pass' : 'warn',
      message: outOfRange === 0
        ? `All exchange rates within expected range (${MIN_RATE}–${MAX_RATE} EUR/USD)`
        : `${outOfRange} rate(s) outside expected range — verify manually`,
    });
  }

  // 3. EUR consistency — proceeds(EUR) - cost basis(EUR) ≈ gain/loss(EUR)
  {
    let failures = 0;
    for (const t of transactions) {
      const expected = roundCents(t.proceedsEur - t.costBasisEur);
      if (Math.abs(expected - t.gainLossEur) > 0.02) {
        failures++;
      }
    }
    checks.push({
      name: 'EUR Gain/Loss Consistency',
      status: failures === 0 ? 'pass' : 'fail',
      message: failures === 0
        ? 'All EUR calculations: proceeds - cost basis = gain/loss'
        : `${failures} transaction(s) have EUR calculation errors`,
    });
  }

  // 4. Sum check — individual EUR gains sum to total
  {
    const total = roundCents(transactions.reduce((s, t) => s + t.gainLossEur, 0));
    const sumOfParts = roundCents(
      transactions.reduce((s, t) => s + (t.proceedsEur - t.costBasisEur), 0)
    );
    const diff = Math.abs(total - sumOfParts);
    checks.push({
      name: 'EUR Sum Verification',
      status: diff < 0.05 ? 'pass' : 'warn',
      message: diff < 0.05
        ? `Sum of individual gains (${total.toFixed(2)}) matches total`
        : `Sum discrepancy: individual gains sum to ${sumOfParts.toFixed(2)}, total is ${total.toFixed(2)}`,
    });
  }

  // 5. Date ordering — dateAcquired <= dateSold (skip if no acquisition date)
  {
    const withDates = transactions.filter((t) => t.hasAcquisitionDate);
    let violations = 0;
    for (const t of withDates) {
      if (t.dateAcquired > t.dateSold) violations++;
    }
    const noAcqDate = transactions.length - withDates.length;
    const noAcqNote = noAcqDate > 0 ? ` (${noAcqDate} transaction(s) without acquisition date — skipped)` : '';
    checks.push({
      name: 'Date Ordering',
      status: violations === 0 ? 'pass' : 'warn',
      message: violations === 0
        ? `All transactions: acquisition date <= sale date${noAcqNote}`
        : `${violations} transaction(s) have acquisition date after sale date${noAcqNote}`,
    });
  }

  // 6. No missing exchange rates
  {
    let missing = 0;
    for (const t of transactions) {
      if (t.exchangeRateSold === 0) missing++;
      if (t.exchangeRateAcquired === 0) missing++;
    }
    checks.push({
      name: 'Exchange Rate Coverage',
      status: missing === 0 ? 'pass' : 'fail',
      message: missing === 0
        ? 'All transaction dates have valid exchange rates'
        : `${missing} missing exchange rate(s) — EUR calculations will be incorrect`,
    });
  }

  // 7. Cross-check USD totals
  {
    const sumProceeds = roundCents(transactions.reduce((s, t) => s + t.proceedsUsd, 0));
    const sumCostBasis = roundCents(transactions.reduce((s, t) => s + t.costBasisUsd, 0));
    const sumGainLoss = roundCents(transactions.reduce((s, t) => s + t.gainLossUsd, 0));
    const expectedTotal = roundCents(sumProceeds - sumCostBasis);
    const diff = Math.abs(expectedTotal - sumGainLoss);
    checks.push({
      name: 'USD Totals Cross-Check',
      status: diff < 1.0 ? 'pass' : 'warn',
      message: diff < 1.0
        ? `USD totals consistent: proceeds ($${sumProceeds.toFixed(2)}) - cost ($${sumCostBasis.toFixed(2)}) = gain ($${sumGainLoss.toFixed(2)})`
        : `USD totals discrepancy of $${diff.toFixed(2)} — may include wash sale adjustments`,
    });
  }

  return checks;
}
