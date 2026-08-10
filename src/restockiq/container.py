"""
Dependency Injection container — the composition root.

This module is the ONE place where concrete implementations are wired to their
port interfaces.  Domain code and service code must never instantiate concrete
implementations directly.

Design: a simple manual DI container using Python dataclasses.  We deliberately
avoid third-party DI frameworks (FastAPI Depends is used only at the HTTP boundary)
to keep the domain testable without the web framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession
    from restockiq.optimizer.saa_solver import SaaSolver

from restockiq.config import Settings


@dataclass
class Container:
    """
    Application DI container.

    Holds all long-lived singletons (engine, session factory, services).
    Created once at application startup via build_container().

    Note: services that require a per-request AsyncSession are created
    inside FastAPI endpoint factories using the session dependency in deps.py,
    not stored here as singletons.
    """

    settings: Settings
    _engine: "AsyncEngine | None" = field(default=None, repr=False)
    _session_factory: "async_sessionmaker[AsyncSession] | None" = field(default=None, repr=False)

    def __post_init__(self) -> None:
        from restockiq.db.session import make_engine, make_session_factory

        self._engine = make_engine(
            self.settings.database_url,
            echo=self.settings.db_echo,
        )
        self._session_factory = make_session_factory(self._engine)  

    @property
    def engine(self) -> "AsyncEngine":
        assert self._engine is not None
        return self._engine

    @property
    def session_factory(self) -> "async_sessionmaker[AsyncSession]":
        assert self._session_factory is not None
        return self._session_factory

    def make_solver(self) -> "SaaSolver":
        """Create the SAA solver with the configured seed."""
        from restockiq.optimizer.saa_solver import SaaSolver

        return SaaSolver(seed=self.settings.saa_seed)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()


_container: Container | None = None


def get_container() -> Container:
    """Return the global Container singleton."""
    if _container is None:
        raise RuntimeError(
            "Container has not been initialised. Call build_container() during application startup."
        )
    return _container


def build_container(settings: Settings | None = None) -> Container:
    """
    Build and register the global Container singleton.

    Called once in main.py's lifespan handler.
    """
    global _container
    _container = Container(settings=settings or get_settings())
    return _container
