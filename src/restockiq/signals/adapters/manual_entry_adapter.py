"""
ManualEntryAdapter — translates a merchant's hand-typed form into a MerchantFinancialSignal.

This adapter is the primary standalone path: a merchant who does not use WERET
can still use RestockIQ by entering their recent sales data manually.

Expected raw_input shape (dict):
    {
        "merchant_id": str (UUID),
        "currency": str (ISO 4217),
        "cash_on_hand": str | float | int (non-negative),
        "sales": [
            {"sku_code": str, "quantity_sold": int, "period_days": int},
            ...
        ],
        "captured_at": str (ISO 8601 datetime, timezone-aware) | None
    }
"""

from __future__ import annotations

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


class ManualEntryAdapter(SignalSourcePort):
    """
    Translates a validated form submission dict into a MerchantFinancialSignal.

    The adapter is intentionally strict: any missing or malformed field raises
    an AdapterError with a field name so the API layer can surface a useful
    validation message to the merchant.
    """

    SOURCE = "ManualEntryAdapter"

    def build_signal(self, raw_input: object) -> MerchantFinancialSignal:
        """
        Args:
            raw_input: A dict matching the expected schema above.

        Returns:
            A validated MerchantFinancialSignal.

        Raises:
            AdapterError: on any missing, wrong-typed, or out-of-range field.
        """
        if not isinstance(raw_input, dict):
            raise AdapterError(
                self.SOURCE,
                f"Expected a dict, got {type(raw_input).__name__}",
            )
        data: dict[str, Any] = raw_input

        merchant_id = self._parse_merchant_id(data)
        cash_on_hand = self._parse_cash_on_hand(data)
        sales_records = self._parse_sales(data)
        captured_at = self._parse_captured_at(data)

        return MerchantFinancialSignal(
            merchant_id=merchant_id,
            cash_on_hand=cash_on_hand,
            sales_records=tuple(sales_records),
            input_method=SignalInputMethod.MANUAL_ENTRY,
            captured_at=captured_at,
            cash_source=CashSource.MANUAL,
        )

    #  Field parsers

    def _parse_merchant_id(self, data: dict[str, Any]) -> MerchantId:
        raw = data.get("merchant_id")
        if raw is None:
            raise AdapterError(self.SOURCE, "missing required field", field="merchant_id")
        try:
            return MerchantId.from_str(str(raw))
        except Exception as exc:
            raise AdapterError(
                self.SOURCE, f"invalid merchant_id: {exc}", field="merchant_id"
            ) from exc

    def _parse_cash_on_hand(self, data: dict[str, Any]) -> Money:
        raw_cash = data.get("cash_on_hand")
        currency = data.get("currency", "ETB")
        if raw_cash is None:
            raise AdapterError(self.SOURCE, "missing required field", field="cash_on_hand")
        try:
            amount = Decimal(str(raw_cash))
        except InvalidOperation as exc:
            raise AdapterError(
                self.SOURCE,
                f"cash_on_hand must be a valid decimal number, got {raw_cash!r}",
                field="cash_on_hand",
            ) from exc
        try:
            return Money(amount=amount, currency=str(currency))
        except Exception as exc:
            raise AdapterError(self.SOURCE, str(exc), field="cash_on_hand") from exc

    def _parse_sales(self, data: dict[str, Any]) -> list[SkuSalesRecord]:
        raw_sales = data.get("sales")
        if raw_sales is None:
            raise AdapterError(self.SOURCE, "missing required field", field="sales")
        if not isinstance(raw_sales, list):
            raise AdapterError(
                self.SOURCE,
                f"'sales' must be a list, got {type(raw_sales).__name__}",
                field="sales",
            )
        if not raw_sales:
            raise AdapterError(
                self.SOURCE,
                "'sales' list must contain at least one entry",
                field="sales",
            )

        records = []
        for i, row in enumerate(raw_sales):
            records.append(self._parse_sales_row(row, row_index=i))
        return records

    def _parse_sales_row(self, row: Any, *, row_index: int) -> SkuSalesRecord:
        field_prefix = f"sales[{row_index}]"
        if not isinstance(row, dict):
            raise AdapterError(
                self.SOURCE,
                f"each sales entry must be a dict, got {type(row).__name__}",
                field=field_prefix,
            )
        sku_raw = row.get("sku_code")
        qty_raw = row.get("quantity_sold")
        days_raw = row.get("period_days")

        if sku_raw is None:
            raise AdapterError(self.SOURCE, "missing 'sku_code'", field=f"{field_prefix}.sku_code")
        if qty_raw is None:
            raise AdapterError(
                self.SOURCE, "missing 'quantity_sold'", field=f"{field_prefix}.quantity_sold"
            )
        if days_raw is None:
            raise AdapterError(
                self.SOURCE, "missing 'period_days'", field=f"{field_prefix}.period_days"
            )

        try:
            sku_code = SkuCode(str(sku_raw))
        except Exception as exc:
            raise AdapterError(self.SOURCE, str(exc), field=f"{field_prefix}.sku_code") from exc

        try:
            quantity_sold = int(qty_raw)
        except (TypeError, ValueError) as exc:
            raise AdapterError(
                self.SOURCE,
                f"quantity_sold must be an integer, got {qty_raw!r}",
                field=f"{field_prefix}.quantity_sold",
            ) from exc

        try:
            period_days = int(days_raw)
        except (TypeError, ValueError) as exc:
            raise AdapterError(
                self.SOURCE,
                f"period_days must be an integer, got {days_raw!r}",
                field=f"{field_prefix}.period_days",
            ) from exc

        try:
            return SkuSalesRecord(
                sku_code=sku_code,
                quantity_sold=quantity_sold,
                period_days=period_days,
            )
        except Exception as exc:
            raise AdapterError(self.SOURCE, str(exc), field=field_prefix) from exc

    def _parse_captured_at(self, data: dict[str, Any]) -> datetime:
        raw = data.get("captured_at")
        if raw is None:
            return datetime.now(tz=UTC)
        try:
            dt = datetime.fromisoformat(str(raw))
        except ValueError as exc:
            raise AdapterError(
                self.SOURCE,
                f"captured_at must be an ISO 8601 datetime string, got {raw!r}",
                field="captured_at",
            ) from exc
        else:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
