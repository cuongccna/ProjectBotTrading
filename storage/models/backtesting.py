"""
Backtesting Domain ORM Models.

============================================================
PURPOSE
============================================================
Models for storing backtesting data: runs, parameters, trades,
metrics, parity validations, and replay checkpoints.

============================================================
DATA LIFECYCLE ROLE
============================================================
- Stage: ANALYTICAL
- Mutability: IMMUTABLE
- Source: Backtesting engine
- Consumers: Research, validation, reporting

============================================================
MODELS
============================================================
- BacktestRun: Backtest run metadata
- BacktestParameter: Run parameter snapshots
- BacktestTrade: Simulated trades
- BacktestPerformanceMetric: Performance metrics
- ParityValidation: Live vs backtest parity checks
- ParityMismatch: Parity mismatch records
- ReplayCheckpoint: Replay state checkpoints

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


class BacktestRun(Base):
    """
    Backtest run metadata.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores metadata for each backtest run including time range,
    configuration, and overall status.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: ANALYTICAL
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: Backtest runner
    
    ============================================================
    TRACEABILITY
    ============================================================
    - run_id: Primary identifier
    - Full config snapshot stored
    - version: Backtest engine version
    
    ============================================================
    """
    
    __tablename__ = "backtest_runs"
    
    # Primary Key
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for backtest run"
    )
    
    # Run Identification
    run_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable run name"
    )
    
    run_description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Run description"
    )
    
    # Strategy
    strategy_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Strategy being tested"
    )
    
    strategy_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Strategy version"
    )
    
    # Time Range
    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Backtest start date"
    )
    
    end_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Backtest end date"
    )
    
    # Scope
    symbols: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        comment="Symbols included in backtest"
    )
    
    exchanges: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        comment="Exchanges included"
    )
    
    # Initial Capital
    initial_capital: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Initial capital amount"
    )
    
    capital_currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Capital currency"
    )
    
    # Configuration Snapshot
    config_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full configuration snapshot"
    )
    
    # Data Sources
    data_sources: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Data sources used"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="Status: pending, running, completed, failed, cancelled"
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if failed"
    )
    
    # Progress
    progress_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Progress percentage"
    )
    
    current_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Current date in simulation"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When run was created"
    )
    
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When run started"
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When run completed"
    )
    
    # Duration
    duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Run duration in seconds"
    )
    
    # Tags
    tags: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Run tags for organization"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Backtest engine version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_bt_run_name", "run_name"),
        Index("idx_bt_run_strategy", "strategy_name"),
        Index("idx_bt_run_status", "status"),
        Index("idx_bt_run_created_at", "created_at"),
        Index("idx_bt_run_dates", "start_date", "end_date"),
    )


class BacktestParameter(Base):
    """
    Backtest parameter snapshots.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores individual parameters used in backtest runs for
    reproducibility and parameter sweep analysis.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: ANALYTICAL
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: Backtest runner
    
    ============================================================
    TRACEABILITY
    ============================================================
    - run_id: FK to backtest run
    - Full parameter details
    
    ============================================================
    """
    
    __tablename__ = "backtest_parameters"
    
    # Primary Key
    parameter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for parameter"
    )
    
    # Foreign Key
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backtest_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to backtest run"
    )
    
    # Parameter Details
    parameter_category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Parameter category: strategy, risk, execution"
    )
    
    parameter_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Parameter name"
    )
    
    parameter_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Parameter value (JSON string)"
    )
    
    parameter_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Value type: int, float, string, bool, json"
    )
    
    # Metadata
    is_default: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        comment="Whether using default value"
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Parameter description"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When record was created"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_bt_param_run", "run_id"),
        Index("idx_bt_param_category", "parameter_category"),
        Index("idx_bt_param_name", "parameter_name"),
    )


class BacktestTrade(Base):
    """
    Simulated backtest trades.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores all trades executed during backtest simulation.
    Mirrors production trade structure for parity analysis.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: ANALYTICAL
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: Backtest runner
    
    ============================================================
    TRACEABILITY
    ============================================================
    - run_id: FK to backtest run
    - Simulated trade details
    
    ============================================================
    """
    
    __tablename__ = "backtest_trades"
    
    # Primary Key
    trade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for trade"
    )
    
    # Foreign Key
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backtest_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to backtest run"
    )
    
    # Trade Details
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Trading symbol"
    )
    
    exchange: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Exchange"
    )
    
    side: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Side: long, short"
    )
    
    # Entry
    entry_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Entry time"
    )
    
    entry_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Entry price"
    )
    
    entry_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Entry quantity"
    )
    
    entry_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Entry value"
    )
    
    # Exit
    exit_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Exit time"
    )
    
    exit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Exit price"
    )
    
    exit_quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Exit quantity"
    )
    
    exit_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Exit value"
    )
    
    exit_reason: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Exit reason"
    )
    
    # P&L
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        default=Decimal("0"),
        comment="Realized P&L"
    )
    
    realized_pnl_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        default=Decimal("0"),
        comment="Realized P&L percentage"
    )
    
    # Fees (simulated)
    entry_fee: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Simulated entry fee"
    )
    
    exit_fee: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        default=Decimal("0"),
        comment="Simulated exit fee"
    )
    
    net_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        default=Decimal("0"),
        comment="Net P&L after fees"
    )
    
    # Trade Duration
    duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Trade duration in seconds"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        comment="Status: open, closed"
    )
    
    # Decision Context
    entry_signal_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Signal data at entry"
    )
    
    exit_signal_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Signal data at exit"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_bt_trade_run", "run_id"),
        Index("idx_bt_trade_symbol", "symbol"),
        Index("idx_bt_trade_entry", "entry_time"),
        Index("idx_bt_trade_status", "status"),
    )


class BacktestPerformanceMetric(Base):
    """
    Backtest performance metrics.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores calculated performance metrics for backtest runs.
    Supports both overall and periodic metrics.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: ANALYTICAL
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: Backtest runner
    
    ============================================================
    TRACEABILITY
    ============================================================
    - run_id: FK to backtest run
    - Metric calculation details
    
    ============================================================
    """
    
    __tablename__ = "backtest_performance_metrics"
    
    # Primary Key
    metric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for metric"
    )
    
    # Foreign Key
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backtest_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to backtest run"
    )
    
    # Metric Details
    metric_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Metric name"
    )
    
    metric_category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Category: returns, risk, efficiency"
    )
    
    metric_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Metric value"
    )
    
    # Period (for periodic metrics)
    period_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Period type: overall, daily, weekly, monthly"
    )
    
    period_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Period start"
    )
    
    period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Period end"
    )
    
    # Context
    calculation_details: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Calculation details"
    )
    
    # Timestamps
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When metric was calculated"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_bt_metric_run", "run_id"),
        Index("idx_bt_metric_name", "metric_name"),
        Index("idx_bt_metric_category", "metric_category"),
        Index("idx_bt_metric_period", "period_type"),
    )


class ParityValidation(Base):
    """
    Live vs backtest parity validations.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores results of parity checks comparing live trading
    behavior to backtest predictions.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: ANALYTICAL
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: Parity validator
    
    ============================================================
    TRACEABILITY
    ============================================================
    - run_id: FK to backtest run
    - live_trade_id: Reference to live trade
    - Full comparison data
    
    ============================================================
    """
    
    __tablename__ = "parity_validations"
    
    # Primary Key
    validation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for validation"
    )
    
    # References
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backtest_runs.run_id", ondelete="SET NULL"),
        nullable=True,
        comment="Reference to backtest run"
    )
    
    live_trade_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trade_records.trade_id", ondelete="SET NULL"),
        nullable=True,
        comment="Reference to live trade"
    )
    
    backtest_trade_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backtest_trades.trade_id", ondelete="SET NULL"),
        nullable=True,
        comment="Reference to backtest trade"
    )
    
    # Validation Period
    validation_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Validation period start"
    )
    
    validation_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Validation period end"
    )
    
    # Validation Result
    is_parity: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Whether parity was achieved"
    )
    
    parity_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Parity score 0-1"
    )
    
    # Metrics Comparison
    metrics_comparison: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Detailed metrics comparison"
    )
    
    # Discrepancies
    discrepancy_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of discrepancies found"
    )
    
    major_discrepancies: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        comment="List of major discrepancies"
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
        Index("idx_parity_run", "run_id"),
        Index("idx_parity_live_trade", "live_trade_id"),
        Index("idx_parity_is_parity", "is_parity"),
        Index("idx_parity_validated_at", "validated_at"),
    )


class ParityMismatch(Base):
    """
    Parity mismatch records.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores individual parity mismatches for detailed analysis.
    Each mismatch is a specific discrepancy between live and backtest.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: ANALYTICAL
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: Parity validator
    
    ============================================================
    TRACEABILITY
    ============================================================
    - validation_id: FK to parity validation
    - Detailed mismatch data
    
    ============================================================
    """
    
    __tablename__ = "parity_mismatches"
    
    # Primary Key
    mismatch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for mismatch"
    )
    
    # Foreign Key
    validation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parity_validations.validation_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to validation"
    )
    
    # Mismatch Details
    mismatch_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Mismatch type: signal, entry, exit, size, timing"
    )
    
    mismatch_field: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Field with mismatch"
    )
    
    # Values
    live_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Live value (JSON)"
    )
    
    backtest_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Backtest value (JSON)"
    )
    
    deviation: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Numerical deviation if applicable"
    )
    
    deviation_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4),
        nullable=True,
        comment="Deviation percentage"
    )
    
    # Severity
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Severity: minor, moderate, major, critical"
    )
    
    # Analysis
    likely_cause: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Likely cause of mismatch"
    )
    
    impact_assessment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Impact assessment"
    )
    
    # Timestamps
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When mismatch occurred"
    )
    
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When mismatch was detected"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_mismatch_validation", "validation_id"),
        Index("idx_mismatch_type", "mismatch_type"),
        Index("idx_mismatch_severity", "severity"),
        Index("idx_mismatch_occurred_at", "occurred_at"),
    )


class ReplayCheckpoint(Base):
    """
    Replay state checkpoints.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores state checkpoints during replay execution for
    resume capability and debugging.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: ANALYTICAL
    - Mutability: IMMUTABLE
    - Retention: 30 days
    - Source: Replay engine
    
    ============================================================
    TRACEABILITY
    ============================================================
    - run_id: FK to backtest run
    - Full state snapshot
    
    ============================================================
    """
    
    __tablename__ = "replay_checkpoints"
    
    # Primary Key
    checkpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for checkpoint"
    )
    
    # Foreign Key
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backtest_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to backtest run"
    )
    
    # Checkpoint Details
    checkpoint_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type: periodic, milestone, manual"
    )
    
    checkpoint_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Checkpoint name"
    )
    
    # Simulation Time
    simulation_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Simulation time at checkpoint"
    )
    
    # State Snapshot
    state_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full state snapshot"
    )
    
    # Position State
    positions_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Positions at checkpoint"
    )
    
    balance_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Balances at checkpoint"
    )
    
    # Metrics at Checkpoint
    cumulative_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Cumulative P&L at checkpoint"
    )
    
    trade_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Trade count at checkpoint"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When checkpoint was created"
    )
    
    # Sequence
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Checkpoint sequence number"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_checkpoint_run", "run_id"),
        Index("idx_checkpoint_type", "checkpoint_type"),
        Index("idx_checkpoint_sim_time", "simulation_time"),
        Index("idx_checkpoint_sequence", "run_id", "sequence_number"),
    )
