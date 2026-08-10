"""
StockoutDetector tests.
"""

from __future__ import annotations

import pytest

from restockiq.shared_kernel.value_objects import SkuCode
from restockiq.signals.domain import SkuSalesRecord
from restockiq.stockout_analysis.detector import detect_stockouts


@pytest.fixture
def sku() -> SkuCode:
    return SkuCode("SUGAR-1KG")


@pytest.fixture
def strong_baseline(sku: SkuCode) -> list[SkuSalesRecord]:
    """4 weeks of ~10 units/day."""
    return [
        SkuSalesRecord(sku, 70, 7),
        SkuSalesRecord(sku, 63, 7),
        SkuSalesRecord(sku, 77, 7),
        SkuSalesRecord(sku, 70, 7),
    ]


class TestStockoutDetector:
    def test_detects_high_severity_stockout(
        self, sku: SkuCode, strong_baseline: list[SkuSalesRecord]
    ) -> None:
        """Velocity drop to < 25% of baseline → HIGH severity."""
        # Recent record: only 1 unit sold in 7 days (velocity ≈ 0.14, vs baseline ~10)
        recent = [SkuSalesRecord(sku, 1, 7)]
        events = detect_stockouts(sku, recent, strong_baseline)
        assert len(events) == 1
        assert events[0].severity == "HIGH"
        assert events[0].estimated_missed_sales_units > 0

    def test_detects_medium_severity_stockout(
        self, sku: SkuCode, strong_baseline: list[SkuSalesRecord]
    ) -> None:
        """Velocity drop to ~35% of baseline → MEDIUM severity."""
        # Baseline ~10/day; 35% ≈ 3.5/day → 25 units in 7 days
        recent = [SkuSalesRecord(sku, 25, 7)]
        events = detect_stockouts(sku, recent, strong_baseline)
        assert len(events) == 1
        assert events[0].severity == "MEDIUM"

    def test_no_stockout_for_normal_sales(
        self, sku: SkuCode, strong_baseline: list[SkuSalesRecord]
    ) -> None:
        """Velocity within 50% of baseline → no stockout detected."""
        # 60% of baseline = 6/day → 42/7days
        recent = [SkuSalesRecord(sku, 42, 7)]
        events = detect_stockouts(sku, recent, strong_baseline)
        assert events == []

    def test_no_baseline_returns_empty(self, sku: SkuCode) -> None:
        """Without a baseline we cannot detect a stockout."""
        recent = [SkuSalesRecord(sku, 0, 7)]
        events = detect_stockouts(sku, recent, baseline_records=[])
        assert events == []

    def test_zero_baseline_velocity_returns_empty(self, sku: SkuCode) -> None:
        """If baseline velocity is 0, we cannot define 'a drop'."""
        baseline = [SkuSalesRecord(sku, 0, 7)]
        recent = [SkuSalesRecord(sku, 0, 7)]
        events = detect_stockouts(sku, recent, baseline)
        assert events == []

    def test_missed_sales_estimate_is_positive(
        self, sku: SkuCode, strong_baseline: list[SkuSalesRecord]
    ) -> None:
        recent = [SkuSalesRecord(sku, 0, 7)]
        events = detect_stockouts(sku, recent, strong_baseline)
        assert len(events) == 1
        assert events[0].estimated_missed_sales_units > 0
