"""
In-memory fake SignalSourcePort and SignalRepository for cross-module tests.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode
from restockiq.signals.domain import (
    MerchantFinancialSignal,
    SignalInputMethod,
    SkuSalesRecord,
)
from restockiq.signals.ports import SignalRepository, SignalSourcePort

if TYPE_CHECKING:
    from collections.abc import Sequence


class FakeSignalSourcePort(SignalSourcePort):
    """
    Deterministic fake SignalSourcePort.

    Wraps a pre-built MerchantFinancialSignal; build_signal() simply returns it.
    Use this to inject a known signal into tests of downstream services without
    going through a real adapter.
    """

    def __init__(self, signal: MerchantFinancialSignal) -> None:
        self._signal = signal

    def build_signal(self, raw_input: object) -> MerchantFinancialSignal:
        return self._signal

    @classmethod
    def with_defaults(
        cls,
        merchant_id: MerchantId | None = None,
        cash_on_hand: str = "1000",
        currency: str = "ETB",
        sales: list[tuple[str, int, int]] | None = None,
    ) -> FakeSignalSourcePort:
        """
        Convenience constructor with sensible defaults.

        Args:
            merchant_id:  Merchant to associate the signal with.
            cash_on_hand: Cash string (e.g. "1000").
            currency:     ISO 4217 code.
            sales:        List of (sku_code, quantity_sold, period_days) tuples.
        """
        mid = merchant_id or MerchantId.generate()
        if sales is None:
            sales = [("SUGAR-1KG", 50, 7)]
        records = tuple(
            SkuSalesRecord(sku_code=SkuCode(s[0]), quantity_sold=s[1], period_days=s[2])
            for s in sales
        )
        signal = MerchantFinancialSignal(
            merchant_id=mid,
            cash_on_hand=Money(Decimal(cash_on_hand), currency),
            sales_records=records,
            input_method=SignalInputMethod.MANUAL_ENTRY,
            captured_at=datetime.now(tz=UTC),
        )
        return cls(signal)


class InMemorySignalRepository(SignalRepository):
    """In-memory fake SignalRepository for unit tests."""

    def __init__(self) -> None:
        self._store: dict[MerchantId, list[MerchantFinancialSignal]] = defaultdict(list)

    async def save(self, signal: MerchantFinancialSignal) -> None:
        self._store[signal.merchant_id].append(signal)

    async def get_history_for_merchant(
        self,
        merchant_id: MerchantId,
        limit: int = 30,
    ) -> Sequence[MerchantFinancialSignal]:
        history = self._store.get(merchant_id, [])
        # Return newest first
        return list(reversed(history))[:limit]

    def count(self) -> int:
        """Total number of signals persisted (useful in assertions)."""
        return sum(len(signals) for signals in self._store.values())
