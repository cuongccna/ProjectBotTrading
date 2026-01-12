"""
Risk Budget Manager - ORM Models.

============================================================
PURPOSE
============================================================
SQLAlchemy ORM models for persisting risk budget data.

Includes:
- Risk evaluation decisions
- Position risk tracking
- Daily risk usage
- Drawdown history
- Alert records

============================================================
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    JSON,
    Index,
    Enum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class RiskEvaluationRecord(Base):
    """
    Record of a trade risk evaluation.
    
    Every call to evaluate_request() creates a record,
    regardless of decision outcome.
    """
    
    __tablename__ = "risk_evaluations"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Request Identity
    request_id = Column(String(64), nullable=False, index=True)
    """Unique request identifier."""
    
    symbol = Column(String(32), nullable=False, index=True)
    """Trading pair."""
    
    exchange = Column(String(32), nullable=False)
    """Exchange identifier."""
    
    # Request Details
    direction = Column(String(16), nullable=False)
    """Trade direction: LONG or SHORT."""
    
    entry_price = Column(Float, nullable=False)
    """Proposed entry price."""
    
    stop_loss_price = Column(Float, nullable=False)
    """Proposed stop loss price."""
    
    position_size = Column(Float, nullable=False)
    """Proposed position size."""
    
    proposed_risk_pct = Column(Float, nullable=False)
    """Proposed risk as percentage of equity."""
    
    proposed_risk_amount = Column(Float, nullable=False)
    """Proposed risk in quote currency."""
    
    # Decision
    decision = Column(String(32), nullable=False, index=True)
    """Decision: ALLOW_TRADE, REDUCE_SIZE, REJECT_TRADE."""
    
    reason = Column(String(64), nullable=True)
    """Reason code for rejection or reduction."""
    
    # Allowed Values (if applicable)
    allowed_risk_pct = Column(Float, nullable=True)
    """Allowed risk percentage."""
    
    allowed_position_size = Column(Float, nullable=True)
    """Allowed position size."""
    
    size_reduction_pct = Column(Float, nullable=True)
    """Size reduction percentage."""
    
    # Budget State at Evaluation
    account_equity = Column(Float, nullable=False)
    """Account equity at evaluation."""
    
    daily_limit_pct = Column(Float, nullable=False)
    """Daily limit at evaluation."""
    
    daily_used_pct = Column(Float, nullable=False)
    """Daily risk used at evaluation."""
    
    daily_remaining_pct = Column(Float, nullable=False)
    """Daily risk remaining at evaluation."""
    
    open_limit_pct = Column(Float, nullable=False)
    """Open position limit at evaluation."""
    
    open_used_pct = Column(Float, nullable=False)
    """Open position risk at evaluation."""
    
    open_remaining_pct = Column(Float, nullable=False)
    """Open position remaining at evaluation."""
    
    current_drawdown_pct = Column(Float, nullable=False)
    """Current drawdown at evaluation."""
    
    # Context
    strategy_id = Column(String(64), nullable=True)
    """Strategy that generated the request."""
    
    intent_id = Column(String(64), nullable=True)
    """TradeIntent ID from Strategy Engine."""
    
    # Budget Checks (JSON)
    budget_checks_json = Column(JSON, nullable=True)
    """Detailed budget check results."""
    
    # Metadata
    evaluation_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    """When evaluation occurred."""
    
    evaluation_duration_ms = Column(Float, nullable=True)
    """Evaluation duration in milliseconds."""
    
    engine_version = Column(String(16), default="1.0.0")
    """Risk Budget Manager version."""
    
    # Indexes
    __table_args__ = (
        Index("ix_risk_eval_symbol_timestamp", "symbol", "evaluation_timestamp"),
        Index("ix_risk_eval_decision_timestamp", "decision", "evaluation_timestamp"),
    )


class PositionRiskRecord(Base):
    """
    Record of risk held for a position.
    
    Created when position opens, updated on stop changes,
    closed when position closes.
    """
    
    __tablename__ = "position_risk"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Position Identity
    position_id = Column(String(64), nullable=False, unique=True, index=True)
    """Unique position identifier."""
    
    symbol = Column(String(32), nullable=False, index=True)
    """Trading pair."""
    
    exchange = Column(String(32), nullable=False)
    """Exchange identifier."""
    
    direction = Column(String(16), nullable=False)
    """Trade direction."""
    
    # Entry Details
    entry_price = Column(Float, nullable=False)
    """Entry price."""
    
    initial_stop_loss = Column(Float, nullable=False)
    """Initial stop loss price."""
    
    current_stop_loss = Column(Float, nullable=False)
    """Current stop loss price."""
    
    initial_size = Column(Float, nullable=False)
    """Initial position size."""
    
    current_size = Column(Float, nullable=False)
    """Current position size."""
    
    # Risk at Entry
    initial_risk_pct = Column(Float, nullable=False)
    """Initial risk as percentage."""
    
    initial_risk_amount = Column(Float, nullable=False)
    """Initial risk in quote currency."""
    
    current_risk_pct = Column(Float, nullable=False)
    """Current risk percentage."""
    
    current_risk_amount = Column(Float, nullable=False)
    """Current risk amount."""
    
    equity_at_entry = Column(Float, nullable=False)
    """Account equity when position opened."""
    
    # Status
    status = Column(String(32), nullable=False, index=True)
    """OPEN, PARTIALLY_CLOSED, CLOSED, EXPIRED."""
    
    # Timestamps
    opened_at = Column(DateTime, nullable=False)
    """When position was opened."""
    
    closed_at = Column(DateTime, nullable=True)
    """When position was closed."""
    
    # Result (when closed)
    realized_pnl = Column(Float, nullable=True)
    """Realized P&L."""
    
    exit_price = Column(Float, nullable=True)
    """Exit price."""
    
    # Stop Loss History (JSON array)
    stop_loss_history = Column(JSON, nullable=True)
    """History of stop loss changes."""
    
    # Indexes
    __table_args__ = (
        Index("ix_position_risk_status_symbol", "status", "symbol"),
        Index("ix_position_risk_opened", "opened_at"),
    )


class DailyRiskRecord(Base):
    """
    Daily risk budget usage record.
    
    One record per trading day.
    """
    
    __tablename__ = "daily_risk"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Date
    date = Column(String(10), nullable=False, unique=True, index=True)
    """Date in YYYY-MM-DD format."""
    
    # Budget Configuration
    risk_budget_limit = Column(Float, nullable=False)
    """Configured daily limit."""
    
    equity_at_start = Column(Float, nullable=True)
    """Equity at start of day."""
    
    equity_at_end = Column(Float, nullable=True)
    """Equity at end of day."""
    
    # Usage
    risk_consumed = Column(Float, nullable=False, default=0.0)
    """Total risk consumed."""
    
    peak_open_risk = Column(Float, nullable=False, default=0.0)
    """Peak concurrent open risk."""
    
    # Trade Stats
    trades_evaluated = Column(Integer, nullable=False, default=0)
    """Total evaluations."""
    
    trades_allowed = Column(Integer, nullable=False, default=0)
    """Trades allowed at full size."""
    
    trades_reduced = Column(Integer, nullable=False, default=0)
    """Trades with size reduction."""
    
    trades_rejected = Column(Integer, nullable=False, default=0)
    """Trades rejected."""
    
    # P&L
    realized_pnl = Column(Float, nullable=False, default=0.0)
    """Realized P&L for the day."""
    
    unrealized_pnl_eod = Column(Float, nullable=True)
    """Unrealized P&L at end of day."""
    
    # Drawdown
    max_drawdown_intraday = Column(Float, nullable=True)
    """Maximum intraday drawdown."""
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class DrawdownRecord(Base):
    """
    Drawdown tracking record.
    
    Updated on each equity change, captures peak and trough.
    """
    
    __tablename__ = "drawdown_history"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Equity Values
    peak_equity = Column(Float, nullable=False)
    """Peak equity value."""
    
    trough_equity = Column(Float, nullable=False)
    """Trough equity value."""
    
    current_equity = Column(Float, nullable=False)
    """Current equity at record time."""
    
    # Drawdown
    drawdown_pct = Column(Float, nullable=False)
    """Drawdown percentage."""
    
    drawdown_amount = Column(Float, nullable=False)
    """Drawdown in absolute terms."""
    
    # Recovery
    is_recovering = Column(Boolean, nullable=False, default=False)
    """Whether currently recovering from drawdown."""
    
    recovery_pct = Column(Float, nullable=True)
    """Recovery progress percentage."""
    
    # Events
    is_new_peak = Column(Boolean, nullable=False, default=False)
    """Whether this record represents a new peak."""
    
    is_new_trough = Column(Boolean, nullable=False, default=False)
    """Whether this record represents a new trough."""
    
    triggered_halt = Column(Boolean, nullable=False, default=False)
    """Whether this triggered a trading halt."""
    
    # Timestamp
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class RiskAlertRecord(Base):
    """
    Record of risk-related alerts.
    
    Tracks all alerts sent for audit.
    """
    
    __tablename__ = "risk_alerts"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Alert Details
    severity = Column(String(16), nullable=False, index=True)
    """Alert severity: INFO, WARNING, CRITICAL, EMERGENCY."""
    
    title = Column(String(256), nullable=False)
    """Alert title."""
    
    message = Column(Text, nullable=False)
    """Alert message."""
    
    # Context
    alert_type = Column(String(64), nullable=True)
    """Type of alert for categorization."""
    
    related_symbol = Column(String(32), nullable=True)
    """Related symbol if applicable."""
    
    related_position_id = Column(String(64), nullable=True)
    """Related position if applicable."""
    
    # State at Alert
    account_equity = Column(Float, nullable=True)
    """Account equity when alert was generated."""
    
    daily_risk_used = Column(Float, nullable=True)
    """Daily risk used when alert was generated."""
    
    current_drawdown = Column(Float, nullable=True)
    """Drawdown when alert was generated."""
    
    # Delivery
    telegram_sent = Column(Boolean, nullable=False, default=False)
    """Whether Telegram notification was sent."""
    
    telegram_message_id = Column(String(64), nullable=True)
    """Telegram message ID if sent."""
    
    # Metadata
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Indexes
    __table_args__ = (
        Index("ix_risk_alerts_severity_timestamp", "severity", "timestamp"),
    )


class TradingHaltRecord(Base):
    """
    Record of trading halts.
    
    Tracks when trading was halted and resumed.
    """
    
    __tablename__ = "trading_halts"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Halt Details
    reason = Column(String(64), nullable=False)
    """Reason for halt."""
    
    description = Column(Text, nullable=True)
    """Detailed description."""
    
    # State at Halt
    equity_at_halt = Column(Float, nullable=False)
    """Equity when halted."""
    
    drawdown_at_halt = Column(Float, nullable=False)
    """Drawdown when halted."""
    
    daily_risk_at_halt = Column(Float, nullable=True)
    """Daily risk used when halted."""
    
    open_positions_at_halt = Column(Integer, nullable=True)
    """Open positions when halted."""
    
    # Timestamps
    halted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    """When trading was halted."""
    
    resumed_at = Column(DateTime, nullable=True)
    """When trading was resumed."""
    
    # Resume Details
    resumed_by = Column(String(64), nullable=True)
    """Who/what resumed trading."""
    
    resume_reason = Column(String(256), nullable=True)
    """Why trading was resumed."""
    
    # Duration
    halt_duration_minutes = Column(Integer, nullable=True)
    """Duration of halt in minutes."""
    
    # Indexes
    __table_args__ = (
        Index("ix_trading_halts_halted_at", "halted_at"),
    )


class EquitySnapshotRecord(Base):
    """
    Periodic equity snapshots.
    
    Used for tracking equity over time and calculating drawdown.
    """
    
    __tablename__ = "equity_snapshots"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Equity Values
    account_equity = Column(Float, nullable=False)
    """Total account equity."""
    
    available_balance = Column(Float, nullable=False)
    """Available balance."""
    
    unrealized_pnl = Column(Float, nullable=False)
    """Unrealized P&L."""
    
    # Peak Tracking
    peak_equity = Column(Float, nullable=False)
    """Peak equity at this point."""
    
    drawdown_from_peak = Column(Float, nullable=False)
    """Drawdown from peak (percentage)."""
    
    # Risk State
    open_positions = Column(Integer, nullable=False)
    """Number of open positions."""
    
    open_risk_pct = Column(Float, nullable=False)
    """Open position risk percentage."""
    
    daily_risk_used_pct = Column(Float, nullable=False)
    """Daily risk used percentage."""
    
    # Source
    exchange = Column(String(32), nullable=False)
    """Exchange this data came from."""
    
    # Timestamp
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Indexes
    __table_args__ = (
        Index("ix_equity_snapshots_exchange_timestamp", "exchange", "timestamp"),
    )
