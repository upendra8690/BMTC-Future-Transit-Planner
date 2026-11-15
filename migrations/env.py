"""Alembic environment for the planner.

The database URL comes from backend/app/config.py, the same place the server reads it, so the command line
and the running server always point at the same file. Two ways to run it:

* alembic upgrade head               (from the project folder, with the same .env as the server)
* app.schema_migrations.upgrade_to_head(engine)   (called by the server on start-up, with its own connection)
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy.engine import Connection

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "backend"))

from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.config import Settings
from app.database import Base, Database

config = context.config
target_metadata = Base.metadata

# Configure logging only when this file runs as the alembic command. When the server passes its own
# connection, fileConfig would silence the application's loggers, so it is skipped.
if config.config_file_name is not None and "connection" not in config.attributes:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _run_with(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # SQLite cannot alter most columns in place; batch mode rebuilds the table instead.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Emit SQL to the console without connecting. Useful for reviewing a migration before it runs."""
    url = Settings.from_env().database_url
    dialect = url.split(":", 1)[0].split("+", 1)[0]
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_as_batch=dialect == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied = config.attributes.get("connection")
    if supplied is not None:
        _run_with(supplied)
        return
    db = Database(Settings.from_env().database_url)
    try:
        with db.engine.connect() as connection:
            _run_with(connection)
            connection.commit()
    finally:
        db.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
