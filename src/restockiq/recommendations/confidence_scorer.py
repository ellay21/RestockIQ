"""
ConfidenceScorer — scores recommendation trustworthiness from signal metadata.

Scoring model:
  Base scores:
    WERET_WEBHOOK  → 0.80  (real transaction data from WERET)
    CSV_IMPORT     → 0.55  (uploaded file — better than manual, unverified)
    MANUAL_ENTRY   → 0.50  (self-reported — most uncertain)

  Adjustments (additive, applied after base):
    sample_size >= 30:  +0.12  (strong history)
    sample_size >= 10:  +0.06  (decent history)
    sample_size == 1:   -0.15  (single observation — very rough)
    sample_size == 0:   -0.30  (no history at all)

  Final score is clamped to [0.10, 0.95]:
    - 0.10 minimum: we never express zero confidence (there's always *some* signal)
    - 0.95 maximum: no model is certain

This module is pure domain logic — zero I/O, zero framework imports.
"""
from __future__ import annotations

from restockiq.recommendations.domain import ConfidenceLevel
from restockiq.signals.domain import MerchantFinancialSignal, SignalInputMethod

# Base scores per signal input method
_BASE_SCORES: dict[SignalInputMethod, float] = {
    SignalInputMethod.WERET_WEBHOOK: 0.80,
    SignalInputMethod.CSV_IMPORT: 0.55,
    SignalInputMethod.MANUAL_ENTRY: 0.50,
}

_MIN_SCORE = 0.10
_MAX_SCORE = 0.95


def score(
    signal: MerchantFinancialSignal,
    sample_size: int,
) -> tuple[float, ConfidenceLevel]:
    """
    Compute a confidence score and level for a recommendation.

    Args:
        signal:      The signal the recommendation was built from.
        sample_size: Total number of SkuSalesRecord observations used by the
                     demand estimator (sum across all SKUs).

    Returns:
        A (score, level) tuple where score ∈ [0.10, 0.95].
    """
    base = _BASE_SCORES.get(signal.input_method, 0.50)

    # Sample-size adjustment
    if sample_size >= 30:
        adjustment = 0.12
    elif sample_size >= 10:
        adjustment = 0.06
    elif sample_size == 1:
        adjustment = -0.15
    elif sample_size == 0:
        adjustment = -0.30
    else:
        adjustment = 0.0

    raw_score = base + adjustment
    final_score = max(_MIN_SCORE, min(_MAX_SCORE, raw_score))
    level = ConfidenceLevel.from_score(final_score)
    return final_score, level


class ConfidenceScorer:
    """
    Stateless scorer — wraps the module-level `score()` function as a class
    so it can be injected as a dependency in RecommendationService tests.
    """

    def score(
        self,
        signal: MerchantFinancialSignal,
        sample_size: int,
    ) -> tuple[float, ConfidenceLevel]:
        return score(signal, sample_size)
