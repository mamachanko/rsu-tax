export interface SchwabTransaction {
  id?: number;
  symbol: string;
  name?: string;
  quantity: number;
  dateAcquired: string;    // YYYY-MM-DD — may equal dateSold if not available in CSV
  dateSold: string;        // YYYY-MM-DD
  proceedsUsd: number;
  costBasisUsd: number;
  gainLossUsd: number;
  term: 'Short Term' | 'Long Term' | 'Unknown';
  washSale: number;
  costBasisMethod?: string;  // e.g. "Specific Lots", "FIFO"
  hasAcquisitionDate: boolean; // false when dateAcquired was not in CSV (using dateSold as fallback)
}

export interface ExchangeRate {
  date: string;            // YYYY-MM-DD
  usdToEur: number;        // 1 USD = X EUR (i.e., the reciprocal of ECB's EUR/USD rate)
}

export interface ComputedTransaction extends SchwabTransaction {
  exchangeRateSold: number;
  exchangeRateAcquired: number;
  proceedsEur: number;
  costBasisEur: number;
  gainLossEur: number;
  isSellToCover: boolean;
  verificationStatus: 'pass' | 'warn' | 'fail';
  verificationNotes: string[];
}

export interface VerificationCheck {
  name: string;
  status: 'pass' | 'warn' | 'fail';
  message: string;
}

export interface TaxSummary {
  taxYear: number;
  totalTransactions: number;
  voluntarySales: number;
  sellToCoverSales: number;
  totalProceedsEur: number;
  totalCostBasisEur: number;
  netGainLossEur: number;
  voluntaryGainLossEur: number;
  sellToCoverGainLossEur: number;
  totalProceedsUsd: number;
  totalCostBasisUsd: number;
  netGainLossUsd: number;
}

export interface ColumnMapping {
  symbol: string;
  name: string;
  quantity: string;
  dateAcquired: string;
  dateSold: string;
  proceeds: string;
  costBasis: string;
  gainLoss: string;
  term: string;
  washSale: string;
  costBasisMethod: string;
  stGainLoss: string;
  ltGainLoss: string;
}
