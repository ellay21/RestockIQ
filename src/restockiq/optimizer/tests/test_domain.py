"""
Optimizer domain unit tests.

Tests the OrderPlan cash-cap invariant and domain entity construction.
Pure: no PuLP, no I/O.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from restockiq.optimizer.domain import (
    OptimizationResult,
    OrderPlan,
    SkuInputLine,
    SkuOrderLine,
)
from restockiq.shared_kernel.errors import DomainValidationError
from restockiq.shared_kernel.value_objects import Money, SkuCode

# Fixtures


def make_sku_input(
    code: str = "SUGAR",
    cost: str = "20",
    sell: str = "25",
    mean_daily: float = 10.0,
    currency: str = "ETB",
) -> SkuInputLine:
    return SkuInputLine(
        sku_code=SkuCode(code),
        cost_per_unit=Money(Decimal(cost), currency),
        sell_price_per_unit=Money(Decimal(sell), currency),
        mean_daily_demand=mean_daily,
    )


def make_order_line(
    code: str = "SUGAR",
    units: int = 5,
    cost: str = "20",
    sell: str = "25",
    expected_sold: float = 4.5,
    currency: str = "ETB",
) -> SkuOrderLine:
    return SkuOrderLine(
        sku_code=SkuCode(code),
        units_to_order=units,
        cost_per_unit=Money(Decimal(cost), currency),
        sell_price_per_unit=Money(Decimal(sell), currency),
        expected_units_sold=expected_sold,
    )


# SkuInputLine


class TestSkuInputLine:
    def test_negative_mean_daily_demand_raises(self) -> None:
        with pytest.raises(DomainValidationError, match="negative"):
            make_sku_input(mean_daily=-1.0)

    def test_sell_price_at_or_below_cost_raises(self) -> None:
        with pytest.raises(DomainValidationError, match="sell_price"):
            SkuInputLine(
                sku_code=SkuCode("X"),
                cost_per_unit=Money(Decimal("20"), "ETB"),
                sell_price_per_unit=Money(Decimal("20"), "ETB"),
                mean_daily_demand=5.0,
            )

    def test_margin_per_unit_correct(self) -> None:
        sku = make_sku_input(cost="20", sell="25")
        assert sku.margin_per_unit == Money(Decimal("5"), "ETB")


# SkuOrderLine

class TestSkuOrderLine:
    def test_negative_units_to_order_raises(self) -> None:
        with pytest.raises(DomainValidationError, match="negative"):
            make_order_line(units=-1)

    def test_zero_units_is_valid(self) -> None:
        line = make_order_line(units=0)
        assert line.units_to_order == 0
        assert line.total_cost == Money.zero("ETB")

    def test_total_cost_computation(self) -> None:
        line = make_order_line(units=5, cost="20")
        assert line.total_cost == Money(Decimal("100"), "ETB")

    def test_expected_margin_computation(self) -> None:
        line = make_order_line(units=5, cost="20", sell="25", expected_sold=4.0)
        # margin = 5 ETB/unit, 4 units sold → 20 ETB
        assert line.expected_margin == Money(Decimal("20"), "ETB")


# OrderPlan cash-cap invariant

class TestOrderPlanCashCapInvariant:
    def test_order_plan_within_cash_cap_is_valid(self) -> None:
        line = make_order_line(units=5, cost="20")  # total = 100 ETB
        plan = OrderPlan(
            lines=(line,),
            cash_cap=Money(Decimal("200"), "ETB"),
        )
        assert plan.total_cost == Money(Decimal("100"), "ETB")

    def test_order_plan_never_exceeds_cash_cap(self) -> None:
        """The invariant must be enforced: no plan can exceed its own cash cap."""
        line = make_order_line(units=10, cost="20")  # total = 200 ETB
        with pytest.raises(DomainValidationError, match="cash cap"):
            OrderPlan(
                lines=(line,),
                cash_cap=Money(Decimal("100"), "ETB"),  # Too small
            )

    def test_order_plan_exactly_at_cash_cap_is_valid(self) -> None:
        line = make_order_line(units=5, cost="20")  # total = 100 ETB
        plan = OrderPlan(
            lines=(line,),
            cash_cap=Money(Decimal("100"), "ETB"),  # Exact match
        )
        assert plan.total_cost.amount == Decimal("100")

    def test_zero_unit_order_plan_is_valid(self) -> None:
        line = make_order_line(units=0, cost="20")
        plan = OrderPlan(lines=(line,), cash_cap=Money(Decimal("0"), "ETB"))
        assert plan.total_cost == Money.zero("ETB")

    def test_ordered_lines_excludes_zero_unit_lines(self) -> None:
        line_a = make_order_line(code="A", units=3)
        line_b = make_order_line(code="B", units=0)
        plan = OrderPlan(
            lines=(line_a, line_b),
            cash_cap=Money(Decimal("200"), "ETB"),
        )
        assert len(plan.ordered_lines) == 1
        assert plan.ordered_lines[0].sku_code == SkuCode("A")


# OptimizationResult

class TestOptimizationResult:
    def test_invalid_status_raises(self) -> None:
        plan = OrderPlan(
            lines=(make_order_line(units=0),),
            cash_cap=Money(Decimal("100"), "ETB"),
        )
        with pytest.raises(DomainValidationError, match="solver_status"):
            OptimizationResult(
                order_plan=plan,
                solver_status="UNKNOWN",
                objective_value=0.0,
            )
