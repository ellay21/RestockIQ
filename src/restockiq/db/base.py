"""
Shared declarative Base used by every module's orm_models.py.

All SQLAlchemy ORM models must inherit from this single Base so that
Alembic's autogenerate can discover them all in one pass.

Only infrastructure lives here — no domain models.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Shared declarative base for all RestockIQ ORM models.

    Every module's orm_models.py imports this Base:
        from restockiq.db.base import Base

    Never define columns or table mappings in this file.
    """
