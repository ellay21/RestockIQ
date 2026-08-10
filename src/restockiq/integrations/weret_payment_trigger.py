"""
WeretPaymentTrigger — initiates supplier payments via WERET Pay.

Architecture: driven adapter — not importable from domain or ports.
Uses httpx + tenacity with idempotency key to prevent duplicate payments.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from restockiq.integrations.ports import PaymentTriggerPort
from restockiq.shared_kernel.errors import ExternalServiceError

if TYPE_CHECKING:
    from restockiq.shared_kernel.value_objects import MerchantId, Money

logger = logging.getLogger(__name__)


class WeretPaymentTrigger(PaymentTriggerPort):
    """
    Initiates a supplier payment via the WERET Pay API.

    Sends an idempotency key with every payment request so retries
    after a network timeout cannot trigger duplicate charges.

    Retry policy: 3 attempts, exponential backoff (1s, 2s, 4s).
    """

    PAYMENT_PATH = "/api/payments/trigger"

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    def trigger_payment(
        self,
        merchant_id: MerchantId,
        amount: Money,
        reference: str,
    ) -> str:
        idempotency_key = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{merchant_id}:{reference}"))
        payload = {
            "merchant_id": str(merchant_id),
            "amount": str(amount.amount),
            "currency": amount.currency,
            "reference": reference,
            "idempotency_key": idempotency_key,
        }

        try:
            response = httpx.post(
                f"{self._base_url}{self.PAYMENT_PATH}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                },
                timeout=15.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                "WERET",
                f"Payment API returned HTTP {exc.response.status_code}: {exc.response.text}",
            ) from exc
        except httpx.TransportError:
            raise  # Allow tenacity to retry
        except Exception as exc:
            raise ExternalServiceError("WERET", f"Unexpected error: {exc}") from exc

        data = response.json()
        transaction_id: str = data.get("transaction_id", idempotency_key)
        logger.info(
            "Triggered payment for merchant %s: %s %s (txn: %s)",
            merchant_id,
            amount.amount,
            amount.currency,
            transaction_id,
        )
        return transaction_id
