"""
SaaSolver — Sample Average Approximation LP/MILP solver using PuLP.

This is the concrete adapter implementing SolverPort.  It is the ONLY place
in the codebase where PuLP may be imported.  Domain code (domain.py, ports.py)
must never import PuLP directly.

Algorithm (SAA for cash-constrained newsvendor):
  1. Generate S demand scenarios by sampling from each SKU's Poisson distribution.
  2. Formulate a MILP:
       Maximize  (1/S) * ΣΣ margin_i * y_{i,s}
       subject to
         Σ cost_i * x_i  ≤  cash_cap          (budget constraint)
         y_{i,s}         ≤  x_i  ∀ i,s         (can't sell more than ordered)
         y_{i,s}         ≤  d_{i,s}  ∀ i,s     (can't sell more than demanded)
         x_i in Z>=0                              (integer order quantities)
         y_{i,s} ≥ 0                            (non-negative sales)
  3. Solve with CBC (PuLP's bundled open-source solver).
  4. Wrap the solution in the domain types defined in domain.py.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pulp

from restockiq.optimizer.domain import (
    OptimizationInput,
    OptimizationResult,
    OrderPlan,
    SkuOrderLine,
)
from restockiq.optimizer.ports import SolverPort
from restockiq.shared_kernel.errors import OptimizationError

if TYPE_CHECKING:
    from restockiq.shared_kernel.value_objects import SkuCode


class SaaSolver(SolverPort):
    """
    PuLP-based Sample Average Approximation solver.

    Thread-safety: each call to solve() uses its own local PuLP model and
    variables.  The instance's only mutable state is the random seed.
    """

    def __init__(self, seed: int | None = None) -> None:
        """
        Args:
            seed: Random seed for reproducible scenario generation.
                  Set to a fixed integer in tests; leave None in production.
        """
        self._rng = random.Random(seed)

    # Public API
    def solve(self, problem: OptimizationInput) -> OptimizationResult:
        """Solve the cash-constrained restocking MILP via SAA."""
        if problem.cash_cap.amount <= 0:
            return self._zero_result(problem)

        n_s = problem.n_scenarios

        scenarios = self._generate_scenarios(problem, n_s)

        prob = pulp.LpProblem("RestockIQ_SAA", pulp.LpMaximize)

        x: dict[SkuCode, pulp.LpVariable] = {
            sku.sku_code: pulp.LpVariable(
                name=f"x_{sku.sku_code.code}",
                lowBound=0,
                cat=pulp.LpInteger,
            )
            for sku in problem.sku_lines
        }

        y: dict[SkuCode, dict[int, pulp.LpVariable]] = {
            sku.sku_code: {
                s: pulp.LpVariable(
                    name=f"y_{sku.sku_code.code}_{s}",
                    lowBound=0,
                )
                for s in range(n_s)
            }
            for sku in problem.sku_lines
        }

        prob += (
            pulp.lpSum(
                float(sku.margin_per_unit.amount) * y[sku.sku_code][s]
                for sku in problem.sku_lines
                for s in range(n_s)
            )
            / n_s,
            "Expected_Profit",
        )

        prob += (
            pulp.lpSum(
                float(sku.cost_per_unit.amount) * x[sku.sku_code] for sku in problem.sku_lines
            )
            <= float(problem.cash_cap.amount),
            "Budget",
        )

        for sku in problem.sku_lines:
            for s in range(n_s):
                demand_s = scenarios[sku.sku_code][s]
                prob += y[sku.sku_code][s] <= x[sku.sku_code], f"ylex_{sku.sku_code.code}_{s}"
                prob += (
                    y[sku.sku_code][s] <= demand_s,
                    f"yled_{sku.sku_code.code}_{s}",
                )

        solver = pulp.PULP_CBC_CMD(msg=0)
        prob.solve(solver)

        if prob.status == -1:
            return self._zero_result(problem)

        lines = self._extract_solution(problem, x, y, scenarios, n_s)

        status_map = {1: "OPTIMAL", 0: "INFEASIBLE", -1: "INFEASIBLE", -2: "INFEASIBLE"}
        solver_status = status_map.get(prob.status, "FEASIBLE")

        try:
            order_plan = OrderPlan(lines=tuple(lines), cash_cap=problem.cash_cap)
        except Exception as exc:
            raise OptimizationError(
                f"SaaSolver produced a plan that violates the cash cap: {exc}"
            ) from exc

        return OptimizationResult(
            order_plan=order_plan,
            solver_status=solver_status,
            objective_value=float(pulp.value(prob.objective) or 0.0),
        )

    # Private helpers
    def _generate_scenarios(
        self,
        problem: OptimizationInput,
        n_scenarios: int,
    ) -> dict[SkuCode, list[int]]:
        """
        Generate Poisson demand scenarios for each SKU over its lead-time horizon.

        Uses the standard Knuth algorithm for Poisson sampling (exact for
        small lambda).  For large lambda (> 30), uses a normal approximation
        to avoid overflow in the Knuth loop.
        """
        scenarios: dict[SkuCode, list[int]] = {}
        for sku in problem.sku_lines:
            lam = sku.mean_daily_demand * sku.lead_time_days
            scenarios[sku.sku_code] = [self._poisson_sample(lam) for _ in range(n_scenarios)]
        return scenarios

    def _poisson_sample(self, lam: float) -> int:
        """Draw one sample from Poisson(lam)."""
        if lam <= 0:
            return 0
        if lam > 30:
            # Normal approximation for large lambda
            sample = self._rng.gauss(lam, math.sqrt(lam))
            return max(0, round(int(sample)))
        # Knuth's exact algorithm
        threshold = math.exp(-lam)
        k = 0
        p = 1.0
        while p > threshold:
            k += 1
            p *= self._rng.random()
        return k - 1

    def _extract_solution(
        self,
        problem: OptimizationInput,
        x: dict[SkuCode, pulp.LpVariable],
        y: dict[SkuCode, dict[int, pulp.LpVariable]],
        scenarios: dict[SkuCode, list[int]],
        n_s: int,
    ) -> list[SkuOrderLine]:
        lines = []
        for sku in problem.sku_lines:
            raw_units = pulp.value(x[sku.sku_code])
            units = max(0, round(raw_units or 0.0))
            expected_sold = sum(min(units, scenarios[sku.sku_code][s]) for s in range(n_s)) / n_s
            lines.append(
                SkuOrderLine(
                    sku_code=sku.sku_code,
                    units_to_order=units,
                    cost_per_unit=sku.cost_per_unit,
                    sell_price_per_unit=sku.sell_price_per_unit,
                    expected_units_sold=expected_sold,
                )
            )
        return lines

    def _zero_result(self, problem: OptimizationInput) -> OptimizationResult:
        """Return a zero-order plan when the problem is infeasible (e.g. zero cash)."""
        lines = tuple(
            SkuOrderLine(
                sku_code=sku.sku_code,
                units_to_order=0,
                cost_per_unit=sku.cost_per_unit,
                sell_price_per_unit=sku.sell_price_per_unit,
                expected_units_sold=0.0,
            )
            for sku in problem.sku_lines
        )
        return OptimizationResult(
            order_plan=OrderPlan(lines=lines, cash_cap=problem.cash_cap),
            solver_status="INFEASIBLE",
            objective_value=0.0,
        )
