"""
WeretNotifier - sends push notifications to merchants via the WERET API.

Uses httpx with tenacity retry logic (3 attempts, exponential backoff).

Architecture: this module is a driven adapter - it must not be imported
from any domain module, port, or service.  It is wired in via container.py.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from restockiq.integrations.ports import NotificationPort
from restockiq.shared_kernel.errors import ExternalServiceError

if TYPE_CHECKING:
    from restockiq.recommendations.domain import RestockRecommendation
    from restockiq.shared_kernel.value_objects import MerchantId

logger = logging.getLogger(__name__)


class WeretNotifier(NotificationPort):
    """
    Sends a push notification to a merchant via the WERET notification API.

    The notification payload includes:
      - The total recommended order amount
      - The confidence level
      - A deep-link URL to the RestockIQ recommendation

    Retry policy: 3 attempts with exponential backoff (1s, 2s, 4s).
    """

    NOTIFICATION_PATH = "/api/notifications/push"

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    def notify_recommendation_ready(
        self,
        merchant_id: MerchantId,
        recommendation: RestockRecommendation,
    ) -> None:
        payload = {
            "merchant_id": str(merchant_id),
            "type": "recommendation_ready",
            "recommendation_id": str(recommendation.id),
            "total_estimated_cost": str(recommendation.total_estimated_cost.amount),
            "currency": recommendation.total_estimated_cost.currency,
            "confidence_level": recommendation.confidence_level.value,
            "actionable_sku_count": len(recommendation.actionable_items),
        }

        try:
            response = httpx.post(
                f"{self._base_url}{self.NOTIFICATION_PATH}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                "WERET",
                f"Notification API returned HTTP {exc.response.status_code}: {exc.response.text}",
            ) from exc
        except httpx.TransportError:
            raise  # Allow tenacity to retry
        except Exception as exc:
            raise ExternalServiceError("WERET", f"Unexpected error: {exc}") from exc

        logger.info(
            "Sent recommendation notification to merchant %s (recommendation %s)",
            merchant_id,
            recommendation.id,
        )
