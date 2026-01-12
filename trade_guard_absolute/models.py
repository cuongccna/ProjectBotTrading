"""
Trade Guard Absolute - ORM Models.

============================================================
PURPOSE
============================================================
SQLAlchemy models for persisting guard decisions.

ALL guard decisions are logged for:
- Audit trail
- Performance analysis
- Debugging blocked trades
- Alert history

============================================================
"""

from datetime import datetime
from typing import Optional
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
    Enum as SQLEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import enum


# ============================================================
# BASE CLASS
# ============================================================

class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# ============================================================
# ENUMS FOR DATABASE
# ============================================================

class GuardDecisionEnum(str, enum.Enum):
    """Guard decision values."""
    EXECUTE = "EXECUTE"
    BLOCK = "BLOCK"


class BlockSeverityEnum(str, enum.Enum):
    """Block severity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


class BlockCategoryEnum(str, enum.Enum):
    """Block categories."""
    SYSTEM_INTEGRITY = "SYSTEM_INTEGRITY"
    EXECUTION_SAFETY = "EXECUTION_SAFETY"
    STATE_CONSISTENCY = "STATE_CONSISTENCY"
    RULE_VIOLATION = "RULE_VIOLATION"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ============================================================
# GUARD DECISION LOG
# ============================================================

class GuardDecisionLog(Base):
    """
    Record of every guard evaluation.
    
    ALL decisions are logged - both EXECUTE and BLOCK.
    This provides complete audit trail.
    """
    
    __tablename__ = "guard_decision_log"
    
    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Evaluation Identity
    evaluation_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    """Unique evaluation ID (e.g., GUARD-20240115120000123456-abc12345)"""
    
    # Trade Intent
    request_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    """Original trade request ID"""
    
    symbol: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    """Trading symbol"""
    
    direction: Mapped[str] = mapped_column(String(16), nullable=True)
    """Trade direction (LONG/SHORT)"""
    
    # Decision
    decision: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
    )
    """EXECUTE or BLOCK"""
    
    # Block Details (only for BLOCK decisions)
    block_reason: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    """Block reason code (e.g., SI_STALE_MARKET_DATA)"""
    
    block_severity: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
    )
    """Block severity (LOW, MEDIUM, HIGH, CRITICAL, EMERGENCY)"""
    
    block_category: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )
    """Block category (e.g., SYSTEM_INTEGRITY)"""
    
    block_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    """Human-readable block message"""
    
    # Details
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    """Full decision details as JSON"""
    
    validation_results: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    """All validation results as JSON"""
    
    # Timing
    evaluation_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    """Time taken for evaluation in milliseconds"""
    
    # Timestamps
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )
    """When the evaluation occurred"""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    """Record creation timestamp"""
    
    # Indexes
    __table_args__ = (
        Index("ix_guard_decision_symbol_timestamp", "symbol", "timestamp"),
        Index("ix_guard_decision_block_category_timestamp", "block_category", "timestamp"),
        Index("ix_guard_decision_block_reason_timestamp", "block_reason", "timestamp"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<GuardDecisionLog("
            f"id={self.id}, "
            f"evaluation_id={self.evaluation_id!r}, "
            f"symbol={self.symbol!r}, "
            f"decision={self.decision!r}"
            f")>"
        )


# ============================================================
# BLOCK ALERT LOG
# ============================================================

class GuardBlockAlertLog(Base):
    """
    Record of alerts sent for BLOCK decisions.
    
    Tracks Telegram alerts with rate limiting.
    """
    
    __tablename__ = "guard_block_alert_log"
    
    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Reference to Decision
    evaluation_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    """Reference to guard_decision_log.evaluation_id"""
    
    # Alert Details
    alert_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    """Alert type (e.g., TELEGRAM, EMAIL)"""
    
    alert_severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    """Alert severity"""
    
    # Content
    alert_title: Mapped[str] = mapped_column(String(256), nullable=False)
    """Alert title/subject"""
    
    alert_message: Mapped[str] = mapped_column(Text, nullable=False)
    """Full alert message"""
    
    # Status
    sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    """Whether alert was successfully sent"""
    
    send_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    """Error message if send failed"""
    
    rate_limited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    """Whether alert was rate limited"""
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    """When the alert was created"""
    
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )
    """When the alert was sent"""
    
    def __repr__(self) -> str:
        return (
            f"<GuardBlockAlertLog("
            f"id={self.id}, "
            f"evaluation_id={self.evaluation_id!r}, "
            f"sent={self.sent}"
            f")>"
        )


# ============================================================
# GUARD STATISTICS
# ============================================================

class GuardDailyStats(Base):
    """
    Daily statistics for guard performance.
    
    Aggregated for dashboard and monitoring.
    """
    
    __tablename__ = "guard_daily_stats"
    
    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Date
    stat_date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        unique=True,
        index=True,
    )
    """Date for these statistics"""
    
    # Counts
    total_evaluations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Total evaluations performed"""
    
    execute_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Number of EXECUTE decisions"""
    
    block_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Number of BLOCK decisions"""
    
    # Block Breakdown by Category
    blocks_system_integrity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Blocks for system integrity"""
    
    blocks_execution_safety: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Blocks for execution safety"""
    
    blocks_state_consistency: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Blocks for state consistency"""
    
    blocks_rule_violation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Blocks for rule violations"""
    
    blocks_environmental: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Blocks for environmental conditions"""
    
    blocks_internal_error: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Blocks for internal errors"""
    
    # Block Breakdown by Severity
    severity_low: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """LOW severity blocks"""
    
    severity_medium: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """MEDIUM severity blocks"""
    
    severity_high: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """HIGH severity blocks"""
    
    severity_critical: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """CRITICAL severity blocks"""
    
    severity_emergency: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """EMERGENCY severity blocks"""
    
    # Performance
    avg_evaluation_time_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    """Average evaluation time in ms"""
    
    max_evaluation_time_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    """Maximum evaluation time in ms"""
    
    # Alerts
    alerts_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Number of alerts sent"""
    
    alerts_rate_limited: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Number of alerts rate limited"""
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    """Record creation timestamp"""
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    """Last update timestamp"""
    
    def __repr__(self) -> str:
        return (
            f"<GuardDailyStats("
            f"date={self.stat_date}, "
            f"execute={self.execute_count}, "
            f"block={self.block_count}"
            f")>"
        )
    
    @property
    def block_rate(self) -> float:
        """Calculate block rate as percentage."""
        if self.total_evaluations == 0:
            return 0.0
        return (self.block_count / self.total_evaluations) * 100
