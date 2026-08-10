"""
RecommendationService orchestration test.

This is the keystone test: it exercises the FULL pipeline
(signal → demand → optimize → score → rationale → persist) using ONLY fakes
for every dependency — no database, no solver, no HTTP.

"proves the pieces actually compose before
touching a database or the web framework."

"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from tests.fakes.fake_solver import FakeSolver

from restockiq.merchants.domain import Merchant, Sku
from restockiq.merchants.repository import InMemoryMerchantRepository
from restockiq.merchants.service import MerchantService
from restockiq.recommendations.domain import ConfidenceLevel, RestockRecommendation
from restockiq.recommendations.repository import InMemoryRecommendationRepository
from restockiq.recommendations.service import RecommendationService
from restockiq.shared_kernel.clock import FakeClock
from restockiq.shared_kernel.errors import OptimizationError
from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode
from restockiq.signals.domain import MerchantFinancialSignal, SignalInputMethod, SkuSalesRecord

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


async def _make_merchant_service(
    merchant_id: MerchantId,
    skus: list[Sku],
) -> MerchantService:
    """Return a MerchantService pre-populated with the given merchant and SKUs."""
    repo = InMemoryMerchantRepository()
    merchant = Merchant(id=merchant_id, name="Test Merchant", currency="ETB")
    for sku in skus:
        merchant.add_sku(sku)
    await repo.save(merchant)
    return MerchantService(repository=repo)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def merchant_id() -> MerchantId:
    return MerchantId.generate()


@pytest.fixture
def catalog_skus() -> list[Sku]:
    """Real SKU catalog entries with actual cost/sell prices."""
    return [
        Sku(
            code=SkuCode("SUGAR-1KG"),
            name="1kg Sugar",
            cost_price=Money(Decimal("15"), "ETB"),
            sell_price=Money(Decimal("20"), "ETB"),
        ),
        Sku(
            code=SkuCode("OIL-1L"),
            name="1L Cooking Oil",
            cost_price=Money(Decimal("40"), "ETB"),
            sell_price=Money(Decimal("50"), "ETB"),
        ),
    ]


@pytest.fixture
def signal(merchant_id: MerchantId) -> MerchantFinancialSignal:
    return MerchantFinancialSignal(
        merchant_id=merchant_id,
        cash_on_hand=Money(Decimal("500"), "ETB"),
        sales_records=(
            SkuSalesRecord(sku_code=SkuCode("SUGAR-1KG"), quantity_sold=70, period_days=7),
            SkuSalesRecord(sku_code=SkuCode("OIL-1L"), quantity_sold=30, period_days=7),
        ),
        input_method=SignalInputMethod.WERET_WEBHOOK,
        captured_at=datetime.now(tz=UTC),
    )


@pytest.fixture
async def service(
    merchant_id: MerchantId,
    catalog_skus: list[Sku],
) -> RecommendationService:
    """Service wired entirely with fakes — no I/O."""
    merchant_service = await _make_merchant_service(merchant_id, catalog_skus)
    return RecommendationService(
        solver=FakeSolver(),
        repository=InMemoryRecommendationRepository(),
        merchant_service=merchant_service,
        clock=FakeClock(),
        default_n_scenarios=20,  # Small for fast tests
    )


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────




class TestRecommendationServiceOrchestration:
    pytestmark = pytest.mark.asyncio

    async def test_service_orchestrates_full_pipeline_with_fakes(
        self,
        service: RecommendationService,
        signal: MerchantFinancialSignal,
    ) -> None:
        """
        End-to-end pipeline through fakes: signal → demand → optimize → score → rationale.

        Asserts the final RestockRecommendation has all fields populated and
        is persisted in the repository.
        """
        recommendation = await service.generate_recommendation(signal)

        assert isinstance(recommendation, RestockRecommendation)
        assert recommendation.merchant_id == signal.merchant_id
        # Confidence should be HIGH for WERET-sourced signal with reasonable history
        assert recommendation.confidence_level in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
        # Must have one SKU recommendation per sales record
        assert len(recommendation.sku_recommendations) == 2
        # All recommendations must have a non-empty rationale
        for sku_rec in recommendation.sku_recommendations:
            assert sku_rec.rationale.strip(), f"Empty rationale for {sku_rec.sku_code}"
        # Recommendation must be persisted
        assert recommendation.id is not None
        # solver_status must be surfaced on the aggregate
        assert recommendation.solver_status in ("OPTIMAL", "FEASIBLE")

    async def test_recommendation_uses_real_catalog_prices(
        self,
        service: RecommendationService,
        signal: MerchantFinancialSignal,
        catalog_skus: list[Sku],
    ) -> None:
        """
        The recommendation's estimated cost must reflect the real catalog
        cost prices, not placeholder values.
        """
        recommendation = await service.generate_recommendation(signal)

        # Build a cost lookup from the catalog fixtures
        cost_by_sku = {sku.code: sku.cost_price for sku in catalog_skus}

        for sku_rec in recommendation.sku_recommendations:
            sku_code = sku_rec.sku_code
            if sku_rec.units_to_order > 0:
                expected_cost_per_unit = cost_by_sku[sku_code].amount
                actual_cost_per_unit = (
                    sku_rec.estimated_cost.amount / sku_rec.units_to_order
                )
                assert actual_cost_per_unit == expected_cost_per_unit, (
                    f"SKU {sku_code}: expected cost/unit {expected_cost_per_unit}, "
                    f"got {actual_cost_per_unit}. Catalog prices are not being used."
                )

    async def test_weret_signal_yields_higher_confidence_than_manual(
        self,
        merchant_id: MerchantId,
        catalog_skus: list[Sku],
    ) -> None:
        merchant_service = await _make_merchant_service(merchant_id, catalog_skus)
        svc = RecommendationService(
            solver=FakeSolver(),
            repository=InMemoryRecommendationRepository(),
            merchant_service=merchant_service,
            clock=FakeClock(),
        )

        weret_signal = MerchantFinancialSignal(
            merchant_id=merchant_id,
            cash_on_hand=Money(Decimal("500"), "ETB"),
            sales_records=(SkuSalesRecord(SkuCode("SUGAR-1KG"), 50, 7),),
            input_method=SignalInputMethod.WERET_WEBHOOK,
            captured_at=datetime.now(tz=UTC),
        )
        manual_signal = MerchantFinancialSignal(
            merchant_id=merchant_id,
            cash_on_hand=Money(Decimal("500"), "ETB"),
            sales_records=(SkuSalesRecord(SkuCode("SUGAR-1KG"), 50, 7),),
            input_method=SignalInputMethod.MANUAL_ENTRY,
            captured_at=datetime.now(tz=UTC),
        )

        weret_rec = await svc.generate_recommendation(weret_signal)
        manual_rec = await svc.generate_recommendation(manual_signal)

        assert weret_rec.confidence_score > manual_rec.confidence_score

    async def test_recommendation_is_persisted_and_retrievable(
        self,
        service: RecommendationService,
        signal: MerchantFinancialSignal,
    ) -> None:
        rec = await service.generate_recommendation(signal)
        latest = await service._repo.get_latest_for_merchant(signal.merchant_id)
        assert len(latest) == 1
        assert latest[0].id == rec.id

    async def test_total_cost_does_not_exceed_cash_on_hand(
        self,
        service: RecommendationService,
        signal: MerchantFinancialSignal,
    ) -> None:
        rec = await service.generate_recommendation(signal)
        assert rec.total_estimated_cost.amount <= signal.cash_on_hand.amount + Decimal("0.01"), (
            f"Total cost {rec.total_estimated_cost} exceeds cash on hand {signal.cash_on_hand}"
        )

    async def test_acceptance_does_not_modify_original(
        self,
        service: RecommendationService,
        signal: MerchantFinancialSignal,
    ) -> None:
        """Accept is immutable — the original remains unaccepted."""
        rec = await service.generate_recommendation(signal)
        accepted = rec.accept()
        assert accepted.is_accepted is True
        assert rec.is_accepted is False  # Original unchanged

    async def test_infeasible_plan_raises_optimization_error(
        self,
        merchant_id: MerchantId,
        catalog_skus: list[Sku],
    ) -> None:
        """
        When the optimizer returns INFEASIBLE the service must raise
        OptimizationError rather than silently returning a zero-item
        recommendation.

        We use a custom FakeSolver that always returns INFEASIBLE to isolate
        this behaviour without depending on a real solver or a specific price.
        """
        from restockiq.optimizer.domain import OptimizationInput, OptimizationResult, OrderPlan
        from restockiq.optimizer.ports import SolverPort

        class AlwaysInfeasibleSolver(SolverPort):
            def solve(self, problem: OptimizationInput) -> OptimizationResult:
                return OptimizationResult(
                    order_plan=OrderPlan(lines=(), cash_cap=problem.cash_cap),
                    solver_status="INFEASIBLE",
                    objective_value=0.0,
                )

        merchant_service = await _make_merchant_service(merchant_id, catalog_skus)
        infeasible_service = RecommendationService(
            solver=AlwaysInfeasibleSolver(),
            repository=InMemoryRecommendationRepository(),
            merchant_service=merchant_service,
            clock=FakeClock(),
        )
        signal = MerchantFinancialSignal(
            merchant_id=merchant_id,
            cash_on_hand=Money(Decimal("1"), "ETB"),
            sales_records=(SkuSalesRecord(SkuCode("SUGAR-1KG"), 10, 7),),
            input_method=SignalInputMethod.MANUAL_ENTRY,
            captured_at=datetime.now(tz=UTC),
        )
        with pytest.raises(OptimizationError):
            await infeasible_service.generate_recommendation(signal)

    async def test_sku_not_in_catalog_falls_back_to_default_prices(
        self,
        merchant_id: MerchantId,
    ) -> None:
        """
        If a SKU has demand history but is not in the merchant's catalog,
        the service must still produce a recommendation (using default prices)
        rather than raising or silently dropping the SKU.
        """
        # Register merchant with NO SKUs in the catalog
        merchant_service = await _make_merchant_service(merchant_id, skus=[])
        svc = RecommendationService(
            solver=FakeSolver(),
            repository=InMemoryRecommendationRepository(),
            merchant_service=merchant_service,
            clock=FakeClock(),
        )
        signal = MerchantFinancialSignal(
            merchant_id=merchant_id,
            cash_on_hand=Money(Decimal("500"), "ETB"),
            sales_records=(SkuSalesRecord(SkuCode("SUGAR-1KG"), 30, 7),),
            input_method=SignalInputMethod.MANUAL_ENTRY,
            captured_at=datetime.now(tz=UTC),
        )
        rec = await svc.generate_recommendation(signal)
        # Should still produce a recommendation — default prices kick in
        assert isinstance(rec, RestockRecommendation)
        assert len(rec.sku_recommendations) == 1
