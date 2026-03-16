import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import type { ComputedTransaction, TaxSummary, VerificationCheck } from '../types';

export function exportToPdf(
  transactions: ComputedTransaction[],
  summary: TaxSummary,
  checks: VerificationCheck[],
  filename: string
): void {
  const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });

  // Title
  doc.setFontSize(16);
  doc.text(`RSU Capital Gains Report — Tax Year ${summary.taxYear}`, 14, 15);
  doc.setFontSize(9);
  doc.text('For German Tax Declaration (Abgeltungssteuer)', 14, 21);
  doc.text(`Generated: ${new Date().toISOString().slice(0, 10)}`, 14, 26);

  // Summary
  doc.setFontSize(12);
  doc.text('Summary', 14, 35);

  autoTable(doc, {
    startY: 38,
    head: [['Metric', 'Value']],
    body: [
      ['Total Transactions', String(summary.totalTransactions)],
      ['Voluntary Sales', String(summary.voluntarySales)],
      ['Sell-to-Cover Sales', String(summary.sellToCoverSales)],
      ['Total Proceeds (EUR)', formatEur(summary.totalProceedsEur)],
      ['Total Cost Basis (EUR)', formatEur(summary.totalCostBasisEur)],
      ['Net Capital Gain/Loss (EUR)', formatEur(summary.netGainLossEur)],
      ['  — from Voluntary Sales (EUR)', formatEur(summary.voluntaryGainLossEur)],
      ['  — from Sell-to-Cover (EUR)', formatEur(summary.sellToCoverGainLossEur)],
      ['Net Gain/Loss (USD)', formatUsd(summary.netGainLossUsd)],
    ],
    theme: 'grid',
    styles: { fontSize: 8 },
    columnStyles: { 1: { halign: 'right' } },
  });

  // Transaction table
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tableY: number = (doc as any).lastAutoTable?.finalY ?? 90;
  doc.setFontSize(12);
  doc.text('Transactions', 14, tableY + 10);

  autoTable(doc, {
    startY: tableY + 13,
    head: [[
      'Symbol', 'Qty', 'Acquired', 'Sold', 'Term',
      'Proceeds\n(USD)', 'Cost Basis\n(USD)', 'G/L\n(USD)',
      'Rate\n(Acq)', 'Rate\n(Sold)',
      'Proceeds\n(EUR)', 'Cost Basis\n(EUR)', 'G/L\n(EUR)',
      'Type', 'Check',
    ]],
    body: transactions.map((t) => [
      t.symbol,
      t.quantity.toFixed(4),
      t.hasAcquisitionDate ? t.dateAcquired : 'N/A',
      t.dateSold,
      t.term === 'Short Term' ? 'ST' : t.term === 'Long Term' ? 'LT' : '?',
      t.proceedsUsd.toFixed(2),
      t.costBasisUsd.toFixed(2),
      t.gainLossUsd.toFixed(2),
      t.exchangeRateAcquired.toFixed(4),
      t.exchangeRateSold.toFixed(4),
      t.proceedsEur.toFixed(2),
      t.costBasisEur.toFixed(2),
      t.gainLossEur.toFixed(2),
      t.isSellToCover ? 'S2C' : 'Vol',
      t.verificationStatus === 'pass' ? 'OK' : t.verificationStatus.toUpperCase(),
    ]),
    theme: 'grid',
    styles: { fontSize: 6, cellPadding: 1 },
    headStyles: { fontSize: 6 },
  });

  // Verification section
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const verifyY: number = (doc as any).lastAutoTable?.finalY ?? 180;
  if (verifyY + 40 > doc.internal.pageSize.getHeight()) {
    doc.addPage();
  }

  doc.setFontSize(12);
  doc.text('Verification Checks', 14, verifyY + 10);

  autoTable(doc, {
    startY: verifyY + 13,
    head: [['Check', 'Status', 'Details']],
    body: checks.map((c) => [c.name, c.status.toUpperCase(), c.message]),
    theme: 'grid',
    styles: { fontSize: 7 },
  });

  // Footer
  const pageCount = doc.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    doc.setFontSize(7);
    doc.text(
      'Exchange rates: ECB reference rates via Frankfurter API (api.frankfurter.app). For information purposes.',
      14,
      doc.internal.pageSize.getHeight() - 5
    );
  }

  doc.save(filename);
}

function formatEur(n: number): string {
  return `${n >= 0 ? '' : '-'}€${Math.abs(n).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatUsd(n: number): string {
  return `${n >= 0 ? '' : '-'}$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
