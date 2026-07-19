"""
StockoutDetector — identifies when a SKU has likely stocked out based on its
sales velocity dropping to near-zero in the most recent period.

Domain logic only: no I/O, no framework imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from restockiq.shared_kernel.value_objects import SkuCode
    from restockiq.signals.domain import SkuSalesRecord


@dataclass(frozen=True)
class StockoutEvent:
    """
    A detected stockout for a specific SKU.

    Attributes:
        sku_code:           The affected product.
        detected_velocity:  The velocity (units/day) during the suspected stockout.
        baseline_velocity:  The historical average velocity before the stockout.
        severity:           "HIGH" | "MEDIUM" | "LOW" — based on relative velocity drop.
        estimated_missed_sales_units: Units we estimate were not sold due to the stockout.
    """

    sku_code: SkuCode
    detected_velocity: float
    baseline_velocity: float
    severity: str  # "HIGH" | "MEDIUM" | "LOW"
    estimated_missed_sales_units: float


# Thresholds for severity classification
_HIGH_THRESHOLD = 0.25   # velocity dropped to < 25% of baseline → HIGH severity
_MEDIUM_THRESHOLD = 0.50  # velocity dropped to < 50% of baseline → MEDIUM


def detect_stockouts(
    sku_code: SkuCode,
    recent_records: list[SkuSalesRecord],
    baseline_records: list[SkuSalesRecord],
    *,
    lookback_periods: int = 1,
) -> list[StockoutEvent]:
    """
    Detect stockout events for a single SKU.

    Algorithm:
      1. Compute the baseline daily velocity from historical records.
      2. Compare the most recent `lookback_periods` records' velocity to the baseline.
      3. If velocity dropped below threshold, emit a StockoutEvent.

    Args:
        sku_code:         The SKU to analyse.
        recent_records:   The most recent sales records (newest first).
        baseline_records: Historical records used to establish the velocity baseline.
        lookback_periods: Number of recent periods to inspect (default: 1).

    Returns:
        A (possibly empty) list of StockoutEvent objects.
    """
    if not baseline_records:
        return []  # No baseline → cannot detect stockout

    # Compute baseline velocity
    baseline_total_units = sum(r.quantity_sold for r in baseline_records)
    baseline_total_days = sum(r.period_days for r in baseline_records)
    if baseline_total_days == 0:
        return []
    baseline_velocity = baseline_total_units / baseline_total_days

    if baseline_velocity == 0:
        return []  # No sales even historically → cannot detect a drop

    events = []
    for record in recent_records[:lookback_periods]:
        velocity = record.daily_velocity
        velocity_ratio = velocity / baseline_velocity

        if velocity_ratio < _HIGH_THRESHOLD:
            severity = "HIGH"
        elif velocity_ratio < _MEDIUM_THRESHOLD:
            severity = "MEDIUM"
        else:
            continue  # No significant drop — no stockout

        missed = max(0.0, (baseline_velocity - velocity) * record.period_days)
        events.append(
            StockoutEvent(
                sku_code=sku_code,
                detected_velocity=velocity,
                baseline_velocity=baseline_velocity,
                severity=severity,
                estimated_missed_sales_units=missed,
            )
        )

    return events
