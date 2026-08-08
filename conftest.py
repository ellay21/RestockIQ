"""
Shared test fixtures for all API tests.

Uses FastAPI's TestClient with dependency overrides to inject in-memory fakes
instead of real databases. Each test gets its own fresh repositories so tests
never share state.
"""
from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from tests.fakes.fake_signal_source import InMemorySignalRepository
from tests.fakes.fake_solver import FakeSolver

from restockiq.main import app
from restockiq.merchants.repository import InMemoryMerchantRepository
from restockiq.merchants.service import MerchantService
from restockiq.recommendations.repository import InMemoryRecommendationRepository
from restockiq.recommendations.service import RecommendationService
from restockiq.shared_kernel.clock import FakeClock
from restockiq.signals.service import SignalService


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient with all DB dependencies overridden by in-memory fakes.

    Per-test repository instances ensure state is shared between endpoints
    within the same test call (e.g. POST then GET) while keeping tests isolated.
    """
    from restockiq.api.deps import (
        get_merchant_service,
        get_recommendation_service,
        get_signal_service,
    )
    from restockiq.config import Settings

    merchant_repo = InMemoryMerchantRepository()
    signal_repo = InMemorySignalRepository()
    rec_repo = InMemoryRecommendationRepository()

    merchant_service = MerchantService(repository=merchant_repo)
    signal_service = SignalService(repository=signal_repo)
    rec_service = RecommendationService(
        solver=FakeSolver(),
        repository=rec_repo,
        merchant_service=merchant_service,
        clock=FakeClock(),
        default_n_scenarios=10,
    )

    fake_container = MagicMock()
    fake_container.settings = Settings(
        database_url="postgresql+asyncpg://fake:fake@localhost:5432/fake",
        app_env="testing",
    )
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock(return_value=None)
    fake_container.engine = fake_engine

    app.dependency_overrides[get_merchant_service] = lambda: merchant_service
    app.dependency_overrides[get_signal_service] = lambda: signal_service
    app.dependency_overrides[get_recommendation_service] = lambda: rec_service

    with patch("restockiq.main.build_container", return_value=fake_container), TestClient(
        app, raise_server_exceptions=True
    ) as c:
        yield c

    app.dependency_overrides.clear()
