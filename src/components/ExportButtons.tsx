import type { ComputedTransaction, TaxSummary, VerificationCheck } from '../types';
import { downloadCsv } from '../lib/export-csv';
import { exportToPdf } from '../lib/export-pdf';

interface Props {
  transactions: ComputedTransaction[];
  summary: TaxSummary;
  checks: VerificationCheck[];
}

export function ExportButtons({ transactions, summary, checks }: Props) {
  const filename = `rsu-capital-gains-${summary.taxYear}`;

  return (
    <div className="flex gap-3">
      <button
        onClick={() => downloadCsv(transactions, `${filename}.csv`)}
        className="bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded hover:bg-gray-50 transition-colors text-sm font-medium"
      >
        Export CSV
      </button>
      <button
        onClick={() => exportToPdf(transactions, summary, checks, `${filename}.pdf`)}
        className="bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded hover:bg-gray-50 transition-colors text-sm font-medium"
      >
        Export PDF
      </button>
    </div>
  );
}
