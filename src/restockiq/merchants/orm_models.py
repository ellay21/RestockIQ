"""
SQLAlchemy ORM models for the merchants module.

These models are the persistence representation - they live only in the
driven-adapter layer and must never be imported by domain.py or service.py.
The PostgresMerchantRepository is responsible for mapping between these
models and the Merchant/Sku domain entities.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from restockiq.db.base import Base


class MerchantModel(Base):
    """Persistence representation of the Merchant aggregate root."""

    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    skus: Mapped[list[SkuModel]] = relationship(
        "SkuModel",
        back_populates="merchant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<MerchantModel id={self.id} name={self.name!r}>"


class SkuModel(Base):
    """Persistence representation of a Sku entity."""

    __tablename__ = "skus"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cost_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    sell_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    reorder_point: Mapped[int | None] = mapped_column(nullable=True)

    merchant: Mapped[MerchantModel] = relationship("MerchantModel", back_populates="skus")

    def __repr__(self) -> str:
        return f"<SkuModel code={self.code!r} merchant_id={self.merchant_id}>"
