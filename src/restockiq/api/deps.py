"""
FastAPI dependency providers.

All FastAPI route dependencies (Depends(...)) are defined here.
Each dependency creates per-request infrastructure objects (AsyncSession,
services) using the container's engine/session_factory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

from restockiq.container import get_container
from restockiq.merchants.postgres_repository import PostgresMerchantRepository
from restockiq.merchants.service import MerchantService
from restockiq.recommendations.postgres_repository import PostgresRecommendationRepository
from restockiq.recommendations.service import RecommendationService
from restockiq.signals.postgres_repository import PostgresSignalRepository
from restockiq.signals.service import SignalService

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session per request."""
    container = get_container()
    factory: async_sessionmaker[AsyncSession] = container.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_merchant_service(
    session: AsyncSession = Depends(get_session),
) -> MerchantService:
    """Provide a MerchantService backed by the Postgres repository."""
    repo = PostgresMerchantRepository(session)
    return MerchantService(repository=repo)


def get_signal_service(
    session: AsyncSession = Depends(get_session),
) -> SignalService:
    """Provide a SignalService backed by the Postgres repository."""
    repo = PostgresSignalRepository(session)
    return SignalService(repository=repo)


def get_recommendation_service(
    session: AsyncSession = Depends(get_session),
) -> RecommendationService:
    """Provide a RecommendationService wired to all Postgres repositories."""
    container = get_container()
    rec_repo = PostgresRecommendationRepository(session)
    merchant_repo = PostgresMerchantRepository(session)
    solver = container.make_solver()
    return RecommendationService(
        solver=solver,
        repository=rec_repo,
        merchant_service=MerchantService(repository=merchant_repo),
        default_n_scenarios=container.settings.saa_n_scenarios,
    )
