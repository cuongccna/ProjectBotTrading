"""
Pydantic Schemas for Human-in-the-Loop Review System.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


# =============================================================
# ENUMS
# =============================================================

class ReviewStatusEnum(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    EXPIRED = "expired"


class TriggerTypeEnum(str, Enum):
    TRADE_GUARD_BLOCK = "trade_guard_block"
    DRAWDOWN_THRESHOLD = "drawdown_threshold"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    RISK_OSCILLATION = "risk_oscillation"
    DATA_SOURCE_DEGRADED = "data_source_degraded"
    SIGNAL_CONTRADICTION = "signal_contradiction"
    BACKTEST_DIVERGENCE = "backtest_divergence"
    MANUAL_REQUEST = "manual_request"


class DecisionTypeEnum(str, Enum):
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


class ConfidenceLevelEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PriorityEnum(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# =============================================================
# CONTEXT SCHEMAS (Embedded in Review Event)
# =============================================================

class MarketContextSchema(BaseModel):
    """Market state at trigger time."""
    token: str
    price: float
    price_change_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    regime: Optional[str] = None
    volatility_percentile: Optional[float] = None
    trend_direction: Optional[str] = None


class RiskStateSnapshot(BaseModel):
    """Risk state at trigger time."""
    global_risk_score: float
    risk_level: str
    trading_allowed: bool
    sentiment_risk: Optional[float] = None
    flow_risk: Optional[float] = None
    smart_money_risk: Optional[float] = None
    market_condition_risk: Optional[float] = None
    weights: Optional[Dict[str, float]] = None


class SentimentSummary(BaseModel):
    """Sentiment summary at trigger time."""
    overall_sentiment: float
    sentiment_label: str
    news_count_24h: int
    dominant_tokens: Optional[List[str]] = None


class FlowContext(BaseModel):
    """On-chain flow context."""
    exchange_flow_score: Optional[float] = None
    whale_activity_score: Optional[float] = None
    net_flow_direction: Optional[str] = None


class SmartMoneyContext(BaseModel):
    """Smart money signals."""
    smart_money_score: Optional[float] = None
    smart_money_signal: Optional[str] = None
    confidence: Optional[float] = None


class StrategyDecision(BaseModel):
    """What the strategy wanted to do."""
    intended_action: str  # buy, sell, hold
    token: str
    size: Optional[float] = None
    reason: Optional[str] = None


class TradeGuardRuleInfo(BaseModel):
    """Trade Guard rule information."""
    rule_id: str
    rule_name: str
    triggered: bool
    reason: Optional[str] = None


class ExecutionOutcome(BaseModel):
    """Execution result if trade happened."""
    executed: bool
    order_id: Optional[str] = None
    executed_size: Optional[float] = None
    executed_price: Optional[float] = None
    slippage_percent: Optional[float] = None
    pnl: Optional[float] = None


# =============================================================
# REVIEW EVENT SCHEMAS
# =============================================================

class ReviewEventCreate(BaseModel):
    """Schema for creating a new review event."""
    correlation_id: str
    trigger_type: TriggerTypeEnum
    trigger_reason: str
    trigger_value: Optional[float] = None
    trigger_threshold: Optional[float] = None
    priority: PriorityEnum = PriorityEnum.NORMAL
    
    # Context
    market_context: Optional[Dict[str, Any]] = None
    risk_state_snapshot: Optional[Dict[str, Any]] = None
    sentiment_summary: Optional[Dict[str, Any]] = None
    flow_context: Optional[Dict[str, Any]] = None
    smart_money_context: Optional[Dict[str, Any]] = None
    strategy_decision: Optional[Dict[str, Any]] = None
    trade_guard_rules: Optional[List[Dict[str, Any]]] = None
    execution_outcome: Optional[Dict[str, Any]] = None
    
    # Related IDs
    entry_decision_id: Optional[int] = None
    risk_state_id: Optional[int] = None


class ReviewEventResponse(BaseModel):
    """Schema for review event response."""
    id: int
    correlation_id: str
    trigger_type: str
    trigger_reason: str
    trigger_value: Optional[float] = None
    trigger_threshold: Optional[float] = None
    status: str
    priority: str
    
    # Context
    market_context: Optional[Dict[str, Any]] = None
    risk_state_snapshot: Optional[Dict[str, Any]] = None
    sentiment_summary: Optional[Dict[str, Any]] = None
    flow_context: Optional[Dict[str, Any]] = None
    smart_money_context: Optional[Dict[str, Any]] = None
    strategy_decision: Optional[Dict[str, Any]] = None
    trade_guard_rules: Optional[List[Dict[str, Any]]] = None
    execution_outcome: Optional[Dict[str, Any]] = None
    
    # Timestamps
    created_at: datetime
    expires_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    # Assignment
    assigned_to: Optional[str] = None
    telegram_notified: bool = False
    
    class Config:
        from_attributes = True


class ReviewEventSummary(BaseModel):
    """Summary view for listing review events."""
    id: int
    trigger_type: str
    trigger_reason: str
    status: str
    priority: str
    created_at: datetime
    token: Optional[str] = None  # extracted from context


# =============================================================
# HUMAN DECISION SCHEMAS
# =============================================================

class HumanDecisionCreate(BaseModel):
    """Schema for creating a human decision."""
    review_event_id: int
    decision_type: DecisionTypeEnum
    reason_code: str
    confidence_level: ConfidenceLevelEnum = ConfidenceLevelEnum.MEDIUM
    comment: Optional[str] = None
    
    # Parameter change (if applicable)
    parameter_before: Optional[Dict[str, Any]] = None
    parameter_after: Optional[Dict[str, Any]] = None


class HumanDecisionResponse(BaseModel):
    """Schema for human decision response."""
    id: int
    review_event_id: int
    decision_type: str
    reason_code: str
    confidence_level: str
    comment: Optional[str] = None
    user_id: str
    user_role: str
    parameter_before: Optional[Dict[str, Any]] = None
    parameter_after: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# =============================================================
# PARAMETER CHANGE SCHEMAS
# =============================================================

class ParameterBounds(BaseModel):
    """Allowed bounds for a parameter."""
    min_value: Optional[float] = None
    max_value: Optional[float] = None


class ParameterChangeCreate(BaseModel):
    """Schema for creating a parameter change."""
    parameter_category: str
    parameter_name: str
    parameter_path: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Any
    change_reason: Optional[str] = None


class ParameterChangeResponse(BaseModel):
    """Schema for parameter change response."""
    id: int
    parameter_category: str
    parameter_name: str
    parameter_path: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Any
    applied_at: datetime
    changed_by: str
    is_active: bool
    
    class Config:
        from_attributes = True


# =============================================================
# ANNOTATION SCHEMAS
# =============================================================

class AnnotationCreate(BaseModel):
    """Schema for creating an annotation."""
    review_event_id: Optional[int] = None
    correlation_id: Optional[str] = None
    annotation_type: str  # note, tag, warning, insight
    tag: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None


class AnnotationResponse(BaseModel):
    """Schema for annotation response."""
    id: int
    review_event_id: Optional[int] = None
    correlation_id: Optional[str] = None
    annotation_type: str
    tag: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    created_by: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# =============================================================
# OUTCOME EVALUATION SCHEMAS
# =============================================================

class OutcomeEvaluationCreate(BaseModel):
    """Schema for creating an outcome evaluation."""
    review_event_id: int
    human_decision_id: Optional[int] = None
    verdict: str  # correct, incorrect, inconclusive, false_positive, false_negative
    pnl_impact: Optional[float] = None
    risk_impact: Optional[float] = None
    actual_outcome: Optional[Dict[str, Any]] = None
    expected_outcome: Optional[Dict[str, Any]] = None
    evaluation_window_hours: Optional[float] = None
    evaluation_notes: Optional[str] = None


class OutcomeEvaluationResponse(BaseModel):
    """Schema for outcome evaluation response."""
    id: int
    review_event_id: int
    human_decision_id: Optional[int] = None
    verdict: str
    pnl_impact: Optional[float] = None
    risk_impact: Optional[float] = None
    actual_outcome: Optional[Dict[str, Any]] = None
    expected_outcome: Optional[Dict[str, Any]] = None
    evaluator_id: str
    evaluated_at: datetime
    
    class Config:
        from_attributes = True


# =============================================================
# DASHBOARD RESPONSE SCHEMAS
# =============================================================

class ReviewQueueResponse(BaseModel):
    """Response for the review queue."""
    events: List[ReviewEventResponse]
    total_pending: int = 0
    total_in_progress: int = 0
    total_resolved: int = 0
    avg_resolution_time_hours: Optional[float] = None


class ReviewDetailResponse(BaseModel):
    """Detailed review event with all context."""
    success: bool
    event: ReviewEventResponse
    decisions: List[HumanDecisionResponse]
    annotations: List[AnnotationResponse]


# =============================================================
# ALLOWED ACTIONS CONFIG
# =============================================================

ALLOWED_ACTIONS = {
    DecisionTypeEnum.ADJUST_RISK_THRESHOLD: {
        "description": "Adjust risk thresholds within predefined bounds",
        "requires_approval": False,
        "parameters": ["threshold_name", "new_value"],
        "bounds": {
            "max_drawdown": {"min": 0.05, "max": 0.20},
            "max_position_size": {"min": 0.01, "max": 0.10},
            "risk_score_threshold": {"min": 30, "max": 80},
        }
    },
    DecisionTypeEnum.PAUSE_STRATEGY: {
        "description": "Temporarily pause a strategy",
        "requires_approval": False,
        "parameters": ["strategy_name", "pause_duration_hours"],
        "bounds": {"pause_duration_hours": {"min": 1, "max": 168}}  # max 1 week
    },
    DecisionTypeEnum.REDUCE_POSITION_LIMIT: {
        "description": "Reduce position size limits",
        "requires_approval": False,
        "parameters": ["token", "new_limit_percent"],
        "bounds": {"new_limit_percent": {"min": 0.5, "max": 5.0}}
    },
    DecisionTypeEnum.ENABLE_DATA_SOURCE: {
        "description": "Enable a data source",
        "requires_approval": True,
        "parameters": ["source_name"],
    },
    DecisionTypeEnum.DISABLE_DATA_SOURCE: {
        "description": "Disable a data source",
        "requires_approval": False,
        "parameters": ["source_name"],
    },
    DecisionTypeEnum.MARK_ANOMALY: {
        "description": "Mark an event as anomaly for learning",
        "requires_approval": False,
        "parameters": ["anomaly_type"],
    },
    DecisionTypeEnum.APPROVE_ROLLBACK: {
        "description": "Approve parameter rollback to previous value",
        "requires_approval": True,
        "parameters": ["parameter_change_id"],
    },
    DecisionTypeEnum.ADD_ANNOTATION: {
        "description": "Add annotation or tag",
        "requires_approval": False,
        "parameters": ["annotation_type", "content"],
    },
    DecisionTypeEnum.ACKNOWLEDGE_ONLY: {
        "description": "Acknowledge event without action",
        "requires_approval": False,
        "parameters": [],
    },
    DecisionTypeEnum.ESCALATE: {
        "description": "Escalate to higher authority",
        "requires_approval": False,
        "parameters": ["escalation_reason"],
    },
}

# Forbidden actions (for documentation)
FORBIDDEN_ACTIONS = [
    "Place trades",
    "Force execution",
    "Override Trade Guard directly",
    "Modify historical data",
    "Delete review events",
    "Change user roles",
]
