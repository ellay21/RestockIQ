"""
RationaleGenerator tests.

test_rationale_mentions_the_actual_deciding_factor.
The rationale must reference the real number (margin, velocity), not a
generic template string that could apply to any SKU.

"""

from __future__ import annotations

from decimal import Decimal

import pytest

from restockiq.optimizer.domain import (
    OptimizationResult,
    OrderPlan,
    SkuOrderLine,
)
from restockiq.recommendations.rationale_generator import (
    FACTOR_HIGH_MARGIN,
    FACTOR_HIGH_VELOCITY,
    FACTOR_SKIP,
    RationaleGenerator,
)
from restockiq.shared_kernel.value_objects import Money, SkuCode


def make_result(
    cash: str,
    lines: list[tuple[str, int, str, str, float]],  # (code, units, cost, sell, exp_sold)
) -> OptimizationResult:
    order_lines = tuple(
        SkuOrderLine(
            sku_code=SkuCode(code),
            units_to_order=units,
            cost_per_unit=Money(Decimal(cost), "ETB"),
            sell_price_per_unit=Money(Decimal(sell), "ETB"),
            expected_units_sold=exp_sold,
        )
        for code, units, cost, sell, exp_sold in lines
    )
    return OptimizationResult(
        order_plan=OrderPlan(
            lines=order_lines,
            cash_cap=Money(Decimal(cash), "ETB"),
        ),
        solver_status="OPTIMAL",
        objective_value=10.0,
    )


@pytest.fixture
def generator() -> RationaleGenerator:
    return RationaleGenerator()


class TestRationaleGenerator:
    def test_rationale_mentions_the_actual_deciding_factor(
        self, generator: RationaleGenerator
    ) -> None:
        """
        The deciding factor must be reflected in the rationale text.
        A high-margin SKU must have a rationale that references its margin,
        not a generic string.
        """
        result = make_result(
            cash="200",
            lines=[
                ("HIGH-MARGIN", 5, "20", "40", 4.0),  # margin = 20 ETB, 50%
                ("LOW-MARGIN", 5, "20", "22", 4.0),  # margin = 2 ETB, 9%
            ],
        )
        recommendations = generator.generate(result, currency="ETB")
        by_code = {r.sku_code.code: r for r in recommendations}

        high_margin_rec = by_code["HIGH-MARGIN"]
        assert high_margin_rec.deciding_factor == FACTOR_HIGH_MARGIN
        # The rationale must mention a number (margin amount or percentage)
        assert any(char.isdigit() for char in high_margin_rec.rationale), (
            f"Rationale should contain a number but got: {high_margin_rec.rationale!r}"
        )

    def test_skipped_skus_have_skip_factor(self, generator: RationaleGenerator) -> None:
        result = make_result(
            cash="20",
            lines=[
                ("ORDERED", 1, "20", "25", 0.9),
                ("SKIPPED", 0, "20", "25", 0.0),
            ],
        )
        recommendations = generator.generate(result, currency="ETB")
        by_code = {r.sku_code.code: r for r in recommendations}
        assert by_code["SKIPPED"].deciding_factor == FACTOR_SKIP
        assert by_code["SKIPPED"].units_to_order == 0

    def test_highest_velocity_gets_velocity_factor(self, generator: RationaleGenerator) -> None:
        result = make_result(
            cash="200",
            lines=[
                ("FAST-SELLER", 5, "20", "25", 9.5),  # highest velocity
                ("SLOW-SELLER", 5, "20", "28", 1.0),  # highest margin
            ],
        )
        recommendations = generator.generate(result, currency="ETB")
        by_code = {r.sku_code.code: r for r in recommendations}
        assert by_code["FAST-SELLER"].deciding_factor == FACTOR_HIGH_VELOCITY

    def test_generates_one_recommendation_per_line(self, generator: RationaleGenerator) -> None:
        result = make_result(
            cash="200",
            lines=[
                ("A", 3, "20", "25", 2.5),
                ("B", 2, "20", "25", 1.5),
                ("C", 0, "20", "25", 0.0),
            ],
        )
        recs = generator.generate(result, currency="ETB")
        assert len(recs) == 3
