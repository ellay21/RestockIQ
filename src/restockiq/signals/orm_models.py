"""
SQLAlchemy ORM models for the signals module.

Adapter layer only — never imported from domain.py, service.py, or ports.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from restockiq.db.base import Base


class SignalModel(Base):
    """Persistence representation of a MerchantFinancialSignal snapshot."""

    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    cash_on_hand: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    input_method: Mapped[str] = mapped_column(String(32), nullable=False)
    cash_source: Mapped[str] = mapped_column(String(32), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    sku_records: Mapped[list[SkuSalesRecordModel]] = relationship(
        "SkuSalesRecordModel",
        back_populates="signal",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<SignalModel id={self.id} merchant_id={self.merchant_id}>"


class SkuSalesRecordModel(Base):
    """Persistence representation of a SkuSalesRecord within a signal."""

    __tablename__ = "sku_sales_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), nullable=False
    )
    sku_code: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity_sold: Mapped[int] = mapped_column(Integer, nullable=False)
    period_days: Mapped[int] = mapped_column(Integer, nullable=False)

    signal: Mapped[SignalModel] = relationship("SignalModel", back_populates="sku_records")
