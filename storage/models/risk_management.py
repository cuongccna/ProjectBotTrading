"""
Risk Management Domain ORM Models.

============================================================
PURPOSE
============================================================
Models for storing risk management events: system halts,
strategy pauses, drawdown events, threshold breaches, and
configuration audit trail.

============================================================
DATA LIFECYCLE ROLE
============================================================
- Stage: DERIVED (risk events)
- Mutability: IMMUTABLE (append-only)
- Source: Risk monitoring systems
- Consumers: Audit, reporting, recovery

============================================================
MODELS
============================================================
- SystemHalt: System-wide trading halts
- StrategyPause: Individual strategy pauses
- DrawdownEvent: Drawdown threshold events
- RiskThresholdBreach: Risk threshold breaches
- RiskConfigurationAudit: Configuration change audit

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


class SystemHalt(Base):
    """
    System-wide trading halts.
    
    ============================================================
    PURPOSE
    ============================================================
    Records system-wide trading halts triggered by critical
    risk events. All trading stops until halt is cleared.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: EVENT (critical)
    - Mutability: IMMUTABLE
    - Retention: 10 years (regulatory)
    - Source: System guard
    
    ============================================================
    TRACEABILITY
    ============================================================
    - halt_reason: Full reason chain
    - triggered_by: Component that triggered
    - All context preserved
    
    ============================================================
    """
    
    __tablename__ = "system_halts"
    
    # Primary Key
    halt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for halt"
    )
    
    # Halt Details
    halt_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Halt type: emergency, scheduled, risk_triggered"
    )
    
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Severity: warning, critical, emergency"
    )
    
    halt_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Reason for halt"
    )
    
    triggered_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Component that triggered halt"
    )
    
    # Scope
    affected_exchanges: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        comment="List of affected exchanges"
    )
    
    affected_symbols: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Affected symbols (null = all)"
    )
    
    # Thresholds
    threshold_breached: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Threshold that was breached"
    )
    
    threshold_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Threshold value"
    )
    
    actual_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Actual value that triggered"
    )
    
    # Context
    context_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full context data"
    )
    
    # Timestamps
    halted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When halt was triggered"
    )
    
    resumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When trading resumed"
    )
    
    halt_duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Halt duration in seconds"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="Status: active, resolved, expired"
    )
    
    resolution_note: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Note on resolution"
    )
    
    resolved_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Who/what resolved the halt"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="System version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_halt_halted_at", "halted_at"),
        Index("idx_halt_status", "status"),
        Index("idx_halt_severity", "severity"),
        Index("idx_halt_type", "halt_type"),
    )


class StrategyPause(Base):
    """
    Individual strategy pauses.
    
    ============================================================
    PURPOSE
    ============================================================
    Records pauses of individual trading strategies due to
    performance issues, risk limits, or manual intervention.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: EVENT
    - Mutability: IMMUTABLE
    - Retention: 5 years
    - Source: Strategy guard
    
    ============================================================
    TRACEABILITY
    ============================================================
    - strategy_id: Strategy paused
    - pause_reason: Full reason
    - version: Guard version
    
    ============================================================
    """
    
    __tablename__ = "strategy_pauses"
    
    # Primary Key
    pause_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for pause"
    )
    
    # Strategy Reference
    strategy_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Strategy identifier"
    )
    
    strategy_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Strategy name"
    )
    
    # Pause Details
    pause_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Pause type: performance, risk, manual, technical"
    )
    
    pause_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Reason for pause"
    )
    
    triggered_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Component/user that triggered"
    )
    
    # Scope
    affected_symbols: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Affected symbols (null = all strategy symbols)"
    )
    
    # Performance Metrics at Pause
    metrics_at_pause: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Strategy metrics at time of pause"
    )
    
    # Thresholds
    threshold_breached: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Threshold breached"
    )
    
    threshold_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Threshold value"
    )
    
    actual_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Actual value"
    )
    
    # Timestamps
    paused_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When pause was triggered"
    )
    
    resume_after: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Scheduled resume time"
    )
    
    resumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Actual resume time"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="Status: active, resumed, expired"
    )
    
    resume_note: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Note on resume"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Guard version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_strat_pause_strategy", "strategy_id"),
        Index("idx_strat_pause_paused_at", "paused_at"),
        Index("idx_strat_pause_status", "status"),
        Index("idx_strat_pause_type", "pause_type"),
    )


class DrawdownEvent(Base):
    """
    Drawdown threshold events.
    
    ============================================================
    PURPOSE
    ============================================================
    Records drawdown events when account or strategy drawdown
    crosses predefined thresholds.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: EVENT
    - Mutability: IMMUTABLE
    - Retention: 5 years
    - Source: Drawdown monitor
    
    ============================================================
    TRACEABILITY
    ============================================================
    - scope: Account or strategy
    - threshold_level: Which threshold hit
    - Full metrics at event
    
    ============================================================
    """
    
    __tablename__ = "drawdown_events"
    
    # Primary Key
    drawdown_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for event"
    )
    
    # Scope
    scope: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Scope: account, strategy, symbol"
    )
    
    scope_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Strategy/symbol ID if applicable"
    )
    
    exchange: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Exchange"
    )
    
    # Drawdown Details
    drawdown_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type: daily, weekly, total, trailing"
    )
    
    drawdown_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        comment="Drawdown percentage"
    )
    
    drawdown_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Drawdown amount in quote currency"
    )
    
    peak_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Peak value before drawdown"
    )
    
    current_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Current value at event"
    )
    
    # Threshold
    threshold_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Threshold level: warning, limit, critical"
    )
    
    threshold_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        comment="Threshold percentage"
    )
    
    # Action Taken
    action_taken: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Action: alert_only, reduce_size, pause, halt"
    )
    
    action_details: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Details of action taken"
    )
    
    # Timestamps
    event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When event occurred"
    )
    
    recovered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When drawdown recovered"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="Status: active, recovering, recovered"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Monitor version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_dd_event_scope", "scope", "scope_id"),
        Index("idx_dd_event_type", "drawdown_type"),
        Index("idx_dd_event_at", "event_at"),
        Index("idx_dd_event_status", "status"),
        Index("idx_dd_event_level", "threshold_level"),
    )


class RiskThresholdBreach(Base):
    """
    Risk threshold breach events.
    
    ============================================================
    PURPOSE
    ============================================================
    Records any risk threshold breach across the system.
    Generic model for various risk metrics.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: EVENT
    - Mutability: IMMUTABLE
    - Retention: 5 years
    - Source: Risk management system
    
    ============================================================
    TRACEABILITY
    ============================================================
    - metric_name: Which metric breached
    - scope: Where breach occurred
    - version: Risk system version
    
    ============================================================
    """
    
    __tablename__ = "risk_threshold_breaches"
    
    # Primary Key
    breach_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for breach"
    )
    
    # Scope
    scope: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Scope: system, account, strategy, trade"
    )
    
    scope_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Scope ID if applicable"
    )
    
    # Metric Details
    metric_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Risk metric name"
    )
    
    metric_category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Metric category"
    )
    
    # Values
    threshold_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Threshold value"
    )
    
    actual_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Actual value"
    )
    
    breach_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Amount by which threshold exceeded"
    )
    
    breach_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        comment="Percentage exceeded"
    )
    
    # Severity
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Severity: info, warning, error, critical"
    )
    
    # Action
    action_required: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Required action"
    )
    
    action_taken: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Action actually taken"
    )
    
    action_result: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Result of action"
    )
    
    # Context
    context_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Additional context"
    )
    
    # Timestamps
    breached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When breach occurred"
    )
    
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When breach resolved"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="Status: active, acknowledged, resolved"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="System version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_breach_scope", "scope", "scope_id"),
        Index("idx_breach_metric", "metric_name"),
        Index("idx_breach_category", "metric_category"),
        Index("idx_breach_severity", "severity"),
        Index("idx_breach_at", "breached_at"),
        Index("idx_breach_status", "status"),
    )


class RiskConfigurationAudit(Base):
    """
    Risk configuration change audit trail.
    
    ============================================================
    PURPOSE
    ============================================================
    Records all changes to risk configuration parameters.
    Immutable audit trail for regulatory compliance.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: AUDIT
    - Mutability: IMMUTABLE
    - Retention: 10 years (regulatory)
    - Source: Configuration system
    
    ============================================================
    TRACEABILITY
    ============================================================
    - changed_by: Who made change
    - previous_value: What it was
    - new_value: What it became
    
    ============================================================
    """
    
    __tablename__ = "risk_configuration_audit"
    
    # Primary Key
    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for audit entry"
    )
    
    # Configuration Details
    config_section: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Configuration section"
    )
    
    config_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Configuration key"
    )
    
    # Values
    previous_value: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Previous value (JSON string)"
    )
    
    new_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="New value (JSON string)"
    )
    
    # Change Details
    change_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Change type: create, update, delete"
    )
    
    change_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Reason for change"
    )
    
    changed_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Who made the change"
    )
    
    # Authorization
    authorized_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Who authorized if different"
    )
    
    requires_approval: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether change required approval"
    )
    
    approval_status: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Approval status if required"
    )
    
    # Effective Period
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When change becomes effective"
    )
    
    effective_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When change expires (if temporary)"
    )
    
    # Timestamps
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When change was made"
    )
    
    # Context
    context_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional context"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="System version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_risk_audit_section", "config_section"),
        Index("idx_risk_audit_key", "config_key"),
        Index("idx_risk_audit_changed_at", "changed_at"),
        Index("idx_risk_audit_changed_by", "changed_by"),
        Index("idx_risk_audit_effective", "effective_from", "effective_until"),
    )
