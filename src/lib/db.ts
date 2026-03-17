import initSqlJs, { Database } from 'sql.js';
import type { SchwabTransaction, ExchangeRate, ComputedTransaction } from '../types';

const DB_NAME = 'rsu-tax-db';

let db: Database | null = null;

export async function initDb(): Promise<Database> {
  if (db) return db;

  const SQL = await initSqlJs({
    locateFile: (file: string) => `/${file}`,
  });

  // Try to load from IndexedDB
  const saved = await loadFromIndexedDB();
  if (saved) {
    db = new SQL.Database(saved);
  } else {
    db = new SQL.Database();
  }

  db.run(`
    CREATE TABLE IF NOT EXISTS transactions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      symbol TEXT NOT NULL,
      name TEXT,
      quantity REAL NOT NULL,
      date_acquired TEXT NOT NULL,
      date_sold TEXT NOT NULL,
      proceeds_usd REAL NOT NULL,
      cost_basis_usd REAL NOT NULL,
      gain_loss_usd REAL NOT NULL,
      term TEXT NOT NULL DEFAULT 'Unknown',
      wash_sale REAL NOT NULL DEFAULT 0,
      cost_basis_method TEXT,
      has_acquisition_date INTEGER NOT NULL DEFAULT 1
    )
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS exchange_rates (
      date TEXT PRIMARY KEY,
      usd_to_eur REAL NOT NULL
    )
  `);

  await saveToIndexedDB(db);
  return db;
}

export function getDb(): Database {
  if (!db) throw new Error('Database not initialized. Call initDb() first.');
  return db;
}

// --- Transactions ---

export function insertTransactions(transactions: SchwabTransaction[]): void {
  const d = getDb();
  d.run('DELETE FROM transactions');
  const stmt = d.prepare(
    `INSERT INTO transactions (symbol, name, quantity, date_acquired, date_sold, proceeds_usd, cost_basis_usd, gain_loss_usd, term, wash_sale, cost_basis_method, has_acquisition_date)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  );
  for (const t of transactions) {
    stmt.run([t.symbol, t.name ?? null, t.quantity, t.dateAcquired, t.dateSold, t.proceedsUsd, t.costBasisUsd, t.gainLossUsd, t.term, t.washSale, t.costBasisMethod ?? null, t.hasAcquisitionDate ? 1 : 0]);
  }
  stmt.free();
  saveToIndexedDB(d);
}

export function getTransactions(): SchwabTransaction[] {
  const d = getDb();
  const results = d.exec('SELECT * FROM transactions ORDER BY date_sold, date_acquired');
  if (results.length === 0) return [];
  return results[0].values.map((row: unknown[]) => ({
    id: row[0] as number,
    symbol: row[1] as string,
    name: (row[2] as string) || undefined,
    quantity: row[3] as number,
    dateAcquired: row[4] as string,
    dateSold: row[5] as string,
    proceedsUsd: row[6] as number,
    costBasisUsd: row[7] as number,
    gainLossUsd: row[8] as number,
    term: row[9] as SchwabTransaction['term'],
    washSale: row[10] as number,
    costBasisMethod: (row[11] as string) || undefined,
    hasAcquisitionDate: (row[12] as number) === 1,
  }));
}

export function clearTransactions(): void {
  const d = getDb();
  d.run('DELETE FROM transactions');
  saveToIndexedDB(d);
}

// --- Exchange Rates ---

export function insertExchangeRates(rates: ExchangeRate[]): void {
  const d = getDb();
  const stmt = d.prepare(
    'INSERT OR REPLACE INTO exchange_rates (date, usd_to_eur) VALUES (?, ?)'
  );
  for (const r of rates) {
    stmt.run([r.date, r.usdToEur]);
  }
  stmt.free();
  saveToIndexedDB(d);
}

export function getExchangeRates(): Map<string, number> {
  const d = getDb();
  const results = d.exec('SELECT date, usd_to_eur FROM exchange_rates ORDER BY date');
  const map = new Map<string, number>();
  if (results.length === 0) return map;
  for (const row of results[0].values) {
    map.set(row[0] as string, row[1] as number);
  }
  return map;
}

export function getCachedRateDateRange(): { min: string; max: string } | null {
  const d = getDb();
  const results = d.exec('SELECT MIN(date), MAX(date) FROM exchange_rates');
  if (results.length === 0 || !results[0].values[0][0]) return null;
  return {
    min: results[0].values[0][0] as string,
    max: results[0].values[0][1] as string,
  };
}

// --- IndexedDB persistence ---

function loadFromIndexedDB(): Promise<Uint8Array | null> {
  return new Promise((resolve) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore('db');
    };
    request.onsuccess = () => {
      const idb = request.result;
      const tx = idb.transaction('db', 'readonly');
      const store = tx.objectStore('db');
      const get = store.get('data');
      get.onsuccess = () => resolve(get.result ?? null);
      get.onerror = () => resolve(null);
    };
    request.onerror = () => resolve(null);
  });
}

function saveToIndexedDB(database: Database): Promise<void> {
  return new Promise((resolve) => {
    const data = database.export();
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore('db');
    };
    request.onsuccess = () => {
      const idb = request.result;
      const tx = idb.transaction('db', 'readwrite');
      const store = tx.objectStore('db');
      store.put(data, 'data');
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    };
    request.onerror = () => resolve();
  });
}

export function exportDbForVerification(): { transactions: SchwabTransaction[]; rates: Map<string, number> } {
  return {
    transactions: getTransactions(),
    rates: getExchangeRates(),
  };
}

// Re-export ComputedTransaction for convenience
export type { ComputedTransaction };
