"""
PostgresSignalRepository — async SQLAlchemy implementation of SignalRepository.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select

from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode
from restockiq.signals.domain import (
    CashSource,
    MerchantFinancialSignal,
    SignalInputMethod,
    SkuSalesRecord,
)
from restockiq.signals.orm_models import SignalModel, SkuSalesRecordModel
from restockiq.signals.ports import SignalRepository

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class PostgresSignalRepository(SignalRepository):
    """Postgres-backed implementation of SignalRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, signal: MerchantFinancialSignal) -> None:  # type: ignore[override]
        model = SignalModel(
            id=uuid.uuid4(),
            merchant_id=signal.merchant_id.id,
            cash_on_hand=float(signal.cash_on_hand.amount),
            currency=signal.cash_on_hand.currency,
            input_method=signal.input_method.value,
            cash_source=signal.cash_source.value,
            captured_at=signal.captured_at,
        )
        for record in signal.sales_records:
            model.sku_records.append(
                SkuSalesRecordModel(
                    id=uuid.uuid4(),
                    sku_code=str(record.sku_code),
                    quantity_sold=record.quantity_sold,
                    period_days=record.period_days,
                )
            )
        self._session.add(model)

    async def get_history_for_merchant(  # type: ignore[override]
        self,
        merchant_id: MerchantId,
        limit: int = 30,
    ) -> Sequence[MerchantFinancialSignal]:
        stmt = (
            select(SignalModel)
            .where(SignalModel.merchant_id == merchant_id.id)
            .order_by(SignalModel.captured_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    @staticmethod
    def _to_domain(model: SignalModel) -> MerchantFinancialSignal:
        records = tuple(
            SkuSalesRecord(
                sku_code=SkuCode(r.sku_code),
                quantity_sold=r.quantity_sold,
                period_days=r.period_days,
            )
            for r in model.sku_records
        )
        return MerchantFinancialSignal(
            merchant_id=MerchantId(id=model.merchant_id),
            cash_on_hand=Money(Decimal(str(model.cash_on_hand)), model.currency),
            sales_records=records,
            input_method=SignalInputMethod(model.input_method),
            captured_at=model.captured_at,
            cash_source=CashSource(model.cash_source),
        )
