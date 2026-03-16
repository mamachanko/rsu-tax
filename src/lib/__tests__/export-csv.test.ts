import { describe, it, expect } from 'vitest';
import { exportToCsv } from '../export-csv';
import type { ComputedTransaction } from '../../types';

describe('exportToCsv', () => {
  it('generates valid CSV with headers and data', () => {
    const transactions: ComputedTransaction[] = [{
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
      exchangeRateSold: 0.93,
      exchangeRateAcquired: 0.92,
      proceedsEur: 1395,
      costBasisEur: 1104,
      gainLossEur: 291,
      isSellToCover: false,
      verificationStatus: 'pass',
      verificationNotes: [],
    }];

    const csv = exportToCsv(transactions);
    const lines = csv.split('\n');

    // Header line
    expect(lines[0]).toContain('Symbol');
    expect(lines[0]).toContain('Gain/Loss (EUR)');

    // Data line
    expect(lines[1]).toContain('GOOG');
    expect(lines[1]).toContain('1395.00');
    expect(lines[1]).toContain('291.00');
    expect(lines[1]).toContain('Voluntary');
    expect(lines[1]).toContain('2023-01-15'); // has acquisition date
  });

  it('exports empty acquisition date when not available', () => {
    const transactions: ComputedTransaction[] = [{
      symbol: 'ABCD',
      quantity: 71,
      dateAcquired: '2025-06-15',
      dateSold: '2025-06-15',
      proceedsUsd: 17855.57,
      costBasisUsd: 17632.85,
      gainLossUsd: 222.72,
      term: 'Short Term',
      washSale: 0,
      hasAcquisitionDate: false,
      exchangeRateSold: 0.89,
      exchangeRateAcquired: 0.89,
      proceedsEur: 15891.46,
      costBasisEur: 15693.24,
      gainLossEur: 198.22,
      isSellToCover: true,
      verificationStatus: 'warn',
      verificationNotes: [],
    }];

    const csv = exportToCsv(transactions);
    const lines = csv.split('\n');
    // Date Acquired column should be empty
    const dataLine = lines[1];
    // Third column (index 2) should be empty
    expect(dataLine).toContain('""'); // empty quoted field for date acquired
  });
});
