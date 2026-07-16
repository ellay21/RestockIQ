"""
WeretAdapter - translates inbound WERET webhook payloads into MerchantFinancialSignal.

WERET sends a webhook after each merchant cash-flow event.  The adapter validates
the HMAC-SHA256 signature and translates the payload into the canonical signal shape.

Expected webhook payload (JSON):
    {
        "merchant_id": str (UUID),
        "currency": str (ISO 4217),
        "available_cash": float,
        "items": [
            {
                "sku_code": str,
                "units_sold": int,
                "period_days": int
            },
            ...
        ],
        "event_timestamp": str (ISO 8601, UTC)
    }
"WERET sends a webhook if connected; otherwise the merchant enters data manually."
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from restockiq.shared_kernel.errors import AdapterError
from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode
from restockiq.signals.domain import (
    CashSource,
    MerchantFinancialSignal,
    SignalInputMethod,
    SkuSalesRecord,
)
from restockiq.signals.ports import SignalSourcePort

SOURCE = "WeretAdapter"


class WeretAdapter(SignalSourcePort):
    """
    Translates inbound WERET webhook payloads into MerchantFinancialSignal.

    Optionally validates the HMAC-SHA256 signature header when a webhook_secret
    is configured.  In test mode (webhook_secret=None), signature validation is
    skipped entirely.
    """

    def __init__(self, webhook_secret: str | None = None) -> None:
        """
        Args:
            webhook_secret: The shared HMAC-SHA256 secret from the .env file.
                            Set to None to disable signature verification (tests only).
        """
        self._secret = webhook_secret

    def build_signal(self, raw_input: object) -> MerchantFinancialSignal:
        """
        Args:
            raw_input: A dict with keys: payload (dict), signature (str | None).
                       {
                           "payload": {...},          # the WERET JSON body
                           "signature": "sha256=..."  # X-Weret-Signature header value
                       }

        Raises:
            AdapterError: if the signature is invalid or payload is malformed.
        """
        if not isinstance(raw_input, dict):
            raise AdapterError(SOURCE, f"Expected dict, got {type(raw_input).__name__}")

        raw: dict[str, Any] = raw_input
        payload = raw.get("payload")
        signature = raw.get("signature")

        if not isinstance(payload, dict):
            raise AdapterError(SOURCE, "raw_input.payload must be a dict", field="payload")

        # Validate signature if a secret is configured
        if self._secret:
            self._verify_signature(payload, signature)

        return self._parse_payload(payload)

    # Signature verification 

    def _verify_signature(self, payload: dict[str, Any], signature: str | None) -> None:
        if not self._secret:
            raise AdapterError(
                SOURCE,
                "Webhook secret is not configured for signature verification",
                field="signature",
            )
        if not signature:
            raise AdapterError(
                SOURCE,
                "Webhook signature header is missing — potential spoofed request",
                field="signature",
            )
        if not signature.startswith("sha256="):
            raise AdapterError(
                SOURCE,
                f"Unexpected signature format: {signature!r}",
                field="signature",
            )
        import json
        body_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        expected = "sha256=" + hmac.new(
            self._secret.encode(), body_bytes, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise AdapterError(
                SOURCE,
                "HMAC-SHA256 signature mismatch — request rejected",
                field="signature",
            )

    # Payload parsing

    def _parse_payload(self, payload: dict[str, Any]) -> MerchantFinancialSignal:
        merchant_id = self._parse_merchant_id(payload)
        cash_on_hand = self._parse_cash(payload)
        captured_at = self._parse_timestamp(payload)
        sales_records = self._parse_items(payload)

        return MerchantFinancialSignal(
            merchant_id=merchant_id,
            cash_on_hand=cash_on_hand,
            sales_records=tuple(sales_records),
            input_method=SignalInputMethod.WERET_WEBHOOK,
            captured_at=captured_at,
            cash_source=CashSource.WERET_FORECAST,
        )

    def _parse_merchant_id(self, payload: dict[str, Any]) -> MerchantId:
        raw = payload.get("merchant_id")
        if raw is None:
            raise AdapterError(SOURCE, "missing merchant_id", field="merchant_id")
        try:
            return MerchantId.from_str(str(raw))
        except Exception as exc:
            raise AdapterError(SOURCE, f"invalid merchant_id: {exc}", field="merchant_id") from exc

    def _parse_cash(self, payload: dict[str, Any]) -> Money:
        raw_cash = payload.get("available_cash")
        currency = str(payload.get("currency", "ETB"))
        if raw_cash is None:
            raise AdapterError(SOURCE, "missing available_cash", field="available_cash")
        try:
            amount = Decimal(str(raw_cash))
        except InvalidOperation as exc:
            raise AdapterError(
                SOURCE,
                f"available_cash must be a valid decimal, got {raw_cash!r}",
                field="available_cash",
            ) from exc
        try:
            return Money(amount=amount, currency=currency)
        except Exception as exc:
            raise AdapterError(SOURCE, str(exc), field="available_cash") from exc

    def _parse_timestamp(self, payload: dict[str, Any]) -> datetime:
        raw = payload.get("event_timestamp")
        if raw is None:
            return datetime.now(tz=UTC)
        try:
            dt = datetime.fromisoformat(str(raw))
        except ValueError as exc:
            raise AdapterError(
                SOURCE,
                f"event_timestamp must be ISO 8601, got {raw!r}",
                field="event_timestamp",
            ) from exc
        else:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt

    def _parse_items(self, payload: dict[str, Any]) -> list[SkuSalesRecord]:
        raw_items = payload.get("items")
        if raw_items is None:
            raise AdapterError(SOURCE, "missing items array", field="items")
        if not isinstance(raw_items, list):
            raise AdapterError(SOURCE, "items must be a list", field="items")
        if not raw_items:
            raise AdapterError(SOURCE, "items array is empty", field="items")

        return [self._parse_item(item, idx) for idx, item in enumerate(raw_items)]

    def _parse_item(self, item: Any, idx: int) -> SkuSalesRecord:
        field_prefix = f"items[{idx}]"
        if not isinstance(item, dict):
            raise AdapterError(SOURCE, "item must be a dict", field=field_prefix)

        raw_sku = item.get("sku_code")
        raw_qty = item.get("units_sold")
        raw_days = item.get("period_days")

        if raw_sku is None:
            raise AdapterError(SOURCE, "missing sku_code", field=f"{field_prefix}.sku_code")
        if raw_qty is None:
            raise AdapterError(SOURCE, "missing units_sold", field=f"{field_prefix}.units_sold")
        if raw_days is None:
            raise AdapterError(SOURCE, "missing period_days", field=f"{field_prefix}.period_days")

        try:
            sku_code = SkuCode(str(raw_sku))
        except Exception as exc:
            raise AdapterError(SOURCE, str(exc), field=f"{field_prefix}.sku_code") from exc

        try:
            return SkuSalesRecord(
                sku_code=sku_code,
                quantity_sold=int(raw_qty),
                period_days=int(raw_days),
            )
        except Exception as exc:
            raise AdapterError(SOURCE, str(exc), field=field_prefix) from exc
