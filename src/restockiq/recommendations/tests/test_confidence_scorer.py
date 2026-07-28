"""
ConfidenceScorer tests.
  - test_confidence_is_higher_for_weret_sourced_signal_than_manual
  - test_confidence_reflects_sample_size

"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from restockiq.recommendations.confidence_scorer import ConfidenceScorer
from restockiq.recommendations.domain import ConfidenceLevel
from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode
from restockiq.signals.domain import MerchantFinancialSignal, SignalInputMethod, SkuSalesRecord


def make_signal(method: SignalInputMethod) -> MerchantFinancialSignal:
    return MerchantFinancialSignal(
        merchant_id=MerchantId.generate(),
        cash_on_hand=Money(Decimal("500"), "ETB"),
        sales_records=(SkuSalesRecord(SkuCode("SUGAR"), 50, 7),),
        input_method=method,
        captured_at=datetime.now(tz=UTC),
    )


@pytest.fixture
def scorer() -> ConfidenceScorer:
    return ConfidenceScorer()


class TestConfidenceScorer:
    def test_confidence_is_higher_for_weret_sourced_signal_than_manual(
        self, scorer: ConfidenceScorer
    ) -> None:
        weret_signal = make_signal(SignalInputMethod.WERET_WEBHOOK)
        manual_signal = make_signal(SignalInputMethod.MANUAL_ENTRY)

        weret_score, _ = scorer.score(weret_signal, sample_size=10)
        manual_score, _ = scorer.score(manual_signal, sample_size=10)

        assert weret_score > manual_score, (
            f"WERET score ({weret_score:.2f}) should exceed manual score ({manual_score:.2f})"
        )

    def test_confidence_reflects_sample_size(self, scorer: ConfidenceScorer) -> None:
        """A signal with 30+ samples must score higher than the same signal with 1 sample."""
        signal = make_signal(SignalInputMethod.MANUAL_ENTRY)
        high_sample_score, _ = scorer.score(signal, sample_size=30)
        low_sample_score, _ = scorer.score(signal, sample_size=1)

        assert high_sample_score > low_sample_score, (
            f"High-sample score ({high_sample_score:.2f}) should exceed "
            f"low-sample score ({low_sample_score:.2f})"
        )

    def test_score_is_clamped_between_min_and_max(self, scorer: ConfidenceScorer) -> None:
        """Score must always be in [0.10, 0.95] regardless of inputs."""
        signal = make_signal(SignalInputMethod.MANUAL_ENTRY)
        for sample_size in [0, 1, 5, 10, 30, 100]:
            s, _ = scorer.score(signal, sample_size=sample_size)
            assert 0.10 <= s <= 0.95, f"Score {s:.3f} out of range for sample_size={sample_size}"

    def test_weret_with_large_sample_yields_high_confidence(
        self, scorer: ConfidenceScorer
    ) -> None:
        signal = make_signal(SignalInputMethod.WERET_WEBHOOK)
        _score, level = scorer.score(signal, sample_size=30)
        assert level == ConfidenceLevel.HIGH

    def test_manual_with_no_history_yields_low_confidence(
        self, scorer: ConfidenceScorer
    ) -> None:
        signal = make_signal(SignalInputMethod.MANUAL_ENTRY)
        _score, level = scorer.score(signal, sample_size=0)
        assert level == ConfidenceLevel.LOW

    def test_csv_is_higher_confidence_than_manual(self, scorer: ConfidenceScorer) -> None:
        csv_signal = make_signal(SignalInputMethod.CSV_IMPORT)
        manual_signal = make_signal(SignalInputMethod.MANUAL_ENTRY)
        csv_score, _ = scorer.score(csv_signal, sample_size=5)
        manual_score, _ = scorer.score(manual_signal, sample_size=5)
        assert csv_score >= manual_score
