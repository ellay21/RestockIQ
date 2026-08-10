"""
Signal domain unit tests.

Tests MerchantFinancialSignal and SkuSalesRecord invariants.
Pure: no I/O, no mocks.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from restockiq.shared_kernel.errors import DomainValidationError, SignalValidationError
from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode
from restockiq.signals.domain import (
    MerchantFinancialSignal,
    SignalInputMethod,
    SkuSalesRecord,
)


@pytest.fixture
def valid_record() -> SkuSalesRecord:
    return SkuSalesRecord(
        sku_code=SkuCode("SUGAR"),
        quantity_sold=50,
        period_days=7,
    )


@pytest.fixture
def valid_signal(valid_record: SkuSalesRecord) -> MerchantFinancialSignal:
    return MerchantFinancialSignal(
        merchant_id=MerchantId.generate(),
        cash_on_hand=Money(Decimal("500"), "ETB"),
        sales_records=(valid_record,),
        input_method=SignalInputMethod.MANUAL_ENTRY,
        captured_at=datetime.now(tz=UTC),
    )


class TestSkuSalesRecord:
    def test_negative_quantity_sold_raises(self) -> None:
        with pytest.raises(SignalValidationError, match="negative"):
            SkuSalesRecord(sku_code=SkuCode("SUGAR"), quantity_sold=-1, period_days=7)

    def test_zero_quantity_sold_is_valid(self) -> None:
        """A period with zero sales is a valid observation (SKU may have stocked out)."""
        record = SkuSalesRecord(sku_code=SkuCode("SUGAR"), quantity_sold=0, period_days=7)
        assert record.quantity_sold == 0

    def test_zero_period_days_raises(self) -> None:
        with pytest.raises(SignalValidationError, match="positive"):
            SkuSalesRecord(sku_code=SkuCode("SUGAR"), quantity_sold=10, period_days=0)

    def test_daily_velocity_computation(self) -> None:
        record = SkuSalesRecord(sku_code=SkuCode("SUGAR"), quantity_sold=14, period_days=7)
        assert abs(record.daily_velocity - 2.0) < 1e-9


class TestMerchantFinancialSignal:
    def test_signal_rejects_negative_cash_on_hand(self) -> None:
        """Negative cash_on_hand must be rejected — either by Money or Signal."""
        with pytest.raises(DomainValidationError):
            MerchantFinancialSignal(
                merchant_id=MerchantId.generate(),
                cash_on_hand=Money(Decimal("-100"), "ETB"),
                sales_records=(SkuSalesRecord(SkuCode("SUGAR"), 10, 7),),
                input_method=SignalInputMethod.MANUAL_ENTRY,
                captured_at=datetime.now(tz=UTC),
            )

    def test_signal_rejects_empty_sales_records(self) -> None:
        with pytest.raises(SignalValidationError, match="at least one"):
            MerchantFinancialSignal(
                merchant_id=MerchantId.generate(),
                cash_on_hand=Money(Decimal("500"), "ETB"),
                sales_records=(),
                input_method=SignalInputMethod.MANUAL_ENTRY,
                captured_at=datetime.now(tz=UTC),
            )

    def test_signal_rejects_naive_datetime(self) -> None:
        with pytest.raises(SignalValidationError, match="timezone"):
            MerchantFinancialSignal(
                merchant_id=MerchantId.generate(),
                cash_on_hand=Money(Decimal("500"), "ETB"),
                sales_records=(SkuSalesRecord(SkuCode("SUGAR"), 10, 7),),
                input_method=SignalInputMethod.MANUAL_ENTRY,
                captured_at=datetime(2024, 1, 1),  # naive — no tzinfo
            )

    def test_is_weret_sourced_true_for_weret_webhook(self, valid_record: SkuSalesRecord) -> None:
        signal = MerchantFinancialSignal(
            merchant_id=MerchantId.generate(),
            cash_on_hand=Money(Decimal("500"), "ETB"),
            sales_records=(valid_record,),
            input_method=SignalInputMethod.WERET_WEBHOOK,
            captured_at=datetime.now(tz=UTC),
        )
        assert signal.is_weret_sourced is True

    def test_is_weret_sourced_false_for_manual(self, valid_signal: MerchantFinancialSignal) -> None:
        assert valid_signal.is_weret_sourced is False

    def test_sku_codes_returns_frozenset(self, valid_signal: MerchantFinancialSignal) -> None:
        assert SkuCode("SUGAR") in valid_signal.sku_codes

    def test_get_record_for_sku_returns_none_if_absent(
        self, valid_signal: MerchantFinancialSignal
    ) -> None:
        result = valid_signal.get_record_for_sku(SkuCode("OIL"))
        assert result is None
