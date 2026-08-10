"""
FakeSolver — deterministic fake SolverPort for tests.

Returns a predictable plan where each SKU gets floor(cash_cap / cost_per_unit / n_skus)
units, staying within budget.  The result is deterministic and reproducible —
the actual allocation is not optimal, but it is always valid (cash cap respected).
"""

from __future__ import annotations

from decimal import Decimal

from restockiq.optimizer.domain import (
    OptimizationInput,
    OptimizationResult,
    OrderPlan,
    SkuOrderLine,
)
from restockiq.optimizer.ports import SolverPort


class FakeSolver(SolverPort):
    """
    Deterministic fake solver for unit tests.

    Allocation strategy: distribute the cash cap evenly across all SKUs,
    rounding down so the total never exceeds the budget.  This produces a
    predictable, valid plan without invoking PuLP.

    Not for production use.
    """

    def solve(self, problem: OptimizationInput) -> OptimizationResult:
        n = len(problem.sku_lines)
        cash_per_sku = problem.cash_cap.amount / Decimal(str(n)) if n > 0 else Decimal(0)

        lines = []
        for sku in problem.sku_lines:
            if sku.cost_per_unit.amount == Decimal(0) or problem.cash_cap.amount == Decimal(0):
                units = 0
            else:
                units = int(cash_per_sku // sku.cost_per_unit.amount)
            expected_sold = min(float(units), sku.mean_daily_demand * sku.lead_time_days)
            lines.append(
                SkuOrderLine(
                    sku_code=sku.sku_code,
                    units_to_order=units,
                    cost_per_unit=sku.cost_per_unit,
                    sell_price_per_unit=sku.sell_price_per_unit,
                    expected_units_sold=expected_sold,
                )
            )

        return OptimizationResult(
            order_plan=OrderPlan(lines=tuple(lines), cash_cap=problem.cash_cap),
            solver_status="FEASIBLE",
            objective_value=sum(float(line.expected_margin.amount) for line in lines),
        )
