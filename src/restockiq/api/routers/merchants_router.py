"""
Merchants router — CRUD for merchants and SKU catalog.

All request/response schemas are defined here as Pydantic models.
Domain types are never exposed directly in HTTP responses - they are
mapped to these response schemas by the endpoint handlers.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field, field_validator

from restockiq.api.deps import get_merchant_service
from restockiq.merchants.domain import Sku
from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode

if TYPE_CHECKING:
    from restockiq.merchants.service import MerchantService

router = APIRouter(tags=["Merchants"])


# Schemas

class SkuSchema(BaseModel):
    code: str
    name: str
    cost_price: Decimal
    sell_price: Decimal
    currency: str
    margin: Decimal
    margin_rate: float


class MerchantSchema(BaseModel):
    id: uuid.UUID
    name: str
    currency: str
    sku_count: int


class RegisterMerchantRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    currency: str = Field(..., min_length=3, max_length=3, pattern="^[A-Z]{3}$")

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, v: str) -> str:
        return v.upper()


class AddSkuRequest(BaseModel):
    code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=255)
    cost_price: Decimal = Field(..., gt=0)  # type: ignore[reportArgumentType]
    sell_price: Decimal = Field(..., gt=0)  # type: ignore[reportArgumentType]


# Helpers


def sku_to_schema(sku: Sku) -> SkuSchema:
    return SkuSchema(
        code=str(sku.code),
        name=sku.name,
        cost_price=sku.cost_price.amount,
        sell_price=sku.sell_price.amount,
        currency=sku.currency,
        margin=sku.margin.amount,
        margin_rate=sku.margin_rate,
    )


# Endpoints


@router.post(
    "/merchants",
    response_model=MerchantSchema,
    status_code=201,
    summary="Register a new merchant",
)
async def register_merchant(
    body: RegisterMerchantRequest,
    service: MerchantService = Depends(get_merchant_service),
) -> MerchantSchema:
    merchant_id = MerchantId.generate()
    merchant = await service.register_merchant(merchant_id, body.name, body.currency)
    return MerchantSchema(
        id=merchant.id.id,
        name=merchant.name,
        currency=merchant.currency,
        sku_count=merchant.sku_count,
    )


@router.get(
    "/merchants/{merchant_id}",
    response_model=MerchantSchema,
    summary="Get merchant by ID",
)
async def get_merchant(
    merchant_id: uuid.UUID = Path(...),
    service: MerchantService = Depends(get_merchant_service),
) -> MerchantSchema:
    merchant = await service.get_merchant(MerchantId(id=merchant_id))
    return MerchantSchema(
        id=merchant.id.id,
        name=merchant.name,
        currency=merchant.currency,
        sku_count=merchant.sku_count,
    )


@router.get(
    "/merchants/{merchant_id}/catalog",
    response_model=list[SkuSchema],
    summary="Get all SKUs in a merchant's catalog",
)
async def get_catalog(
    merchant_id: uuid.UUID = Path(...),
    service: MerchantService = Depends(get_merchant_service),
) -> list[SkuSchema]:
    skus = await service.get_catalog(MerchantId(id=merchant_id))
    return [sku_to_schema(sku) for sku in skus]


@router.post(
    "/merchants/{merchant_id}/catalog",
    response_model=list[SkuSchema],
    status_code=201,
    summary="Add a SKU to the merchant's catalog",
)
async def add_sku(
    body: AddSkuRequest,
    merchant_id: uuid.UUID = Path(...),
    service: MerchantService = Depends(get_merchant_service),
) -> list[SkuSchema]:
    # the merchant's currency for the Money objects
    merchant = await service.get_merchant(MerchantId(id=merchant_id))
    sku = Sku(
        code=SkuCode(body.code),
        name=body.name,
        cost_price=Money(amount=body.cost_price, currency=merchant.currency),
        sell_price=Money(amount=body.sell_price, currency=merchant.currency),
    )
    updated = await service.add_sku(MerchantId(id=merchant_id), sku)
    return [sku_to_schema(s) for s in updated.list_skus()]


@router.delete(
    "/merchants/{merchant_id}/catalog/{sku_code}",
    status_code=204,
    summary="Remove a SKU from the catalog",
)
async def remove_sku(
    merchant_id: uuid.UUID = Path(...),
    sku_code: str = Path(...),
    service: MerchantService = Depends(get_merchant_service),
) -> None:
    await service.remove_sku(MerchantId(id=merchant_id), SkuCode(sku_code))
