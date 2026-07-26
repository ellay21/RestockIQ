"""
RestockRecommendation aggregate and SkuRecommendation value object.

This is the final output of the full pipeline: signal → demand → optimize →
score → rationale → RestockRecommendation.

Hexagonal rigor: FULL — no framework imports. Zero I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode


class ConfidenceLevel(StrEnum):
    """
    Human-readable confidence band for the recommendation.

    HIGH:   Built from 30+ real WERET transactions — solid data.
    MEDIUM: Built from manual entry or moderate history — useful but imprecise.
    LOW:    Very few observations; treat as a rough starting point only.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @classmethod
    def from_score(cls, score: float) -> ConfidenceLevel:
        """Classify a numeric score [0, 1] into a ConfidenceLevel."""
        if score >= 0.75:
            return cls.HIGH
        if score >= 0.45:
            return cls.MEDIUM
        return cls.LOW


@dataclass(frozen=True)
class SkuRecommendation:
    """
    Recommendation for a single SKU: how many to order and why.

    Attributes:
        sku_code:        Product identifier.
        units_to_order:  Recommended purchase quantity (0 = skip this cycle).
        estimated_cost:  Total cash outlay for this line.
        expected_margin: Expected gross profit from ordering this quantity.
        rationale:       Plain-language reason for the recommendation.
        deciding_factor: Machine-readable deciding factor key.
    """

    sku_code: SkuCode
    units_to_order: int
    estimated_cost: Money
    expected_margin: Money
    rationale: str
    deciding_factor: str  # e.g. "MARGIN", "VELOCITY", "CASH_CONSTRAINED"


@dataclass(frozen=True)
class RestockRecommendation:
    """
    The complete restocking recommendation for a merchant.

    This is the aggregate root for the recommendations module.  It is the
    output of the full pipeline and is persisted by the RecommendationRepository.

    Attributes:
        id:                    Unique recommendation ID (UUID).
        merchant_id:           The merchant this recommendation is for.
        signal_captured_at:    When the underlying signal was captured.
        created_at:            When this recommendation was generated.
        sku_recommendations:   One entry per SKU in the merchant's catalog.
        total_estimated_cost:  Sum of all line estimated costs.
        total_expected_margin: Sum of all line expected margins.
        confidence_score:      Numeric confidence [0.10, 0.95].
        confidence_level:      Human-readable confidence band.
        solver_status:         Optimizer outcome: "OPTIMAL", "FEASIBLE", or
                               "INFEASIBLE".  INFEASIBLE is never stored
                               (the service raises OptimizationError instead),
                               but FEASIBLE signals a relaxed solution.
        is_accepted:           True once the merchant accepts this recommendation.
    """

    id: uuid.UUID
    merchant_id: MerchantId
    signal_captured_at: datetime
    created_at: datetime
    sku_recommendations: tuple[SkuRecommendation, ...]
    total_estimated_cost: Money
    total_expected_margin: Money
    confidence_score: float
    confidence_level: ConfidenceLevel
    solver_status: str  # "OPTIMAL" | "FEASIBLE" (never "INFEASIBLE" — service raises)
    is_accepted: bool = False

    @property
    def actionable_items(self) -> list[SkuRecommendation]:
        """Return only the SKUs with a positive order recommendation."""
        return [r for r in self.sku_recommendations if r.units_to_order > 0]

    def accept(self) -> RestockRecommendation:
        """
        Return a new RestockRecommendation with is_accepted=True.

        Frozen dataclass: acceptance creates a new object rather than mutating.
        """
        from dataclasses import replace
        return replace(self, is_accepted=True)
