"""
Execution Engine - ORM Models.

============================================================
PURPOSE
============================================================
SQLAlchemy ORM models for execution persistence.

TABLES:
- execution_orders: Order records
- execution_fills: Fill records
- execution_events: State transition events
- execution_alerts: Alert history

AUDIT REQUIREMENTS:
- All orders must be persisted
- All state changes must be logged
- All fills must be recorded
- Complete audit trail

============================================================
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    Column,
    String,
    Integer,
    Numeric,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    Index,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.declarative import declarative_base

from .types import OrderState, OrderSide, OrderType, TimeInForce, PositionSide


# ============================================================
# BASE
# ============================================================

# Import Base from storage module
try:
    from storage.models.base import Base
except ImportError:
    # Fallback for standalone usage
    from sqlalchemy.orm import DeclarativeBase
    
    class Base(DeclarativeBase):
        """Base class for ORM models."""
        pass


# ============================================================
# EXECUTION ORDER MODEL
# ============================================================

class ExecutionOrderModel(Base):
    """
    Persisted order record.
    
    Stores complete order lifecycle information.
    """
    
    __tablename__ = "execution_orders"
    
    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Identifiers
    order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    intent_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    client_order_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    
    # State
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    previous_state: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Order parameters
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 8))
    stop_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 8))
    time_in_force: Mapped[str] = mapped_column(String(8), default="GTC")
    position_side: Mapped[str] = mapped_column(String(8), default="BOTH")
    reduce_only: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Fill tracking
    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    remaining_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    average_fill_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 8))
    commission: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    commission_asset: Mapped[Optional[str]] = mapped_column(String(16))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Execution metadata
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    exchange_error_code: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Source metadata
    strategy_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    signal_id: Mapped[Optional[str]] = mapped_column(String(64))
    exchange_id: Mapped[str] = mapped_column(String(32), default="binance")
    
    # Relationships
    fills: Mapped[List["ExecutionFillModel"]] = relationship(
        "ExecutionFillModel",
        back_populates="order",
        cascade="all, delete-orphan",
    )
    events: Mapped[List["ExecutionEventModel"]] = relationship(
        "ExecutionEventModel",
        back_populates="order",
        cascade="all, delete-orphan",
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_execution_orders_symbol_state", "symbol", "state"),
        Index("ix_execution_orders_strategy_created", "strategy_id", "created_at"),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "order_id": self.order_id,
            "intent_id": self.intent_id,
            "exchange_order_id": self.exchange_order_id,
            "client_order_id": self.client_order_id,
            "state": self.state,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "quantity": str(self.quantity),
            "price": str(self.price) if self.price else None,
            "filled_quantity": str(self.filled_quantity),
            "average_fill_price": str(self.average_fill_price) if self.average_fill_price else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
        }


# ============================================================
# EXECUTION FILL MODEL
# ============================================================

class ExecutionFillModel(Base):
    """
    Individual trade fill record.
    
    One order can have multiple fills.
    """
    
    __tablename__ = "execution_fills"
    
    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Fill identifiers
    fill_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    trade_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    
    # Order reference
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("execution_orders.order_id"), nullable=False, index=True)
    
    # Fill details
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    quote_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    
    # Commission
    commission: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    commission_asset: Mapped[Optional[str]] = mapped_column(String(16))
    
    # Timestamps
    filled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Execution context
    is_maker: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationship
    order: Mapped["ExecutionOrderModel"] = relationship("ExecutionOrderModel", back_populates="fills")
    
    # Indexes
    __table_args__ = (
        Index("ix_execution_fills_symbol_filled", "symbol", "filled_at"),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "fill_id": self.fill_id,
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": str(self.quantity),
            "price": str(self.price),
            "commission": str(self.commission),
            "commission_asset": self.commission_asset,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "is_maker": self.is_maker,
        }


# ============================================================
# EXECUTION EVENT MODEL
# ============================================================

class ExecutionEventModel(Base):
    """
    Order state transition event.
    
    Captures all state changes for audit trail.
    """
    
    __tablename__ = "execution_events"
    
    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Event identifiers
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    
    # Order reference
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("execution_orders.order_id"), nullable=False, index=True)
    
    # State transition
    from_state: Mapped[str] = mapped_column(String(32), nullable=False)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    
    # Event details
    reason: Mapped[Optional[str]] = mapped_column(Text)
    exchange_update: Mapped[bool] = mapped_column(Boolean, default=False)
    details_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON string
    
    # Timestamps
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationship
    order: Mapped["ExecutionOrderModel"] = relationship("ExecutionOrderModel", back_populates="events")
    
    # Indexes
    __table_args__ = (
        Index("ix_execution_events_order_occurred", "order_id", "occurred_at"),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "order_id": self.order_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "exchange_update": self.exchange_update,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
        }


# ============================================================
# EXECUTION ALERT MODEL
# ============================================================

class ExecutionAlertModel(Base):
    """
    Alert history record.
    """
    
    __tablename__ = "execution_alerts"
    
    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Alert identifiers
    alert_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    
    # Alert details
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[Optional[str]] = mapped_column(Text)
    
    # Related entities
    order_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Status
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Indexes
    __table_args__ = (
        Index("ix_execution_alerts_severity_created", "severity", "created_at"),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "message": self.message,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "sent": self.sent,
            "acknowledged": self.acknowledged,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================
# RECONCILIATION LOG MODEL
# ============================================================

class ReconciliationLogModel(Base):
    """
    Reconciliation run log.
    """
    
    __tablename__ = "execution_reconciliation_logs"
    
    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Run identifiers
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    
    # Results
    orders_checked: Mapped[int] = mapped_column(Integer, default=0)
    orders_synced: Mapped[int] = mapped_column(Integer, default=0)
    mismatches_found: Mapped[int] = mapped_column(Integer, default=0)
    mismatches_resolved: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Status
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    has_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Details
    errors_json: Mapped[Optional[str]] = mapped_column(Text)
    mismatches_json: Mapped[Optional[str]] = mapped_column(Text)
    
    # Timestamps
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "orders_checked": self.orders_checked,
            "orders_synced": self.orders_synced,
            "mismatches_found": self.mismatches_found,
            "success": self.success,
            "has_critical": self.has_critical,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
