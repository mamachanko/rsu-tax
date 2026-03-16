import { describe, it, expect } from 'vitest';
import { computeCapitalGains, computeSummary } from '../calculator';
import type { SchwabTransaction } from '../../types';

function makeRates(entries: [string, number][]): Map<string, number> {
  return new Map(entries);
}

describe('computeCapitalGains', () => {
  const rates = makeRates([
    ['2023-01-15', 0.92],  // 1 USD = 0.92 EUR
    ['2024-06-20', 0.93],
    ['2024-03-01', 0.91],
    ['2024-09-15', 0.90],
    ['2025-06-15', 0.89],
  ]);

  it('computes EUR gain/loss correctly with acquisition date', () => {
    const transactions: SchwabTransaction[] = [{
      symbol: 'GOOG',
      quantity: 10,
      dateAcquired: '2023-01-15',
      dateSold: '2024-06-20',
      proceedsUsd: 1500,
      costBasisUsd: 1200,
      gainLossUsd: 300,
      term: 'Long Term',
      washSale: 0,
      hasAcquisitionDate: true,
    }];

    const result = computeCapitalGains(transactions, rates);
    expect(result).toHaveLength(1);
    const t = result[0];

    // Proceeds: 1500 * 0.93 = 1395.00 EUR
    expect(t.proceedsEur).toBe(1395);
    // Cost basis: 1200 * 0.92 = 1104.00 EUR
    expect(t.costBasisEur).toBe(1104);
    // Gain: 1395 - 1104 = 291.00 EUR
    expect(t.gainLossEur).toBe(291);
    expect(t.verificationStatus).toBe('pass');
    expect(t.isSellToCover).toBe(false);
  });

  it('uses sale date rate for both when no acquisition date', () => {
    const transactions: SchwabTransaction[] = [{
      symbol: 'ABCD',
      quantity: 71,
      dateAcquired: '2025-06-15', // same as dateSold (fallback)
      dateSold: '2025-06-15',
      proceedsUsd: 17855.57,
      costBasisUsd: 17632.85,
      gainLossUsd: 222.72,
      term: 'Short Term',
      washSale: 0,
      hasAcquisitionDate: false,
      costBasisMethod: 'Specific Lots',
    }];

    const result = computeCapitalGains(transactions, rates);
    const t = result[0];

    // Both should use the sale date rate (0.89)
    expect(t.exchangeRateSold).toBe(0.89);
    expect(t.exchangeRateAcquired).toBe(0.89);
    // Status should be 'warn' due to missing acquisition date
    expect(t.verificationStatus).toBe('warn');
    expect(t.verificationNotes.some(n => n.includes('acquisition date not available'))).toBe(true);
  });

  it('detects sell-to-cover transactions', () => {
    const transactions: SchwabTransaction[] = [{
      symbol: 'GOOG',
      quantity: 5,
      dateAcquired: '2024-06-20',
      dateSold: '2024-06-20',
      proceedsUsd: 750,
      costBasisUsd: 750,
      gainLossUsd: 0,
      term: 'Short Term',
      washSale: 0,
      hasAcquisitionDate: true,
    }];

    const result = computeCapitalGains(transactions, rates);
    expect(result[0].isSellToCover).toBe(true);
  });

  it('detects sell-to-cover via Specific Lots when no acquisition date', () => {
    const transactions: SchwabTransaction[] = [{
      symbol: 'ABCD',
      quantity: 71,
      dateAcquired: '2025-06-15',
      dateSold: '2025-06-15',
      proceedsUsd: 17855.57,
      costBasisUsd: 17855.00,
      gainLossUsd: 0.57,
      term: 'Short Term',
      washSale: 0,
      hasAcquisitionDate: false,
      costBasisMethod: 'Specific Lots',
    }];

    const result = computeCapitalGains(transactions, rates);
    expect(result[0].isSellToCover).toBe(true);
  });

  it('flags missing exchange rates', () => {
    const transactions: SchwabTransaction[] = [{
      symbol: 'GOOG',
      quantity: 10,
      dateAcquired: '2020-01-01', // not in rates
      dateSold: '2024-06-20',
      proceedsUsd: 1500,
      costBasisUsd: 1200,
      gainLossUsd: 300,
      term: 'Long Term',
      washSale: 0,
      hasAcquisitionDate: true,
    }];

    const result = computeCapitalGains(transactions, rates);
    expect(result[0].verificationStatus).toBe('fail');
    expect(result[0].verificationNotes.length).toBeGreaterThan(0);
  });
});

describe('computeSummary', () => {
  it('separates voluntary vs sell-to-cover totals', () => {
    const rates = makeRates([
      ['2023-01-15', 0.92],
      ['2024-06-20', 0.93],
    ]);

    const transactions: SchwabTransaction[] = [
      {
        symbol: 'GOOG', quantity: 10,
        dateAcquired: '2023-01-15', dateSold: '2024-06-20',
        proceedsUsd: 1500, costBasisUsd: 1200, gainLossUsd: 300,
        term: 'Long Term', washSale: 0, hasAcquisitionDate: true,
      },
      {
        symbol: 'GOOG', quantity: 5,
        dateAcquired: '2024-06-20', dateSold: '2024-06-20',
        proceedsUsd: 750, costBasisUsd: 750, gainLossUsd: 0,
        term: 'Short Term', washSale: 0, hasAcquisitionDate: true,
      },
    ];

    const computed = computeCapitalGains(transactions, rates);
    const summary = computeSummary(computed);

    expect(summary.totalTransactions).toBe(2);
    expect(summary.voluntarySales).toBe(1);
    expect(summary.sellToCoverSales).toBe(1);
    expect(summary.voluntaryGainLossEur).toBe(291); // 1500*0.93 - 1200*0.92
    expect(summary.sellToCoverGainLossEur).toBe(0);  // 750*0.93 - 750*0.93
  });
});
