"""
StockoutLossEstimator — estimates cash lost due to a stockout event.

Pure domain logic: no I/O.  Takes a StockoutEvent and a SKU's sell price
to compute the estimated gross revenue and margin lost.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from restockiq.shared_kernel.value_objects import Money, SkuCode

if TYPE_CHECKING:
    from restockiq.stockout_analysis.detector import StockoutEvent


@dataclass(frozen=True)
class StockoutLossEstimate:
    """
    Estimated revenue and margin lost due to a stockout.

    Attributes:
        sku_code:       The affected product.
        missed_units:   Estimated units not sold.
        revenue_lost:   Revenue that could have been earned.
        margin_lost:    Gross profit that could have been earned.
        severity:       Forwarded from the StockoutEvent.
    """

    sku_code: SkuCode
    missed_units: float
    revenue_lost: Money
    margin_lost: Money
    severity: str


def estimate_loss(
    event: StockoutEvent,
    sell_price: Money,
    cost_price: Money,
) -> StockoutLossEstimate:
    """
    Estimate the monetary cost of a stockout event.

    Args:
        event:      The detected stockout event.
        sell_price: What the merchant charges per unit.
        cost_price: What the merchant pays per unit (for margin computation).

    Returns:
        A StockoutLossEstimate with revenue_lost and margin_lost in the
        same currency as sell_price.
    """
    missed = event.estimated_missed_sales_units

    revenue_lost = Money(
        amount=Decimal(str(missed)) * sell_price.amount,
        currency=sell_price.currency,
    )
    margin_per_unit = sell_price.amount - cost_price.amount
    margin_lost = Money(
        amount=Decimal(str(missed)) * margin_per_unit,
        currency=sell_price.currency,
    )

    return StockoutLossEstimate(
        sku_code=event.sku_code,
        missed_units=missed,
        revenue_lost=revenue_lost,
        margin_lost=margin_lost,
        severity=event.severity,
    )
