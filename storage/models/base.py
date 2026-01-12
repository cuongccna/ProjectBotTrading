"""
Base ORM Model and Mixins.

============================================================
PURPOSE
============================================================
Provides the declarative base and common mixins used by all
ORM models in the trading system.

============================================================
COMPONENTS
============================================================
- Base: SQLAlchemy declarative base for all models
- TimestampMixin: Common timestamp columns

============================================================
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Declarative base for all ORM models.
    
    All models in the trading system inherit from this base.
    This provides a common foundation for table creation and
    relationship mapping.
    """
    
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    """
    Mixin providing standard timestamp columns.
    
    Adds created_at and updated_at columns to models that
    require temporal tracking. All timestamps are timezone-aware.
    
    Usage:
        class MyModel(Base, TimestampMixin):
            __tablename__ = "my_table"
            ...
    """
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Record creation timestamp (UTC)"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update timestamp (UTC)"
    )
