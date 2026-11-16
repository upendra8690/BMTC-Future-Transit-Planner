"""Database engine and session management. SQLite for local use, PostgreSQL via DATABASE_URL for production."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .services.text import FOLD_FUNCTION, fold


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        parsed = make_url(url)
        self.is_sqlite = parsed.get_backend_name() == "sqlite"
        connect_args: dict = {}
        if self.is_sqlite:
            connect_args["check_same_thread"] = False
            if parsed.database and parsed.database != ":memory:":
                Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        if self.is_sqlite:
            @event.listens_for(self.engine, "connect")
            def _sqlite_pragmas(dbapi_connection, _record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()
                # SQLite's own lower() only changes ASCII letters. This lets search fold Unicode text too.
                dbapi_connection.create_function(FOLD_FUNCTION, 1, fold, deterministic=True)
        self._sessionmaker = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def create_schema(self) -> str:
        """Create or upgrade the schema through the Alembic migrations. Returns the revision now in place."""
        from .schema_migrations import upgrade_to_head

        return upgrade_to_head(self.engine)

    def session(self) -> Session:
        return self._sessionmaker()

    def dispose(self) -> None:
        self.engine.dispose()
