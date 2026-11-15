"""Alembic environment: runs migrations on the application's database.

The application passes its own connection (`backend.database.session.init_db`); the `alembic`
command line builds one from the same settings the application uses.
"""

from alembic import context
from sqlalchemy import Connection, text

import backend.models  # noqa: F401  registers tables on Base.metadata
from backend.core.config import get_settings
from backend.database.session import Base, make_engine


# Any constant works; it only has to be the same in every process migrating this database.
MIGRATION_LOCK = 7_203_145


def run(connection: Connection) -> None:
    if connection.dialect.name == "postgresql":
        # The API and the worker start together; the second waits here instead of colliding.
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK})
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,  # lets SQLite alter tables, by copying them
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("offline (--sql) mode is not supported; run against the database")

supplied = context.config.attributes.get("connection")
if supplied is not None:
    run(supplied)
else:
    engine = make_engine(get_settings().app.database_url)
    with engine.begin() as own:
        run(own)
    engine.dispose()
