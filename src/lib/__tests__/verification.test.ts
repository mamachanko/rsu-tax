import { describe, it, expect } from 'vitest';
import { runVerification } from '../verification';
import type { ComputedTransaction } from '../../types';

function makeTransaction(overrides: Partial<ComputedTransaction> = {}): ComputedTransaction {
  return {
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
    ...overrides,
  };
}

describe('runVerification', () => {
  it('all checks pass for valid data', () => {
    const transactions = [makeTransaction()];
    const checks = runVerification(transactions);
    expect(checks.every((c) => c.status === 'pass')).toBe(true);
  });

  it('warns on USD gain/loss mismatch', () => {
    const transactions = [makeTransaction({ gainLossUsd: 500 })]; // wrong!
    const checks = runVerification(transactions);
    const usdCheck = checks.find((c) => c.name === 'USD Gain/Loss Consistency');
    expect(usdCheck?.status).not.toBe('pass');
  });

  it('fails on missing exchange rates', () => {
    const transactions = [makeTransaction({ exchangeRateSold: 0 })];
    const checks = runVerification(transactions);
    const rateCheck = checks.find((c) => c.name === 'Exchange Rate Coverage');
    expect(rateCheck?.status).toBe('fail');
  });

  it('warns on out-of-range exchange rates', () => {
    const transactions = [makeTransaction({ exchangeRateSold: 2.5 })];
    const checks = runVerification(transactions);
    const sanityCheck = checks.find((c) => c.name === 'Exchange Rate Sanity');
    expect(sanityCheck?.status).toBe('warn');
  });

  it('warns on date ordering violation', () => {
    const transactions = [makeTransaction({ dateAcquired: '2025-01-01', dateSold: '2024-06-20' })];
    const checks = runVerification(transactions);
    const dateCheck = checks.find((c) => c.name === 'Date Ordering');
    expect(dateCheck?.status).toBe('warn');
  });

  it('skips date ordering check for transactions without acquisition date', () => {
    const transactions = [makeTransaction({
      hasAcquisitionDate: false,
      dateAcquired: '2024-06-20',
      dateSold: '2024-06-20',
    })];
    const checks = runVerification(transactions);
    const dateCheck = checks.find((c) => c.name === 'Date Ordering');
    expect(dateCheck?.status).toBe('pass');
    expect(dateCheck?.message).toContain('without acquisition date');
  });
});
