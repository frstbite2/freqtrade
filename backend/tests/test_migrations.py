"""Schema migrations: fresh databases, databases created before migrations existed, and reversal.

Runs on SQLite always, and also on the database named by MIGRATION_TEST_DATABASE_URL when set
(CI points it at PostgreSQL). That database is emptied by these tests: never point it at real data.
"""

import os
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, date, datetime
from multiprocessing import get_context

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


URLS = ["sqlite"] + [u for u in [os.environ.get("MIGRATION_TEST_DATABASE_URL")] if u]


@pytest.fixture(params=URLS, ids=lambda u: u.split(":")[0].split("+")[0])
def engine(request, tmp_path):
    url = f"sqlite:///{tmp_path}/m.sqlite" if request.param == "sqlite" else request.param
    engine = make_engine(url)
    wipe(engine)
    yield engine
    wipe(engine)
    engine.dispose()


def wipe(engine):
    with engine.begin() as conn:
        Base.metadata.drop_all(conn)
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


def tables(engine):
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def version(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def migrate(engine, direction, target):
    config = migration_config()
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        getattr(command, direction)(config, target)


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
