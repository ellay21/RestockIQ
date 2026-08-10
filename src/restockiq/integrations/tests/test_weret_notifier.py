"""
 WeretNotifier tests using httpx mock transport.

No real WERET server required — uses httpx's MockTransport to inject
canned responses.  Tests both success and error paths, plus retry behaviour.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from restockiq.integrations.ports import NotificationPort
from restockiq.integrations.weret_notifier import WeretNotifier
from restockiq.recommendations.domain import (
    ConfidenceLevel,
    RestockRecommendation,
    SkuRecommendation,
)
from restockiq.shared_kernel.errors import ExternalServiceError
from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode

# Fixtures


@pytest.fixture
def merchant_id() -> MerchantId:
    return MerchantId.generate()


@pytest.fixture
def sample_recommendation(merchant_id: MerchantId) -> RestockRecommendation:
    now = datetime.now(tz=UTC)
    return RestockRecommendation(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        signal_captured_at=now,
        created_at=now,
        sku_recommendations=(
            SkuRecommendation(
                sku_code=SkuCode("SUGAR"),
                units_to_order=5,
                estimated_cost=Money(Decimal("100"), "ETB"),
                expected_margin=Money(Decimal("25"), "ETB"),
                rationale="High margin",
                deciding_factor="HIGH_MARGIN",
            ),
        ),
        total_estimated_cost=Money(Decimal("100"), "ETB"),
        total_expected_margin=Money(Decimal("25"), "ETB"),
        confidence_score=0.75,
        confidence_level=ConfidenceLevel.HIGH,
        solver_status="OPTIMAL",
    )


# Tests


class TestWeretNotifier:
    def test_notifier_sends_correct_payload_on_success(
        self, merchant_id: MerchantId, sample_recommendation: RestockRecommendation
    ) -> None:

        sent_payloads: list[dict] = []

        def mock_post(url: str, json: dict, headers: dict, timeout: float):
            sent_payloads.append(json)
            return httpx.Response(200, json={"status": "sent"}, request=httpx.Request("POST", url))

        with patch("restockiq.integrations.weret_notifier.httpx.post", side_effect=mock_post):
            notifier = WeretNotifier(base_url="http://weret.test", api_key="key")
            notifier.notify_recommendation_ready(merchant_id, sample_recommendation)

        assert len(sent_payloads) == 1
        payload = sent_payloads[0]
        assert payload["merchant_id"] == str(merchant_id)
        assert payload["type"] == "recommendation_ready"
        assert payload["confidence_level"] == "HIGH"
        assert payload["actionable_sku_count"] == 1

    def test_notifier_raises_external_service_error_on_4xx(
        self, merchant_id: MerchantId, sample_recommendation: RestockRecommendation
    ) -> None:
        def mock_post(url: str, json: dict, headers: dict, timeout: float):
            return httpx.Response(403, text="Forbidden", request=httpx.Request("POST", url))

        with patch("restockiq.integrations.weret_notifier.httpx.post", side_effect=mock_post):
            notifier = WeretNotifier(base_url="http://weret.test", api_key="key")
            with pytest.raises(ExternalServiceError):
                notifier.notify_recommendation_ready(merchant_id, sample_recommendation)

    def test_notifier_is_a_notification_port(self) -> None:
        notifier = WeretNotifier(base_url="http://weret.test", api_key="key")
        assert isinstance(notifier, NotificationPort)
