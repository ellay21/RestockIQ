"""
Cross-merchant benchmarking service tests.
Tests that a merchant's own data is strictly excluded from their baseline
to prevent data leakage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from restockiq.benchmarking.service import BenchmarkService
from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode
from restockiq.signals.domain import MerchantFinancialSignal, SignalInputMethod, SkuSalesRecord


@pytest.fixture
def merchant_a() -> MerchantId:
    return MerchantId.generate()


@pytest.fixture
def merchant_b() -> MerchantId:
    return MerchantId.generate()


@pytest.fixture
def merchant_c() -> MerchantId:
    return MerchantId.generate()


def make_signal(merchant_id: MerchantId, sku: str, qty: int, days: int) -> MerchantFinancialSignal:
    return MerchantFinancialSignal(
        merchant_id=merchant_id,
        cash_on_hand=Money(Decimal("100"), "ETB"),
        sales_records=(SkuSalesRecord(SkuCode(sku), qty, days),),
        input_method=SignalInputMethod.MANUAL_ENTRY,
        captured_at=datetime.now(tz=UTC),
    )


class TestBenchmarkService:
    def test_cross_merchant_benchmark_excludes_the_merchant_being_scored(
        self, merchant_a: MerchantId, merchant_b: MerchantId, merchant_c: MerchantId
    ) -> None:
        """
        No data leakage: a merchant's own sales must not be included
        in the aggregate baseline they are compared against.
        """
        # Merchant A sells 10/day
        sig_a = make_signal(merchant_a, "SUGAR", 70, 7)
        # Merchant B sells 20/day
        sig_b = make_signal(merchant_b, "SUGAR", 140, 7)
        # Merchant C sells 30/day
        sig_c = make_signal(merchant_c, "SUGAR", 210, 7)

        service = BenchmarkService()

        # We benchmark Merchant A against the population [A, B, C]
        benchmark = service.compute_benchmark(
            target_merchant_id=merchant_a,
            sku_code=SkuCode("SUGAR"),
            population_signals=[sig_a, sig_b, sig_c],
        )

        # Baseline should be average of B (20) and C (30) = 25.
        # If A was included, average would be (10+20+30)/3 = 20.
        assert benchmark.peer_average_daily_velocity == 25.0
        assert benchmark.target_merchant_daily_velocity == 10.0
        assert benchmark.percentile_rank is not None
        assert benchmark.percentile_rank < 50.0  # They are below average

    def test_benchmark_handles_empty_peer_group(self, merchant_a: MerchantId) -> None:
        """If there are no other merchants selling this SKU, return a neutral benchmark."""
        sig_a = make_signal(merchant_a, "SUGAR", 70, 7)

        service = BenchmarkService()
        benchmark = service.compute_benchmark(
            target_merchant_id=merchant_a,
            sku_code=SkuCode("SUGAR"),
            population_signals=[sig_a],  # Only A
        )

        assert benchmark.peer_average_daily_velocity == 0.0
        assert benchmark.percentile_rank is None
