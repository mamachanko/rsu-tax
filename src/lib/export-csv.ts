import type { ComputedTransaction } from '../types';

export function exportToCsv(transactions: ComputedTransaction[]): string {
  const headers = [
    'Symbol',
    'Quantity',
    'Date Acquired',
    'Date Sold',
    'Term',
    'Proceeds (USD)',
    'Cost Basis (USD)',
    'Gain/Loss (USD)',
    'Wash Sale (USD)',
    'EUR/USD Rate (Acquired)',
    'EUR/USD Rate (Sold)',
    'Proceeds (EUR)',
    'Cost Basis (EUR)',
    'Gain/Loss (EUR)',
    'Type',
    'Verification',
  ];

  const rows = transactions.map((t) => [
    t.symbol,
    t.quantity.toString(),
    t.hasAcquisitionDate ? t.dateAcquired : '',
    t.dateSold,
    t.term,
    t.proceedsUsd.toFixed(2),
    t.costBasisUsd.toFixed(2),
    t.gainLossUsd.toFixed(2),
    t.washSale.toFixed(2),
    t.exchangeRateAcquired.toFixed(6),
    t.exchangeRateSold.toFixed(6),
    t.proceedsEur.toFixed(2),
    t.costBasisEur.toFixed(2),
    t.gainLossEur.toFixed(2),
    t.isSellToCover ? 'Sell-to-Cover' : 'Voluntary',
    t.verificationStatus,
  ]);

  const csvContent = [
    headers.join(','),
    ...rows.map((r) => r.map((v) => `"${v}"`).join(',')),
  ].join('\n');

  return csvContent;
}

export function downloadCsv(transactions: ComputedTransaction[], filename: string): void {
  const csv = exportToCsv(transactions);
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
