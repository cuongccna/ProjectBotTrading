"""
Risk Scoring Engine - Persistence Layer.

============================================================
PURPOSE
============================================================
ORM models and repository for persisting risk assessments.

Enables:
- Historical tracking of risk scores
- Analysis of risk patterns over time
- Alerting based on stored data
- Audit trail for compliance

============================================================
MODELS
============================================================
1. RiskSnapshot: Complete point-in-time assessment
2. RiskDimensionScore: Per-dimension breakdown (child of RiskSnapshot)
3. RiskStateTransition: State change events for alerting

============================================================
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Index,
    Enum as SQLAlchemyEnum,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship, Mapped, mapped_column

from database.engine import Base


# ============================================================
# RISK SNAPSHOT MODEL
# ============================================================


class RiskSnapshot(Base):
    """
    Complete point-in-time risk assessment snapshot.
    
    ============================================================
    WHAT IT STORES
    ============================================================
    - Total score (0-8)
    - Risk level classification
    - Timestamp
    - Engine version for compatibility tracking
    
    ============================================================
    RELATIONSHIPS
    ============================================================
    - Has many RiskDimensionScore (one per dimension)
    
    ============================================================
    """
    
    __tablename__ = "risk_snapshots"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    
    # Core scoring data
    total_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Total risk score (0-8)",
    )
    
    risk_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Risk level: LOW, MEDIUM, HIGH, CRITICAL",
    )
    
    # Timestamps
    assessment_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the assessment was performed",
    )
    
    input_data_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the input data used",
    )
    
    # Metadata
    engine_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
        comment="Risk scoring engine version",
    )
    
    # Optional: Full output as JSON for debugging
    raw_output_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Full RiskScoringOutput as JSON",
    )
    
    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    
    # Relationships
    dimension_scores: Mapped[List["RiskDimensionScore"]] = relationship(
        "RiskDimensionScore",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="joined",
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_risk_snapshots_timestamp", "assessment_timestamp"),
        Index("ix_risk_snapshots_risk_level", "risk_level"),
        Index("ix_risk_snapshots_total_score", "total_score"),
    )
    
    def __repr__(self) -> str:
        return (
            f"RiskSnapshot("
            f"id={self.id}, "
            f"score={self.total_score}, "
            f"level={self.risk_level}, "
            f"timestamp={self.assessment_timestamp})"
        )


# ============================================================
# RISK DIMENSION SCORE MODEL
# ============================================================


class RiskDimensionScore(Base):
    """
    Per-dimension risk score breakdown.
    
    ============================================================
    WHAT IT STORES
    ============================================================
    - Dimension (MARKET, LIQUIDITY, VOLATILITY, SYSTEM_INTEGRITY)
    - State (SAFE=0, WARNING=1, DANGEROUS=2)
    - Reason text
    - Contributing factors
    
    ============================================================
    """
    
    __tablename__ = "risk_dimension_scores"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    
    # Foreign key to snapshot
    snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("risk_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Dimension identification
    dimension: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="MARKET, LIQUIDITY, VOLATILITY, SYSTEM_INTEGRITY",
    )
    
    # Scoring
    state: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        comment="SAFE, WARNING, DANGEROUS",
    )
    
    state_value: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Numeric state: 0, 1, 2",
    )
    
    # Explanation
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable reason for state",
    )
    
    # Contributing factors as JSON array
    contributing_factors: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        comment="List of factors contributing to state",
    )
    
    # Thresholds used (for audit/debugging)
    thresholds_used: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Thresholds that were applied",
    )
    
    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    
    # Relationships
    snapshot: Mapped["RiskSnapshot"] = relationship(
        "RiskSnapshot",
        back_populates="dimension_scores",
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_risk_dimension_scores_snapshot_id", "snapshot_id"),
        Index("ix_risk_dimension_scores_dimension", "dimension"),
        Index("ix_risk_dimension_scores_state", "state"),
    )
    
    def __repr__(self) -> str:
        return (
            f"RiskDimensionScore("
            f"dimension={self.dimension}, "
            f"state={self.state})"
        )


# ============================================================
# RISK STATE TRANSITION MODEL
# ============================================================


class RiskStateTransition(Base):
    """
    Records risk state changes for alerting and analysis.
    
    ============================================================
    WHAT IT STORES
    ============================================================
    - Which dimension changed
    - Old state → New state
    - Reason for change
    - Whether alert was sent
    
    ============================================================
    """
    
    __tablename__ = "risk_state_transitions"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    
    # Reference to the snapshot that triggered this
    snapshot_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("risk_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # What changed
    dimension: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="MARKET, LIQUIDITY, VOLATILITY, SYSTEM_INTEGRITY",
    )
    
    old_state: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        comment="Previous state: SAFE, WARNING, DANGEROUS",
    )
    
    new_state: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        comment="New state: SAFE, WARNING, DANGEROUS",
    )
    
    old_state_value: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Previous numeric state: 0, 1, 2",
    )
    
    new_state_value: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="New numeric state: 0, 1, 2",
    )
    
    # Direction of change
    is_escalation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if risk increased",
    )
    
    # Explanation
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Reason for state change",
    )
    
    # Alerting tracking
    alert_sent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether alert was sent for this transition",
    )
    
    alert_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When alert was sent",
    )
    
    # Timestamps
    transition_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the transition occurred",
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_risk_state_transitions_timestamp", "transition_timestamp"),
        Index("ix_risk_state_transitions_dimension", "dimension"),
        Index("ix_risk_state_transitions_alert_sent", "alert_sent"),
        Index("ix_risk_state_transitions_is_escalation", "is_escalation"),
    )
    
    def __repr__(self) -> str:
        return (
            f"RiskStateTransition("
            f"dimension={self.dimension}, "
            f"{self.old_state} → {self.new_state})"
        )
