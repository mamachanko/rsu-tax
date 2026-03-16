import { useState, useEffect, useCallback } from 'react';
import { initDb, insertTransactions, getTransactions, clearTransactions } from './lib/db';
import { ensureRatesForDates } from './lib/exchange-rates';
import { computeCapitalGains, computeSummary } from './lib/calculator';
import { runVerification } from './lib/verification';
import { CsvImport } from './components/CsvImport';
import { TransactionTable } from './components/TransactionTable';
import { Summary } from './components/Summary';
import { ExportButtons } from './components/ExportButtons';
import { VerificationPanel } from './components/VerificationPanel';
import type { SchwabTransaction, ComputedTransaction, TaxSummary, VerificationCheck } from './types';

type AppState = 'loading' | 'import' | 'processing' | 'results' | 'error';

export default function App() {
  const [state, setState] = useState<AppState>('loading');
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState('');
  const [computed, setComputed] = useState<ComputedTransaction[]>([]);
  const [summary, setSummary] = useState<TaxSummary | null>(null);
  const [checks, setChecks] = useState<VerificationCheck[]>([]);

  // Initialize DB on mount
  useEffect(() => {
    initDb()
      .then(() => {
        const existing = getTransactions();
        if (existing.length > 0) {
          processTransactions(existing);
        } else {
          setState('import');
        }
      })
      .catch((err) => {
        setError(`Failed to initialize database: ${err.message}`);
        setState('error');
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const processTransactions = useCallback(async (transactions: SchwabTransaction[]) => {
    setState('processing');
    setError(null);

    try {
      // Collect all unique dates needed for exchange rates
      setStatusMessage('Collecting transaction dates...');
      const allDates = new Set<string>();
      for (const t of transactions) {
        allDates.add(t.dateSold);
        if (t.hasAcquisitionDate) {
          allDates.add(t.dateAcquired);
        }
      }

      // Fetch exchange rates
      setStatusMessage(`Fetching ECB exchange rates for ${allDates.size} dates...`);
      const rates = await ensureRatesForDates([...allDates]);

      // Compute capital gains
      setStatusMessage('Computing capital gains in EUR...');
      const results = computeCapitalGains(transactions, rates);
      const taxSummary = computeSummary(results);

      // Run verification
      setStatusMessage('Running verification checks...');
      const verificationChecks = runVerification(results);

      setComputed(results);
      setSummary(taxSummary);
      setChecks(verificationChecks);
      setState('results');
    } catch (err) {
      setError(`Processing failed: ${err instanceof Error ? err.message : String(err)}`);
      setState('error');
    }
  }, []);

  const handleImport = useCallback(async (transactions: SchwabTransaction[]) => {
    insertTransactions(transactions);
    await processTransactions(transactions);
  }, [processTransactions]);

  const handleReset = useCallback(() => {
    clearTransactions();
    setComputed([]);
    setSummary(null);
    setChecks([]);
    setState('import');
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">RSU Tax Calculator</h1>
            <p className="text-xs text-gray-500">Capital Gains for German Tax Declaration (Abgeltungssteuer)</p>
          </div>
          {state === 'results' && (
            <button
              onClick={handleReset}
              className="text-sm text-gray-500 hover:text-gray-700 underline"
            >
              Import New CSV
            </button>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {state === 'loading' && (
          <div className="text-center py-12 text-gray-500">
            Initializing database...
          </div>
        )}

        {state === 'import' && (
          <section>
            <h2 className="text-lg font-semibold mb-3">Import Schwab CSV</h2>
            <CsvImport onImport={handleImport} />
          </section>
        )}

        {state === 'processing' && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-blue-600 border-t-transparent mb-3"></div>
            <p className="text-gray-600">{statusMessage}</p>
          </div>
        )}

        {state === 'error' && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-700">{error}</p>
            <button
              onClick={handleReset}
              className="mt-3 text-sm text-red-600 underline"
            >
              Start Over
            </button>
          </div>
        )}

        {state === 'results' && summary && (
          <>
            <section>
              <Summary summary={summary} />
            </section>

            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold">Verification</h2>
              </div>
              <VerificationPanel checks={checks} />
            </section>

            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold">Transactions</h2>
                <ExportButtons transactions={computed} summary={summary} checks={checks} />
              </div>
              <TransactionTable transactions={computed} />
            </section>
          </>
        )}
      </main>

      <footer className="border-t mt-12 py-4 text-center text-xs text-gray-400">
        Exchange rates from ECB via Frankfurter API. For information purposes only.
        All data stored locally in your browser.
      </footer>
    </div>
  );
}
