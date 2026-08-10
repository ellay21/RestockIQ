"""
RationaleGenerator — produces a plain-language reason for each SKU recommendation.

Per Context.md: "not just 'buy 20kg sugar,' but WHY." The rationale must
mention the actual deciding factor, not a generic template string.

Deciding factors (in priority order):
  CASH_CONSTRAINED  — the solver left money unspent only because this SKU
                      gives the best margin-per-birr; more cash would mean more.
  HIGH_MARGIN       — highest absolute margin in the current plan.
  HIGH_VELOCITY     — fastest-selling SKU in the current plan.
  BALANCED          — neither extreme; a reasonable balanced buy.
  SKIP              — zero units recommended.

This module is pure domain logic — zero I/O, zero framework imports.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from restockiq.recommendations.domain import SkuRecommendation
from restockiq.shared_kernel.value_objects import Money, SkuCode

if TYPE_CHECKING:
    from restockiq.optimizer.domain import OptimizationResult, SkuOrderLine

# Deciding factor keys (used as machine-readable tags in SkuRecommendation)
FACTOR_CASH_CONSTRAINED = "CASH_CONSTRAINED"
FACTOR_HIGH_MARGIN = "HIGH_MARGIN"
FACTOR_HIGH_VELOCITY = "HIGH_VELOCITY"
FACTOR_BALANCED = "BALANCED"
FACTOR_SKIP = "SKIP"


class RationaleGenerator:
    """
    Generates a one-line plain-language rationale for each SKU recommendation.
    """

    def generate(
        self,
        optimization_result: OptimizationResult,
        currency: str,
    ) -> list[SkuRecommendation]:
        """
        Produce a SkuRecommendation (with rationale) for every order line.

        Args:
            optimization_result: The output of the optimizer.
            currency:            ISO 4217 code for money formatting.

        Returns:
            A list of SkuRecommendation objects with rationale text.
        """
        lines = optimization_result.order_plan.lines
        if not lines:
            return []

        ordered = [line for line in lines if line.units_to_order > 0]
        skipped = [line for line in lines if line.units_to_order == 0]

        # Find the deciding factors among ordered lines
        highest_margin_sku = self._find_highest_margin(ordered)
        highest_velocity_sku = self._find_highest_velocity(ordered)

        is_cash_constrained = (
            optimization_result.order_plan.total_cost.amount
            >= optimization_result.order_plan.cash_cap.amount * Decimal("0.95")
            and len(ordered) < len(lines)
        )

        recommendations = []

        for line in ordered:
            factor, rationale = self._decide_factor_and_rationale(
                line=line,
                highest_margin_sku=highest_margin_sku,
                highest_velocity_sku=highest_velocity_sku,
                is_cash_constrained=is_cash_constrained,
            )
            recommendations.append(
                SkuRecommendation(
                    sku_code=line.sku_code,
                    units_to_order=line.units_to_order,
                    estimated_cost=line.total_cost,
                    expected_margin=line.expected_margin,
                    rationale=rationale,
                    deciding_factor=factor,
                )
            )

        for line in skipped:
            recommendations.append(
                SkuRecommendation(
                    sku_code=line.sku_code,
                    units_to_order=0,
                    estimated_cost=Money.zero(currency),
                    expected_margin=Money.zero(currency),
                    rationale="Not ordered this cycle — other SKUs give a better return "
                    "for your available cash.",
                    deciding_factor=FACTOR_SKIP,
                )
            )

        return recommendations

    def _decide_factor_and_rationale(
        self,
        line: SkuOrderLine,
        highest_margin_sku: SkuCode | None,
        highest_velocity_sku: SkuCode | None,
        is_cash_constrained: bool,
    ) -> tuple[str, str]:
        margin_amount = line.sell_price_per_unit.amount - line.cost_per_unit.amount
        margin_pct = (
            int((margin_amount / line.sell_price_per_unit.amount) * 100)
            if line.sell_price_per_unit.amount
            else 0
        )

        # Cash-constrained: this SKU was chosen over others because of its return
        if is_cash_constrained and line.sku_code == highest_margin_sku:
            return (
                FACTOR_CASH_CONSTRAINED,
                f"Best return per {line.cost_per_unit.currency} invested "
                f"({margin_pct}% gross margin) — your cash is fully allocated to your "
                f"highest-profit items.",
            )

        # Highest absolute margin
        if line.sku_code == highest_margin_sku:
            return (
                FACTOR_HIGH_MARGIN,
                f"Highest margin in your current order: "
                f"{margin_amount:.2f} {line.cost_per_unit.currency} profit per unit sold "
                f"({margin_pct}% gross margin).",
            )

        # Fastest-selling
        if line.sku_code == highest_velocity_sku:
            velocity = line.expected_units_sold / 7 if line.expected_units_sold else 0
            return (
                FACTOR_HIGH_VELOCITY,
                f"Sells fastest in your catalog: approximately {velocity:.1f} units/day "
                f"on average — consistent stock prevents lost sales.",
            )

        return (
            FACTOR_BALANCED,
            f"Balanced buy: {line.units_to_order} units covers your expected demand "
            f"this week at {margin_pct}% gross margin.",
        )

    @staticmethod
    def _find_highest_margin(lines: list[SkuOrderLine]) -> SkuCode | None:
        if not lines:
            return None
        return max(
            lines,
            key=lambda line_: line_.sell_price_per_unit.amount - line_.cost_per_unit.amount,
        ).sku_code

    @staticmethod
    def _find_highest_velocity(lines: list[SkuOrderLine]) -> SkuCode | None:
        if not lines:
            return None
        return max(lines, key=lambda line_: line_.expected_units_sold).sku_code
