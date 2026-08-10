"""
Signals router — ingest merchant financial signals via manual entry or CSV.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, File, Form, Path, UploadFile
from pydantic import BaseModel, Field

from restockiq.api.deps import get_signal_service
from restockiq.signals.adapters.csv_import_adapter import CsvImportAdapter
from restockiq.signals.adapters.manual_entry_adapter import ManualEntryAdapter

if TYPE_CHECKING:
    from restockiq.signals.service import SignalService

router = APIRouter(tags=["Signals"])


# Schemas


class SkuSalesInput(BaseModel):
    sku_code: str = Field(..., min_length=1)
    quantity_sold: int = Field(..., ge=0)
    period_days: int = Field(..., ge=1)


class ManualSignalRequest(BaseModel):
    merchant_id: uuid.UUID
    currency: str = Field("ETB", min_length=3, max_length=3)
    cash_on_hand: Decimal = Field(..., ge=0)  # type: ignore[reportArgumentType]
    sales: list[SkuSalesInput] = Field(..., min_length=1)
    captured_at: datetime | None = None


class SignalResponse(BaseModel):
    merchant_id: uuid.UUID
    cash_on_hand: Decimal
    currency: str
    sales_record_count: int
    captured_at: datetime
    input_method: str


# Endpoints


@router.post(
    "/merchants/{merchant_id}/signals/manual",
    response_model=SignalResponse,
    status_code=201,
    summary="Submit a financial signal via manual entry",
)
async def ingest_manual_signal(
    body: ManualSignalRequest,
    merchant_id: uuid.UUID = Path(...),
    service: SignalService = Depends(get_signal_service),
) -> SignalResponse:
    raw_input: dict[str, Any] = {
        "merchant_id": str(merchant_id),
        "currency": body.currency,
        "cash_on_hand": str(body.cash_on_hand),
        "sales": [
            {
                "sku_code": s.sku_code,
                "quantity_sold": s.quantity_sold,
                "period_days": s.period_days,
            }
            for s in body.sales
        ],
        "captured_at": (body.captured_at.isoformat() if body.captured_at else None),
    }
    adapter = ManualEntryAdapter()
    signal = await service.ingest_from_adapter(adapter, raw_input)
    return SignalResponse(
        merchant_id=signal.merchant_id.id,
        cash_on_hand=signal.cash_on_hand.amount,
        currency=signal.cash_on_hand.currency,
        sales_record_count=len(signal.sales_records),
        captured_at=signal.captured_at,
        input_method=signal.input_method.value,
    )


@router.post(
    "/merchants/{merchant_id}/signals/csv",
    response_model=SignalResponse,
    status_code=201,
    summary="Submit a financial signal via CSV file upload",
)
async def ingest_csv_signal(
    merchant_id: uuid.UUID = Path(...),
    cash_on_hand: Decimal = Form(..., ge=0),  # type: ignore[reportArgumentType]
    currency: str = Form("ETB"),
    file: UploadFile = File(...),
    service: SignalService = Depends(get_signal_service),
) -> SignalResponse:
    csv_content = await file.read()
    raw_input: dict[str, Any] = {
        "merchant_id": str(merchant_id),
        "currency": currency,
        "cash_on_hand": str(cash_on_hand),
        "csv_content": csv_content,
    }
    adapter = CsvImportAdapter()
    signal = await service.ingest_from_adapter(adapter, raw_input)
    return SignalResponse(
        merchant_id=signal.merchant_id.id,
        cash_on_hand=signal.cash_on_hand.amount,
        currency=signal.cash_on_hand.currency,
        sales_record_count=len(signal.sales_records),
        captured_at=signal.captured_at,
        input_method=signal.input_method.value,
    )
