# Past database schemas

One file per past commit that changed the models: the SQLite DDL that commit's own
`Base.metadata.create_all` produced, read back from `sqlite_master`. `test_migrations.py` loads
each one and checks that the migrations adopt it without losing rows or leaving the schema
different from the models.

Do not edit these. They record what really existed; a new one is only needed if a database could
have been created by code that predates migrations and is not covered here (it cannot: every
later schema change goes through Alembic).
