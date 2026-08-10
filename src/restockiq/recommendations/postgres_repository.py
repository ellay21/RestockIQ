"""
PostgresRecommendationRepository — async SQLAlchemy implementation.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select

from restockiq.recommendations.domain import (
    ConfidenceLevel,
    RestockRecommendation,
    SkuRecommendation,
)
from restockiq.recommendations.orm_models import RecommendationModel, SkuRecommendationModel
from restockiq.recommendations.repository import RecommendationRepository
from restockiq.shared_kernel.errors import NotFoundError
from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class PostgresRecommendationRepository(RecommendationRepository):
    """Postgres-backed implementation of RecommendationRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, recommendation: RestockRecommendation) -> None:
        currency = recommendation.total_estimated_cost.currency
        model = RecommendationModel(
            id=recommendation.id,
            merchant_id=recommendation.merchant_id.id,
            signal_captured_at=recommendation.signal_captured_at,
            created_at=recommendation.created_at,
            total_estimated_cost=float(recommendation.total_estimated_cost.amount),
            total_expected_margin=float(recommendation.total_expected_margin.amount),
            currency=currency,
            confidence_score=recommendation.confidence_score,
            confidence_level=recommendation.confidence_level.value,
            solver_status=recommendation.solver_status,
            is_accepted=recommendation.is_accepted,
        )
        for sku_rec in recommendation.sku_recommendations:
            model.sku_recommendations.append(
                SkuRecommendationModel(
                    id=uuid.uuid4(),
                    sku_code=str(sku_rec.sku_code),
                    units_to_order=sku_rec.units_to_order,
                    estimated_cost=float(sku_rec.estimated_cost.amount),
                    expected_margin=float(sku_rec.expected_margin.amount),
                    currency=sku_rec.estimated_cost.currency,
                    rationale=sku_rec.rationale,
                    deciding_factor=sku_rec.deciding_factor,
                )
            )
        # Upsert: merge if already exists
        self._session.add(model)

    async def get_by_id(self, recommendation_id: uuid.UUID) -> RestockRecommendation:
        stmt = select(RecommendationModel).where(RecommendationModel.id == recommendation_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise NotFoundError("RestockRecommendation", str(recommendation_id))
        return self._to_domain(model)

    async def get_latest_for_merchant(
        self,
        merchant_id: MerchantId,
        limit: int = 10,
    ) -> Sequence[RestockRecommendation]:
        stmt = (
            select(RecommendationModel)
            .where(RecommendationModel.merchant_id == merchant_id.id)
            .order_by(RecommendationModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    @staticmethod
    def _to_domain(model: RecommendationModel) -> RestockRecommendation:
        currency = model.currency
        sku_recs = tuple(
            SkuRecommendation(
                sku_code=SkuCode(r.sku_code),
                units_to_order=r.units_to_order,
                estimated_cost=Money(Decimal(str(r.estimated_cost)), currency),
                expected_margin=Money(Decimal(str(r.expected_margin)), currency),
                rationale=r.rationale,
                deciding_factor=r.deciding_factor,
            )
            for r in model.sku_recommendations
        )
        return RestockRecommendation(
            id=model.id,
            merchant_id=MerchantId(id=model.merchant_id),
            signal_captured_at=model.signal_captured_at,
            created_at=model.created_at,
            sku_recommendations=sku_recs,
            total_estimated_cost=Money(Decimal(str(model.total_estimated_cost)), currency),
            total_expected_margin=Money(Decimal(str(model.total_expected_margin)), currency),
            confidence_score=model.confidence_score,
            confidence_level=ConfidenceLevel(model.confidence_level),
            solver_status=model.solver_status,
            is_accepted=model.is_accepted,
        )
