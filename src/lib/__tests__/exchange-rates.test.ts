import { describe, it, expect } from 'vitest';
import { findRate } from '../exchange-rates';

describe('findRate', () => {
  const rates = new Map([
    ['2024-01-02', 0.92],
    ['2024-01-03', 0.925],
    ['2024-01-04', 0.93],
    ['2024-01-05', 0.928],
    // Jan 6-7 = weekend (no rates)
    ['2024-01-08', 0.931],
  ]);

  it('returns exact match', () => {
    expect(findRate('2024-01-03', rates)).toBe(0.925);
  });

  it('falls back to previous business day for weekends', () => {
    // Jan 6 (Saturday) → should return Jan 5's rate
    expect(findRate('2024-01-06', rates)).toBe(0.928);
    // Jan 7 (Sunday) → should return Jan 5's rate
    expect(findRate('2024-01-07', rates)).toBe(0.928);
  });

  it('returns null when no rate found within 7 days', () => {
    expect(findRate('2020-06-15', rates)).toBeNull();
  });
});
