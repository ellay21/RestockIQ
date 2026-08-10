"""
SolverPort — the abstract contract every solver implementation must satisfy.

Hexagonal rigor: FULL — no concrete solver library (PuLP, OR-Tools) may
appear in this file.  The actual PuLP-based implementation lives in
saa_solver.py and is wired in via the composition root (container.py).
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from restockiq.optimizer.domain import OptimizationInput, OptimizationResult


class SolverPort(abc.ABC):
    """
    Port: contract for the cash-constrained restocking optimizer.

    Any solver implementation (PuLP SAA, OR-Tools, a cloud API, or a
    deterministic fake for tests) must implement this single method.

    Implementations:
      - SaaSolver   (PuLP-based SAA, the production solver)
      - FakeSolver  (deterministic fake for tests, tests/fakes/fake_solver.py)
    """

    @abc.abstractmethod
    def solve(self, problem: OptimizationInput) -> OptimizationResult:
        """
        Find the optimal restocking order plan given the input.

        The returned OptimizationResult's OrderPlan is guaranteed (by the
        OrderPlan invariant) to never exceed the cash cap.

        Args:
            problem: Full description of the optimization problem.

        Returns:
            OptimizationResult with status OPTIMAL, FEASIBLE, or INFEASIBLE.
            If INFEASIBLE, the OrderPlan will contain zero-unit lines for all SKUs.

        Raises:
            OptimizationError: if the solver encounters an unrecoverable error.
        """
        ...
