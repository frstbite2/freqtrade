"""Baseline: every table the platform had when migrations were introduced.

Before this, tables were created at start-up from the models. A database from that time already
has some or all of these tables, so each one is created only if it is missing; existing tables and
their rows are left exactly as they are.

Revision: 0001
Follows: nothing
"""

import sqlalchemy as sa
from alembic import op


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


TABLES = (
    "institutional_holding",
    "insider_transaction",
    "beneficial_owner",
    "price_coverage",
    "price_bar",
    "job_run",
    "institutional_manager",
    "institutional_filing",
    "insider_issuer",
    "insider_filing",
    "beneficial_issuer",
    "beneficial_filing",
    "audit_log",
)  # children before parents: the order they can be dropped in


def upgrade() -> None:  # noqa: C901  one independent branch per table
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "audit_log" not in existing:
        op.create_table(
            "audit_log",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("actor", sa.String(length=64), nullable=False),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("detail", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("audit_log", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_audit_log_action"), ["action"], unique=False)
            batch_op.create_index(batch_op.f("ix_audit_log_ts"), ["ts"], unique=False)
    if "beneficial_filing" not in existing:
        op.create_table(
            "beneficial_filing",
            sa.Column("accession", sa.String(length=20), nullable=False),
            sa.Column("issuer_cik", sa.Integer(), nullable=False),
            sa.Column("form", sa.String(length=16), nullable=False),
            sa.Column("schedule", sa.String(length=3), nullable=False),
            sa.Column("is_amendment", sa.Boolean(), nullable=False),
            sa.Column("amendment_number", sa.Integer(), nullable=True),
            sa.Column("structured", sa.Boolean(), nullable=False),
            sa.Column("filer_cik", sa.Integer(), nullable=True),
            sa.Column("filer_name", sa.Text(), nullable=True),
            sa.Column("cusip", sa.String(length=16), nullable=True),
            sa.Column("security_title", sa.Text(), nullable=True),
            sa.Column("event_date", sa.Date(), nullable=True),
            sa.Column("filed_date", sa.Date(), nullable=False),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("rule", sa.Text(), nullable=True),
            sa.Column("purpose", sa.Text(), nullable=True),
            sa.Column("issues", sa.JSON(), nullable=False),
            sa.Column("url", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("accession"),
        )
        with op.batch_alter_table("beneficial_filing", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_beneficial_filing_accepted_at"), ["accepted_at"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_beneficial_filing_filer_cik"), ["filer_cik"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_beneficial_filing_issuer_cik"), ["issuer_cik"], unique=False
            )
    if "beneficial_issuer" not in existing:
        op.create_table(
            "beneficial_issuer",
            sa.Column("cik", sa.Integer(), autoincrement=False, nullable=False),
            sa.Column("ticker", sa.String(length=16), nullable=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("history_since", sa.Date(), nullable=False),
            sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("failed_filings", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("cik"),
        )
        with op.batch_alter_table("beneficial_issuer", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_beneficial_issuer_ticker"), ["ticker"], unique=False
            )
    if "insider_filing" not in existing:
        op.create_table(
            "insider_filing",
            sa.Column("accession", sa.String(length=20), nullable=False),
            sa.Column("form_type", sa.String(length=4), nullable=False),
            sa.Column("issuer_cik", sa.Integer(), nullable=False),
            sa.Column("issuer_name", sa.Text(), nullable=False),
            sa.Column("issuer_ticker", sa.Text(), nullable=True),
            sa.Column("period_of_report", sa.Date(), nullable=True),
            sa.Column("filed_date", sa.Date(), nullable=False),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("original_filed_date", sa.Date(), nullable=True),
            sa.Column("aff10b5one", sa.Boolean(), nullable=True),
            sa.Column("owner_cik", sa.Integer(), nullable=False),
            sa.Column("owner_name", sa.Text(), nullable=False),
            sa.Column("is_director", sa.Boolean(), nullable=False),
            sa.Column("is_officer", sa.Boolean(), nullable=False),
            sa.Column("is_ten_percent_owner", sa.Boolean(), nullable=False),
            sa.Column("officer_title", sa.Text(), nullable=True),
            sa.Column("owners", sa.JSON(), nullable=False),
            sa.Column("remarks", sa.Text(), nullable=False),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("classifier_version", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("accession"),
        )
        with op.batch_alter_table("insider_filing", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_insider_filing_accepted_at"), ["accepted_at"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_insider_filing_issuer_cik"), ["issuer_cik"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_insider_filing_owner_cik"), ["owner_cik"], unique=False
            )
    if "insider_issuer" not in existing:
        op.create_table(
            "insider_issuer",
            sa.Column("cik", sa.Integer(), autoincrement=False, nullable=False),
            sa.Column("ticker", sa.String(length=16), nullable=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("history_since", sa.Date(), nullable=False),
            sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("failed_filings", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("cik"),
        )
        with op.batch_alter_table("insider_issuer", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_insider_issuer_ticker"), ["ticker"], unique=False)
    if "institutional_filing" not in existing:
        op.create_table(
            "institutional_filing",
            sa.Column("accession", sa.String(length=20), nullable=False),
            sa.Column("manager_cik", sa.Integer(), nullable=False),
            sa.Column("form", sa.String(length=10), nullable=False),
            sa.Column("period", sa.Date(), nullable=False),
            sa.Column("filed_date", sa.Date(), nullable=False),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("report_type", sa.Text(), nullable=False),
            sa.Column("is_amendment", sa.Boolean(), nullable=False),
            sa.Column("amendment_type", sa.Text(), nullable=True),
            sa.Column("confidential_omitted", sa.Boolean(), nullable=True),
            sa.Column("value_multiplier", sa.Integer(), nullable=False),
            sa.Column("entry_total", sa.Integer(), nullable=True),
            sa.Column("value_total", sa.Numeric(precision=28, scale=4), nullable=True),
            sa.Column("issues", sa.JSON(), nullable=False),
            sa.Column("url", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("accession"),
        )
        with op.batch_alter_table("institutional_filing", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_institutional_filing_accepted_at"), ["accepted_at"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_institutional_filing_manager_cik"), ["manager_cik"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_institutional_filing_period"), ["period"], unique=False
            )
    if "institutional_manager" not in existing:
        op.create_table(
            "institutional_manager",
            sa.Column("cik", sa.Integer(), autoincrement=False, nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("history_since", sa.Date(), nullable=False),
            sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("failed_filings", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("cik"),
        )
    if "job_run" not in existing:
        op.create_table(
            "job_run",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("job", sa.String(length=32), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=12), nullable=False),
            sa.Column("detail", sa.JSON(), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("job", "active"),
        )
        with op.batch_alter_table("job_run", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_job_run_job"), ["job"], unique=False)
            batch_op.create_index(batch_op.f("ix_job_run_started_at"), ["started_at"], unique=False)
    if "price_bar" not in existing:
        op.create_table(
            "price_bar",
            sa.Column("symbol", sa.String(length=10), nullable=False),
            sa.Column("timeframe", sa.String(length=4), nullable=False),
            sa.Column("adjustment", sa.String(length=8), nullable=False),
            sa.Column("source", sa.String(length=24), nullable=False),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("open", sa.Numeric(precision=24, scale=8), nullable=False),
            sa.Column("high", sa.Numeric(precision=24, scale=8), nullable=False),
            sa.Column("low", sa.Numeric(precision=24, scale=8), nullable=False),
            sa.Column("close", sa.Numeric(precision=24, scale=8), nullable=False),
            sa.Column("volume", sa.Numeric(precision=24, scale=8), nullable=False),
            sa.Column("trade_count", sa.Integer(), nullable=True),
            sa.Column("vwap", sa.Numeric(precision=24, scale=8), nullable=True),
            sa.PrimaryKeyConstraint("symbol", "timeframe", "adjustment", "source", "ts"),
        )
    if "price_coverage" not in existing:
        op.create_table(
            "price_coverage",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("symbol", sa.String(length=10), nullable=False),
            sa.Column("timeframe", sa.String(length=4), nullable=False),
            sa.Column("adjustment", sa.String(length=8), nullable=False),
            sa.Column("source", sa.String(length=24), nullable=False),
            sa.Column("start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end", sa.DateTime(timezone=True), nullable=False),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("rejected_bars", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("price_coverage", schema=None) as batch_op:
            batch_op.create_index(
                "ix_price_coverage_key",
                ["symbol", "timeframe", "adjustment", "source"],
                unique=False,
            )
    if "beneficial_owner" not in existing:
        op.create_table(
            "beneficial_owner",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("accession", sa.String(length=20), nullable=False),
            sa.Column("row_index", sa.Integer(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("cik", sa.Integer(), nullable=True),
            sa.Column("shares", sa.Numeric(precision=28, scale=4), nullable=True),
            sa.Column("percent", sa.Numeric(precision=9, scale=4), nullable=True),
            sa.Column("person_type", sa.Text(), nullable=True),
            sa.Column("sole_voting", sa.Numeric(precision=28, scale=4), nullable=True),
            sa.Column("shared_voting", sa.Numeric(precision=28, scale=4), nullable=True),
            sa.Column("sole_dispositive", sa.Numeric(precision=28, scale=4), nullable=True),
            sa.Column("shared_dispositive", sa.Numeric(precision=28, scale=4), nullable=True),
            sa.Column("issues", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(
                ["accession"],
                ["beneficial_filing.accession"],
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("accession", "row_index"),
        )
        with op.batch_alter_table("beneficial_owner", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_beneficial_owner_accession"), ["accession"], unique=False
            )
    if "insider_transaction" not in existing:
        op.create_table(
            "insider_transaction",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("accession", sa.String(length=20), nullable=False),
            sa.Column("row_index", sa.Integer(), nullable=False),
            sa.Column("table", sa.String(length=16), nullable=False),
            sa.Column("is_holding", sa.Boolean(), nullable=False),
            sa.Column("security_title", sa.Text(), nullable=True),
            sa.Column("transaction_date", sa.Date(), nullable=True),
            sa.Column("code", sa.String(length=2), nullable=True),
            sa.Column("equity_swap", sa.Boolean(), nullable=False),
            sa.Column("shares", sa.Numeric(precision=24, scale=6), nullable=True),
            sa.Column("price", sa.Numeric(precision=24, scale=6), nullable=True),
            sa.Column("acquired_disposed", sa.String(length=1), nullable=True),
            sa.Column("shares_after", sa.Numeric(precision=24, scale=6), nullable=True),
            sa.Column("ownership", sa.String(length=1), nullable=True),
            sa.Column("nature_of_ownership", sa.Text(), nullable=True),
            sa.Column("exercise_price", sa.Numeric(precision=24, scale=6), nullable=True),
            sa.Column("underlying_title", sa.Text(), nullable=True),
            sa.Column("underlying_shares", sa.Numeric(precision=24, scale=6), nullable=True),
            sa.Column("footnotes", sa.Text(), nullable=False),
            sa.Column("category", sa.String(length=32), nullable=False),
            sa.Column("plan_10b5_1", sa.Boolean(), nullable=False),
            sa.Column("plan_basis", sa.String(length=24), nullable=True),
            sa.Column("issues", sa.JSON(), nullable=False),
            sa.Column("signal", sa.String(length=20), nullable=True),
            sa.ForeignKeyConstraint(
                ["accession"],
                ["insider_filing.accession"],
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("accession", "row_index"),
        )
        with op.batch_alter_table("insider_transaction", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_insider_transaction_accession"), ["accession"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_insider_transaction_category"), ["category"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_insider_transaction_signal"), ["signal"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_insider_transaction_transaction_date"),
                ["transaction_date"],
                unique=False,
            )
    if "institutional_holding" not in existing:
        op.create_table(
            "institutional_holding",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("accession", sa.String(length=20), nullable=False),
            sa.Column("row_index", sa.Integer(), nullable=False),
            sa.Column("issuer_name", sa.Text(), nullable=False),
            sa.Column("title_of_class", sa.Text(), nullable=True),
            sa.Column("cusip", sa.String(length=16), nullable=False),
            sa.Column("value", sa.Numeric(precision=28, scale=4), nullable=False),
            sa.Column("amount", sa.Numeric(precision=28, scale=4), nullable=False),
            sa.Column("amount_type", sa.String(length=8), nullable=True),
            sa.Column("put_call", sa.String(length=8), nullable=True),
            sa.Column("discretion", sa.Text(), nullable=True),
            sa.Column("other_managers", sa.Text(), nullable=True),
            sa.Column("voting_sole", sa.Numeric(precision=28, scale=4), nullable=True),
            sa.Column("voting_shared", sa.Numeric(precision=28, scale=4), nullable=True),
            sa.Column("voting_none", sa.Numeric(precision=28, scale=4), nullable=True),
            sa.Column("issues", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(
                ["accession"],
                ["institutional_filing.accession"],
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("accession", "row_index"),
        )
        with op.batch_alter_table("institutional_holding", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_institutional_holding_accession"), ["accession"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_institutional_holding_cusip"), ["cusip"], unique=False
            )

    # Tables made by early versions of the platform lack two columns added later (found by
    # rebuilding the database as each past commit created it). Existing rows get 0: for
    # classifier_version that is below every real version, so ingestion re-classifies them; for
    # failed_filings it stands until the next ingestion run overwrites it.
    inspector = sa.inspect(op.get_bind())
    for table, column in (
        ("insider_filing", "classifier_version"),
        ("insider_issuer", "failed_filings"),
    ):
        if table in existing and column not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(
                table, sa.Column(column, sa.Integer(), nullable=False, server_default="0")
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Nothing may write between the emptiness check below and the drop.
        bind.execute(sa.text(f"LOCK TABLE {', '.join(TABLES)} IN ACCESS EXCLUSIVE MODE"))
    holding = [t for t in TABLES if bind.execute(sa.text(f"SELECT 1 FROM {t} LIMIT 1")).first()]
    if holding:
        # Going below the baseline means dropping everything; never do that to stored data.
        raise RuntimeError(f"refusing to drop tables that hold data: {holding}")
    for table in TABLES:
        op.drop_table(table)
