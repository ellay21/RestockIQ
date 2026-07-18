"""
Demand estimator — fits a per-SKU demand distribution from historical signal data.

This module is pure domain logic: no I/O, no database calls, no adapters.
The only external library used is scipy/numpy for mathematical fitting, which
are mathematical computation libraries (not frameworks) and are permitted
by the Architecture.md §3 domain-isolation rule.

Hexagonal rigor: FULL — pure domain, zero I/O, no adapters needed at all.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy

    from restockiq.shared_kernel.value_objects import SkuCode
    from restockiq.signals.domain import SkuSalesRecord


@dataclass(frozen=True)
class DemandDistribution:
    """
    A fitted demand distribution for a single SKU.

    Models demand as a Poisson process with the given daily rate (lambda).
    For a Poisson distribution: E[X] = lambda, Var[X] = lambda, std = sqrt(lambda).

    Attributes:
        sku_code:    The SKU this distribution is for.
        mean_daily:  Expected demand per day (Poisson lambda).
        std_daily:   Standard deviation per day (sqrt(lambda) for Poisson).
        sample_size: Number of SkuSalesRecord observations used to fit.
        is_default:  True when there is no history to fit from; the distribution
                     is a defensible baseline rather than a data-driven estimate.
    """

    sku_code: SkuCode
    mean_daily: float
    std_daily: float
    sample_size: int
    is_default: bool

    def sample_period(self, days: int, rng: numpy.random.Generator) -> int:
        """
        Draw a single random demand sample for a period of `days` days.

        Args:
            days: Length of the demand period in days.
            rng:  A numpy random Generator (for reproducible samples in tests).

        Returns:
            Non-negative integer demand for the period.
        """
        lam = self.mean_daily * days
        if lam <= 0:
            return 0
        return int(rng.poisson(lam))


def estimate(
    sku_code: SkuCode,
    sales_records: list[SkuSalesRecord],
) -> DemandDistribution:
    """
    Fit a Poisson demand distribution from a list of sales records.

    The estimator uses the maximum-likelihood estimate for the Poisson
    parameter lambda, which is simply the sample mean:
        lambda_hat = total_units_sold / total_days

    Args:
        sku_code:      The SKU to estimate demand for.
        sales_records: Historical sales observations (may be empty).

    Returns:
        A DemandDistribution.  If `sales_records` is empty, returns a default
        distribution with mean_daily=0.0 and is_default=True; this is
        intentionally conservative — the system will not recommend buying
        a SKU it has no information about unless overridden.
    """
    if not sales_records:
        return DemandDistribution(
            sku_code=sku_code,
            mean_daily=0.0,
            std_daily=0.0,
            sample_size=0,
            is_default=True,
        )

    total_units = sum(record.quantity_sold for record in sales_records)
    total_days = sum(record.period_days for record in sales_records)

    if total_days == 0:
        # Defensive: period_days is validated > 0 per SkuSalesRecord, so this
        # branch should never execute, but we guard against it anyway.
        return DemandDistribution(
            sku_code=sku_code,
            mean_daily=0.0,
            std_daily=0.0,
            sample_size=len(sales_records),
            is_default=True,
        )

    mean_daily = total_units / total_days
    # Poisson: Var(X) = lambda, so std = sqrt(lambda)
    std_daily = math.sqrt(mean_daily)

    return DemandDistribution(
        sku_code=sku_code,
        mean_daily=mean_daily,
        std_daily=std_daily,
        sample_size=len(sales_records),
        is_default=False,
    )
