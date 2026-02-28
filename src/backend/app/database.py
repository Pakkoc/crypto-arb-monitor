"""SQLAlchemy async engine, session factory, and WAL configuration.

WAL PRAGMAs are applied to every connection via an event listener so that
the database is always in a safe, performant state regardless of how the
connection was obtained.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def _apply_wal_pragmas(dbapi_connection, connection_record):  # noqa: ANN001
    """Apply SQLite WAL-mode PRAGMAs on every new connection.

    Per DD-8: WAL mode, NORMAL synchronous, 5s busy timeout,
    20 MB page cache, FK enforcement, temp tables in RAM.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.execute("PRAGMA cache_size = -20000")  # 20 MB (negative = kibibytes)
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA temp_store = MEMORY")
    cursor.close()


def create_engine(database_url: str | None = None) -> AsyncEngine:
    """Create and configure the async SQLAlchemy engine."""
    url = database_url or settings.database_url
    engine = create_async_engine(
        url,
        echo=settings.debug,
        # SQLite + aiosqlite: NullPool avoids connection pool exhaustion
        # and "cannot operate on a closed database" errors.
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    # Register the PRAGMA setup hook on the underlying sync driver
    event.listen(engine.sync_engine, "connect", _apply_wal_pragmas)
    return engine


# Module-level engine and session factory — initialised in lifespan
engine: AsyncEngine | None = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str | None = None) -> None:
    """Initialise the module-level engine and session factory.

    Called once during application startup (lifespan).
    """
    global engine, async_session_factory
    engine = create_engine(database_url)
    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    if async_session_factory is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    async with async_session_factory() as session:
        yield session


async def create_all_tables() -> None:
    """Create all tables defined in ORM models (used for testing / first run)."""
    if engine is None:
        raise RuntimeError("Engine not initialised.")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_engine() -> None:
    """Dispose the engine connection pool on shutdown."""
    if engine is not None:
        await engine.dispose()
