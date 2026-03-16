import { useState, useCallback } from 'react';
import { parseSchwabCsv, type ParseResult } from '../lib/csv-parser';
import type { SchwabTransaction } from '../types';

interface Props {
  onImport: (transactions: SchwabTransaction[]) => void;
}

export function CsvImport({ onImport }: Props) {
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback((file: File) => {
    setError(null);
    setParseResult(null);

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const text = e.target?.result as string;
        const result = parseSchwabCsv(text);
        if (result.transactions.length === 0) {
          setError('No valid transactions found in the CSV file. Please check the format.');
          return;
        }
        setParseResult(result);
      } catch (err) {
        setError(`Failed to parse CSV: ${err instanceof Error ? err.message : String(err)}`);
      }
    };
    reader.readAsText(file);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const confirmImport = () => {
    if (parseResult) {
      onImport(parseResult.transactions);
    }
  };

  return (
    <div className="space-y-4">
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          dragOver ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => document.getElementById('csv-file-input')?.click()}
      >
        <p className="text-lg font-medium text-gray-600">
          Drop your Schwab Realized Gains &amp; Losses CSV here
        </p>
        <p className="text-sm text-gray-400 mt-1">or click to browse</p>
        <input
          id="csv-file-input"
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleFileInput}
        />
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-3 text-red-700 text-sm">
          {error}
        </div>
      )}

      {parseResult && (
        <div className="space-y-3">
          {parseResult.warnings.length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
              <p className="font-medium text-yellow-800 text-sm">Warnings:</p>
              <ul className="text-sm text-yellow-700 list-disc list-inside mt-1">
                {parseResult.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="bg-white border rounded p-3">
            <p className="font-medium text-sm mb-2">
              Detected {parseResult.transactions.length} transaction(s)
            </p>
            <div className="text-xs text-gray-500 mb-2">
              Column mapping: {Object.entries(parseResult.mapping)
                .filter(([, v]) => v !== '__none__')
                .map(([k, v]) => `${k} → "${v}"`)
                .join(', ')}
            </div>

            <div className="overflow-x-auto max-h-64 overflow-y-auto">
              <table className="text-xs w-full">
                <thead>
                  <tr className="bg-gray-50">
                    <th className="px-2 py-1 text-left">Symbol</th>
                    <th className="px-2 py-1 text-left">Qty</th>
                    <th className="px-2 py-1 text-left">Acquired</th>
                    <th className="px-2 py-1 text-left">Sold</th>
                    <th className="px-2 py-1 text-right">Proceeds</th>
                    <th className="px-2 py-1 text-right">Cost Basis</th>
                    <th className="px-2 py-1 text-right">Gain/Loss</th>
                    <th className="px-2 py-1 text-left">Term</th>
                  </tr>
                </thead>
                <tbody>
                  {parseResult.transactions.slice(0, 20).map((t, i) => (
                    <tr key={i} className="border-t">
                      <td className="px-2 py-1">{t.symbol}</td>
                      <td className="px-2 py-1">{t.quantity}</td>
                      <td className="px-2 py-1">{t.hasAcquisitionDate ? t.dateAcquired : <span className="text-gray-400">N/A</span>}</td>
                      <td className="px-2 py-1">{t.dateSold}</td>
                      <td className="px-2 py-1 text-right">${t.proceedsUsd.toFixed(2)}</td>
                      <td className="px-2 py-1 text-right">${t.costBasisUsd.toFixed(2)}</td>
                      <td className={`px-2 py-1 text-right ${t.gainLossUsd >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        ${t.gainLossUsd.toFixed(2)}
                      </td>
                      <td className="px-2 py-1">{t.term}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {parseResult.transactions.length > 20 && (
                <p className="text-xs text-gray-400 mt-1 px-2">
                  ... and {parseResult.transactions.length - 20} more rows
                </p>
              )}
            </div>
          </div>

          <button
            onClick={confirmImport}
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 transition-colors text-sm font-medium"
          >
            Import {parseResult.transactions.length} Transactions
          </button>
        </div>
      )}
    </div>
  );
}
