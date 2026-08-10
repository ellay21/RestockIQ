"""
Confidence scorer stability property tests.

Tests that confidence scores are monotonically ordered across input methods
and sample sizes for all possible combinations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from restockiq.recommendations.confidence_scorer import _MAX_SCORE, _MIN_SCORE, ConfidenceScorer
from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode
from restockiq.signals.domain import MerchantFinancialSignal, SignalInputMethod, SkuSalesRecord

# Strategy helpers


def make_test_signal(method: SignalInputMethod) -> MerchantFinancialSignal:
    return MerchantFinancialSignal(
        merchant_id=MerchantId.generate(),
        cash_on_hand=Money(Decimal("500"), "ETB"),
        sales_records=(SkuSalesRecord(SkuCode("SUGAR"), 50, 7),),
        input_method=method,
        captured_at=datetime.now(tz=UTC),
    )


# Properties


@pytest.mark.slow
class TestConfidenceStability:
    @given(sample_size=st.integers(min_value=0, max_value=200))
    @settings(max_examples=100, deadline=1_000)
    def test_confidence_score_always_in_valid_range(self, sample_size: int) -> None:
        """For any sample_size and any input method, score ∈ [0.10, 0.95]."""
        scorer = ConfidenceScorer()
        for method in SignalInputMethod:
            signal = make_test_signal(method)
            score, _ = scorer.score(signal, sample_size)
            assert _MIN_SCORE <= score <= _MAX_SCORE, (
                f"Score {score:.4f} out of range [{_MIN_SCORE}, {_MAX_SCORE}] "
                f"for method={method.value}, sample_size={sample_size}"
            )

    @given(sample_size=st.integers(min_value=0, max_value=200))
    @settings(max_examples=50, deadline=1_000)
    def test_weret_always_scores_higher_than_manual(self, sample_size: int) -> None:
        """
        WERET-sourced signals must always score higher than manual-entry signals
        at the same sample size.

        This is a contractual invariant: merchants who use WERET get higher
        confidence recommendations, which creates a business incentive to integrate.
        """
        scorer = ConfidenceScorer()
        weret_score, _ = scorer.score(
            make_test_signal(SignalInputMethod.WERET_WEBHOOK), sample_size
        )
        manual_score, _ = scorer.score(
            make_test_signal(SignalInputMethod.MANUAL_ENTRY), sample_size
        )
        assert weret_score > manual_score, (
            f"WERET ({weret_score:.4f}) should always beat manual ({manual_score:.4f}) "
            f"at sample_size={sample_size}"
        )

    @given(
        s1=st.integers(min_value=0, max_value=29),
        s2=st.integers(min_value=30, max_value=200),
    )
    @settings(max_examples=50, deadline=1_000)
    def test_higher_sample_size_never_reduces_confidence(self, s1: int, s2: int) -> None:
        """
        For any input method, a larger sample size must yield a confidence score
        >= the score at a smaller sample size.

        Confidence should be monotonically non-decreasing with sample size.
        (The scoring model has discrete bands, so equal scores are valid.)
        """
        scorer = ConfidenceScorer()
        for method in SignalInputMethod:
            signal = make_test_signal(method)
            score_low, _ = scorer.score(signal, s1)
            score_high, _ = scorer.score(signal, s2)
            assert score_high >= score_low, (
                f"Confidence decreased with more data! "
                f"method={method.value}, s1={s1} → {score_low:.4f}, "
                f"s2={s2} → {score_high:.4f}"
            )
