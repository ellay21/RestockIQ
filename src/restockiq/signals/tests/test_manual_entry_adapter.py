"""
ManualEntryAdapter tests.

Proves the adapter correctly translates a form dict into a MerchantFinancialSignal
and rejects malformed inputs with clear error messages.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from restockiq.shared_kernel.errors import AdapterError
from restockiq.shared_kernel.value_objects import MerchantId, SkuCode
from restockiq.signals.adapters.manual_entry_adapter import ManualEntryAdapter
from restockiq.signals.domain import MerchantFinancialSignal, SignalInputMethod


@pytest.fixture
def adapter() -> ManualEntryAdapter:
    return ManualEntryAdapter()


@pytest.fixture
def valid_form(merchant_id: str) -> dict:
    return {
        "merchant_id": merchant_id,
        "currency": "ETB",
        "cash_on_hand": "500.00",
        "sales": [
            {"sku_code": "SUGAR-1KG", "quantity_sold": 50, "period_days": 7},
            {"sku_code": "OIL-1L", "quantity_sold": 20, "period_days": 7},
        ],
    }


@pytest.fixture
def merchant_id() -> str:
    return str(MerchantId.generate())


class TestManualEntryAdapter:
    def test_manual_entry_adapter_produces_valid_signal_from_form_dict(
        self, adapter: ManualEntryAdapter, valid_form: dict
    ) -> None:
        signal = adapter.build_signal(valid_form)
        assert isinstance(signal, MerchantFinancialSignal)
        assert signal.input_method == SignalInputMethod.MANUAL_ENTRY
        assert signal.cash_on_hand.amount == Decimal("500.00")
        assert len(signal.sales_records) == 2

    def test_adapter_normalises_sku_code_to_uppercase(
        self, adapter: ManualEntryAdapter, merchant_id: str
    ) -> None:
        form = {
            "merchant_id": merchant_id,
            "currency": "ETB",
            "cash_on_hand": "100",
            "sales": [{"sku_code": "sugar-1kg", "quantity_sold": 5, "period_days": 7}],
        }
        signal = adapter.build_signal(form)
        assert SkuCode("SUGAR-1KG") in signal.sku_codes

    def test_missing_merchant_id_raises_adapter_error(
        self, adapter: ManualEntryAdapter, valid_form: dict
    ) -> None:
        del valid_form["merchant_id"]
        with pytest.raises(AdapterError) as exc_info:
            adapter.build_signal(valid_form)
        assert exc_info.value.field == "merchant_id"

    def test_missing_cash_on_hand_raises_adapter_error(
        self, adapter: ManualEntryAdapter, valid_form: dict
    ) -> None:
        del valid_form["cash_on_hand"]
        with pytest.raises(AdapterError) as exc_info:
            adapter.build_signal(valid_form)
        assert exc_info.value.field == "cash_on_hand"

    def test_empty_sales_list_raises_adapter_error(
        self, adapter: ManualEntryAdapter, valid_form: dict
    ) -> None:
        valid_form["sales"] = []
        with pytest.raises(AdapterError) as exc_info:
            adapter.build_signal(valid_form)
        assert exc_info.value.field == "sales"

    def test_malformed_sales_row_raises_with_row_index(
        self, adapter: ManualEntryAdapter, valid_form: dict
    ) -> None:
        valid_form["sales"][1]["quantity_sold"] = "not-a-number"
        with pytest.raises(AdapterError) as exc_info:
            adapter.build_signal(valid_form)
        assert "sales[1]" in (exc_info.value.field or "")

    def test_non_dict_input_raises(self, adapter: ManualEntryAdapter) -> None:
        with pytest.raises(AdapterError):
            adapter.build_signal("not a dict")

    def test_default_captured_at_is_timezone_aware(
        self, adapter: ManualEntryAdapter, valid_form: dict
    ) -> None:
        """captured_at must be timezone-aware even when not supplied."""
        signal = adapter.build_signal(valid_form)
        assert signal.captured_at.tzinfo is not None
