"""
Outbound integration ports - abstract contracts for external service calls.

All outbound WERET calls must go through these ports so the application
can be tested without a real WERET server.

Hexagonal rigor: FULL - no httpx or external service imports permitted.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from restockiq.recommendations.domain import RestockRecommendation
    from restockiq.shared_kernel.value_objects import MerchantId, Money


class NotificationPort(abc.ABC):
    """
    Port: send a push notification to a merchant via WERET.

    Called after a recommendation is generated to alert the merchant
    that their weekly restocking advice is ready.
    """

    @abc.abstractmethod
    def notify_recommendation_ready(
        self,
        merchant_id: MerchantId,
        recommendation: RestockRecommendation,
    ) -> None:
        """
        Send a notification to the merchant that their recommendation is ready.

        Args:
            merchant_id:     The merchant to notify.
            recommendation:  The recommendation that was just generated.

        Raises:
            ExternalServiceError: if the WERET API call fails after retries.
        """
        ...


class PaymentTriggerPort(abc.ABC):
    """
    Port: initiate a supplier payment via WERET's payment trigger API.

    Called after a merchant accepts a recommendation to auto-initiate payment
    to the supplier.  This is optional — merchants can also pay manually.

    See Context.md: "Auto-initiate payment if merchant uses WERET Pay."
    """

    @abc.abstractmethod
    def trigger_payment(
        self,
        merchant_id: MerchantId,
        amount: Money,
        reference: str,
    ) -> str:
        """
        Trigger a supplier payment via WERET Pay.

        Args:
            merchant_id: The merchant initiating the payment.
            amount:      The payment amount (must match the merchant's currency).
            reference:   The recommendation ID or order reference for auditing.

        Returns:
            A payment transaction ID from the WERET API.

        Raises:
            ExternalServiceError: if the WERET payment API call fails after retries.
        """
        ...
