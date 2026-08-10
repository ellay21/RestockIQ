"""
These are unit tests — no real WERET server.  The HMAC signature tests use
a locally computed signature to prove the verification path works.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest

from restockiq.shared_kernel.errors import AdapterError
from restockiq.shared_kernel.value_objects import SkuCode
from restockiq.signals.adapters.weret_adapter import WeretAdapter
from restockiq.signals.domain import CashSource, MerchantFinancialSignal, SignalInputMethod

VALID_PAYLOAD = {
    "merchant_id": str(uuid.uuid4()),
    "currency": "ETB",
    "available_cash": 500.0,
    "items": [
        {"sku_code": "SUGAR-1KG", "units_sold": 50, "period_days": 7},
        {"sku_code": "OIL-1L", "units_sold": 20, "period_days": 7},
    ],
    "event_timestamp": "2024-01-15T10:00:00+00:00",
}


def sign_payload(payload: dict, secret: str) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestWeretAdapterNoSecret:
    """Tests when no webhook_secret is configured (signature validation disabled)."""

    @pytest.fixture
    def adapter(self) -> WeretAdapter:
        return WeretAdapter(webhook_secret=None)

    def test_valid_payload_produces_weret_signal(self, adapter: WeretAdapter) -> None:
        signal = adapter.build_signal({"payload": VALID_PAYLOAD, "signature": None})
        assert isinstance(signal, MerchantFinancialSignal)
        assert signal.input_method == SignalInputMethod.WERET_WEBHOOK
        assert signal.cash_source == CashSource.WERET_FORECAST
        assert len(signal.sales_records) == 2

    def test_missing_items_raises(self, adapter: WeretAdapter) -> None:
        payload = dict(VALID_PAYLOAD)
        del payload["items"]
        with pytest.raises(AdapterError) as exc_info:
            adapter.build_signal({"payload": payload, "signature": None})
        assert exc_info.value.field == "items"

    def test_empty_items_raises(self, adapter: WeretAdapter) -> None:
        payload = dict(VALID_PAYLOAD)
        payload["items"] = []
        with pytest.raises(AdapterError) as exc_info:
            adapter.build_signal({"payload": payload, "signature": None})
        assert "empty" in exc_info.value.reason

    def test_invalid_sku_code_raises_with_field(self, adapter: WeretAdapter) -> None:
        payload = dict(VALID_PAYLOAD)
        payload["items"] = [{"sku_code": "INVALID CODE", "units_sold": 10, "period_days": 7}]
        with pytest.raises(AdapterError) as exc_info:
            adapter.build_signal({"payload": payload, "signature": None})
        assert "items[0].sku_code" in (exc_info.value.field or "")

    def test_sku_codes_normalised_to_uppercase(self, adapter: WeretAdapter) -> None:
        payload = dict(VALID_PAYLOAD)
        payload["items"] = [{"sku_code": "sugar-1kg", "units_sold": 50, "period_days": 7}]
        signal = adapter.build_signal({"payload": payload, "signature": None})
        assert SkuCode("SUGAR-1KG") in signal.sku_codes

    def test_weret_signal_is_weret_sourced(self, adapter: WeretAdapter) -> None:
        signal = adapter.build_signal({"payload": VALID_PAYLOAD, "signature": None})
        assert signal.is_weret_sourced is True

    def test_verify_signature_without_secret_raises(self, adapter: WeretAdapter) -> None:
        with pytest.raises(AdapterError, match="not configured"):
            adapter._verify_signature(VALID_PAYLOAD, "sha256=abc")


class TestWeretAdapterWithSecret:
    """Tests when webhook_secret is configured — signature verification required."""

    SECRET = "test-secret-key-12345"

    @pytest.fixture
    def adapter(self) -> WeretAdapter:
        return WeretAdapter(webhook_secret=self.SECRET)

    def test_valid_signature_passes(self, adapter: WeretAdapter) -> None:
        signature = sign_payload(VALID_PAYLOAD, self.SECRET)
        signal = adapter.build_signal({"payload": VALID_PAYLOAD, "signature": signature})
        assert isinstance(signal, MerchantFinancialSignal)

    def test_invalid_signature_raises(self, adapter: WeretAdapter) -> None:
        with pytest.raises(AdapterError, match="mismatch"):
            adapter.build_signal({"payload": VALID_PAYLOAD, "signature": "sha256=bad"})

    def test_missing_signature_raises(self, adapter: WeretAdapter) -> None:
        with pytest.raises(AdapterError, match="missing"):
            adapter.build_signal({"payload": VALID_PAYLOAD, "signature": None})

    def test_wrong_format_signature_raises(self, adapter: WeretAdapter) -> None:
        with pytest.raises(AdapterError, match="format"):
            adapter.build_signal({"payload": VALID_PAYLOAD, "signature": "basic abc123"})
