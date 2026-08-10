"""
RecommendationService — orchestrates the full pipeline.

signal → demand estimation → optimization → confidence scoring → rationale → persist.

This is the core application service.  It wires together every upstream module
through their port interfaces, so a test can swap any dependency with a fake
without changing the service code.

Pricing: SKU cost/sell prices are sourced from the merchant's own catalog
(MerchantService).  If a SKU appears in demand history but has not yet been
added to the catalog, a configurable default price is used and a WARNING is
emitted so the operator can correct the catalog.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from restockiq.demand.estimator import DemandDistribution, estimate
from restockiq.optimizer.domain import OptimizationInput, SkuInputLine
from restockiq.recommendations.confidence_scorer import ConfidenceScorer
from restockiq.recommendations.domain import RestockRecommendation
from restockiq.recommendations.rationale_generator import RationaleGenerator
from restockiq.shared_kernel.clock import Clock, SystemClock
from restockiq.shared_kernel.errors import OptimizationError
from restockiq.shared_kernel.value_objects import Money, SkuCode

if TYPE_CHECKING:
    from restockiq.merchants.domain import Sku
    from restockiq.merchants.service import MerchantService
    from restockiq.optimizer.ports import SolverPort
    from restockiq.recommendations.repository import RecommendationRepository
    from restockiq.signals.domain import MerchantFinancialSignal, SkuSalesRecord

logger = logging.getLogger(__name__)

# Default pricing used only when a SKU exists in demand history but has not yet
# been registered in the merchant's catalog.  These values trigger a WARNING
# so the operator knows the catalog needs to be updated.
_DEFAULT_COST = Decimal("20")
_DEFAULT_SELL = Decimal("25")


class RecommendationService:
    """
    Orchestrates: signal → demand → optimize → score → rationale → persist.

    All dependencies are injected through their port interfaces.  A full set
    of fakes can be injected for testing without any real infrastructure.
    """

    def __init__(
        self,
        solver: SolverPort,
        repository: RecommendationRepository,
        merchant_service: MerchantService,
        confidence_scorer: ConfidenceScorer | None = None,
        rationale_generator: RationaleGenerator | None = None,
        clock: Clock | None = None,
        default_lead_time_days: int = 7,
        default_n_scenarios: int = 200,
    ) -> None:
        self._solver = solver
        self._repo = repository
        self._merchant_service = merchant_service
        self._scorer = confidence_scorer or ConfidenceScorer()
        self._rationale = rationale_generator or RationaleGenerator()
        self._clock = clock or SystemClock()
        self._lead_time = default_lead_time_days
        self._n_scenarios = default_n_scenarios

    async def generate_recommendation(
        self,
        signal: MerchantFinancialSignal,
        historical_signals: list[MerchantFinancialSignal] | None = None,
    ) -> RestockRecommendation:
        """
        Run the full pipeline for a given signal snapshot.

        Args:
            signal:             The current merchant snapshot (cash + recent sales).
            historical_signals: All historical signals for demand fitting.
                                If None, only the current signal is used.

        Returns:
            A persisted RestockRecommendation.

        Raises:
            ValueError:        If no SKU input lines can be built from the signal.
            OptimizationError: If the optimizer returns INFEASIBLE (cash cap is
                               too small to buy even one unit of any SKU).
        """
        logger.info(
            "Generating recommendation for merchant=%s skus=%d",
            signal.merchant_id,
            len(signal.sales_records),
        )

        all_signals = [*(historical_signals or []), signal]
        currency = signal.cash_on_hand.currency

        # Step 1: Fit demand distributions
        # Aggregate all SkuSalesRecords from all signals per SKU so that
        # historical signals contribute to the distribution even when the
        # current signal does not repeat those SKUs.
        records_by_sku: dict[SkuCode, list[SkuSalesRecord]] = {}
        for sig in all_signals:
            for record in sig.sales_records:
                records_by_sku.setdefault(record.sku_code, []).append(record)

        # Map SkuCode → DemandDistribution (one entry per unique SKU across all signals)
        demand_by_sku: dict[SkuCode, DemandDistribution] = {
            sku_code: estimate(sku_code=sku_code, sales_records=records)
            for sku_code, records in records_by_sku.items()
        }

        total_sample_size = sum(d.sample_size for d in demand_by_sku.values())

        # Step 2: Fetch the merchant's catalog to get real cost/sell prices
        catalog_skus = await self._merchant_service.get_catalog(signal.merchant_id)
        catalog: dict[SkuCode, Sku] = {sku.code: sku for sku in catalog_skus}

        # Step 3: Build SkuInputLines using real catalog prices
        sku_input_lines = self._build_sku_input_lines(demand_by_sku, catalog, currency)

        if not sku_input_lines:
            raise ValueError("Cannot generate a recommendation with no SKU input lines")

        # Step 4: Optimise
        optimization_input = OptimizationInput(
            cash_cap=signal.cash_on_hand,
            sku_lines=tuple(sku_input_lines),
            n_scenarios=self._n_scenarios,
        )
        optimization_result = self._solver.solve(optimization_input)

        logger.info(
            "Optimizer finished: status=%s objective=%.4f",
            optimization_result.solver_status,
            optimization_result.objective_value,
        )

        # Step 5: Guard against infeasible plans
        # An INFEASIBLE result means the cash cap is too small to buy even
        # one unit of any SKU.  Returning a zero-item recommendation silently
        # would mislead the merchant — raise instead so the API layer can
        # return a meaningful 422 with a reason.
        if optimization_result.solver_status == "INFEASIBLE":
            raise OptimizationError(
                f"No affordable restocking plan exists for merchant "
                f"{signal.merchant_id} with cash cap {signal.cash_on_hand}. "
                "The cash available is too small to purchase even one unit of "
                "any SKU at current cost prices."
            )

        # Step 6: Score confidence
        confidence_score, confidence_level = self._scorer.score(signal, total_sample_size)

        # Step 7: Generate rationale
        sku_recommendations = self._rationale.generate(optimization_result, currency)

        # Step 8: Assemble and persist
        plan = optimization_result.order_plan
        recommendation = RestockRecommendation(
            id=uuid.uuid4(),
            merchant_id=signal.merchant_id,
            signal_captured_at=signal.captured_at,
            created_at=self._clock.now(),
            sku_recommendations=tuple(sku_recommendations),
            total_estimated_cost=plan.total_cost,
            total_expected_margin=plan.total_expected_margin,
            confidence_score=confidence_score,
            confidence_level=confidence_level,
            solver_status=optimization_result.solver_status,
        )
        await self._repo.save(recommendation)
        return recommendation

    def _build_sku_input_lines(
        self,
        demand_by_sku: dict[SkuCode, DemandDistribution],
        catalog: dict[SkuCode, Sku],
        currency: str,
    ) -> list[SkuInputLine]:
        """
        Build SkuInputLine objects from demand distributions and the merchant's
        catalog prices.

        For each SKU with a fitted demand distribution, the cost and sell prices
        are sourced from the merchant's catalog (Sku.cost_price / Sku.sell_price).
        If a SKU has demand history but is not yet registered in the catalog, a
        default price pair is used and a WARNING is logged so the operator can
        add the missing SKU to the catalog.

        Duplicate SKU codes are handled implicitly because demand_by_sku is
        keyed by SkuCode.
        """
        lines: list[SkuInputLine] = []
        for sku_code, dist in demand_by_sku.items():
            catalog_sku = catalog.get(sku_code)
            if catalog_sku is not None:
                cost = catalog_sku.cost_price
                sell = catalog_sku.sell_price
            else:
                # SKU has demand history but is not in the catalog yet.
                # Use defaults and warn so the operator can fix the catalog.
                logger.warning(
                    "SKU %s has demand history but is not in the merchant catalog. "
                    "Using default prices (cost=%s, sell=%s %s). "
                    "Add this SKU to the catalog to use real prices.",
                    sku_code,
                    _DEFAULT_COST,
                    _DEFAULT_SELL,
                    currency,
                )
                cost = Money(_DEFAULT_COST, currency)
                sell = Money(_DEFAULT_SELL, currency)

            lines.append(
                SkuInputLine(
                    sku_code=sku_code,
                    cost_per_unit=cost,
                    sell_price_per_unit=sell,
                    mean_daily_demand=dist.mean_daily,
                    lead_time_days=self._lead_time,
                )
            )
        return lines
