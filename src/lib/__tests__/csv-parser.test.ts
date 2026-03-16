import { describe, it, expect } from 'vitest';
import { parseSchwabCsv, detectColumnMapping } from '../csv-parser';

describe('detectColumnMapping', () => {
  it('maps standard Schwab headers', () => {
    const headers = ['Symbol', 'Quantity', 'Date Acquired', 'Date Sold', 'Proceeds', 'Cost Basis', 'Gain/Loss', 'Term', 'Wash Sale'];
    const mapping = detectColumnMapping(headers);
    expect(mapping.symbol).toBe('Symbol');
    expect(mapping.quantity).toBe('Quantity');
    expect(mapping.dateAcquired).toBe('Date Acquired');
    expect(mapping.dateSold).toBe('Date Sold');
    expect(mapping.proceeds).toBe('Proceeds');
    expect(mapping.costBasis).toBe('Cost Basis');
    expect(mapping.gainLoss).toBe('Gain/Loss');
    expect(mapping.term).toBe('Term');
    expect(mapping.washSale).toBe('Wash Sale');
  });

  it('maps actual Schwab Realized Gain/Loss headers', () => {
    const headers = [
      'Symbol', 'Name', 'Closed Date', 'Quantity', 'Closing Price',
      'Cost Basis Method', 'Proceeds', 'Cost Basis (CB)',
      'Total Gain/Loss ($)', 'Total Gain/Loss (%)',
      'Long Term (LT) Gain/Loss ($)', 'Long Term (LT) Gain/Loss (%)',
      'Short Term (ST) Gain/Loss ($)', 'Short Term (ST) Gain/Loss (%)',
      'Wash Sale?', 'Disallowed Loss',
    ];
    const mapping = detectColumnMapping(headers);
    expect(mapping.symbol).toBe('Symbol');
    expect(mapping.name).toBe('Name');
    expect(mapping.dateSold).toBe('Closed Date');
    expect(mapping.quantity).toBe('Quantity');
    expect(mapping.proceeds).toBe('Proceeds');
    expect(mapping.costBasis).toBe('Cost Basis (CB)');
    expect(mapping.gainLoss).toBe('Total Gain/Loss ($)');
    expect(mapping.costBasisMethod).toBe('Cost Basis Method');
    expect(mapping.ltGainLoss).toBe('Long Term (LT) Gain/Loss ($)');
    expect(mapping.stGainLoss).toBe('Short Term (ST) Gain/Loss ($)');
    expect(mapping.washSale).toBe('Wash Sale?');
    expect(mapping.dateAcquired).toBe('__none__');
  });

  it('handles alternative header names', () => {
    const headers = ['Security', 'Shares', 'Acquisition Date', 'Close Date', 'Total Proceeds', 'Adjusted Cost Basis', 'Realized Gain/Loss'];
    const mapping = detectColumnMapping(headers);
    expect(mapping.symbol).toBe('Security');
    expect(mapping.quantity).toBe('Shares');
    expect(mapping.dateAcquired).toBe('Acquisition Date');
    expect(mapping.dateSold).toBe('Close Date');
    expect(mapping.proceeds).toBe('Total Proceeds');
    expect(mapping.costBasis).toBe('Adjusted Cost Basis');
    expect(mapping.gainLoss).toBe('Realized Gain/Loss');
  });
});

describe('parseSchwabCsv', () => {
  it('parses a basic CSV with standard columns', () => {
    const csv = `Symbol,Quantity,Date Acquired,Date Sold,Proceeds,Cost Basis,Gain/Loss,Term
GOOG,10,01/15/2023,06/20/2024,"$1,500.00","$1,200.00","$300.00",Long Term
GOOG,5,06/20/2024,06/20/2024,$750.00,$748.00,$2.00,Short Term`;

    const result = parseSchwabCsv(csv);
    expect(result.transactions).toHaveLength(2);

    const t1 = result.transactions[0];
    expect(t1.symbol).toBe('GOOG');
    expect(t1.quantity).toBe(10);
    expect(t1.dateAcquired).toBe('2023-01-15');
    expect(t1.dateSold).toBe('2024-06-20');
    expect(t1.proceedsUsd).toBe(1500);
    expect(t1.costBasisUsd).toBe(1200);
    expect(t1.gainLossUsd).toBe(300);
    expect(t1.term).toBe('Long Term');
    expect(t1.hasAcquisitionDate).toBe(true);
  });

  it('parses actual Schwab Realized Gain/Loss format', () => {
    const csv = `"Realized Gain/Loss for ...482 for 01/01/2025 to 12/31/2025 as of Sat Mar 14  09:23:17 EDT 2026","","","","","","","","","","","","","","","","","","","","","","",""
"Symbol","Name","Closed Date","Quantity","Closing Price","Cost Basis Method","Proceeds","Cost Basis (CB)","Total Gain/Loss ($)","Total Gain/Loss (%)","Long Term (LT) Gain/Loss ($)","Long Term (LT) Gain/Loss (%)","Short Term (ST) Gain/Loss ($)","Short Term (ST) Gain/Loss (%)","Wash Sale?","Disallowed Loss","Transaction Closed Date","Transaction Cost Basis","Total Transaction Gain/Loss ($)","Total Transaction Gain/Loss (%)","LT Transaction Gain/Loss ($)","LT Transaction Gain/Loss (%)","ST Transaction Gain/Loss ($)","ST Transaction Gain/Loss (%)"
"XYZC","EXAMPLE CORP","03/15/2025","45","$187.32","Specific Lots","$8,429.40","$8,312.55","$116.85","1.405717340165%","--","--","$116.85","1.405717340165214%","No","","03/15/2025","","","","","","",""
"XYZC","EXAMPLE CORP","07/10/2025","150","$195.40","FIFO","$29,310.00","$28,475.30","$834.70","2.931266417498%","--","--","$834.70","2.931266417498159%","No","","07/10/2025","","","","","","",""
"Total","","","","","","$50,371.90","$49,629.03","$742.87","1.496841458498%","$0.00","N/A","$742.87","1.496841458498372%","","","","","","","","","",""`;

    const result = parseSchwabCsv(csv);
    expect(result.transactions).toHaveLength(2);

    const t1 = result.transactions[0];
    expect(t1.symbol).toBe('XYZC');
    expect(t1.name).toBe('EXAMPLE CORP');
    expect(t1.quantity).toBe(45);
    expect(t1.dateSold).toBe('2025-03-15');
    expect(t1.proceedsUsd).toBe(8429.40);
    expect(t1.costBasisUsd).toBe(8312.55);
    expect(t1.gainLossUsd).toBe(116.85);
    expect(t1.term).toBe('Short Term');
    expect(t1.costBasisMethod).toBe('Specific Lots');
    expect(t1.washSale).toBe(0);
    expect(t1.hasAcquisitionDate).toBe(false);
    // dateAcquired should fall back to dateSold
    expect(t1.dateAcquired).toBe('2025-03-15');
  });

  it('detects term from ST/LT gain/loss columns', () => {
    const csv = `"Symbol","Name","Closed Date","Quantity","Proceeds","Cost Basis (CB)","Total Gain/Loss ($)","Long Term (LT) Gain/Loss ($)","Short Term (ST) Gain/Loss ($)"
"ABCD","ACME","06/15/2025","10","$1000.00","$900.00","$100.00","--","$100.00"
"ABCD","ACME","06/15/2025","10","$1000.00","$900.00","$100.00","$100.00","--"`;

    const result = parseSchwabCsv(csv);
    expect(result.transactions[0].term).toBe('Short Term');
    expect(result.transactions[1].term).toBe('Long Term');
  });

  it('handles negative gains (losses) with -$ format', () => {
    const csv = `"Symbol","Name","Closed Date","Quantity","Proceeds","Cost Basis (CB)","Total Gain/Loss ($)","Long Term (LT) Gain/Loss ($)","Short Term (ST) Gain/Loss ($)"
"ABCD","ACME","09/15/2025","73","$25,727.98","$26,012.82","-$284.84","--","-$284.84"`;

    const result = parseSchwabCsv(csv);
    expect(result.transactions[0].gainLossUsd).toBe(-284.84);
  });

  it('handles negative gains with parentheses format', () => {
    const csv = `Symbol,Quantity,Date Acquired,Date Sold,Proceeds,Cost Basis,Gain/Loss,Term
AAPL,3,03/01/2024,09/15/2024,$450.00,$500.00,($50.00),Short Term`;

    const result = parseSchwabCsv(csv);
    expect(result.transactions[0].gainLossUsd).toBe(-50);
  });

  it('skips total/summary rows', () => {
    const csv = `Symbol,Quantity,Date Acquired,Date Sold,Proceeds,Cost Basis,Gain/Loss,Term
GOOG,10,01/15/2023,06/20/2024,$1500.00,$1200.00,$300.00,Long Term
Total,,,,,$1200.00,$300.00,`;

    const result = parseSchwabCsv(csv);
    expect(result.transactions).toHaveLength(1);
  });

  it('handles Schwab header/footer noise', () => {
    const csv = `"Realized Gain/Loss"
"As of 12/31/2024"
Symbol,Quantity,Date Acquired,Date Sold,Proceeds,Cost Basis,Gain/Loss
GOOG,10,01/15/2023,06/20/2024,$1500.00,$1200.00,$300.00
***End of Report***`;

    const result = parseSchwabCsv(csv);
    expect(result.transactions).toHaveLength(1);
    expect(result.transactions[0].symbol).toBe('GOOG');
  });

  it('warns when no dateAcquired column is found', () => {
    const csv = `"Symbol","Closed Date","Quantity","Proceeds","Cost Basis (CB)","Total Gain/Loss ($)"
"ABCD","06/15/2025","10","$1000.00","$900.00","$100.00"`;

    const result = parseSchwabCsv(csv);
    expect(result.warnings.some(w => w.includes('Date Acquired'))).toBe(true);
    expect(result.transactions[0].hasAcquisitionDate).toBe(false);
  });
});
