"""
Recommendations router - generate and retrieve restocking recommendations.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel

from restockiq.api.deps import get_recommendation_service, get_signal_service
from restockiq.shared_kernel.value_objects import MerchantId

if TYPE_CHECKING:
    from restockiq.recommendations.service import RecommendationService
    from restockiq.signals.service import SignalService

router = APIRouter(tags=["Recommendations"])


# Schemas


class SkuRecommendationSchema(BaseModel):
    sku_code: str
    units_to_order: int
    estimated_cost: Decimal
    expected_margin: Decimal
    currency: str
    rationale: str
    deciding_factor: str


class RecommendationSchema(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    signal_captured_at: datetime
    created_at: datetime
    sku_recommendations: list[SkuRecommendationSchema]
    total_estimated_cost: Decimal
    total_expected_margin: Decimal
    currency: str
    confidence_score: float
    confidence_level: str
    solver_status: str
    is_accepted: bool


# Endpoints


@router.post(
    "/merchants/{merchant_id}/recommendations",
    response_model=RecommendationSchema,
    status_code=201,
    summary="Generate a restocking recommendation from the latest signal",
    description=(
        "Reads the merchant's most recent signal, runs the SAA optimizer, "
        "and returns a confidence-scored, rationale-annotated restocking plan."
    ),
)
async def generate_recommendation(
    merchant_id: uuid.UUID = Path(...),
    rec_service: RecommendationService = Depends(get_recommendation_service),
    signal_service: SignalService = Depends(get_signal_service),
) -> RecommendationSchema:
    # Fetch signal history through the signal service's repository
    # get history from the signal repository
    history = await signal_service._repo.get_history_for_merchant(
        MerchantId(id=merchant_id), limit=30
    )
    if not history:
        from restockiq.shared_kernel.errors import NotFoundError

        raise NotFoundError(
            "Signal",
            f"No signal history found for merchant {merchant_id}. "
            "Submit a signal first via POST /merchants/{id}/signals/manual",
        )

    current_signal = history[0]  # Newest signal (get_history_for_merchant returns newest first)
    historical = list(history[1:])

    rec = await rec_service.generate_recommendation(
        signal=current_signal,
        historical_signals=historical,
    )
    currency = rec.total_estimated_cost.currency
    return RecommendationSchema(
        id=rec.id,
        merchant_id=rec.merchant_id.id,
        signal_captured_at=rec.signal_captured_at,
        created_at=rec.created_at,
        sku_recommendations=[
            SkuRecommendationSchema(
                sku_code=str(r.sku_code),
                units_to_order=r.units_to_order,
                estimated_cost=r.estimated_cost.amount,
                expected_margin=r.expected_margin.amount,
                currency=r.estimated_cost.currency,
                rationale=r.rationale,
                deciding_factor=r.deciding_factor,
            )
            for r in rec.sku_recommendations
        ],
        total_estimated_cost=rec.total_estimated_cost.amount,
        total_expected_margin=rec.total_expected_margin.amount,
        currency=currency,
        confidence_score=rec.confidence_score,
        confidence_level=rec.confidence_level.value,
        solver_status=rec.solver_status,
        is_accepted=rec.is_accepted,
    )


@router.get(
    "/merchants/{merchant_id}/recommendations",
    response_model=list[RecommendationSchema],
    summary="Get recent recommendations for a merchant",
)
async def get_recommendations(
    merchant_id: uuid.UUID = Path(...),
    rec_service: RecommendationService = Depends(get_recommendation_service),
) -> list[RecommendationSchema]:
    recs = await rec_service._repo.get_latest_for_merchant(MerchantId(id=merchant_id), limit=10)
    result = []
    for rec in recs:
        currency = rec.total_estimated_cost.currency
        result.append(
            RecommendationSchema(
                id=rec.id,
                merchant_id=rec.merchant_id.id,
                signal_captured_at=rec.signal_captured_at,
                created_at=rec.created_at,
                sku_recommendations=[
                    SkuRecommendationSchema(
                        sku_code=str(r.sku_code),
                        units_to_order=r.units_to_order,
                        estimated_cost=r.estimated_cost.amount,
                        expected_margin=r.expected_margin.amount,
                        currency=r.estimated_cost.currency,
                        rationale=r.rationale,
                        deciding_factor=r.deciding_factor,
                    )
                    for r in rec.sku_recommendations
                ],
                total_estimated_cost=rec.total_estimated_cost.amount,
                total_expected_margin=rec.total_expected_margin.amount,
                currency=currency,
                confidence_score=rec.confidence_score,
                confidence_level=rec.confidence_level.value,
                solver_status=rec.solver_status,
                is_accepted=rec.is_accepted,
            )
        )
    return result
