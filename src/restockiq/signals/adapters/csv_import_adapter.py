"""
CsvImportAdapter — translates an uploaded CSV file into a MerchantFinancialSignal.

Expected CSV format (header row required):
    sku_code,quantity_sold,period_days

Optional CSV headers:
    cash_on_hand   — if present, the first non-header row's value is used as
                     the merchant's available cash.  If absent, the caller must
                     supply cash via the meta dict.

The raw_input accepted by `build_signal` is a dict with:
    {
        "merchant_id": str (UUID),
        "currency": str (ISO 4217),
        "cash_on_hand": str | float | int,   # if not in CSV
        "csv_content": str | bytes,          # the raw CSV text
        "captured_at": str | None,           # optional ISO 8601
    }
"""
from __future__ import annotations

import csv
import io
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

_REQUIRED_COLUMNS = {"sku_code", "quantity_sold", "period_days"}
SOURCE = "CsvImportAdapter"


class CsvImportAdapter(SignalSourcePort):
    """
    Translates a UTF-8 CSV upload into a MerchantFinancialSignal.

    Parsing is strict by default: any malformed row raises AdapterError with
    the row number and field name so the API layer can return a precise error
    to the merchant.
    """

    def build_signal(self, raw_input: object) -> MerchantFinancialSignal:
        if not isinstance(raw_input, dict):
            raise AdapterError(SOURCE, f"Expected a dict, got {type(raw_input).__name__}")
        data: dict[str, Any] = raw_input

        merchant_id = _parse_merchant_id(data)
        cash_on_hand = _parse_cash_on_hand(data)
        captured_at = _parse_captured_at(data)
        sales_records = _parse_csv(data)

        return MerchantFinancialSignal(
            merchant_id=merchant_id,
            cash_on_hand=cash_on_hand,
            sales_records=tuple(sales_records),
            input_method=SignalInputMethod.CSV_IMPORT,
            captured_at=captured_at,
            cash_source=CashSource.MANUAL,
        )


# Module-level helpers (not part of the port interface)


def _parse_merchant_id(data: dict[str, Any]) -> MerchantId:
    raw = data.get("merchant_id")
    if raw is None:
        raise AdapterError(SOURCE, "missing required field", field="merchant_id")
    try:
        return MerchantId.from_str(str(raw))
    except Exception as exc:
        raise AdapterError(SOURCE, f"invalid merchant_id: {exc}", field="merchant_id") from exc


def _parse_cash_on_hand(data: dict[str, Any]) -> Money:
    raw_cash = data.get("cash_on_hand")
    currency = str(data.get("currency", "ETB"))
    if raw_cash is None:
        raise AdapterError(SOURCE, "missing required field", field="cash_on_hand")
    try:
        amount = Decimal(str(raw_cash))
    except InvalidOperation as exc:
        raise AdapterError(
            SOURCE,
            f"cash_on_hand must be a valid decimal, got {raw_cash!r}",
            field="cash_on_hand",
        ) from exc
    try:
        return Money(amount=amount, currency=currency)
    except Exception as exc:
        raise AdapterError(SOURCE, str(exc), field="cash_on_hand") from exc


def _parse_captured_at(data: dict[str, Any]) -> datetime:
    raw = data.get("captured_at")
    if raw is None:
        return datetime.now(tz=UTC)
    try:
        dt = datetime.fromisoformat(str(raw))
    except ValueError as exc:
        raise AdapterError(
            SOURCE,
            f"captured_at must be an ISO 8601 datetime string, got {raw!r}",
            field="captured_at",
        ) from exc
    else:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt


def _parse_csv(data: dict[str, Any]) -> list[SkuSalesRecord]:
    raw_csv = data.get("csv_content")
    if raw_csv is None:
        raise AdapterError(SOURCE, "missing required field", field="csv_content")

    if isinstance(raw_csv, bytes):
        try:
            text = raw_csv.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AdapterError(
                SOURCE, "csv_content must be valid UTF-8 text", field="csv_content"
            ) from exc
    else:
        text = str(raw_csv)

    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        raise AdapterError(SOURCE, "CSV is empty — no header row found", field="csv_content")

    # Normalise column names: strip whitespace and lowercase
    fieldnames_normalised = {f.strip().lower() for f in reader.fieldnames}
    missing = _REQUIRED_COLUMNS - fieldnames_normalised
    if missing:
        raise AdapterError(
            SOURCE,
            f"CSV is missing required columns: {sorted(missing)}. "
            f"Found: {sorted(fieldnames_normalised)}",
            field="csv_content",
        )

    records: list[SkuSalesRecord] = []
    for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is the header
        # Normalise keys
        normalised_row = {k.strip().lower(): v.strip() for k, v in row.items() if k}
        records.append(_parse_csv_row(normalised_row, row_num=row_num))

    if not records:
        raise AdapterError(
            SOURCE,
            "CSV contains a header but no data rows",
            field="csv_content",
        )

    return records


def _parse_csv_row(row: dict[str, str], *, row_num: int) -> SkuSalesRecord:
    """Parse a single normalised CSV row into a SkuSalesRecord."""

    def field_err(field: str, reason: str) -> AdapterError:
        return AdapterError(SOURCE, f"row {row_num}: {reason}", field=field)

    # sku_code
    raw_sku = row.get("sku_code", "").strip()
    if not raw_sku:
        raise field_err("sku_code", "sku_code is empty")
    try:
        sku_code = SkuCode(raw_sku)
    except Exception as exc:
        raise field_err("sku_code", str(exc)) from exc

    # quantity_sold
    raw_qty = row.get("quantity_sold", "").strip()
    if not raw_qty:
        raise field_err("quantity_sold", "quantity_sold is empty")
    try:
        quantity_sold = int(raw_qty)
    except ValueError as exc:
        raise field_err("quantity_sold", f"expected integer, got {raw_qty!r}") from exc

    # period_days
    raw_days = row.get("period_days", "").strip()
    if not raw_days:
        raise field_err("period_days", "period_days is empty")
    try:
        period_days = int(raw_days)
    except ValueError as exc:
        raise field_err("period_days", f"expected integer, got {raw_days!r}") from exc

    try:
        return SkuSalesRecord(
            sku_code=sku_code,
            quantity_sold=quantity_sold,
            period_days=period_days,
        )
    except Exception as exc:
        raise field_err("row", str(exc)) from exc
