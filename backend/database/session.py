"""Database engine and sessions: PostgreSQL/TimescaleDB in deployment, SQLite for dev/tests."""

from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, pool_pre_ping=True)


def init_db(engine: Engine) -> None:
    import backend.models  # noqa: F401  registers tables on Base.metadata

    # shortcut: create_all can't alter existing tables; adopt Alembic once schemas start changing.
    Base.metadata.create_all(engine)


def db_ok(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
