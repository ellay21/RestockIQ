"""
End-to-End pipeline integration test.
This test exercises the full pipeline against a real Postgres database:
  1. Register a merchant with a catalog
  2. Submit a signal via ManualEntryAdapter
  3. Generate a recommendation
  4. Assert the recommendation persists and satisfies all invariants

Marked @pytest.mark.integration — requires Postgres.
"""

from __future__ import annotations

import os
import typing
from decimal import Decimal

import pytest
import pytest_asyncio

from restockiq.db.base import Base
from restockiq.db.session import make_engine, make_session_factory
from restockiq.merchants.domain import Sku
from restockiq.merchants.postgres_repository import PostgresMerchantRepository
from restockiq.merchants.service import MerchantService
from restockiq.optimizer.saa_solver import SaaSolver
from restockiq.recommendations.postgres_repository import PostgresRecommendationRepository
from restockiq.recommendations.service import RecommendationService
from restockiq.shared_kernel.clock import FakeClock
from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode
from restockiq.signals.adapters.manual_entry_adapter import ManualEntryAdapter
from restockiq.signals.postgres_repository import PostgresSignalRepository
from restockiq.signals.service import SignalService

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://restockiq:restockiq@localhost:5432/restockiq",
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest_asyncio.fixture(scope="session")
async def engine() -> typing.AsyncGenerator[typing.Any, None]:
    eng = make_engine(DATABASE_URL, echo=False)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables(engine: typing.Any) -> typing.AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        import restockiq.merchants.orm_models
        import restockiq.recommendations.orm_models
        import restockiq.signals.orm_models  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.integration
class TestFullPipeline:
    async def test_full_pipeline_register_signal_recommend(self, engine: typing.Any) -> None:
        """
        Full E2E: register merchant → submit signal → generate recommendation.

        This is the integration test that proves all layers compose correctly
        with a real database.
        """
        factory = make_session_factory(engine)

        async with factory() as session:
            # Step 1: Register merchant
            merchant_service = MerchantService(repository=PostgresMerchantRepository(session))
            merchant_id = MerchantId.generate()
            await merchant_service.register_merchant(merchant_id, "Integration Shop", "ETB")
            await merchant_service.add_sku(
                merchant_id,
                Sku(
                    code=SkuCode("SUGAR-1KG"),
                    name="Sugar 1kg",
                    cost_price=Money(Decimal("20"), "ETB"),
                    sell_price=Money(Decimal("25"), "ETB"),
                ),
            )
            await session.commit()

        async with factory() as session:
            # Step 2: Submit a manual signal
            signal_service = SignalService(repository=PostgresSignalRepository(session))
            adapter = ManualEntryAdapter()
            raw_input = {
                "merchant_id": str(merchant_id),
                "currency": "ETB",
                "cash_on_hand": "500.00",
                "sales": [
                    {"sku_code": "SUGAR-1KG", "quantity_sold": 70, "period_days": 7},
                ],
            }
            await signal_service.ingest_from_adapter(adapter, raw_input)
            await session.commit()

        async with factory() as session:
            # Step 3: Generate recommendation
            rec_service = RecommendationService(
                solver=SaaSolver(seed=42),
                repository=PostgresRecommendationRepository(session),
                merchant_service=MerchantService(repository=PostgresMerchantRepository(session)),
                clock=FakeClock(),
                default_n_scenarios=30,
            )
            signal_repo = PostgresSignalRepository(session)
            history = await signal_repo.get_history_for_merchant(merchant_id, limit=30)

            assert len(history) >= 1, "Signal not persisted"
            recommendation = await rec_service.generate_recommendation(
                signal=history[0],
                historical_signals=list(history[1:]),
            )
            await session.commit()

        # Step 4: Assertions
        assert recommendation.merchant_id == merchant_id
        assert recommendation.total_estimated_cost.amount >= Decimal(0)
        assert recommendation.total_estimated_cost.amount <= Decimal("500.01")
        assert len(recommendation.sku_recommendations) >= 1
        for sku_rec in recommendation.sku_recommendations:
            assert sku_rec.rationale.strip()
        assert recommendation.confidence_score >= 0.10
        assert recommendation.confidence_score <= 0.95
