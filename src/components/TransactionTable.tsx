import { useState } from 'react';
import type { ComputedTransaction } from '../types';

interface Props {
  transactions: ComputedTransaction[];
}

type SortField = 'dateSold' | 'dateAcquired' | 'symbol' | 'gainLossEur' | 'gainLossUsd' | 'proceedsEur';
type SortDir = 'asc' | 'desc';

export function TransactionTable({ transactions }: Props) {
  const [sortField, setSortField] = useState<SortField>('dateSold');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [filter, setFilter] = useState<'all' | 'voluntary' | 'sell-to-cover'>('all');

  const filtered = transactions.filter((t) => {
    if (filter === 'voluntary') return !t.isSellToCover;
    if (filter === 'sell-to-cover') return t.isSellToCover;
    return true;
  });

  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0;
    switch (sortField) {
      case 'dateSold': cmp = a.dateSold.localeCompare(b.dateSold); break;
      case 'dateAcquired': cmp = a.dateAcquired.localeCompare(b.dateAcquired); break;
      case 'symbol': cmp = a.symbol.localeCompare(b.symbol); break;
      case 'gainLossEur': cmp = a.gainLossEur - b.gainLossEur; break;
      case 'gainLossUsd': cmp = a.gainLossUsd - b.gainLossUsd; break;
      case 'proceedsEur': cmp = a.proceedsEur - b.proceedsEur; break;
    }
    return sortDir === 'asc' ? cmp : -cmp;
  });

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const SortHeader = ({ field, children }: { field: SortField; children: React.ReactNode }) => (
    <th
      className="px-2 py-2 text-left cursor-pointer hover:bg-gray-100 select-none text-xs"
      onClick={() => toggleSort(field)}
    >
      {children} {sortField === field ? (sortDir === 'asc' ? '↑' : '↓') : ''}
    </th>
  );

  const statusIcon = (status: string) => {
    if (status === 'pass') return <span className="text-green-500" title="Verified">&#10003;</span>;
    if (status === 'warn') return <span className="text-yellow-500" title="Warning">&#9888;</span>;
    return <span className="text-red-500" title="Error">&#10007;</span>;
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-2 items-center text-sm">
        <span className="text-gray-500">Filter:</span>
        {(['all', 'voluntary', 'sell-to-cover'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
              filter === f ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {f === 'all' ? `All (${transactions.length})` :
             f === 'voluntary' ? `Voluntary (${transactions.filter(t => !t.isSellToCover).length})` :
             `Sell-to-Cover (${transactions.filter(t => t.isSellToCover).length})`}
          </button>
        ))}
      </div>

      <div className="overflow-x-auto border rounded">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 sticky top-0">
            <tr>
              <th className="px-2 py-2 text-left text-xs w-6"></th>
              <SortHeader field="symbol">Symbol</SortHeader>
              <th className="px-2 py-2 text-right text-xs">Qty</th>
              <SortHeader field="dateAcquired">Acquired</SortHeader>
              <SortHeader field="dateSold">Sold</SortHeader>
              <th className="px-2 py-2 text-left text-xs">Term</th>
              <th className="px-2 py-2 text-right text-xs">Proceeds ($)</th>
              <th className="px-2 py-2 text-right text-xs">Cost ($)</th>
              <SortHeader field="gainLossUsd">G/L ($)</SortHeader>
              <th className="px-2 py-2 text-right text-xs">Rate (Acq)</th>
              <th className="px-2 py-2 text-right text-xs">Rate (Sold)</th>
              <SortHeader field="proceedsEur">Proceeds (&#8364;)</SortHeader>
              <th className="px-2 py-2 text-right text-xs">Cost (&#8364;)</th>
              <SortHeader field="gainLossEur">G/L (&#8364;)</SortHeader>
              <th className="px-2 py-2 text-left text-xs">Type</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((t, i) => (
              <tr
                key={i}
                className={`border-t hover:bg-gray-50 ${t.isSellToCover ? 'bg-gray-25 opacity-70' : ''}`}
                title={t.verificationNotes.length > 0 ? t.verificationNotes.join('\n') : undefined}
              >
                <td className="px-2 py-1.5">{statusIcon(t.verificationStatus)}</td>
                <td className="px-2 py-1.5 font-medium">{t.symbol}</td>
                <td className="px-2 py-1.5 text-right">{t.quantity.toFixed(4)}</td>
                <td className="px-2 py-1.5">{t.hasAcquisitionDate ? t.dateAcquired : <span className="text-gray-400" title="Using sale date (acquisition date not in CSV)">N/A</span>}</td>
                <td className="px-2 py-1.5">{t.dateSold}</td>
                <td className="px-2 py-1.5">{t.term === 'Short Term' ? 'ST' : t.term === 'Long Term' ? 'LT' : '-'}</td>
                <td className="px-2 py-1.5 text-right">{t.proceedsUsd.toFixed(2)}</td>
                <td className="px-2 py-1.5 text-right">{t.costBasisUsd.toFixed(2)}</td>
                <td className={`px-2 py-1.5 text-right font-medium ${t.gainLossUsd >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {t.gainLossUsd.toFixed(2)}
                </td>
                <td className="px-2 py-1.5 text-right text-gray-500">{t.exchangeRateAcquired.toFixed(4)}</td>
                <td className="px-2 py-1.5 text-right text-gray-500">{t.exchangeRateSold.toFixed(4)}</td>
                <td className="px-2 py-1.5 text-right">{t.proceedsEur.toFixed(2)}</td>
                <td className="px-2 py-1.5 text-right">{t.costBasisEur.toFixed(2)}</td>
                <td className={`px-2 py-1.5 text-right font-medium ${t.gainLossEur >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {t.gainLossEur.toFixed(2)}
                </td>
                <td className="px-2 py-1.5">
                  <span className={`px-1.5 py-0.5 rounded text-xs ${
                    t.isSellToCover ? 'bg-gray-100 text-gray-600' : 'bg-blue-50 text-blue-700'
                  }`}>
                    {t.isSellToCover ? 'S2C' : 'Vol'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-400">
        Showing {sorted.length} of {transactions.length} transactions.
        Exchange rates from ECB via Frankfurter API.
      </p>
    </div>
  );
}
