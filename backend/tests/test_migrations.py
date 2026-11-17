"""Schema migrations: fresh databases, databases created before migrations existed, and reversal.

Runs on SQLite always, and also on the database named by MIGRATION_TEST_DATABASE_URL when set
(CI points it at PostgreSQL). That database is emptied by these tests: never point it at real data.
"""

import os
import shutil
import sqlite3
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, date, datetime
from multiprocessing import get_context
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import sessionmaker

import backend.models
from backend.database.session import (
    Base,
    init_db,
    make_engine,
    migration_config,
    schema_drift,
)
from backend.models import AuditLog
from backend.models.insider import InsiderFiling, InsiderIssuer
from backend.services.insider_intelligence.classify import CLASSIFIER_VERSION


URLS = ["sqlite"] + [u for u in [os.environ.get("MIGRATION_TEST_DATABASE_URL")] if u]


@pytest.fixture(params=URLS, ids=lambda u: u.split(":")[0].split("+")[0])
def engine(request, tmp_path):
    url = f"sqlite:///{tmp_path}/m.sqlite" if request.param == "sqlite" else request.param
    engine = make_engine(url)
    wipe(engine)
    yield engine
    empty(engine)
    wipe(engine)
    engine.dispose()


def empty(engine):
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            if inspect(conn).has_table(table.name):
                conn.execute(table.delete())


def wipe(engine):
    with engine.begin() as conn:
        for table in set(inspect(conn).get_table_names()) & set(Base.metadata.tables):
            # A database these tests may empty holds no rows between tests. Rows mean the URL
            # points at something real.
            if conn.execute(text(f"SELECT 1 FROM {table} LIMIT 1")).first():
                raise RuntimeError(f"refusing to wipe {engine.url!r}: table {table} holds data")
        Base.metadata.drop_all(conn)
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


def tables(engine):
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def version(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def migrate(engine, direction, target, config=None):
    config = config or migration_config()
    migrator = make_engine(engine.url.render_as_string(hide_password=False), for_migrations=True)
    with migrator.begin() as conn:
        config.attributes["connection"] = conn
        getattr(command, direction)(config, target)
    migrator.dispose()


def head():
    return ScriptDirectory.from_config(migration_config()).get_current_head()


def test_fresh_database_gets_exactly_the_schema_the_models_describe(engine):
    init_db(engine)
    assert tables(engine) == set(Base.metadata.tables)
    assert version(engine) == head()
    with engine.connect() as conn:
        # Fails when a model changes without a migration: add one with `alembic revision`.
        assert schema_drift(conn) == []


def test_running_again_changes_nothing(engine):
    init_db(engine)
    with sessionmaker(engine)() as s:
        backend.models.record_audit(s, "test", "kept")
    init_db(engine)
    with sessionmaker(engine)() as s:
        assert [a.action for a in s.scalars(select(AuditLog))] == ["kept"]


def test_database_created_before_migrations_is_adopted_with_its_data(engine):
    Base.metadata.create_all(engine)  # how every database was created before migrations
    with sessionmaker(engine)() as s:
        s.add(AuditLog(ts=datetime(2026, 1, 2, tzinfo=UTC), actor="old", action="row", detail={}))
        s.commit()
    init_db(engine)
    assert version(engine) == head()
    with sessionmaker(engine)() as s:
        (row,) = s.scalars(select(AuditLog))
        assert (row.actor, row.ts.date()) == ("old", date(2026, 1, 2))
    with engine.connect() as conn:
        assert schema_drift(conn) == []


def test_older_database_missing_newer_tables_gets_them_and_keeps_the_rest(engine):
    older = [t for name, t in Base.metadata.tables.items() if not name.startswith("beneficial")]
    Base.metadata.create_all(engine, tables=older)
    with sessionmaker(engine)() as s:
        backend.models.record_audit(s, "old", "row")
    init_db(engine)
    assert tables(engine) == set(Base.metadata.tables)
    with sessionmaker(engine)() as s:
        assert s.scalars(select(AuditLog)).one().actor == "old"


def test_every_migration_reverses_and_reapplies(engine):
    init_db(engine)
    migrate(engine, "downgrade", "base")
    assert tables(engine) == set()
    init_db(engine)
    assert tables(engine) == set(Base.metadata.tables)
    with engine.connect() as conn:
        assert schema_drift(conn) == []


def test_reversing_the_baseline_refuses_to_drop_stored_data(engine):
    init_db(engine)
    with sessionmaker(engine)() as s:
        backend.models.record_audit(s, "test", "precious")
    with pytest.raises(RuntimeError, match="refusing to drop tables that hold data"):
        migrate(engine, "downgrade", "base")
    assert version(engine) == head()
    with sessionmaker(engine)() as s:
        assert s.scalars(select(AuditLog)).one().action == "precious"


def test_drift_is_reported_not_hidden(engine, caplog):
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE audit_log ADD COLUMN stray INTEGER"))
    init_db(engine)
    assert "database schema differs from the models" in caplog.text


def start(url):
    init_db(make_engine(url))


def test_api_and_worker_starting_together_do_not_collide(engine):
    if engine.dialect.name == "sqlite":
        pytest.skip(
            "SQLite serves one writer; the deployment that starts two processes is Postgres"
        )
    url = engine.url.render_as_string(hide_password=False)
    # Separate processes, as in deployment (Alembic's environment is per process, not per thread).
    with ProcessPoolExecutor(4, mp_context=get_context("spawn")) as pool:
        for result in [pool.submit(start, url) for _ in range(4)]:
            result.result()
    assert tables(engine) == set(Base.metadata.tables)


# How each past version of the platform created its database (SQLite DDL, captured by running
# that commit's own create_all). See fixtures/schemas/README.md.
PAST_SCHEMAS = sorted((Path(__file__).parent / "fixtures" / "schemas").glob("*.sql"))


@pytest.mark.parametrize("schema", PAST_SCHEMAS, ids=lambda p: p.stem)
def test_database_from_every_past_version_is_adopted(schema, tmp_path, caplog):
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as raw:
        raw.executescript(schema.read_text())
        raw.execute(
            "INSERT INTO audit_log (ts, actor, action, detail) "
            "VALUES ('2026-01-01 00:00:00', 'old', 'row', '{}')"
        )
    engine = make_engine(f"sqlite:///{path}")
    init_db(engine)
    assert "differs from the models" not in caplog.text
    assert tables(engine) == set(Base.metadata.tables)
    with sessionmaker(engine)() as s:
        assert s.scalars(select(AuditLog)).one().actor == "old"
    engine.dispose()


def test_table_missing_a_newer_column_gets_it_and_keeps_its_rows(engine, caplog):
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as s:
        s.add(
            InsiderIssuer(
                cik=320187,
                ticker="NKE",
                name="NIKE",
                history_since=date(2023, 1, 1),
                last_ingested_at=datetime(2026, 1, 2, tzinfo=UTC),
                failed_filings=3,
            )
        )
        s.add(
            InsiderFiling(
                accession="0000320187-24-000001",
                form_type="4",
                issuer_cik=320187,
                issuer_name="NIKE",
                issuer_ticker="NKE",
                period_of_report=date(2024, 1, 2),
                filed_date=date(2024, 1, 3),
                accepted_at=datetime(2024, 1, 3, 21, 5, tzinfo=UTC),
                original_filed_date=None,
                aff10b5one=False,
                owner_cik=1234567,
                owner_name="OWNER",
                is_director=True,
                is_officer=False,
                is_ten_percent_owner=False,
                officer_title=None,
                owners=[],
                remarks="",
                url="https://www.sec.gov/Archives/edgar/data/320187/000032018724000001/x.xml",
                classifier_version=1,
            )
        )
        s.commit()
    with engine.begin() as conn:  # the tables as the first insider version made them
        conn.execute(text("ALTER TABLE insider_issuer DROP COLUMN failed_filings"))
        conn.execute(text("ALTER TABLE insider_filing DROP COLUMN classifier_version"))
    init_db(engine)
    assert "differs from the models" not in caplog.text
    with sessionmaker(engine)() as s:
        issuer = s.scalars(select(InsiderIssuer)).one()
        assert (issuer.ticker, issuer.failed_filings) == ("NKE", 0)
        filing = s.scalars(select(InsiderFiling)).one()
        assert (filing.accession, filing.owner_name, filing.accepted_at) == (
            "0000320187-24-000001",
            "OWNER",
            datetime(2024, 1, 3, 21, 5, tzinfo=UTC),
        )
        # 0 is below every real classifier version, so the next ingestion re-classifies it.
        assert filing.classifier_version == 0 < CLASSIFIER_VERSION


def test_missing_index_is_reported_and_nothing_is_lost(engine, caplog):
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as s:
        backend.models.record_audit(s, "old", "row")
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_audit_log_action"))
    init_db(engine)
    assert "ix_audit_log_action" in caplog.text
    with sessionmaker(engine)() as s:
        assert s.scalars(select(AuditLog)).one().actor == "old"


BROKEN_REVISION = """
import sqlalchemy as sa
from alembic import op

revision = "9999"
down_revision = "0001"


def upgrade():
    op.create_table("half_done", sa.Column("id", sa.Integer(), primary_key=True))
    op.add_column("audit_log", sa.Column("half_done", sa.Integer()))
    op.execute("UPDATE audit_log SET actor = 'overwritten'")
    raise RuntimeError("migration failed half way")


def downgrade():
    pass
"""


@pytest.mark.parametrize("path", ["start-up", "alembic command"])
def test_failed_migration_leaves_the_database_exactly_as_it_was(
    engine, tmp_path, path, monkeypatch
):
    init_db(engine)
    with sessionmaker(engine)() as s:
        backend.models.record_audit(s, "test", "kept")
    scripts = tmp_path / "migrations"
    shutil.copytree(Path(backend.models.__file__).parent.parent / "migrations", scripts)
    (scripts / "versions" / "9999_broken.py").write_text(BROKEN_REVISION)
    config = migration_config()
    config.set_main_option("script_location", str(scripts))

    with pytest.raises(RuntimeError, match="failed half way"):
        if path == "start-up":  # what the API, worker and ingest commands run
            monkeypatch.setattr("backend.database.session.migration_config", lambda: config)
            init_db(engine)
        else:
            migrate(engine, "upgrade", "head", config)

    assert version(engine) == "0001"
    assert "half_done" not in tables(engine)
    with engine.connect() as conn:
        assert schema_drift(conn) == []
    with sessionmaker(engine)() as s:
        assert s.scalars(select(AuditLog)).one().actor == "test"


def test_second_process_waits_for_the_migration_lock_then_finishes(engine):
    if engine.dialect.name != "postgresql":
        pytest.skip("the advisory lock exists on PostgreSQL only")
    url = engine.url.render_as_string(hide_password=False)
    with (
        engine.connect() as holder,
        ProcessPoolExecutor(1, mp_context=get_context("spawn")) as pool,
    ):
        holder.execute(text("SELECT pg_advisory_lock(7203145)"))  # another process, mid-migration
        waiting = pool.submit(start, url)
        time.sleep(3)
        assert not waiting.done()
        assert tables(engine) == set()  # it has not touched the schema while waiting
        holder.execute(text("SELECT pg_advisory_unlock(7203145)"))
        waiting.result(timeout=60)
    assert tables(engine) == set(Base.metadata.tables)
