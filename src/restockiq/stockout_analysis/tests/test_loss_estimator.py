"""
StockoutLossEstimator tests.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from restockiq.shared_kernel.value_objects import Money, SkuCode
from restockiq.stockout_analysis.detector import StockoutEvent
from restockiq.stockout_analysis.loss_estimator import estimate_loss


@pytest.fixture
def high_severity_event() -> StockoutEvent:
    return StockoutEvent(
        sku_code=SkuCode("SUGAR"),
        detected_velocity=1.0,
        baseline_velocity=10.0,
        severity="HIGH",
        estimated_missed_sales_units=63.0,  # 9 units/day x 7 days
    )


class TestStockoutLossEstimator:
    def test_revenue_lost_is_correctly_computed(
        self, high_severity_event: StockoutEvent
    ) -> None:
        estimate = estimate_loss(
            event=high_severity_event,
            sell_price=Money(Decimal("25"), "ETB"),
            cost_price=Money(Decimal("20"), "ETB"),
        )
        # 63 missed units x 25 ETB = 1575 ETB revenue lost
        assert estimate.revenue_lost.amount == Decimal("63.0") * Decimal("25")

    def test_margin_lost_is_correctly_computed(
        self, high_severity_event: StockoutEvent
    ) -> None:
        estimate = estimate_loss(
            event=high_severity_event,
            sell_price=Money(Decimal("25"), "ETB"),
            cost_price=Money(Decimal("20"), "ETB"),
        )
        # margin = 5 ETB/unit x 63 units = 315 ETB
        assert estimate.margin_lost.amount == Decimal("315.0")

    def test_zero_missed_units_yields_zero_losses(self) -> None:
        event = StockoutEvent(
            sku_code=SkuCode("OIL"),
            detected_velocity=5.0,
            baseline_velocity=10.0,
            severity="MEDIUM",
            estimated_missed_sales_units=0.0,
        )
        estimate = estimate_loss(
            event=event,
            sell_price=Money(Decimal("75"), "ETB"),
            cost_price=Money(Decimal("60"), "ETB"),
        )
        assert estimate.revenue_lost.amount == Decimal("0.0")
        assert estimate.margin_lost.amount == Decimal("0.0")

    def test_severity_is_forwarded_from_event(
        self, high_severity_event: StockoutEvent
    ) -> None:
        estimate = estimate_loss(
            event=high_severity_event,
            sell_price=Money(Decimal("25"), "ETB"),
            cost_price=Money(Decimal("20"), "ETB"),
        )
        assert estimate.severity == "HIGH"
