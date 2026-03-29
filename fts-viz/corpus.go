package main

// Document represents a text document in our corpus.
type Document struct {
	Title    string
	Category string
	Body     string
}

// SampleCorpus returns a varied set of documents ranging from tens to thousands of words,
// covering different topics to make FTS exploration interesting.
var SampleCorpus = []Document{
	{
		Title:    "German Tax Basics",
		Category: "tax",
		Body: `Capital gains from selling stocks in Germany are subject to a flat tax rate
called Abgeltungssteuer. This tax applies at a rate of 25% plus solidarity surcharge
and potentially church tax. The total effective rate is approximately 26.375% without
church tax. Each taxpayer has an annual exemption of 1000 EUR for capital gains
(Sparerpauschbetrag). Losses from stock sales can offset gains but cannot be used
against other income types. Brokers typically withhold this tax automatically for
German accounts, but foreign broker accounts require manual declaration in the
annual tax return (Einkommensteuererklarung). The relevant form is Anlage KAP.`,
	},
	{
		Title:    "RSU Vesting and Taxation",
		Category: "tax",
		Body: `Restricted Stock Units (RSUs) are a form of equity compensation where shares
are granted to employees subject to a vesting schedule. When RSUs vest, the fair
market value of the shares on the vesting date is treated as ordinary income for
tax purposes. In Germany, this vesting event triggers income tax (Lohnsteuer)
at the employee's marginal rate. The cost basis for future capital gains calculations
is set at the fair market value on the vesting date. When shares are later sold,
any difference between the sale price and the vesting-date fair market value is
treated as a capital gain or loss subject to Abgeltungssteuer. Sell-to-cover
transactions occur when the employer automatically sells a portion of vested shares
to cover the tax withholding obligation. These transactions typically have near-zero
capital gains since the sale happens at or very close to the vesting price.
Understanding the distinction between the income tax event at vesting and the
capital gains event at sale is crucial for accurate tax reporting.`,
	},
	{
		Title:    "Exchange Rate Conversion for Tax",
		Category: "tax",
		Body: `When reporting foreign currency transactions for German taxes, the European
Central Bank (ECB) reference exchange rate must be used for USD to EUR conversion.
The ECB publishes daily reference rates on business days. For transactions occurring
on weekends or holidays, the last available rate before the transaction date should
be used. The Frankfurter API provides free access to historical ECB rates. Each
transaction requires conversion of both the proceeds and the cost basis from USD
to EUR using the rate applicable on the respective dates. Gains and losses must
be calculated in EUR, not in the original currency. Using incorrect exchange rates
is a common source of errors in tax declarations involving foreign securities.
The Deutsche Bundesbank also publishes these rates and they can serve as a
cross-reference for verification.`,
	},
	{
		Title:    "Stock Market Basics",
		Category: "finance",
		Body: `The stock market is a collection of exchanges where shares of publicly traded
companies are bought and sold. Major exchanges include the New York Stock Exchange
(NYSE), NASDAQ, Frankfurt Stock Exchange (Frankfurter Wertpapierborse), and the
London Stock Exchange. Stock prices are determined by supply and demand. When more
people want to buy a stock than sell it, the price goes up. When more want to sell
than buy, it goes down. Investors can profit from stocks through capital gains
(selling at a higher price than purchased) and dividends (regular payments from
company profits). Important metrics for evaluating stocks include the
price-to-earnings ratio (P/E), earnings per share (EPS), dividend yield, and
market capitalization. Diversification across sectors and geographies helps
manage portfolio risk. Index funds and ETFs provide broad market exposure
at low cost.`,
	},
	{
		Title:    "Understanding Brokerage Statements",
		Category: "finance",
		Body: `Brokerage statements provide detailed records of all transactions in an
investment account. Key sections include realized gains and losses, which show
completed trades and their tax implications. The cost basis method (FIFO, LIFO,
specific lot identification) affects which shares are considered sold and
therefore the calculated gain or loss. Schwab, Fidelity, and other US brokers
provide downloadable CSV files of transaction history. Important fields include
the trade date, settlement date, quantity of shares, price per share, total
proceeds, cost basis, and gain or loss. For international investors, understanding
how wash sale rules and foreign tax credits apply is essential. Brokerage
statements also show dividend payments, interest earned, fees charged, and
margin activity. Reconciling brokerage statements with personal records ensures
accuracy in tax reporting.`,
	},
	{
		Title:    "CSV Data Processing",
		Category: "technical",
		Body: `Parsing CSV files requires handling various edge cases including quoted fields,
embedded commas, different line endings, and character encodings. The CSV format
lacks a formal standard, though RFC 4180 provides guidelines. Common issues
include inconsistent column headers across different export formats, missing
values, and date format variations (MM/DD/YYYY vs DD.MM.YYYY vs ISO 8601).
Robust CSV parsers should auto-detect delimiters and handle BOM markers.
When processing financial CSVs, special attention must be paid to number
formats where commas may be used as decimal separators in European locales.
Data validation after parsing is critical to catch malformed entries.`,
	},
	{
		Title:    "EUR USD Exchange Rate History",
		Category: "finance",
		Body: `The EUR/USD exchange rate has fluctuated significantly since the euro's
introduction in 1999. Starting near parity, the euro weakened initially before
strengthening to a peak of approximately 1.60 USD per EUR in 2008. Following
the global financial crisis and European debt crisis, the rate declined. In
recent years, the rate has typically ranged between 1.05 and 1.25. Exchange
rate movements are driven by interest rate differentials between the ECB and
Federal Reserve, inflation expectations, trade balances, and geopolitical
events. For tax purposes, daily fluctuations matter because even small rate
changes applied to large transactions can result in meaningful differences
in EUR-denominated gains or losses.`,
	},
	{
		Title:    "Quick Reference: Tax Rates",
		Category: "tax",
		Body: `Abgeltungssteuer: 25%. Solidarity surcharge: 5.5% of tax. Church tax: 8-9% of tax (if applicable). Effective rate without church tax: 26.375%. Annual exemption: 1000 EUR per person.`,
	},
	{
		Title:    "Build Systems and Automation",
		Category: "technical",
		Body: `Modern software projects rely on build systems and automation to ensure
consistent, reproducible builds. Python projects use tools like setuptools,
hatchling, and Poetry for package building, while Go uses its built-in module
system. Continuous integration pipelines run tests, linting, and build steps
automatically on every code change. GitHub Actions is a popular CI/CD platform
that allows defining workflows as YAML files. Typical CI steps include
dependency installation, unit testing, integration testing, static analysis,
and deployment. Build reproducibility requires pinning dependencies via lock
files (uv.lock, go.sum, package-lock.json). Automated testing catches
regressions early and reduces the burden of manual QA. Infrastructure as code
tools like Terraform extend automation beyond application code to cloud
resource management. Effective automation reduces human error and speeds up
the development lifecycle while maintaining quality.`,
	},
	{
		Title:    "Terminal User Interfaces",
		Category: "technical",
		Body: `Terminal user interfaces (TUIs) provide rich interactive experiences within
the terminal. The Elm Architecture, adopted by frameworks like Bubble Tea,
structures TUI applications around three concepts: a Model holding application
state, an Update function handling messages and producing new state, and a View
function rendering state to the terminal. Lip Gloss provides a CSS-like styling
system for terminal output, supporting colors, borders, padding, margins, and
alignment. The Bubbles library offers reusable TUI components like text inputs,
spinners, progress bars, viewports, and tables. ANSI escape codes underpin
terminal rendering, controlling cursor position, text color, and screen clearing.
Modern terminals support 256 colors and true color (16 million colors), enabling
sophisticated visual designs. Charm's ecosystem brings web-development ergonomics
to terminal applications. TUIs are especially valued by developers who prefer
keyboard-driven workflows and want to avoid the overhead of graphical
interfaces.`,
	},
	{
		Title:    "Full Text Search Internals",
		Category: "technical",
		Body: `SQLite's FTS5 extension provides full-text search capabilities using an
inverted index data structure. When text is inserted into an FTS5 table, it
is tokenized into individual terms. The default tokenizer splits on whitespace
and punctuation, then lowercases all tokens. Each term maps to a posting list
recording which documents contain it and at what positions. The BM25 ranking
algorithm scores documents by considering term frequency (how often a term
appears in a document), inverse document frequency (how rare a term is across
all documents), and document length normalization (longer documents are
slightly penalized). FTS5 supports prefix queries, phrase queries, NEAR
queries, column filters, and boolean operators (AND, OR, NOT). The highlight
function wraps matching terms in configurable markers for display. The snippet
function extracts the most relevant portion of a document around matching
terms. FTS5 auxiliary functions can access detailed match information including
the number of matching phrases, the number of tokens in each matching phrase,
and the positions of matches within documents. Custom ranking functions can be
built using these auxiliary values. The tokenizer is pluggable, allowing
support for different languages, stemming, and Unicode normalization.`,
	},
	{
		Title:    "Sell-to-Cover Explained",
		Category: "tax",
		Body: `When RSUs vest, the employer withholds shares to cover tax obligations, selling
them at or near the current market price. These are sell-to-cover transactions.
Since the sale price is essentially the same as the vesting price (which sets
the cost basis), the capital gain or loss is typically very small — often less
than one dollar. For tax reporting purposes, sell-to-cover transactions should
be identified and reported separately from voluntary sales. The income tax
component was already handled through payroll withholding at the time of vesting.
Only the (usually negligible) capital gain from the sell-to-cover needs to be
reported under Abgeltungssteuer. Identifying sell-to-cover transactions in
brokerage data often requires heuristic matching: same acquisition and sale date
combined with a near-zero gain is a strong indicator.`,
	},
}
