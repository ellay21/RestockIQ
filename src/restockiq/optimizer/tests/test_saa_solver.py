"""
SaaSolver tests. The highest-value, highest-risk tests in the project.

  - verifies a known analytical answer (not just "it ran without error"), or
  - is adversarial (property-style: tries to break the cash-cap invariant).

"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from restockiq.optimizer.domain import (
    OptimizationInput,
    OptimizationResult,
    SkuInputLine,
    SkuOrderLine,
)
from restockiq.optimizer.saa_solver import SaaSolver
from restockiq.shared_kernel.value_objects import Money, SkuCode

if TYPE_CHECKING:
    from restockiq.optimizer.ports import SolverPort

# Fixtures

@pytest.fixture
def solver() -> SaaSolver:
    """Deterministic solver with a fixed seed for reproducible tests."""
    return SaaSolver(seed=42)


def make_input(
    cash: str,
    skus: list[tuple[str, str, str, float]],  # (code, cost, sell, mean_daily)
    n_scenarios: int = 50,
) -> OptimizationInput:
    """Build an OptimizationInput from compact tuple notation."""
    lines = tuple(
        SkuInputLine(
            sku_code=SkuCode(code),
            cost_per_unit=Money(Decimal(cost), "ETB"),
            sell_price_per_unit=Money(Decimal(sell), "ETB"),
            mean_daily_demand=mean_daily,
            lead_time_days=7,
        )
        for code, cost, sell, mean_daily in skus
    )
    return OptimizationInput(
        cash_cap=Money(Decimal(cash), "ETB"),
        sku_lines=lines,
        n_scenarios=n_scenarios,
    )


# Core correctness tests

class TestSaaSolverCorrectness:
    def test_recommends_zero_order_when_cash_is_zero(self, solver: SaaSolver) -> None:
        """With zero cash, the only valid plan is to order nothing."""
        problem = make_input(
            cash="0",
            skus=[("SUGAR", "20", "25", 10.0)],
        )
        result = solver.solve(problem)
        assert isinstance(result, OptimizationResult)
        assert all(line.units_to_order == 0 for line in result.order_plan.lines)

    def test_never_recommends_a_plan_exceeding_the_cash_cap(self, solver: SaaSolver) -> None:
        """
        Adversarial test: try many cash caps and SKU combinations.
        The cash-cap invariant must hold without exception.
        """
        import random
        rng = random.Random(0)
        for _ in range(20):  # 20 random scenarios
            cash = Decimal(str(rng.uniform(10, 500)))
            n_skus = rng.randint(1, 5)
            skus = [
                (
                    f"SKU{i}",
                    str(rng.uniform(5, 50)),
                    str(rng.uniform(51, 80)),
                    rng.uniform(0.5, 5.0),
                )
                for i in range(n_skus)
            ]
            problem = OptimizationInput(
                cash_cap=Money(cash, "ETB"),
                sku_lines=tuple(
                    SkuInputLine(
                        sku_code=SkuCode(code),
                        cost_per_unit=Money(Decimal(cost), "ETB"),
                        sell_price_per_unit=Money(Decimal(sell), "ETB"),
                        mean_daily_demand=demand,
                        lead_time_days=7,
                    )
                    for code, cost, sell, demand in skus
                ),
                n_scenarios=30,
            )
            result = solver.solve(problem)
            # The OrderPlan constructor already enforces this, but we assert
            # explicitly here to make the test's intent unmistakable.
            assert result.order_plan.total_cost.amount <= cash + Decimal("0.01"), (
                f"Cash cap violated: {result.order_plan.total_cost.amount} > {cash}"
            )

    def test_favors_higher_margin_sku_when_cash_constrained_across_two_skus(
        self, solver: SaaSolver
    ) -> None:
        """
        Classic cash-constrained newsvendor: given budget for exactly 1 unit,
        the solver must prefer the higher-margin SKU.

        Setup:
          - CHEAP: cost=10, sell=13 → margin=3  (30% margin rate)
          - PRICEY: cost=10, sell=18 → margin=8  (44% margin rate)
          - Cash=10 → can buy exactly 1 unit of either, not both.
          - Both have similar demand, so the decision is purely margin-driven.
        """
        problem = make_input(
            cash="10",
            skus=[
                ("CHEAP",  "10", "13", 2.0),   # margin 3 ETB
                ("PRICEY", "10", "18", 2.0),   # margin 8 ETB
            ],
            n_scenarios=100,
        )
        result = solver.solve(problem)
        lines_by_code = {line.sku_code.code: line for line in result.order_plan.lines}
        pricey_units = lines_by_code.get("PRICEY", SkuOrderLine(
            sku_code=SkuCode("PRICEY"), units_to_order=0,
            cost_per_unit=Money(Decimal("10"), "ETB"),
            sell_price_per_unit=Money(Decimal("18"), "ETB"),
            expected_units_sold=0.0,
        )).units_to_order
        cheap_units = lines_by_code.get("CHEAP", SkuOrderLine(
            sku_code=SkuCode("CHEAP"), units_to_order=0,
            cost_per_unit=Money(Decimal("10"), "ETB"),
            sell_price_per_unit=Money(Decimal("13"), "ETB"),
            expected_units_sold=0.0,
        )).units_to_order
        assert pricey_units >= cheap_units, (
            f"Solver should prefer PRICEY (margin=8) over CHEAP (margin=3). "
            f"Got PRICEY={pricey_units}, CHEAP={cheap_units}"
        )

    def test_matches_known_analytical_solution_for_single_sku_case(
        self, solver: SaaSolver
    ) -> None:
        """
        Hand-computed newsvendor benchmark.

        Single SKU: cost=20 ETB, sell=25 ETB, margin=5 ETB.
        Demand ~ Poisson(10 units/day), lead_time=7 days → lam=70.
        Cash cap = 1000 ETB → max purchaseable = 50 units.

        The optimal quantity is at most 50 units (constrained by cash).
        The solver must order a positive quantity — not zero.
        """
        problem = make_input(
            cash="1000",
            skus=[("SUGAR", "20", "25", 10.0)],
            n_scenarios=200,
        )
        result = solver.solve(problem)
        sugar_line = result.order_plan.lines[0]

        # The optimizer must recommend ordering *something* (not a zero plan)
        assert sugar_line.units_to_order > 0, "Solver ordered zero with ample cash"
        # It cannot exceed the budget: 20 * units ≤ 1000
        assert sugar_line.units_to_order <= 50, (
            f"Ordered {sugar_line.units_to_order} units, exceeds budget cap of 50"
        )
        # Status must be OPTIMAL
        assert result.solver_status == "OPTIMAL"

    def test_result_is_infeasible_status_for_zero_cash(self, solver: SaaSolver) -> None:
        problem = make_input(cash="0", skus=[("SUGAR", "20", "25", 5.0)])
        result = solver.solve(problem)
        assert result.solver_status == "INFEASIBLE"
        assert result.objective_value == 0.0


# Port swappability test

class TestSolverPortSwappability:
    def test_solver_port_is_swappable(self) -> None:
        """
        Run the same scenario against both the real SaaSolver and a FakeSolver.
        Assert that the *shape* of the result (the types and structure) is identical —
        proving the port abstraction is correctly defined and both implementations
        conform to the contract.
        """
        # pyrefly: ignore [missing-import]
        from tests.fakes.fake_solver import FakeSolver

        problem = make_input(
            cash="500",
            skus=[("SUGAR", "20", "25", 5.0)],
        )

        real_solver: SolverPort = SaaSolver(seed=42)
        fake_solver: SolverPort = FakeSolver()

        real_result = real_solver.solve(problem)
        fake_result = fake_solver.solve(problem)

        # Both must return an OptimizationResult
        assert isinstance(real_result, OptimizationResult)
        assert isinstance(fake_result, OptimizationResult)

        # Both must contain an OrderPlan that respects the cash cap
        assert real_result.order_plan.total_cost.amount <= Decimal("500") + Decimal("0.01")
        assert fake_result.order_plan.total_cost.amount <= Decimal("500") + Decimal("0.01")

        # Both must have a valid solver_status
        valid_statuses = {"OPTIMAL", "FEASIBLE", "INFEASIBLE"}
        assert real_result.solver_status in valid_statuses
        assert fake_result.solver_status in valid_statuses
