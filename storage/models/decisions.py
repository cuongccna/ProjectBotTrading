"""
Decision Domain ORM Models.

============================================================
PURPOSE
============================================================
Models for storing decision engine outputs: trade eligibility,
veto events, trading decisions, and state transitions.

============================================================
DATA LIFECYCLE ROLE
============================================================
- Stage: DERIVED (decisions)
- Mutability: IMMUTABLE (append-only)
- Source: Scoring outputs
- Consumers: Execution engine, audit

============================================================
MODELS
============================================================
- TradeEligibilityEvaluation: Eligibility check results
- VetoEvent: Veto rule triggers
- TradingDecision: Final trading decisions
- DecisionStateTransition: State machine transitions

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


class TradeEligibilityEvaluation(Base):
    """
    Trade eligibility evaluation results.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores results of eligibility checks for potential trades.
    Each check evaluates whether a trade meets all prerequisites.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (decision)
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: Composite scores, market data
    
    ============================================================
    TRACEABILITY
    ============================================================
    - composite_score_id: FK to composite score
    - version: Eligibility rule version
    - All criteria results stored
    
    ============================================================
    """
    
    __tablename__ = "trade_eligibility_evaluations"
    
    # Primary Key
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for evaluation"
    )
    
    # Foreign Key
    composite_score_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("composite_scores.composite_score_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Reference to composite score"
    )
    
    # Scope
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
    
    # Eligibility Result
    is_eligible: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Whether trade is eligible"
    )
    
    eligibility_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Reason for eligibility decision"
    )
    
    # Criteria Results
    criteria_results: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Individual criteria pass/fail results"
    )
    
    passed_criteria_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of criteria passed"
    )
    
    failed_criteria_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of criteria failed"
    )
    
    # Threshold Values
    score_threshold: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Score threshold applied"
    )
    
    actual_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Actual score evaluated"
    )
    
    # Timestamps
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When evaluation was performed"
    )
    
    data_as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Data timestamp for evaluation"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Eligibility rule version"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="evaluated",
        comment="Processing stage"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_elig_composite", "composite_score_id"),
        Index("idx_elig_symbol", "symbol", "exchange"),
        Index("idx_elig_eligible", "is_eligible"),
        Index("idx_elig_evaluated_at", "evaluated_at"),
    )


class VetoEvent(Base):
    """
    Veto rule trigger events.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores records of veto rules being triggered. Each veto
    blocks a potential trade and must be logged for audit.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (veto)
    - Mutability: IMMUTABLE
    - Retention: 5 years (audit)
    - Source: Eligibility evaluation
    
    ============================================================
    TRACEABILITY
    ============================================================
    - evaluation_id: FK to eligibility evaluation
    - rule_name: Veto rule triggered
    - version: Rule version
    
    ============================================================
    """
    
    __tablename__ = "veto_events"
    
    # Primary Key
    veto_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for veto event"
    )
    
    # Foreign Key
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trade_eligibility_evaluations.evaluation_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Reference to eligibility evaluation"
    )
    
    # Scope
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
    
    # Veto Details
    rule_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Name of veto rule triggered"
    )
    
    rule_category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Rule category: risk, compliance, technical"
    )
    
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Severity: soft, hard, critical"
    )
    
    veto_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Detailed reason for veto"
    )
    
    # Threshold Details
    threshold_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Threshold that was exceeded"
    )
    
    actual_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Actual value that triggered veto"
    )
    
    # Context
    context_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Additional context data"
    )
    
    # Override Info (if applicable)
    can_override: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether veto can be overridden"
    )
    
    override_requires: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Override requirement"
    )
    
    # Timestamps
    vetoed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When veto was triggered"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Rule version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_veto_evaluation", "evaluation_id"),
        Index("idx_veto_symbol", "symbol", "exchange"),
        Index("idx_veto_rule", "rule_name"),
        Index("idx_veto_category", "rule_category"),
        Index("idx_veto_vetoed_at", "vetoed_at"),
    )


class TradingDecision(Base):
    """
    Final trading decisions.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores final trading decisions including action, sizing,
    and all supporting rationale for audit.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (decision)
    - Mutability: IMMUTABLE
    - Retention: 5 years (audit)
    - Source: Eligibility evaluation
    
    ============================================================
    TRACEABILITY
    ============================================================
    - evaluation_id: FK to eligibility evaluation
    - All decision inputs stored
    - version: Decision logic version
    
    ============================================================
    """
    
    __tablename__ = "trading_decisions"
    
    # Primary Key
    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for decision"
    )
    
    # Foreign Key
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trade_eligibility_evaluations.evaluation_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Reference to eligibility evaluation"
    )
    
    # Scope
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
    
    # Decision
    decision_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Decision type: open, close, adjust, hold, skip"
    )
    
    action: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Action: buy, sell, hold"
    )
    
    side: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="Side: long, short"
    )
    
    # Position Sizing
    recommended_size: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Recommended position size"
    )
    
    size_currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Size currency (base or quote)"
    )
    
    max_size_allowed: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Maximum size allowed by risk"
    )
    
    # Risk Parameters
    target_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Target price if applicable"
    )
    
    stop_loss_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Stop loss price"
    )
    
    take_profit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Take profit price"
    )
    
    risk_reward_ratio: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4),
        nullable=True,
        comment="Risk/reward ratio"
    )
    
    # Confidence & Rationale
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Decision confidence 0-1"
    )
    
    rationale: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Decision rationale"
    )
    
    supporting_factors: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Factors supporting decision"
    )
    
    # Execution Instructions
    urgency: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Urgency: immediate, normal, patient"
    )
    
    order_type_hint: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Suggested order type"
    )
    
    time_in_force_hint: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Suggested time in force"
    )
    
    # Timestamps
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When decision was made"
    )
    
    valid_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Decision validity expiry"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="Status: pending, executed, expired, cancelled"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Decision logic version"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="decided",
        comment="Processing stage"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_decision_evaluation", "evaluation_id"),
        Index("idx_decision_symbol", "symbol", "exchange"),
        Index("idx_decision_type", "decision_type"),
        Index("idx_decision_action", "action"),
        Index("idx_decision_decided_at", "decided_at"),
        Index("idx_decision_status", "status"),
    )


class DecisionStateTransition(Base):
    """
    Decision state machine transitions.
    
    ============================================================
    PURPOSE
    ============================================================
    Tracks all state transitions for trading decisions.
    Provides complete audit trail of decision lifecycle.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (audit)
    - Mutability: IMMUTABLE
    - Retention: 5 years (audit)
    - Source: Trading decision updates
    
    ============================================================
    TRACEABILITY
    ============================================================
    - decision_id: FK to trading decision
    - transition_by: What triggered transition
    - Full state history
    
    ============================================================
    """
    
    __tablename__ = "decision_state_transitions"
    
    # Primary Key
    transition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for transition"
    )
    
    # Foreign Key
    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trading_decisions.decision_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Reference to trading decision"
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
    
    transition_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Reason for transition"
    )
    
    transition_by: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="What triggered transition: system, user, expiry"
    )
    
    # Additional Context
    context_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional transition context"
    )
    
    # Timestamps
    transitioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When transition occurred"
    )
    
    # Sequence
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Transition sequence number"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_dec_trans_decision", "decision_id"),
        Index("idx_dec_trans_from", "from_state"),
        Index("idx_dec_trans_to", "to_state"),
        Index("idx_dec_trans_at", "transitioned_at"),
    )
