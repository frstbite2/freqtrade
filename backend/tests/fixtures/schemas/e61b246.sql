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
