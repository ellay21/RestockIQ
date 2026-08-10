"""
SQLAlchemy ORM models for the recommendations module.

Adapter layer only — never imported from domain.py, service.py, or ports.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from restockiq.db.base import Base


class RecommendationModel(Base):
    """Persistence representation of a RestockRecommendation aggregate."""

    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    signal_captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_estimated_cost: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    total_expected_margin: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_level: Mapped[str] = mapped_column(String(16), nullable=False)
    solver_status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPTIMAL")
    is_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    sku_recommendations: Mapped[list[SkuRecommendationModel]] = relationship(
        "SkuRecommendationModel",
        back_populates="recommendation",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SkuRecommendationModel(Base):
    """Persistence representation of a SkuRecommendation within a recommendation."""

    __tablename__ = "sku_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku_code: Mapped[str] = mapped_column(String(64), nullable=False)
    units_to_order: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    expected_margin: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    deciding_factor: Mapped[str] = mapped_column(String(32), nullable=False)

    recommendation: Mapped[RecommendationModel] = relationship(
        "RecommendationModel", back_populates="sku_recommendations"
    )
