CREATE TABLE audit_log (
	id INTEGER NOT NULL, 
	ts DATETIME NOT NULL, 
	actor VARCHAR(64) NOT NULL, 
	action VARCHAR(64) NOT NULL, 
	detail JSON NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_audit_log_ts ON audit_log (ts);
CREATE INDEX ix_audit_log_action ON audit_log (action);
CREATE TABLE insider_issuer (
	cik INTEGER NOT NULL, 
	ticker VARCHAR(16), 
	name TEXT NOT NULL, 
	history_since DATE NOT NULL, 
	last_ingested_at DATETIME NOT NULL, 
	failed_filings INTEGER NOT NULL, 
	PRIMARY KEY (cik)
);
CREATE INDEX ix_insider_issuer_ticker ON insider_issuer (ticker);
CREATE TABLE insider_filing (
	accession VARCHAR(20) NOT NULL, 
	form_type VARCHAR(4) NOT NULL, 
	issuer_cik INTEGER NOT NULL, 
	issuer_name TEXT NOT NULL, 
	issuer_ticker TEXT, 
	period_of_report DATE, 
	filed_date DATE NOT NULL, 
	accepted_at DATETIME NOT NULL, 
	original_filed_date DATE, 
	aff10b5one BOOLEAN, 
	owner_cik INTEGER NOT NULL, 
	owner_name TEXT NOT NULL, 
	is_director BOOLEAN NOT NULL, 
	is_officer BOOLEAN NOT NULL, 
	is_ten_percent_owner BOOLEAN NOT NULL, 
	officer_title TEXT, 
	owners JSON NOT NULL, 
	remarks TEXT NOT NULL, 
	url TEXT NOT NULL, 
	classifier_version INTEGER NOT NULL, 
	PRIMARY KEY (accession)
);
CREATE INDEX ix_insider_filing_issuer_cik ON insider_filing (issuer_cik);
CREATE INDEX ix_insider_filing_accepted_at ON insider_filing (accepted_at);
CREATE INDEX ix_insider_filing_owner_cik ON insider_filing (owner_cik);
CREATE TABLE price_bar (
	symbol VARCHAR(10) NOT NULL, 
	timeframe VARCHAR(4) NOT NULL, 
	adjustment VARCHAR(8) NOT NULL, 
	source VARCHAR(24) NOT NULL, 
	ts DATETIME NOT NULL, 
	open NUMERIC(24, 8) NOT NULL, 
	high NUMERIC(24, 8) NOT NULL, 
	low NUMERIC(24, 8) NOT NULL, 
	close NUMERIC(24, 8) NOT NULL, 
	volume NUMERIC(24, 8) NOT NULL, 
	trade_count INTEGER, 
	vwap NUMERIC(24, 8), 
	PRIMARY KEY (symbol, timeframe, adjustment, source, ts)
);
CREATE TABLE price_coverage (
	id INTEGER NOT NULL, 
	symbol VARCHAR(10) NOT NULL, 
	timeframe VARCHAR(4) NOT NULL, 
	adjustment VARCHAR(8) NOT NULL, 
	source VARCHAR(24) NOT NULL, 
	start DATETIME NOT NULL, 
	"end" DATETIME NOT NULL, 
	fetched_at DATETIME NOT NULL, 
	rejected_bars INTEGER NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_price_coverage_key ON price_coverage (symbol, timeframe, adjustment, source);
CREATE TABLE insider_transaction (
	id INTEGER NOT NULL, 
	accession VARCHAR(20) NOT NULL, 
	row_index INTEGER NOT NULL, 
	"table" VARCHAR(16) NOT NULL, 
	is_holding BOOLEAN NOT NULL, 
	security_title TEXT, 
	transaction_date DATE, 
	code VARCHAR(2), 
	equity_swap BOOLEAN NOT NULL, 
	shares NUMERIC(24, 6), 
	price NUMERIC(24, 6), 
	acquired_disposed VARCHAR(1), 
	shares_after NUMERIC(24, 6), 
	ownership VARCHAR(1), 
	nature_of_ownership TEXT, 
	exercise_price NUMERIC(24, 6), 
	underlying_title TEXT, 
	underlying_shares NUMERIC(24, 6), 
	footnotes TEXT NOT NULL, 
	category VARCHAR(32) NOT NULL, 
	plan_10b5_1 BOOLEAN NOT NULL, 
	plan_basis VARCHAR(24), 
	issues JSON NOT NULL, 
	signal VARCHAR(20), 
	PRIMARY KEY (id), 
	UNIQUE (accession, row_index), 
	FOREIGN KEY(accession) REFERENCES insider_filing (accession)
);
CREATE INDEX ix_insider_transaction_category ON insider_transaction (category);
CREATE INDEX ix_insider_transaction_signal ON insider_transaction (signal);
CREATE INDEX ix_insider_transaction_accession ON insider_transaction (accession);
CREATE INDEX ix_insider_transaction_transaction_date ON insider_transaction (transaction_date);
