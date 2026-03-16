import Papa from 'papaparse';
import type { SchwabTransaction, ColumnMapping } from '../types';

// Known header variants for each field
const HEADER_VARIANTS: Record<keyof ColumnMapping, string[]> = {
  symbol: ['symbol', 'ticker', 'security'],
  name: ['name', 'description', 'company'],
  quantity: ['quantity', 'qty', 'shares', 'number of shares', 'units'],
  dateAcquired: ['date acquired', 'acquisition date', 'open date', 'vest date', 'acquired'],
  dateSold: ['date sold', 'sale date', 'close date', 'closed date', 'sold', 'date of sale', 'transaction closed date'],
  proceeds: ['proceeds', 'sale proceeds', 'total proceeds', 'gross proceeds', 'amount'],
  costBasis: ['cost basis (cb)', 'cost basis', 'adjusted cost basis', 'cost', 'basis', 'purchase price', 'total cost'],
  gainLoss: ['total gain/loss ($)', 'gain/loss', 'gain loss', 'gain(loss)', 'realized gain/loss', 'realized gain', 'gain/loss ($)'],
  term: ['term', 'type', 'holding period', 'short/long'],
  washSale: ['wash sale?', 'wash sale', 'wash sale loss disallowed', 'wash sale adjustment', 'wash'],
  costBasisMethod: ['cost basis method', 'method', 'lot method'],
  stGainLoss: ['short term (st) gain/loss ($)', 'st gain/loss ($)', 'short-term gain/loss'],
  ltGainLoss: ['long term (lt) gain/loss ($)', 'lt gain/loss ($)', 'long-term gain/loss'],
};

function normalize(header: string): string {
  return header.toLowerCase().replace(/[^a-z0-9/ ()$%-]/g, '').trim();
}

export function detectColumnMapping(headers: string[]): ColumnMapping {
  const mapping: Partial<ColumnMapping> = {};
  const normalizedHeaders = headers.map(normalize);
  const usedIndices = new Set<number>();

  // Process fields in a specific order: more specific fields first to avoid
  // substring collisions (e.g., "cost basis method" matching before "cost basis (cb)")
  const fieldOrder: (keyof ColumnMapping)[] = [
    'costBasisMethod', 'stGainLoss', 'ltGainLoss', 'washSale',
    'costBasis', 'gainLoss', 'dateAcquired', 'dateSold',
    'symbol', 'name', 'quantity', 'proceeds', 'term',
  ];

  for (const field of fieldOrder) {
    const variants = HEADER_VARIANTS[field];
    for (const variant of variants) {
      // Try exact match first
      let idx = normalizedHeaders.findIndex((h, i) => !usedIndices.has(i) && h === variant);
      // Then try substring match
      if (idx === -1) {
        idx = normalizedHeaders.findIndex((h, i) => !usedIndices.has(i) && h.includes(variant));
      }
      if (idx !== -1) {
        mapping[field] = headers[idx];
        usedIndices.add(idx);
        break;
      }
    }
  }

  // Defaults for missing optional fields
  if (!mapping.washSale) mapping.washSale = '__none__';
  if (!mapping.term) mapping.term = '__none__';
  if (!mapping.name) mapping.name = '__none__';
  if (!mapping.costBasisMethod) mapping.costBasisMethod = '__none__';
  if (!mapping.stGainLoss) mapping.stGainLoss = '__none__';
  if (!mapping.ltGainLoss) mapping.ltGainLoss = '__none__';
  if (!mapping.dateAcquired) mapping.dateAcquired = '__none__';

  return mapping as ColumnMapping;
}

function parseCurrency(value: string | number | undefined): number {
  if (value === undefined || value === null || value === '' || value === '--') return 0;
  if (typeof value === 'number') return value;
  // Remove $, commas, whitespace
  let cleaned = String(value).replace(/[$,\s]/g, '');
  // Handle parentheses notation for negatives: ($50.00) → -50.00
  const isParenNegative = cleaned.startsWith('(') && cleaned.endsWith(')');
  if (isParenNegative) cleaned = cleaned.slice(1, -1);
  // Handle -$50.00 (after $ is stripped: -50.00)
  const num = parseFloat(cleaned);
  if (isNaN(num)) return 0;
  return isParenNegative ? -num : num;
}

function parseDate(value: string | undefined): string {
  if (!value) return '';
  const cleaned = String(value).trim();

  // Try MM/DD/YYYY
  const mdyMatch = cleaned.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (mdyMatch) {
    return `${mdyMatch[3]}-${mdyMatch[1].padStart(2, '0')}-${mdyMatch[2].padStart(2, '0')}`;
  }

  // Try YYYY-MM-DD (already correct)
  if (/^\d{4}-\d{2}-\d{2}$/.test(cleaned)) return cleaned;

  // Try DD.MM.YYYY (German)
  const dmyMatch = cleaned.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
  if (dmyMatch) {
    return `${dmyMatch[3]}-${dmyMatch[2].padStart(2, '0')}-${dmyMatch[1].padStart(2, '0')}`;
  }

  return cleaned; // Return as-is if unrecognized
}

/**
 * Determine the term (Short Term / Long Term) from available data.
 * Schwab's "Realized Gain/Loss" CSV doesn't have a "Term" column but has
 * separate ST and LT gain/loss columns. We infer the term from those.
 */
function detectTerm(
  row: Record<string, string>,
  mapping: ColumnMapping,
): SchwabTransaction['term'] {
  // If there's an explicit term column, use it
  if (mapping.term !== '__none__') {
    const termVal = row[mapping.term];
    if (termVal) {
      const lower = String(termVal).toLowerCase();
      if (lower.includes('long')) return 'Long Term';
      if (lower.includes('short')) return 'Short Term';
    }
  }

  // Infer from ST/LT gain/loss columns
  if (mapping.stGainLoss !== '__none__' || mapping.ltGainLoss !== '__none__') {
    const stVal = mapping.stGainLoss !== '__none__' ? row[mapping.stGainLoss] : '--';
    const ltVal = mapping.ltGainLoss !== '__none__' ? row[mapping.ltGainLoss] : '--';

    const stIsEmpty = !stVal || stVal.trim() === '--' || stVal.trim() === '';
    const ltIsEmpty = !ltVal || ltVal.trim() === '--' || ltVal.trim() === '';

    if (!stIsEmpty && ltIsEmpty) return 'Short Term';
    if (stIsEmpty && !ltIsEmpty) return 'Long Term';
    // If both have values, check which is non-zero
    if (!stIsEmpty && !ltIsEmpty) {
      const stNum = parseCurrency(stVal);
      const ltNum = parseCurrency(ltVal);
      if (stNum !== 0 && ltNum === 0) return 'Short Term';
      if (ltNum !== 0 && stNum === 0) return 'Long Term';
    }
  }

  return 'Unknown';
}

/**
 * Detect if a wash sale applies.
 * Schwab uses "Yes"/"No" in the "Wash Sale?" column.
 */
function parseWashSale(row: Record<string, string>, mapping: ColumnMapping): number {
  if (mapping.washSale === '__none__') return 0;
  const val = row[mapping.washSale];
  if (!val) return 0;
  const lower = val.trim().toLowerCase();
  // If it's "Yes"/"No", check for disallowed loss column too
  if (lower === 'yes') {
    // Look for a "Disallowed Loss" column in the row
    for (const key of Object.keys(row)) {
      if (normalize(key).includes('disallowed loss')) {
        const amount = parseCurrency(row[key]);
        if (amount !== 0) return amount;
      }
    }
    return 1; // Flag as wash sale even without amount
  }
  if (lower === 'no') return 0;
  // Try to parse as a number (legacy format)
  return parseCurrency(val);
}

export interface ParseResult {
  headers: string[];
  rawRows: Record<string, string>[];
  mapping: ColumnMapping;
  transactions: SchwabTransaction[];
  warnings: string[];
}

export function parseSchwabCsv(csvText: string): ParseResult {
  const warnings: string[] = [];

  // Schwab CSVs sometimes have a header/footer section — try to find the data rows
  const lines = csvText.split('\n');
  let dataStart = 0;
  for (let i = 0; i < Math.min(lines.length, 10); i++) {
    const lower = lines[i].toLowerCase();
    if (lower.includes('symbol') && (lower.includes('date') || lower.includes('proceed') || lower.includes('quantity'))) {
      dataStart = i;
      break;
    }
  }

  // Remove any trailing summary rows (Schwab often adds "Total" rows)
  let dataEnd = lines.length;
  for (let i = lines.length - 1; i > dataStart; i--) {
    const trimmed = lines[i].trim();
    if (trimmed === '' || trimmed.toLowerCase().startsWith('"total') || trimmed.toLowerCase().startsWith('total') || trimmed.startsWith('***')) {
      dataEnd = i;
    } else {
      break;
    }
  }

  const csvData = lines.slice(dataStart, dataEnd).join('\n');

  const parsed = Papa.parse<Record<string, string>>(csvData, {
    header: true,
    skipEmptyLines: true,
    transformHeader: (h: string) => h.trim(),
  });

  if (parsed.errors.length > 0) {
    warnings.push(...parsed.errors.map((e) => `Row ${e.row}: ${e.message}`));
  }

  const headers = parsed.meta.fields ?? [];
  const mapping = detectColumnMapping(headers);

  const hasDateAcquired = mapping.dateAcquired !== '__none__';

  // Check for unmapped required fields
  const required: (keyof ColumnMapping)[] = ['symbol', 'dateSold', 'proceeds', 'costBasis', 'gainLoss'];
  for (const field of required) {
    if (!mapping[field] || mapping[field] === '__none__') {
      warnings.push(`Could not auto-detect column for "${field}". Available headers: ${headers.join(', ')}`);
    }
  }

  if (!hasDateAcquired) {
    warnings.push('No "Date Acquired" column found. Using sale date for exchange rate conversion of cost basis. See GitHub issue for details.');
  }

  const transactions: SchwabTransaction[] = [];
  for (let i = 0; i < parsed.data.length; i++) {
    const row = parsed.data[i];
    // Skip empty/summary rows
    const symbolVal = row[mapping.symbol];
    if (!symbolVal || symbolVal.trim() === '' || symbolVal.toLowerCase() === 'total') continue;

    const dateSold = parseDate(row[mapping.dateSold]);
    const dateAcquired = hasDateAcquired ? parseDate(row[mapping.dateAcquired]) : dateSold;

    const t: SchwabTransaction = {
      symbol: symbolVal.trim(),
      name: mapping.name !== '__none__' ? row[mapping.name]?.trim() : undefined,
      quantity: parseCurrency(row[mapping.quantity]),
      dateAcquired,
      dateSold,
      proceedsUsd: parseCurrency(row[mapping.proceeds]),
      costBasisUsd: parseCurrency(row[mapping.costBasis]),
      gainLossUsd: parseCurrency(row[mapping.gainLoss]),
      term: detectTerm(row, mapping),
      washSale: parseWashSale(row, mapping),
      costBasisMethod: mapping.costBasisMethod !== '__none__' ? row[mapping.costBasisMethod]?.trim() : undefined,
      hasAcquisitionDate: hasDateAcquired,
    };

    if (!t.dateSold) {
      warnings.push(`Row ${i + 1}: Missing sale date, skipping`);
      continue;
    }

    transactions.push(t);
  }

  return { headers, rawRows: parsed.data, mapping, transactions, warnings };
}
