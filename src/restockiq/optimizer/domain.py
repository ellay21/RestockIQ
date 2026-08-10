"""
OrderPlan, OptimizationResult entities, and the cash-cap invariant.

This is the domain core of the optimizer.  It has ZERO framework imports.
The PuLP solver library appears only in saa_solver.py (the adapter side).

Hexagonal rigor: FULL — domain entities only, no solver library imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from restockiq.shared_kernel.errors import DomainValidationError
from restockiq.shared_kernel.value_objects import Money, SkuCode

# ── Per-SKU input to the optimizer ────────────────────────────────────────────


@dataclass(frozen=True)
class SkuInputLine:
    """
    Everything the optimizer needs to know about a single SKU.

    Attributes:
        sku_code:          Product identifier.
        cost_per_unit:     What the merchant pays per unit (used in budget constraint).
        sell_price_per_unit: What customers pay per unit (used to compute margin).
        mean_daily_demand: Estimated mean demand in units per day.
        lead_time_days:    Restocking cycle length — how many days until the next
                           restock opportunity.  The optimizer plans for this horizon.
    """

    sku_code: SkuCode
    cost_per_unit: Money
    sell_price_per_unit: Money
    mean_daily_demand: float
    lead_time_days: int = 7

    def __post_init__(self) -> None:
        if self.mean_daily_demand < 0:
            raise DomainValidationError(
                f"SkuInputLine '{self.sku_code}': mean_daily_demand cannot be negative"
            )
        if self.lead_time_days <= 0:
            raise DomainValidationError(
                f"SkuInputLine '{self.sku_code}': lead_time_days must be positive"
            )
        if self.sell_price_per_unit.currency != self.cost_per_unit.currency:
            raise DomainValidationError(
                f"SkuInputLine '{self.sku_code}': sell_price and cost_price "
                "must share the same currency"
            )
        if self.sell_price_per_unit.amount <= self.cost_per_unit.amount:
            raise DomainValidationError(
                f"SkuInputLine '{self.sku_code}': sell_price must exceed cost_price"
            )

    @property
    def margin_per_unit(self) -> Money:
        return Money(
            amount=self.sell_price_per_unit.amount - self.cost_per_unit.amount,
            currency=self.cost_per_unit.currency,
        )

    @property
    def currency(self) -> str:
        return self.cost_per_unit.currency


# Optimizer input
@dataclass(frozen=True)
class OptimizationInput:
    """
    All inputs required by any SolverPort implementation.

    Invariants:
      - sku_lines must be non-empty
      - n_scenarios >= 10 (SAA needs enough scenarios for reliable estimates)
      - all SKU lines must share the same currency as cash_cap
    """

    cash_cap: Money
    sku_lines: tuple[SkuInputLine, ...]
    n_scenarios: int = 200

    def __post_init__(self) -> None:
        if not self.sku_lines:
            raise DomainValidationError("OptimizationInput must have at least one SkuInputLine")
        if self.n_scenarios < 10:
            raise DomainValidationError(
                f"n_scenarios must be at least 10 for reliable SAA results, got {self.n_scenarios}"
            )
        for line in self.sku_lines:
            if line.currency != self.cash_cap.currency:
                raise DomainValidationError(
                    f"SkuInputLine '{line.sku_code}' currency ({line.currency}) "
                    f"does not match cash_cap currency ({self.cash_cap.currency})"
                )


# Optimizer output
@dataclass(frozen=True)
class SkuOrderLine:
    """
    A single line in a restocking order plan.

    Invariant: units_to_order >= 0 (zero means "skip this SKU this cycle").
    """

    sku_code: SkuCode
    units_to_order: int  # 0 = do not order this cycle
    cost_per_unit: Money
    sell_price_per_unit: Money
    expected_units_sold: float  # Expected realised sales from SAA scenarios

    def __post_init__(self) -> None:
        if self.units_to_order < 0:
            raise DomainValidationError(
                f"SkuOrderLine '{self.sku_code}': units_to_order cannot be negative, "
                f"got {self.units_to_order}"
            )

    @property
    def total_cost(self) -> Money:
        """Total cash outlay for this line (cost_per_unit x units_to_order)."""
        return Money(
            amount=self.cost_per_unit.amount * Decimal(str(self.units_to_order)),
            currency=self.cost_per_unit.currency,
        )

    @property
    def expected_margin(self) -> Money:
        """Expected gross profit from selling expected_units_sold units."""
        margin_each = self.sell_price_per_unit.amount - self.cost_per_unit.amount
        return Money(
            amount=margin_each * Decimal(str(self.expected_units_sold)),
            currency=self.cost_per_unit.currency,
        )


@dataclass(frozen=True)
class OrderPlan:
    """
    The immutable restocking plan produced by the optimizer.

    The most important invariant: the total cost of all order lines MUST NOT
    exceed the cash cap.  This invariant is enforced in __post_init__ so it
    is impossible to construct an invalid OrderPlan — the type system itself
    guards the cash constraint.
    """

    lines: tuple[SkuOrderLine, ...]
    cash_cap: Money

    def __post_init__(self) -> None:
        total = self._total_cost()
        # Use a 1-cent tolerance to absorb floating-point rounding in the solver
        tolerance = Decimal("0.01")
        if total.amount > self.cash_cap.amount + tolerance:
            raise DomainValidationError(
                f"OrderPlan total cost ({total.amount} {total.currency}) "
                f"exceeds cash cap ({self.cash_cap.amount} {self.cash_cap.currency}). "
                "This is an optimizer bug — the cash constraint was violated."
            )

    def _total_cost(self) -> Money:
        if not self.lines:
            return Money.zero(self.cash_cap.currency)
        total = Money.zero(self.cash_cap.currency)
        for line in self.lines:
            total = total + line.total_cost
        return total

    @property
    def total_cost(self) -> Money:
        return self._total_cost()

    @property
    def total_expected_margin(self) -> Money:
        if not self.lines:
            return Money.zero(self.cash_cap.currency)
        total = Money.zero(self.cash_cap.currency)
        for line in self.lines:
            total = total + line.expected_margin
        return total

    @property
    def ordered_lines(self) -> list[SkuOrderLine]:
        """Return only the lines where units_to_order > 0."""
        return [line for line in self.lines if line.units_to_order > 0]


@dataclass(frozen=True)
class OptimizationResult:
    """
    The complete output of a SolverPort.solve() call.

    Attributes:
        order_plan:      The validated plan (cash cap guaranteed).
        solver_status:   "OPTIMAL" | "FEASIBLE" | "INFEASIBLE".
        objective_value: Expected profit (the quantity the solver maximised).
    """

    order_plan: OrderPlan
    solver_status: str
    objective_value: float

    _VALID_STATUSES = frozenset({"OPTIMAL", "FEASIBLE", "INFEASIBLE"})

    def __post_init__(self) -> None:
        if self.solver_status not in self._VALID_STATUSES:
            raise DomainValidationError(
                f"solver_status must be one of {sorted(self._VALID_STATUSES)}, "
                f"got {self.solver_status!r}"
            )
