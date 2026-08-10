"""
SQLAlchemy async engine and session factory.

This module is the single place that creates the database engine.
Everything in the application that needs a database session must use the
session factory provided here — never create engines directly in domain code.

The async engine uses asyncpg for async I/O; the sync engine used by
Alembic migrations is derived automatically from the async URL.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def make_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """
    Create an async SQLAlchemy engine from a database URL.
    Args:
        database_url: PostgreSQL connection URL using the asyncpg driver.
                      Must start with 'postgresql+asyncpg://'.
        echo:         If True, SQLAlchemy logs all SQL statements.
                      Enable in development, disable in production.
    """
    if not database_url.startswith("postgresql+asyncpg://"):
        # Normalise a bare postgresql:// URL to asyncpg
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,  # Re-validate connections before use
        pool_size=5,
        max_overflow=10,
    )


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to the given engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autobegin=True,
    )


@asynccontextmanager
async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that yields a database session and handles
    commit/rollback automatically.

    Usage::

        async with get_session(session_factory) as session:
            session.add(some_model)
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
