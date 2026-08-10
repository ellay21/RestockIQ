"""
WeretPaymentTrigger tests using httpx mock transport.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from restockiq.integrations.ports import PaymentTriggerPort
from restockiq.integrations.weret_payment_trigger import WeretPaymentTrigger
from restockiq.shared_kernel.errors import ExternalServiceError
from restockiq.shared_kernel.value_objects import MerchantId, Money

_DUMMY_REQUEST = httpx.Request("POST", "http://weret.test")


@pytest.fixture
def merchant_id() -> MerchantId:
    return MerchantId.generate()


@pytest.fixture
def trigger() -> WeretPaymentTrigger:
    return WeretPaymentTrigger(base_url="http://weret.test", api_key="key")


class TestWeretPaymentTrigger:
    def test_trigger_payment_returns_transaction_id(
        self, trigger: WeretPaymentTrigger, merchant_id: MerchantId
    ) -> None:
        def mock_post(
            url: str, json: dict[str, Any], headers: dict[str, Any], timeout: float
        ) -> httpx.Response:
            return httpx.Response(
                200, json={"transaction_id": "txn-abc-123"}, request=_DUMMY_REQUEST
            )

        patch_target = "restockiq.integrations.weret_payment_trigger.httpx.post"
        with patch(patch_target, side_effect=mock_post):
            txn_id = trigger.trigger_payment(
                merchant_id=merchant_id,
                amount=Money(Decimal("100"), "ETB"),
                reference="rec-12345",
            )

        assert txn_id == "txn-abc-123"

    def test_trigger_includes_idempotency_key_in_headers(
        self, trigger: WeretPaymentTrigger, merchant_id: MerchantId
    ) -> None:
        captured_headers: list[dict[str, Any]] = []

        def mock_post(
            url: str, json: dict[str, Any], headers: dict[str, Any], timeout: float
        ) -> httpx.Response:
            captured_headers.append(headers)
            return httpx.Response(200, json={"transaction_id": "txn-xyz"}, request=_DUMMY_REQUEST)

        patch_target = "restockiq.integrations.weret_payment_trigger.httpx.post"
        with patch(patch_target, side_effect=mock_post):
            trigger.trigger_payment(
                merchant_id=merchant_id,
                amount=Money(Decimal("100"), "ETB"),
                reference="rec-unique",
            )

        assert "Idempotency-Key" in captured_headers[0]

    def test_same_reference_produces_same_idempotency_key(
        self, trigger: WeretPaymentTrigger, merchant_id: MerchantId
    ) -> None:
        """Idempotency key must be deterministic for the same merchant+reference."""
        keys: list[str] = []

        def mock_post(
            url: str, json: dict[str, Any], headers: dict[str, Any], timeout: float
        ) -> httpx.Response:
            keys.append(headers["Idempotency-Key"])
            return httpx.Response(200, json={"transaction_id": "txn"}, request=_DUMMY_REQUEST)

        patch_target = "restockiq.integrations.weret_payment_trigger.httpx.post"
        with patch(patch_target, side_effect=mock_post):
            trigger.trigger_payment(merchant_id, Money(Decimal("100"), "ETB"), "ref-1")
            trigger.trigger_payment(merchant_id, Money(Decimal("200"), "ETB"), "ref-1")

        assert keys[0] == keys[1], "Same merchant+reference must produce the same idempotency key"

    def test_payment_trigger_raises_on_http_error(
        self, trigger: WeretPaymentTrigger, merchant_id: MerchantId
    ) -> None:
        def mock_post(
            url: str, json: dict[str, Any], headers: dict[str, Any], timeout: float
        ) -> httpx.Response:
            return httpx.Response(400, text="Bad Request", request=_DUMMY_REQUEST)

        patch_target = "restockiq.integrations.weret_payment_trigger.httpx.post"
        with patch(patch_target, side_effect=mock_post), pytest.raises(ExternalServiceError):
            trigger.trigger_payment(merchant_id, Money(Decimal("100"), "ETB"), "ref-fail")

    def test_payment_trigger_is_a_payment_port(self, trigger: WeretPaymentTrigger) -> None:
        assert isinstance(trigger, PaymentTriggerPort)
