"""
Human-in-the-Loop Review Database Models.

Tables:
- review_events: System-generated events requiring human review
- human_decisions: Logged human actions on review events
- parameter_changes: History of parameter modifications
- annotations: Human notes and tags on events
- outcome_evaluations: Post-hoc evaluation of decisions
"""

from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, Text, Float, Boolean, 
    DateTime, ForeignKey, Index, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import enum

from database.engine import Base


# =============================================================
# ENUMS
# =============================================================

class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    EXPIRED = "expired"


class ReviewTriggerType(str, enum.Enum):
    TRADE_GUARD_BLOCK = "trade_guard_block"
    DRAWDOWN_THRESHOLD = "drawdown_threshold"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    RISK_OSCILLATION = "risk_oscillation"
    DATA_SOURCE_DEGRADED = "data_source_degraded"
    SIGNAL_CONTRADICTION = "signal_contradiction"
    BACKTEST_DIVERGENCE = "backtest_divergence"
    MANUAL_REQUEST = "manual_request"


class DecisionType(str, enum.Enum):
    ADJUST_RISK_THRESHOLD = "adjust_risk_threshold"
    PAUSE_STRATEGY = "pause_strategy"
    REDUCE_POSITION_LIMIT = "reduce_position_limit"
    ENABLE_DATA_SOURCE = "enable_data_source"
    DISABLE_DATA_SOURCE = "disable_data_source"
    MARK_ANOMALY = "mark_anomaly"
    APPROVE_ROLLBACK = "approve_rollback"
    ADD_ANNOTATION = "add_annotation"
    ACKNOWLEDGE_ONLY = "acknowledge_only"
    ESCALATE = "escalate"


class ConfidenceLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OutcomeVerdict(str, enum.Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    INCONCLUSIVE = "inconclusive"
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"


# =============================================================
# 1. REVIEW EVENTS TABLE
# =============================================================

class ReviewEvent(Base):
    """
    System-generated events requiring human review.
    
    Created automatically when trigger conditions are met.
    Immutable once created - only status can change.
    """
    __tablename__ = "review_events"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id = Column(String(36), nullable=False, index=True)
    
    # Trigger information
    trigger_type = Column(String(50), nullable=False, index=True)
    trigger_reason = Column(Text, nullable=False)
    trigger_value = Column(Float, nullable=True)  # e.g., drawdown %, consecutive losses
    trigger_threshold = Column(Float, nullable=True)  # threshold that was breached
    
    # Status tracking
    status = Column(String(20), nullable=False, default="pending", index=True)
    priority = Column(String(10), nullable=False, default="normal")  # low, normal, high, critical
    
    # Context snapshots (immutable at creation time)
    market_context = Column(JSONB, nullable=True)  # price, volume, regime
    risk_state_snapshot = Column(JSONB, nullable=True)  # full risk state at trigger time
    sentiment_summary = Column(JSONB, nullable=True)  # sentiment scores
    flow_context = Column(JSONB, nullable=True)  # on-chain flow data
    smart_money_context = Column(JSONB, nullable=True)  # smart money signals
    
    # Strategy and trade info
    strategy_decision = Column(JSONB, nullable=True)  # what the strategy wanted to do
    trade_guard_rules = Column(JSONB, nullable=True)  # which rules were involved
    execution_outcome = Column(JSONB, nullable=True)  # if trade happened, what was result
    
    # Related IDs
    entry_decision_id = Column(BigInteger, ForeignKey("entry_decision.id"), nullable=True)
    risk_state_id = Column(BigInteger, ForeignKey("risk_state.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=True)  # optional expiration
    reviewed_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    # Review assignment
    assigned_to = Column(String(100), nullable=True)  # username if assigned
    
    # Notification tracking
    telegram_notified = Column(Boolean, default=False)
    telegram_message_id = Column(String(50), nullable=True)
    
    # Relationships
    decisions = relationship("HumanDecision", back_populates="review_event")
    annotations = relationship("Annotation", back_populates="review_event")
    
    __table_args__ = (
        Index("idx_review_events_status_created", "status", "created_at"),
        Index("idx_review_events_trigger_type", "trigger_type"),
    )


# =============================================================
# 2. HUMAN DECISIONS TABLE
# =============================================================

class HumanDecision(Base):
    """
    Logged human actions on review events.
    
    Immutable once created. Versioned for audit trail.
    """
    __tablename__ = "human_decisions"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    review_event_id = Column(BigInteger, ForeignKey("review_events.id"), nullable=False, index=True)
    
    # Decision details
    decision_type = Column(String(50), nullable=False)
    reason_code = Column(String(100), nullable=False)
    confidence_level = Column(String(20), nullable=False, default="medium")
    comment = Column(Text, nullable=True)
    
    # Who made the decision
    user_id = Column(String(100), nullable=False)
    user_role = Column(String(50), nullable=False)  # viewer, operator, admin
    
    # What was changed
    parameter_before = Column(JSONB, nullable=True)  # state before change
    parameter_after = Column(JSONB, nullable=True)  # state after change
    
    # Approval chain
    requires_approval = Column(Boolean, default=False)
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    
    # Versioning
    version = Column(BigInteger, nullable=False, default=1)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Relationship
    review_event = relationship("ReviewEvent", back_populates="decisions")
    
    __table_args__ = (
        Index("idx_human_decisions_user", "user_id", "created_at"),
        Index("idx_human_decisions_type", "decision_type"),
    )


# =============================================================
# 3. PARAMETER CHANGES TABLE
# =============================================================

class ParameterChange(Base):
    """
    History of parameter modifications.
    
    Tracks all changes to system parameters with before/after values.
    """
    __tablename__ = "parameter_changes"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    human_decision_id = Column(BigInteger, ForeignKey("human_decisions.id"), nullable=True)
    
    # What changed
    parameter_category = Column(String(50), nullable=False)  # risk, position, data_source, strategy
    parameter_name = Column(String(100), nullable=False)
    parameter_path = Column(String(255), nullable=True)  # full path like "risk.thresholds.max_drawdown"
    
    # Values
    old_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=False)
    
    # Bounds validation
    min_allowed = Column(Float, nullable=True)
    max_allowed = Column(Float, nullable=True)
    
    # Effectiveness tracking
    applied_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    reverted_at = Column(DateTime, nullable=True)
    reverted_by = Column(String(100), nullable=True)
    
    # Who made the change
    changed_by = Column(String(100), nullable=False)
    change_reason = Column(Text, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index("idx_param_changes_category", "parameter_category", "parameter_name"),
        Index("idx_param_changes_active", "is_active", "applied_at"),
    )


# =============================================================
# 4. ANNOTATIONS TABLE
# =============================================================

class Annotation(Base):
    """
    Human notes and tags on events.
    
    Used for institutional memory and learning.
    """
    __tablename__ = "annotations"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    review_event_id = Column(BigInteger, ForeignKey("review_events.id"), nullable=True, index=True)
    correlation_id = Column(String(36), nullable=True, index=True)  # can annotate any correlated event
    
    # Annotation content
    annotation_type = Column(String(50), nullable=False)  # note, tag, warning, insight
    tag = Column(String(100), nullable=True, index=True)  # e.g., "false_positive", "regime_change"
    content = Column(Text, nullable=True)
    
    # Structured tags
    tags = Column(JSONB, nullable=True)  # list of tags
    
    # Who created
    created_by = Column(String(100), nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationship
    review_event = relationship("ReviewEvent", back_populates="annotations")


# =============================================================
# 5. OUTCOME EVALUATIONS TABLE
# =============================================================

class OutcomeEvaluation(Base):
    """
    Post-hoc evaluation of decisions.
    
    Used for learning and feedback loop.
    """
    __tablename__ = "outcome_evaluations"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    review_event_id = Column(BigInteger, ForeignKey("review_events.id"), nullable=False, index=True)
    human_decision_id = Column(BigInteger, ForeignKey("human_decisions.id"), nullable=True)
    
    # Evaluation
    verdict = Column(String(30), nullable=False)  # correct, incorrect, inconclusive, false_positive, false_negative
    
    # Performance impact
    pnl_impact = Column(Float, nullable=True)  # estimated P&L impact
    risk_impact = Column(Float, nullable=True)  # change in risk metrics
    
    # Comparison
    actual_outcome = Column(JSONB, nullable=True)  # what actually happened
    expected_outcome = Column(JSONB, nullable=True)  # what was expected
    
    # Time window
    evaluation_window_hours = Column(Float, nullable=True)
    
    # Notes
    evaluator_id = Column(String(100), nullable=False)
    evaluation_notes = Column(Text, nullable=True)
    
    # Timestamps
    evaluated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_outcome_eval_verdict", "verdict"),
    )


# =============================================================
# EXPORTS
# =============================================================

__all__ = [
    "ReviewStatus",
    "ReviewTriggerType",
    "DecisionType",
    "ConfidenceLevel",
    "OutcomeVerdict",
    "ReviewEvent",
    "HumanDecision",
    "ParameterChange",
    "Annotation",
    "OutcomeEvaluation",
]
