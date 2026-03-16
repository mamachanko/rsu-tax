import type { TaxSummary } from '../types';

interface Props {
  summary: TaxSummary;
}

function fmtEur(n: number): string {
  const sign = n < 0 ? '-' : '';
  return `${sign}${Math.abs(n).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}`;
}

function fmtUsd(n: number): string {
  const sign = n < 0 ? '-' : '';
  return `${sign}${Math.abs(n).toLocaleString('en-US', { style: 'currency', currency: 'USD' })}`;
}

export function Summary({ summary }: Props) {
  const s = summary;
  const isGain = s.netGainLossEur >= 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Main result */}
      <div className={`col-span-1 md:col-span-3 rounded-lg p-6 ${isGain ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
        <p className="text-sm text-gray-600 mb-1">Net Capital Gain/Loss for German Tax Declaration</p>
        <p className={`text-3xl font-bold ${isGain ? 'text-green-700' : 'text-red-700'}`}>
          {fmtEur(s.netGainLossEur)}
        </p>
        <p className="text-sm text-gray-500 mt-1">Tax Year {s.taxYear} &middot; {fmtUsd(s.netGainLossUsd)} (USD)</p>
      </div>

      {/* Breakdown */}
      <div className="bg-white rounded-lg border p-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Voluntary Sales</p>
        <p className={`text-xl font-semibold ${s.voluntaryGainLossEur >= 0 ? 'text-green-600' : 'text-red-600'}`}>
          {fmtEur(s.voluntaryGainLossEur)}
        </p>
        <p className="text-xs text-gray-400 mt-1">{s.voluntarySales} transaction(s)</p>
      </div>

      <div className="bg-white rounded-lg border p-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Sell-to-Cover</p>
        <p className="text-xl font-semibold text-gray-600">
          {fmtEur(s.sellToCoverGainLossEur)}
        </p>
        <p className="text-xs text-gray-400 mt-1">{s.sellToCoverSales} transaction(s)</p>
      </div>

      <div className="bg-white rounded-lg border p-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Totals (EUR)</p>
        <div className="text-xs space-y-1">
          <div className="flex justify-between">
            <span className="text-gray-500">Proceeds</span>
            <span>{fmtEur(s.totalProceedsEur)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Cost Basis</span>
            <span>{fmtEur(s.totalCostBasisEur)}</span>
          </div>
          <div className="flex justify-between font-medium border-t pt-1 mt-1">
            <span>Net</span>
            <span className={isGain ? 'text-green-600' : 'text-red-600'}>{fmtEur(s.netGainLossEur)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
