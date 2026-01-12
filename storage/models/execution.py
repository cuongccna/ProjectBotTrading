"""
Execution Domain ORM Models.

============================================================
PURPOSE
============================================================
Models for storing execution-related data: orders, executions,
positions, balances, and trade records.

============================================================
DATA LIFECYCLE ROLE
============================================================
- Stage: OPERATIONAL (execution)
- Mutability: IMMUTABLE (append-only with state transitions)
- Source: Exchange client, order manager
- Consumers: Position management, reporting, audit

============================================================
MODELS
============================================================
- Order: Order records
- OrderStateTransition: Order state changes
- Execution: Fill/execution records
- ExecutionValidation: Post-execution validations
- Position: Current position snapshots
- PositionSnapshot: Historical position snapshots
- BalanceSnapshot: Account balance snapshots
- TradeRecord: Complete trade records

============================================================
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.models.base import Base


class Order(Base):
    """
    Order records.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores all orders submitted to exchanges. Each order is
    immutable; state changes are tracked via OrderStateTransition.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: IMMUTABLE
    - Retention: 7 years (regulatory)
    - Source: Order manager
    
    ============================================================
    TRACEABILITY
    ============================================================
    - decision_id: FK to trading decision
    - exchange_order_id: Exchange order ID
    - Full order parameters stored
    
    ============================================================
    """
    
    __tablename__ = "orders"
    
    # Primary Key
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Internal order identifier"
    )
    
    # Foreign Key to Decision
    decision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trading_decisions.decision_id", ondelete="RESTRICT"),
        nullable=True,
        comment="Reference to trading decision"
    )
    
    # Exchange Reference
    exchange: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Exchange name"
    )
    
    exchange_order_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Exchange-assigned order ID"
    )
    
    client_order_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Client-assigned order ID"
    )
    
    # Order Details
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Trading symbol"
    )
    
    side: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Side: buy, sell"
    )
    
    order_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Order type: market, limit, stop_limit, etc."
    )
    
    time_in_force: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Time in force: GTC, IOC, FOK"
    )
    
    # Quantities
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Order quantity"
    )
    
    filled_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        default=Decimal("0"),
        comment="Filled quantity"
    )
    
    remaining_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Remaining quantity"
    )
    
    # Prices
    price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Limit price (null for market)"
    )
    
    stop_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Stop trigger price"
    )
    
    average_fill_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Average fill price"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="Status: pending, submitted, partial, filled, cancelled, rejected"
    )
    
    rejection_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Rejection reason if rejected"
    )
    
    # Risk Parameters
    reduce_only: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether order is reduce-only"
    )
    
    post_only: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether order is post-only"
    )
    
    # Fees
    fee: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Total fee paid"
    )
    
    fee_currency: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="Fee currency"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When order was created"
    )
    
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When order was submitted to exchange"
    )
    
    filled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When order was fully filled"
    )
    
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When order was cancelled"
    )
    
    exchange_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Exchange timestamp"
    )
    
    # Metadata
    order_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional order metadata"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="System version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_order_decision", "decision_id"),
        Index("idx_order_exchange", "exchange"),
        Index("idx_order_exchange_id", "exchange_order_id"),
        Index("idx_order_client_id", "client_order_id"),
        Index("idx_order_symbol", "symbol"),
        Index("idx_order_status", "status"),
        Index("idx_order_created_at", "created_at"),
    )


class OrderStateTransition(Base):
    """
    Order state transition records.
    
    ============================================================
    PURPOSE
    ============================================================
    Tracks all state changes for orders. Provides complete
    audit trail of order lifecycle.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL (audit)
    - Mutability: IMMUTABLE
    - Retention: 7 years (regulatory)
    - Source: Order manager
    
    ============================================================
    TRACEABILITY
    ============================================================
    - order_id: FK to order
    - Full state transition history
    
    ============================================================
    """
    
    __tablename__ = "order_state_transitions"
    
    # Primary Key
    transition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for transition"
    )
    
    # Foreign Key
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.order_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Reference to order"
    )
    
    # Transition Details
    from_state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Previous state"
    )
    
    to_state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="New state"
    )
    
    trigger: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="What triggered transition"
    )
    
    # Quantities at Transition
    filled_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Filled quantity at transition"
    )
    
    remaining_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Remaining quantity at transition"
    )
    
    # Context
    exchange_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Exchange message if applicable"
    )
    
    context_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional context"
    )
    
    # Timestamps
    transitioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When transition occurred"
    )
    
    exchange_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Exchange timestamp"
    )
    
    # Sequence
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Transition sequence number"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_order_trans_order", "order_id"),
        Index("idx_order_trans_from", "from_state"),
        Index("idx_order_trans_to", "to_state"),
        Index("idx_order_trans_at", "transitioned_at"),
    )


class Execution(Base):
    """
    Trade execution (fill) records.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores individual trade executions/fills. One order can
    have multiple executions.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: IMMUTABLE
    - Retention: 7 years (regulatory)
    - Source: Exchange client
    
    ============================================================
    TRACEABILITY
    ============================================================
    - order_id: FK to order
    - exchange_trade_id: Exchange trade ID
    
    ============================================================
    """
    
    __tablename__ = "executions"
    
    # Primary Key
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for execution"
    )
    
    # Foreign Key
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.order_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Reference to order"
    )
    
    # Exchange Reference
    exchange: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Exchange name"
    )
    
    exchange_trade_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Exchange trade ID"
    )
    
    # Trade Details
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Trading symbol"
    )
    
    side: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Side: buy, sell"
    )
    
    # Fill Details
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Fill quantity"
    )
    
    price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Fill price"
    )
    
    value: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Fill value (quantity * price)"
    )
    
    # Fees
    fee: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Fee for this fill"
    )
    
    fee_currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Fee currency"
    )
    
    # Role
    is_maker: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Whether this was a maker fill"
    )
    
    # Timestamps
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Execution time"
    )
    
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When we received the execution"
    )
    
    # Raw Data
    raw_response: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Raw exchange response"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="System version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_exec_order", "order_id"),
        Index("idx_exec_exchange", "exchange"),
        Index("idx_exec_trade_id", "exchange_trade_id"),
        Index("idx_exec_symbol", "symbol"),
        Index("idx_exec_executed_at", "executed_at"),
    )


class ExecutionValidation(Base):
    """
    Post-execution validation records.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores validation results for executions to ensure
    they match expectations and are within risk limits.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL (validation)
    - Mutability: IMMUTABLE
    - Retention: 5 years
    - Source: Execution validator
    
    ============================================================
    TRACEABILITY
    ============================================================
    - execution_id: FK to execution
    - All validation checks stored
    
    ============================================================
    """
    
    __tablename__ = "execution_validations"
    
    # Primary Key
    validation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for validation"
    )
    
    # Foreign Key
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("executions.execution_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Reference to execution"
    )
    
    # Validation Results
    is_valid: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Overall validation result"
    )
    
    validation_errors: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        comment="List of validation errors"
    )
    
    # Individual Checks
    price_check_passed: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Price within expected range"
    )
    
    quantity_check_passed: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Quantity matches order"
    )
    
    fee_check_passed: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Fee within expected range"
    )
    
    timing_check_passed: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Timing is reasonable"
    )
    
    # Expected vs Actual
    expected_price_range: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Expected price range"
    )
    
    actual_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Actual execution price"
    )
    
    slippage_bps: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Slippage in basis points"
    )
    
    # Timestamps
    validated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When validation was performed"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Validator version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_exec_val_execution", "execution_id"),
        Index("idx_exec_val_valid", "is_valid"),
        Index("idx_exec_val_validated_at", "validated_at"),
    )


class Position(Base):
    """
    Current position records.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores current positions. Updated via append-only pattern
    where each update creates a new record with higher version.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: APPEND-ONLY (versioned)
    - Retention: Current + 90 days history
    - Source: Position manager
    
    ============================================================
    TRACEABILITY
    ============================================================
    - version: Position version (increments)
    - Last update traceable to execution
    
    ============================================================
    """
    
    __tablename__ = "positions"
    
    # Primary Key
    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for position record"
    )
    
    # Position Key (natural key)
    exchange: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Exchange name"
    )
    
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Trading symbol"
    )
    
    # Position Details
    side: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Side: long, short, flat"
    )
    
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Position quantity"
    )
    
    entry_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Average entry price"
    )
    
    current_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Current market price"
    )
    
    # Value Metrics
    notional_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Notional value"
    )
    
    unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Unrealized PnL"
    )
    
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Realized PnL since position opened"
    )
    
    # Risk Metrics
    liquidation_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Liquidation price if applicable"
    )
    
    margin_used: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Margin used"
    )
    
    leverage: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Leverage used"
    )
    
    # Timestamps
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When position was opened"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When position was last updated"
    )
    
    # Status
    is_current: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        comment="Whether this is the current version"
    )
    
    # Versioning
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Position version number"
    )
    
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="System version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_pos_exchange_symbol", "exchange", "symbol"),
        Index("idx_pos_current", "exchange", "symbol", "is_current"),
        Index("idx_pos_updated_at", "updated_at"),
        Index("idx_pos_side", "side"),
    )


class PositionSnapshot(Base):
    """
    Historical position snapshots.
    
    ============================================================
    PURPOSE
    ============================================================
    Periodic snapshots of all positions for historical analysis
    and reconciliation.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: HISTORICAL
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: Position manager
    
    ============================================================
    TRACEABILITY
    ============================================================
    - snapshot_time: When snapshot was taken
    - All position data preserved
    
    ============================================================
    """
    
    __tablename__ = "position_snapshots"
    
    # Primary Key
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for snapshot"
    )
    
    # Snapshot Time
    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When snapshot was taken"
    )
    
    snapshot_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type: hourly, daily, weekly"
    )
    
    # Position Details
    exchange: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Exchange name"
    )
    
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Trading symbol"
    )
    
    side: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Side: long, short, flat"
    )
    
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Position quantity"
    )
    
    entry_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Average entry price"
    )
    
    mark_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Mark price at snapshot"
    )
    
    # Value Metrics
    notional_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Notional value"
    )
    
    unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Unrealized PnL"
    )
    
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Realized PnL"
    )
    
    # Created At
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When record was created"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="System version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_pos_snap_time", "snapshot_time"),
        Index("idx_pos_snap_type", "snapshot_type"),
        Index("idx_pos_snap_exchange", "exchange", "symbol"),
    )


class BalanceSnapshot(Base):
    """
    Account balance snapshots.
    
    ============================================================
    PURPOSE
    ============================================================
    Periodic snapshots of account balances for historical
    analysis and reconciliation.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: HISTORICAL
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: Exchange client
    
    ============================================================
    TRACEABILITY
    ============================================================
    - snapshot_time: When snapshot was taken
    - All balance data preserved
    
    ============================================================
    """
    
    __tablename__ = "balance_snapshots"
    
    # Primary Key
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for snapshot"
    )
    
    # Snapshot Time
    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When snapshot was taken"
    )
    
    snapshot_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type: hourly, daily, weekly"
    )
    
    # Account Details
    exchange: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Exchange name"
    )
    
    account_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Account type: spot, margin, futures"
    )
    
    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Currency"
    )
    
    # Balances
    total_balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Total balance"
    )
    
    available_balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Available balance"
    )
    
    locked_balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Locked/reserved balance"
    )
    
    # USD Equivalent
    usd_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="USD equivalent value"
    )
    
    # Exchange Rate Used
    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Exchange rate to USD"
    )
    
    # Created At
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When record was created"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="System version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_bal_snap_time", "snapshot_time"),
        Index("idx_bal_snap_type", "snapshot_type"),
        Index("idx_bal_snap_exchange", "exchange"),
        Index("idx_bal_snap_currency", "currency"),
    )


class TradeRecord(Base):
    """
    Complete trade records.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores complete trade records from open to close. Aggregates
    all orders and executions for a single trade cycle.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: APPEND-ONLY
    - Retention: 7 years (regulatory)
    - Source: Trade manager
    
    ============================================================
    TRACEABILITY
    ============================================================
    - decision_id: FK to original decision
    - order_ids: All orders in trade
    - execution_ids: All executions in trade
    
    ============================================================
    """
    
    __tablename__ = "trade_records"
    
    # Primary Key
    trade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for trade"
    )
    
    # Foreign Key
    decision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trading_decisions.decision_id", ondelete="RESTRICT"),
        nullable=True,
        comment="Reference to original decision"
    )
    
    # Trade Details
    exchange: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Exchange name"
    )
    
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Trading symbol"
    )
    
    side: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Trade side: long, short"
    )
    
    # Quantities
    entry_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Entry quantity"
    )
    
    exit_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Exit quantity"
    )
    
    # Prices
    entry_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Average entry price"
    )
    
    exit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Average exit price"
    )
    
    # P&L
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        default=Decimal("0"),
        comment="Realized profit/loss"
    )
    
    realized_pnl_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        default=Decimal("0"),
        comment="Realized P&L percentage"
    )
    
    # Fees
    total_fees: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        default=Decimal("0"),
        comment="Total fees paid"
    )
    
    fee_currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Primary fee currency"
    )
    
    # Net P&L
    net_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        default=Decimal("0"),
        comment="Net P&L after fees"
    )
    
    # Order/Execution References
    order_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        comment="List of order IDs"
    )
    
    execution_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        comment="List of execution IDs"
    )
    
    entry_order_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of entry orders"
    )
    
    exit_order_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of exit orders"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        comment="Status: open, closing, closed, cancelled"
    )
    
    exit_reason: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Reason for exit"
    )
    
    # Timestamps
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When trade was opened"
    )
    
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When trade was closed"
    )
    
    duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Trade duration in seconds"
    )
    
    # Metadata
    trade_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional trade metadata"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="System version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_trade_decision", "decision_id"),
        Index("idx_trade_exchange", "exchange"),
        Index("idx_trade_symbol", "symbol"),
        Index("idx_trade_status", "status"),
        Index("idx_trade_opened_at", "opened_at"),
        Index("idx_trade_closed_at", "closed_at"),
        Index("idx_trade_pnl", "realized_pnl"),
    )
