"""
Database repository integration tests.

These tests require a live Postgres database.  They are marked @pytest.mark.integration

To run locally (with Docker):
    docker compose up -d postgres
    pytest -m integration
"""

from __future__ import annotations

import os
import typing
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from restockiq.db.base import Base
from restockiq.db.session import make_engine
from restockiq.merchants.domain import Merchant, Sku
from restockiq.recommendations.domain import (
    ConfidenceLevel,
    RestockRecommendation,
    SkuRecommendation,
)
from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode
from restockiq.signals.domain import (
    MerchantFinancialSignal,
    SignalInputMethod,
    SkuSalesRecord,
)

# Test database URL

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://restockiq:restockiq@localhost:5432/restockiq",
)


# Fixtures


@pytest_asyncio.fixture(scope="session")
async def engine() -> typing.AsyncGenerator[typing.Any, None]:
    """Create the async engine once per test session."""
    eng = make_engine(DATABASE_URL, echo=False)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables(engine: typing.Any) -> typing.AsyncGenerator[None, None]:
    """
    Create all tables before the test session begins.

    In CI this is done by `alembic upgrade head` before pytest runs.
    For local runs where Alembic has not been executed, we fall back to
    SQLAlchemy's create_all as a convenience.
    """
    async with engine.begin() as conn:
        # Import all ORM models to register their metadata
        import restockiq.merchants.orm_models
        import restockiq.recommendations.orm_models
        import restockiq.signals.orm_models  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
    yield
    # Teardown: drop all tables after the session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def session(engine: typing.Any) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a transactional session that is rolled back after each test.

    This is the "savepoint" pattern: each test operates inside a nested
    transaction, and the savepoint is rolled back at the end of the test,
    leaving the database clean for the next test without a full table drop.
    """
    async with engine.begin() as conn:
        await conn.begin_nested()
        factory = async_sessionmaker(bind=conn, class_=AsyncSession, expire_on_commit=False)
        async with factory() as s:
            yield s
            await s.rollback()


# Postgres Merchant Repository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.mark.integration
class TestPostgresMerchantRepository:
    async def test_save_and_get_merchant(self, session: AsyncSession) -> None:
        from restockiq.merchants.postgres_repository import PostgresMerchantRepository

        repo = PostgresMerchantRepository(session)
        merchant_id = MerchantId.generate()
        merchant = Merchant(id=merchant_id, name="Corner Shop", currency="ETB")
        await repo.save(merchant)

        fetched = await repo.get_by_id(merchant_id)
        assert fetched.id == merchant_id
        assert fetched.name == "Corner Shop"
        assert fetched.currency == "ETB"

    async def test_merchant_with_skus_persists_and_reloads(self, session: AsyncSession) -> None:
        from restockiq.merchants.postgres_repository import PostgresMerchantRepository

        repo = PostgresMerchantRepository(session)
        merchant_id = MerchantId.generate()
        merchant = Merchant(id=merchant_id, name="Test Shop", currency="ETB")
        merchant.add_sku(
            Sku(
                code=SkuCode("SUGAR"),
                name="Sugar",
                cost_price=Money(Decimal("20"), "ETB"),
                sell_price=Money(Decimal("25"), "ETB"),
            )
        )
        await repo.save(merchant)

        fetched = await repo.get_by_id(merchant_id)
        assert fetched.sku_count == 1
        assert fetched.get_sku(SkuCode("SUGAR")).name == "Sugar"

    async def test_get_nonexistent_merchant_raises(self, session: AsyncSession) -> None:
        from restockiq.merchants.postgres_repository import PostgresMerchantRepository
        from restockiq.shared_kernel.errors import NotFoundError

        repo = PostgresMerchantRepository(session)
        with pytest.raises(NotFoundError):
            await repo.get_by_id(MerchantId.generate())


# Postgres Signal Repository


@pytest.mark.integration
class TestPostgresSignalRepository:
    async def test_save_and_retrieve_signal(self, session: AsyncSession) -> None:
        from restockiq.signals.postgres_repository import PostgresSignalRepository

        repo = PostgresSignalRepository(session)
        merchant_id = MerchantId.generate()
        signal = MerchantFinancialSignal(
            merchant_id=merchant_id,
            cash_on_hand=Money(Decimal("500"), "ETB"),
            sales_records=(SkuSalesRecord(SkuCode("SUGAR"), 50, 7),),
            input_method=SignalInputMethod.MANUAL_ENTRY,
            captured_at=datetime.now(tz=UTC),
        )

        await repo.save(signal)
        history = await repo.get_history_for_merchant(merchant_id, limit=10)
        assert len(history) == 1
        assert history[0].merchant_id == merchant_id
        assert history[0].cash_on_hand.amount == Decimal("500")

    async def test_history_is_returned_newest_first(self, session: AsyncSession) -> None:
        from datetime import timedelta

        from restockiq.signals.postgres_repository import PostgresSignalRepository

        repo = PostgresSignalRepository(session)
        merchant_id = MerchantId.generate()
        base_time = datetime.now(tz=UTC)

        for i in range(3):
            sig = MerchantFinancialSignal(
                merchant_id=merchant_id,
                cash_on_hand=Money(Decimal(str(100 * (i + 1))), "ETB"),
                sales_records=(SkuSalesRecord(SkuCode("SUGAR"), 10 * (i + 1), 7),),
                input_method=SignalInputMethod.MANUAL_ENTRY,
                captured_at=base_time + timedelta(days=i),
            )
            await repo.save(sig)

        history = await repo.get_history_for_merchant(merchant_id, limit=10)
        assert len(history) == 3
        # Newest first: the last-saved should be first
        assert history[0].captured_at >= history[1].captured_at


# Postgres Recommendation Repository


@pytest.mark.integration
class TestPostgresRecommendationRepository:
    async def test_save_and_get_recommendation(self, session: AsyncSession) -> None:
        from restockiq.recommendations.postgres_repository import (
            PostgresRecommendationRepository,
        )

        repo = PostgresRecommendationRepository(session)
        merchant_id = MerchantId.generate()
        rec_id = uuid.uuid4()
        rec = RestockRecommendation(
            id=rec_id,
            merchant_id=merchant_id,
            signal_captured_at=datetime.now(tz=UTC),
            created_at=datetime.now(tz=UTC),
            sku_recommendations=(
                SkuRecommendation(
                    sku_code=SkuCode("SUGAR"),
                    units_to_order=5,
                    estimated_cost=Money(Decimal("100"), "ETB"),
                    expected_margin=Money(Decimal("25"), "ETB"),
                    rationale="Best margin this week",
                    deciding_factor="HIGH_MARGIN",
                ),
            ),
            total_estimated_cost=Money(Decimal("100"), "ETB"),
            total_expected_margin=Money(Decimal("25"), "ETB"),
            confidence_score=0.75,
            confidence_level=ConfidenceLevel.HIGH,
            solver_status="OPTIMAL",
        )

        await repo.save(rec)
        fetched = await repo.get_by_id(rec_id)
        assert fetched.id == rec_id
        assert len(fetched.sku_recommendations) == 1
        assert fetched.sku_recommendations[0].sku_code == SkuCode("SUGAR")

    async def test_get_latest_for_merchant_returns_correct_merchant_recs(
        self, session: AsyncSession
    ) -> None:
        from restockiq.recommendations.postgres_repository import (
            PostgresRecommendationRepository,
        )

        repo = PostgresRecommendationRepository(session)
        merchant_a = MerchantId.generate()
        merchant_b = MerchantId.generate()
        now = datetime.now(tz=UTC)

        for mid in (merchant_a, merchant_b):
            rec = RestockRecommendation(
                id=uuid.uuid4(),
                merchant_id=mid,
                signal_captured_at=now,
                created_at=now,
                sku_recommendations=(
                    SkuRecommendation(
                        sku_code=SkuCode("SUGAR"),
                        units_to_order=3,
                        estimated_cost=Money(Decimal("60"), "ETB"),
                        expected_margin=Money(Decimal("15"), "ETB"),
                        rationale="Balanced buy",
                        deciding_factor="BALANCED",
                    ),
                ),
                total_estimated_cost=Money(Decimal("60"), "ETB"),
                total_expected_margin=Money(Decimal("15"), "ETB"),
                confidence_score=0.6,
                confidence_level=ConfidenceLevel.MEDIUM,
                solver_status="OPTIMAL",
            )
            await repo.save(rec)

        recs_a = await repo.get_latest_for_merchant(merchant_a)
        assert len(recs_a) == 1
        assert recs_a[0].merchant_id == merchant_a
