"""
PostgresMerchantRepository - async SQLAlchemy implementation of MerchantRepository.

This module is an adapter (driven side). It may import SQLAlchemy, but must
never be imported from domain.py or service.py.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select

from restockiq.merchants.domain import Merchant, Sku
from restockiq.merchants.orm_models import MerchantModel, SkuModel
from restockiq.merchants.repository import MerchantRepository
from restockiq.shared_kernel.errors import NotFoundError
from restockiq.shared_kernel.value_objects import MerchantId, Money, Quantity, SkuCode

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class PostgresMerchantRepository(MerchantRepository):
    """
    Postgres-backed implementation of MerchantRepository.

    All methods are async and must be called from within an async context.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, merchant: Merchant) -> None:  
        """Upsert a Merchant and all its SKUs."""
        model = await self._get_or_create_model(merchant)
        # Sync fields
        model.name = merchant.name
        model.currency = merchant.currency
        # Sync SKUs: replace collection
        {sku.code for sku in model.skus}
        domain_codes = {str(sku.code) for sku in merchant.list_skus()}

        # Remove deleted SKUs
        model.skus = [s for s in model.skus if s.code in domain_codes]

        # Upsert SKUs
        sku_by_code = {s.code: s for s in model.skus}
        for sku in merchant.list_skus():
            code_str = str(sku.code)
            if code_str in sku_by_code:
                existing = sku_by_code[code_str]
                existing.name = sku.name
                existing.cost_price = float(sku.cost_price.amount)
                existing.sell_price = float(sku.sell_price.amount)
            else:
                model.skus.append(
                    SkuModel(
                        id=uuid.uuid4(),
                        merchant_id=merchant.id.id,
                        code=code_str,
                        name=sku.name,
                        cost_price=float(sku.cost_price.amount),
                        sell_price=float(sku.sell_price.amount),
                        reorder_point=sku.reorder_point.units if sku.reorder_point else None,
                    )
                )
        self._session.add(model)

    async def get_by_id(self, merchant_id: MerchantId) -> Merchant:  
        stmt = select(MerchantModel).where(MerchantModel.id == merchant_id.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise NotFoundError("Merchant", str(merchant_id))
        return self._to_domain(model)

    async def list_all(self) -> Sequence[Merchant]:  
        result = await self._session.execute(select(MerchantModel))
        return [self._to_domain(m) for m in result.scalars().all()]

    async def exists(self, merchant_id: MerchantId) -> bool:  
        stmt = select(MerchantModel.id).where(MerchantModel.id == merchant_id.id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _get_or_create_model(self, merchant: Merchant) -> MerchantModel:
        stmt = select(MerchantModel).where(MerchantModel.id == merchant.id.id)
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        new_model = MerchantModel(
            id=merchant.id.id,
            name=merchant.name,
            currency=merchant.currency,
        )
        self._session.add(new_model)
        return new_model

    @staticmethod
    def _to_domain(model: MerchantModel) -> Merchant:
        merchant = Merchant(
            id=MerchantId(id=model.id),
            name=model.name,
            currency=model.currency,
        )
        for sku_model in model.skus:
            sku = Sku(
                code=SkuCode(sku_model.code),
                name=sku_model.name,
                cost_price=Money(Decimal(str(sku_model.cost_price)), model.currency),
                sell_price=Money(Decimal(str(sku_model.sell_price)), model.currency),
                reorder_point=(
                    Quantity(sku_model.reorder_point) if sku_model.reorder_point else None
                ),
            )
            # Bypass the duplicate check using the internal catalog directly
            merchant._catalog[sku.code] = sku
        return merchant
