import type { ExchangeRate } from '../types';
import { insertExchangeRates, getExchangeRates } from './db';

const FRANKFURTER_BASE = 'https://api.frankfurter.app';

interface FrankfurterResponse {
  base: string;
  start_date: string;
  end_date: string;
  rates: Record<string, { EUR: number }>;
}

/**
 * Fetch USD→EUR exchange rates for a date range from the Frankfurter API (ECB data).
 * The Frankfurter API returns rates with EUR as one of the target currencies.
 * When from=USD, the rate for EUR means: 1 USD = X EUR.
 */
export async function fetchExchangeRates(startDate: string, endDate: string): Promise<ExchangeRate[]> {
  // Frankfurter API: GET /{start_date}..{end_date}?from=USD&to=EUR
  const url = `${FRANKFURTER_BASE}/${startDate}..${endDate}?from=USD&to=EUR`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Failed to fetch exchange rates: ${response.status} ${response.statusText}`);
  }

  const data: FrankfurterResponse = await response.json();
  const rates: ExchangeRate[] = [];

  for (const [date, rateObj] of Object.entries(data.rates)) {
    rates.push({
      date,
      usdToEur: rateObj.EUR,
    });
  }

  // Sort by date
  rates.sort((a, b) => a.date.localeCompare(b.date));
  return rates;
}

/**
 * Ensure we have exchange rates cached for all needed dates.
 * Fetches from the API and stores in SQLite.
 */
export async function ensureRatesForDates(dates: string[]): Promise<Map<string, number>> {
  if (dates.length === 0) return new Map();

  const sorted = [...dates].sort();
  // Extend range by a few days on each side to handle weekends/holidays
  const minDate = shiftDate(sorted[0], -5);
  const maxDate = shiftDate(sorted[sorted.length - 1], 5);

  const existingRates = getExchangeRates();

  // Check if we already have sufficient coverage
  const needsFetch = dates.some((d) => !findRate(d, existingRates));

  if (needsFetch) {
    const fetched = await fetchExchangeRates(minDate, maxDate);
    insertExchangeRates(fetched);
    // Reload from DB
    return getExchangeRates();
  }

  return existingRates;
}

/**
 * Find the exchange rate for a given date.
 * If the exact date is not available (weekend/holiday), walk backward to find the previous business day.
 */
export function findRate(date: string, rates: Map<string, number>): number | null {
  // Try exact date first
  if (rates.has(date)) return rates.get(date)!;

  // Walk backward up to 7 days
  for (let i = 1; i <= 7; i++) {
    const prev = shiftDate(date, -i);
    if (rates.has(prev)) return rates.get(prev)!;
  }

  return null;
}

function shiftDate(dateStr: string, days: number): string {
  const d = new Date(dateStr + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
