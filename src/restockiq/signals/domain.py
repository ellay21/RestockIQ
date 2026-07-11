"""
MerchantFinancialSignal — the core input value object and related types.

A Signal is a snapshot of a merchant's recent sales history and available cash.
It is the primary input to the demand estimator and the optimizer.

Hexagonal rigor: FULL — this is the primary port/adapter surface.
Domain code here has zero I/O or framework imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from restockiq.shared_kernel.errors import SignalValidationError

if TYPE_CHECKING:
    from datetime import datetime

    from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode


class SignalInputMethod(StrEnum):
    """
    Records which adapter produced this MerchantFinancialSignal.

    Used by the ConfidenceScorer: WERET_WEBHOOK data is considered more
    reliable than MANUAL_ENTRY because it comes from real transaction records
    rather than self-reported estimates.
    """

    WERET_WEBHOOK = "weret_webhook"
    MANUAL_ENTRY = "manual_entry"
    CSV_IMPORT = "csv_import"


class CashSource(StrEnum):
    """Records how the cash_on_hand figure was obtained."""

    MANUAL = "manual"          # Merchant typed in a number
    WERET_FORECAST = "weret_forecast"  # Pulled from WERET's cash-flow forecast


@dataclass(frozen=True)
class SkuSalesRecord:
    """
    A single SKU's sales data over a reporting period.

    Invariants:
      - quantity_sold >= 0  (a period with zero sales is valid)
      - period_days > 0     (period must span at least one day)
    """

    sku_code: SkuCode
    quantity_sold: int    # Total units sold in the reporting period
    period_days: int      # Length of the reporting period in calendar days

    def __post_init__(self) -> None:
        if self.quantity_sold < 0:
            raise SignalValidationError(
                f"SkuSalesRecord for '{self.sku_code}': quantity_sold cannot be "
                f"negative, got {self.quantity_sold}"
            )
        if self.period_days <= 0:
            raise SignalValidationError(
                f"SkuSalesRecord for '{self.sku_code}': period_days must be "
                f"positive, got {self.period_days}"
            )

    @property
    def daily_velocity(self) -> float:
        """Average units sold per day over the reporting period."""
        return self.quantity_sold / self.period_days


@dataclass(frozen=True)
class MerchantFinancialSignal:
    """
    Immutable snapshot of a merchant's financial state and recent sales.

    This is the single input shape that ALL signal adapters must produce.
    Every downstream module (demand estimator, optimizer) works exclusively
    with this type — never with the raw webhook payload or CSV row.

    Invariants:
      - sales_records must be non-empty
      - cash_on_hand.amount >= 0  (enforced by Money; explicit check for clarity)
      - captured_at must be timezone-aware
    """

    merchant_id: MerchantId
    cash_on_hand: Money
    sales_records: tuple[SkuSalesRecord, ...]
    input_method: SignalInputMethod
    captured_at: datetime
    cash_source: CashSource = CashSource.MANUAL

    def __post_init__(self) -> None:
        if not self.sales_records:
            raise SignalValidationError(
                "MerchantFinancialSignal must contain at least one SkuSalesRecord"
            )
        # Money already validates non-negative, but we re-state for clarity
        if self.cash_on_hand.amount < 0:
            raise SignalValidationError(
                f"cash_on_hand cannot be negative, got {self.cash_on_hand}"
            )
        if self.captured_at.tzinfo is None:
            raise SignalValidationError(
                "captured_at must be a timezone-aware datetime"
            )

    @property
    def sku_codes(self) -> frozenset[SkuCode]:
        """The set of SKU codes present in this signal."""
        return frozenset(r.sku_code for r in self.sales_records)

    def get_record_for_sku(self, sku_code: SkuCode) -> SkuSalesRecord | None:
        """Return the sales record for a specific SKU, or None if not present."""
        for record in self.sales_records:
            if record.sku_code == sku_code:
                return record
        return None

    @property
    def is_weret_sourced(self) -> bool:
        """True when this signal originated from a WERET webhook."""
        return self.input_method == SignalInputMethod.WERET_WEBHOOK
