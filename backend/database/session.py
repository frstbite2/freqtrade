"""Database engine and sessions: PostgreSQL/TimescaleDB in deployment, SQLite for dev/tests."""

import logging
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, DateTime, Engine, create_engine, text
from sqlalchemy.engine import Dialect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.types import TypeDecorator


logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC on every backend. SQLite would otherwise hand back naive datetimes,
    and a naive/aware mix-up is exactly how look-ahead bugs get into point-in-time queries."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: timestamps must be timezone-aware")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("sqlite"):
        # Python's default SQLite mode commits table changes on the spot, so a migration that
        # failed half way could not be rolled back. This makes DDL part of the transaction.
        return create_engine(url, pool_pre_ping=True, connect_args={"autocommit": False})
    return create_engine(url, pool_pre_ping=True)


def migration_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent.parent / "migrations"))
    return config


def init_db(engine: Engine) -> None:
    """Bring the database to the newest schema. Safe to call on every start and on a database
    created before migrations existed: tables and rows already there are never dropped."""
    import backend.models  # noqa: F401  registers tables on Base.metadata

    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        drift = schema_drift(connection)
    if drift:
        # A table that existed before migrations may predate a column added to its model since.
        logger.error("database schema differs from the models: %s", drift)


def schema_drift(connection: Connection) -> list:
    """Differences between the database and the models; empty when they agree."""
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    return compare_metadata(context, Base.metadata)


def commit_new(session: Session, model: type[Base], key: object) -> bool:
    """Commit a newly added record. False if another process stored the same record first (a
    worker and a manual ingest running together); any other constraint failure is raised."""
    try:
        session.commit()
        return True
    except IntegrityError:
        session.rollback()
        if session.get(model, key) is None:
            raise
        return False


def db_ok(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
