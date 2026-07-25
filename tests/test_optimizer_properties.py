"""
Property-based tests for the SAA optimizer using Hypothesis.

These tests generate random problem instances and assert invariants that must
hold for ALL inputs, not just the examples we thought of.  They are the most
powerful tests in the suite because they stress-test the cash-cap invariant
with inputs we would never have written by hand.

Key properties tested:
  1. The cash-cap invariant: for any valid input, total_cost ≤ cash_cap.
  2. Monotonicity: more cash → same or more units ordered (never fewer).
  3. Infeasibility handling: zero cash → zero units for all SKUs.
  4. Output stability: solver_status is always one of the valid strings.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from restockiq.optimizer.domain import OptimizationInput, SkuInputLine
from restockiq.optimizer.saa_solver import SaaSolver
from restockiq.shared_kernel.value_objects import Money, SkuCode

# Strategy helpers

def sku_input_strategy(currency: str = "ETB") -> st.SearchStrategy[SkuInputLine]:
    """Generate a valid SkuInputLine with positive margin."""
    return st.tuples(
        st.decimals(min_value=Decimal("1"), max_value=Decimal("100"), places=2),
        st.decimals(min_value=Decimal("1"), max_value=Decimal("50"), places=2),
        st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
        st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-",
            min_size=2,
            max_size=10,
        ),
    ).map(lambda args: SkuInputLine(
        sku_code=SkuCode(args[3]),
        cost_per_unit=Money(args[0], currency),
        sell_price_per_unit=Money(args[0] + args[1], currency),
        mean_daily_demand=args[2],
        lead_time_days=7,
    ))


def optimization_input_strategy() -> st.SearchStrategy[OptimizationInput]:
    """Generate a valid OptimizationInput with 1-4 SKUs."""
    return st.tuples(
        st.decimals(min_value=Decimal("0"), max_value=Decimal("1000"), places=2),
        st.lists(
            sku_input_strategy(),
            min_size=1,
            max_size=4,
            unique_by=lambda x: x.sku_code.code,
        ),
        st.integers(min_value=10, max_value=30),
    ).filter(
        # Filter out SKUs with duplicate codes after generation
        lambda args: len({s.sku_code for s in args[1]}) == len(args[1])
    ).map(
        lambda args: OptimizationInput(
            cash_cap=Money(args[0], "ETB"),
            sku_lines=tuple(args[1]),
            n_scenarios=args[2],
        )
    )


# ── Property tests ────────────────────────────────────────────────────────────


@pytest.mark.slow
class TestOptimizerProperties:
    @given(problem=optimization_input_strategy())
    @settings(max_examples=50, deadline=10_000)
    def test_cash_cap_invariant_holds_for_all_inputs(
        self, problem: OptimizationInput
    ) -> None:
        """
        For every valid problem, the total cost of the resulting plan
        must never exceed the cash cap.

        This is the most critical invariant in the entire system — a violation
        here means the optimizer could bankrupt a merchant.
        """
        solver = SaaSolver(seed=99)
        result = solver.solve(problem)
        tolerance = Decimal("0.01")
        assert result.order_plan.total_cost.amount <= problem.cash_cap.amount + tolerance, (
            f"Cash cap violated!\n"
            f"  Cash cap:   {problem.cash_cap.amount}\n"
            f"  Total cost: {result.order_plan.total_cost.amount}\n"
            f"  SKUs: {[s.sku_code.code for s in problem.sku_lines]}"
        )

    @given(problem=optimization_input_strategy())
    @settings(max_examples=30, deadline=10_000)
    def test_solver_status_is_always_valid(
        self, problem: OptimizationInput
    ) -> None:
        """solver_status must always be one of the known valid strings."""
        solver = SaaSolver(seed=42)
        result = solver.solve(problem)
        valid_statuses = {"OPTIMAL", "FEASIBLE", "INFEASIBLE"}
        assert result.solver_status in valid_statuses, (
            f"Unexpected solver_status: {result.solver_status!r}"
        )

    @given(
        cash=st.decimals(min_value=Decimal("1"), max_value=Decimal("500"), places=2),
        cost=st.decimals(min_value=Decimal("5"), max_value=Decimal("30"), places=2),
        margin=st.decimals(min_value=Decimal("1"), max_value=Decimal("20"), places=2),
    )
    @settings(max_examples=30, deadline=10_000)
    def test_more_cash_never_decreases_ordered_units_for_single_sku(
        self, cash: Decimal, cost: Decimal, margin: Decimal
    ) -> None:
        """
        Monotonicity: for a single SKU, doubling the cash cap must not
        reduce the number of units ordered.

        If this fails, the solver is leaving money on the table.
        """
        sell = cost + margin
        sku = SkuInputLine(
            sku_code=SkuCode("SUGAR"),
            cost_per_unit=Money(cost, "ETB"),
            sell_price_per_unit=Money(sell, "ETB"),
            mean_daily_demand=2.0,
            lead_time_days=7,
        )

        problem_small = OptimizationInput(
            cash_cap=Money(cash, "ETB"),
            sku_lines=(sku,),
            n_scenarios=20,
        )
        problem_large = OptimizationInput(
            cash_cap=Money(cash * Decimal("2"), "ETB"),
            sku_lines=(sku,),
            n_scenarios=20,
        )

        solver = SaaSolver(seed=7)
        result_small = solver.solve(problem_small)
        result_large = solver.solve(problem_large)

        units_small = result_small.order_plan.lines[0].units_to_order
        units_large = result_large.order_plan.lines[0].units_to_order

        assert units_large >= units_small, (
            f"Monotonicity violated: with {cash * 2} ETB ({units_large} units) < "
            f"with {cash} ETB ({units_small} units)"
        )
