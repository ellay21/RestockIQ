"""
The estimator is a pure function: same input, same output; no I/O whatsoever.
If any test here requires a mock, a database, or an HTTP call, something
has gone wrong with the module boundary.
"""
from __future__ import annotations

import pytest

from restockiq.demand.estimator import DemandDistribution, estimate
from restockiq.shared_kernel.value_objects import SkuCode
from restockiq.signals.domain import SkuSalesRecord


@pytest.fixture
def sku() -> SkuCode:
    return SkuCode("SUGAR-1KG")


@pytest.fixture
def regular_history(sku: SkuCode) -> list[SkuSalesRecord]:
    """Four weekly sales records, consistently ~10 units/day."""
    return [
        SkuSalesRecord(sku_code=sku, quantity_sold=70, period_days=7),
        SkuSalesRecord(sku_code=sku, quantity_sold=63, period_days=7),
        SkuSalesRecord(sku_code=sku, quantity_sold=77, period_days=7),
        SkuSalesRecord(sku_code=sku, quantity_sold=70, period_days=7),
    ]


class TestEstimator:
    def test_estimator_fits_poisson_from_regular_sales_history(
        self, sku: SkuCode, regular_history: list[SkuSalesRecord]
    ) -> None:
        dist = estimate(sku_code=sku, sales_records=regular_history)
        assert isinstance(dist, DemandDistribution)
        # Mean should be close to 10 units/day
        assert 9.0 < dist.mean_daily < 11.0
        assert dist.sample_size == 4
        assert dist.is_default is False

    def test_estimator_handles_sku_with_zero_historical_sales(self, sku: SkuCode) -> None:
        """No crash, no divide-by-zero — returns a defensible default distribution."""
        dist = estimate(sku_code=sku, sales_records=[])
        assert isinstance(dist, DemandDistribution)
        assert dist.mean_daily == 0.0
        assert dist.is_default is True
        assert dist.sample_size == 0

    def test_estimator_handles_sku_with_all_zero_quantities(self, sku: SkuCode) -> None:
        """A SKU that was stocked but never sold — still valid, not a crash."""
        records = [
            SkuSalesRecord(sku_code=sku, quantity_sold=0, period_days=7),
            SkuSalesRecord(sku_code=sku, quantity_sold=0, period_days=7),
        ]
        dist = estimate(sku_code=sku, sales_records=records)
        assert dist.mean_daily == 0.0
        assert dist.is_default is False  # We have observations, just zero sales

    def test_estimator_is_pure_function_same_input_same_output(
        self, sku: SkuCode, regular_history: list[SkuSalesRecord]
    ) -> None:
        """Calling with identical inputs must produce identical outputs every time."""
        dist_a = estimate(sku_code=sku, sales_records=regular_history)
        dist_b = estimate(sku_code=sku, sales_records=regular_history)
        assert dist_a == dist_b

    def test_estimator_std_matches_poisson_expectation(
        self, sku: SkuCode, regular_history: list[SkuSalesRecord]
    ) -> None:
        """For a Poisson distribution, std = sqrt(lambda)."""
        dist = estimate(sku_code=sku, sales_records=regular_history)
        import math
        expected_std = math.sqrt(dist.mean_daily)
        assert abs(dist.std_daily - expected_std) < 1e-6

    def test_estimator_sku_code_preserved_in_output(
        self, sku: SkuCode, regular_history: list[SkuSalesRecord]
    ) -> None:
        dist = estimate(sku_code=sku, sales_records=regular_history)
        assert dist.sku_code == sku

    def test_estimator_single_record(self, sku: SkuCode) -> None:
        """Single observation: should still produce a non-default distribution."""
        records = [SkuSalesRecord(sku_code=sku, quantity_sold=14, period_days=7)]
        dist = estimate(sku_code=sku, sales_records=records)
        assert abs(dist.mean_daily - 2.0) < 1e-9
        assert dist.is_default is False
