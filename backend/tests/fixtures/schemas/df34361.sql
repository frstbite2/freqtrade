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
CREATE TABLE beneficial_issuer (
	cik INTEGER NOT NULL, 
	ticker VARCHAR(16), 
	name TEXT NOT NULL, 
	history_since DATE NOT NULL, 
	last_ingested_at DATETIME NOT NULL, 
	failed_filings INTEGER NOT NULL, 
	PRIMARY KEY (cik)
);
CREATE INDEX ix_beneficial_issuer_ticker ON beneficial_issuer (ticker);
CREATE TABLE beneficial_filing (
	accession VARCHAR(20) NOT NULL, 
	issuer_cik INTEGER NOT NULL, 
	form VARCHAR(16) NOT NULL, 
	schedule VARCHAR(3) NOT NULL, 
	is_amendment BOOLEAN NOT NULL, 
	amendment_number INTEGER, 
	structured BOOLEAN NOT NULL, 
	filer_cik INTEGER, 
	filer_name TEXT, 
	cusip VARCHAR(16), 
	security_title TEXT, 
	event_date DATE, 
	filed_date DATE NOT NULL, 
	accepted_at DATETIME NOT NULL, 
	rule TEXT, 
	purpose TEXT, 
	issues JSON NOT NULL, 
	url TEXT NOT NULL, 
	PRIMARY KEY (accession)
);
CREATE INDEX ix_beneficial_filing_filer_cik ON beneficial_filing (filer_cik);
CREATE INDEX ix_beneficial_filing_issuer_cik ON beneficial_filing (issuer_cik);
CREATE INDEX ix_beneficial_filing_accepted_at ON beneficial_filing (accepted_at);
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
CREATE INDEX ix_insider_filing_owner_cik ON insider_filing (owner_cik);
CREATE INDEX ix_insider_filing_accepted_at ON insider_filing (accepted_at);
CREATE INDEX ix_insider_filing_issuer_cik ON insider_filing (issuer_cik);
CREATE TABLE institutional_manager (
	cik INTEGER NOT NULL, 
	name TEXT NOT NULL, 
	history_since DATE NOT NULL, 
	last_ingested_at DATETIME NOT NULL, 
	failed_filings INTEGER NOT NULL, 
	PRIMARY KEY (cik)
);
CREATE TABLE institutional_filing (
	accession VARCHAR(20) NOT NULL, 
	manager_cik INTEGER NOT NULL, 
	form VARCHAR(10) NOT NULL, 
	period DATE NOT NULL, 
	filed_date DATE NOT NULL, 
	accepted_at DATETIME NOT NULL, 
	report_type TEXT NOT NULL, 
	is_amendment BOOLEAN NOT NULL, 
	amendment_type TEXT, 
	confidential_omitted BOOLEAN, 
	value_multiplier INTEGER NOT NULL, 
	entry_total INTEGER, 
	value_total NUMERIC(28, 4), 
	issues JSON NOT NULL, 
	url TEXT NOT NULL, 
	PRIMARY KEY (accession)
);
CREATE INDEX ix_institutional_filing_period ON institutional_filing (period);
CREATE INDEX ix_institutional_filing_manager_cik ON institutional_filing (manager_cik);
CREATE INDEX ix_institutional_filing_accepted_at ON institutional_filing (accepted_at);
CREATE TABLE job_run (
	id INTEGER NOT NULL, 
	job VARCHAR(32) NOT NULL, 
	active BOOLEAN, 
	started_at DATETIME NOT NULL, 
	finished_at DATETIME, 
	status VARCHAR(12) NOT NULL, 
	detail JSON NOT NULL, 
	error TEXT, 
	PRIMARY KEY (id), 
	UNIQUE (job, active)
);
CREATE INDEX ix_job_run_job ON job_run (job);
CREATE INDEX ix_job_run_started_at ON job_run (started_at);
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
CREATE TABLE beneficial_owner (
	id INTEGER NOT NULL, 
	accession VARCHAR(20) NOT NULL, 
	row_index INTEGER NOT NULL, 
	name TEXT NOT NULL, 
	cik INTEGER, 
	shares NUMERIC(28, 4), 
	percent NUMERIC(9, 4), 
	person_type TEXT, 
	sole_voting NUMERIC(28, 4), 
	shared_voting NUMERIC(28, 4), 
	sole_dispositive NUMERIC(28, 4), 
	shared_dispositive NUMERIC(28, 4), 
	issues JSON NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (accession, row_index), 
	FOREIGN KEY(accession) REFERENCES beneficial_filing (accession)
);
CREATE INDEX ix_beneficial_owner_accession ON beneficial_owner (accession);
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
CREATE INDEX ix_insider_transaction_transaction_date ON insider_transaction (transaction_date);
CREATE INDEX ix_insider_transaction_accession ON insider_transaction (accession);
CREATE INDEX ix_insider_transaction_signal ON insider_transaction (signal);
CREATE TABLE institutional_holding (
	id INTEGER NOT NULL, 
	accession VARCHAR(20) NOT NULL, 
	row_index INTEGER NOT NULL, 
	issuer_name TEXT NOT NULL, 
	title_of_class TEXT, 
	cusip VARCHAR(16) NOT NULL, 
	value NUMERIC(28, 4) NOT NULL, 
	amount NUMERIC(28, 4) NOT NULL, 
	amount_type VARCHAR(8), 
	put_call VARCHAR(8), 
	discretion TEXT, 
	other_managers TEXT, 
	voting_sole NUMERIC(28, 4), 
	voting_shared NUMERIC(28, 4), 
	voting_none NUMERIC(28, 4), 
	issues JSON NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (accession, row_index), 
	FOREIGN KEY(accession) REFERENCES institutional_filing (accession)
);
CREATE INDEX ix_institutional_holding_accession ON institutional_holding (accession);
CREATE INDEX ix_institutional_holding_cusip ON institutional_holding (cusip);
