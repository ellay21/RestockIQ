"""
BenchmarkService - computes cross-merchant performance metrics.

Provides anonymised aggregate baselines to help merchants understand
if they are under-performing their peers on specific SKUs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from restockiq.shared_kernel.value_objects import MerchantId, SkuCode
    from restockiq.signals.domain import MerchantFinancialSignal


@dataclass(frozen=True)
class SkuBenchmark:
    """Comparison of a merchant's velocity against their peers."""

    sku_code: SkuCode
    target_merchant_daily_velocity: float
    peer_average_daily_velocity: float
    percentile_rank: float | None  # None if not enough peer data


class BenchmarkService:
    """Computes benchmarks from a population of merchant signals."""

    def compute_benchmark(
        self,
        target_merchant_id: MerchantId,
        sku_code: SkuCode,
        population_signals: Sequence[MerchantFinancialSignal],
    ) -> SkuBenchmark:
        """
        Compute velocity benchmark for a SKU.

        Crucially, strictly excludes the target_merchant_id's signals from
        the peer aggregate to prevent data leakage.
        """
        target_units = 0
        target_days = 0

        peer_velocities: list[float] = []

        # Group sales by merchant to compute per-merchant velocity
        peer_units_by_merchant: dict[MerchantId, int] = {}
        peer_days_by_merchant: dict[MerchantId, int] = {}

        for sig in population_signals:
            for record in sig.sales_records:
                if record.sku_code == sku_code:
                    if sig.merchant_id == target_merchant_id:
                        target_units += record.quantity_sold
                        target_days += record.period_days
                    else:
                        peer_units_by_merchant[sig.merchant_id] = (
                            peer_units_by_merchant.get(sig.merchant_id, 0) + record.quantity_sold
                        )
                        peer_days_by_merchant[sig.merchant_id] = (
                            peer_days_by_merchant.get(sig.merchant_id, 0) + record.period_days
                        )

        # Compute target velocity
        target_velocity = target_units / target_days if target_days > 0 else 0.0

        # Compute peer velocities (one data point per peer merchant)
        for mid in peer_units_by_merchant:
            days = peer_days_by_merchant[mid]
            if days > 0:
                peer_velocities.append(peer_units_by_merchant[mid] / days)

        if not peer_velocities:
            return SkuBenchmark(
                sku_code=sku_code,
                target_merchant_daily_velocity=target_velocity,
                peer_average_daily_velocity=0.0,
                percentile_rank=None,
            )

        peer_avg = sum(peer_velocities) / len(peer_velocities)

        # Simple percentile rank: what % of peers is the target faster than?
        slower_peers = sum(1 for v in peer_velocities if target_velocity > v)
        percentile = (slower_peers / len(peer_velocities)) * 100.0

        return SkuBenchmark(
            sku_code=sku_code,
            target_merchant_daily_velocity=target_velocity,
            peer_average_daily_velocity=peer_avg,
            percentile_rank=percentile,
        )
