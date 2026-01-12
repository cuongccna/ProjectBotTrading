"""
Dashboard Database Models - Decision Trace.

============================================================
DECISION TRACE TABLES
============================================================

Tables for tracking trade decisions, reasons, and audit trail.
Every decision must be fully traceable.

Source: Trade Guard, Risk Scoring Engine, Strategy Engine
Update Frequency: On every decision
Retention: 1 year

============================================================
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict
from dataclasses import dataclass, field


class DecisionType(str, Enum):
    """Type of trading decision."""
    ALLOW = "allow"
    BLOCK = "block"
    REDUCE = "reduce"  # Allow with reduced size
    DEFER = "defer"    # Wait for better conditions


class BlockReason(str, Enum):
    """Reason for blocking a trade."""
    HIGH_RISK = "high_risk"
    TRADE_GUARD_RULE = "trade_guard_rule"
    POSITION_LIMIT = "position_limit"
    DRAWDOWN_LIMIT = "drawdown_limit"
    VOLATILITY_LIMIT = "volatility_limit"
    CORRELATION_LIMIT = "correlation_limit"
    LIQUIDITY_CONCERN = "liquidity_concern"
    DATA_STALE = "data_stale"
    SYSTEM_ISSUE = "system_issue"
    MANUAL_PAUSE = "manual_pause"


class TradeGuardRuleType(str, Enum):
    """Type of Trade Guard rule."""
    MAX_POSITION_SIZE = "max_position_size"
    MAX_DRAWDOWN = "max_drawdown"
    MAX_DAILY_LOSS = "max_daily_loss"
    MAX_CORRELATION = "max_correlation"
    MIN_LIQUIDITY = "min_liquidity"
    VOLATILITY_FILTER = "volatility_filter"
    TIME_FILTER = "time_filter"
    SENTIMENT_FILTER = "sentiment_filter"
    SMART_MONEY_FILTER = "smart_money_filter"
    CUSTOM = "custom"


@dataclass
class TradeDecision:
    """
    Individual trade decision record.
    
    Table: trade_decisions
    Primary Key: decision_id
    """
    decision_id: str
    timestamp: datetime
    
    # Request details
    asset: str
    direction: str  # long, short
    requested_size_usd: float
    strategy_id: str
    signal_id: Optional[str]
    
    # Decision outcome
    decision_type: DecisionType
    approved_size_usd: float
    size_reduction_pct: float  # 0 if no reduction
    
    # Reason
    primary_reason: str
    reason_codes: List[str] = field(default_factory=list)
    
    # Risk context at decision time
    risk_score_at_decision: float
    risk_level_at_decision: str
    position_capacity_at_decision: float
    
    # Trade Guard
    trade_guard_triggered: bool = False
    trade_guard_rule_ids: List[str] = field(default_factory=list)
    
    # Execution (if allowed)
    order_id: Optional[str] = None
    executed: bool = False
    
    # Source traceability
    source_module: str = "trade_decision_engine"
    retention_days: int = 365
    
    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp.isoformat(),
            "asset": self.asset,
            "direction": self.direction,
            "requested_size_usd": self.requested_size_usd,
            "strategy_id": self.strategy_id,
            "decision_type": self.decision_type.value,
            "approved_size_usd": self.approved_size_usd,
            "size_reduction_pct": round(self.size_reduction_pct, 1),
            "primary_reason": self.primary_reason,
            "reason_codes": self.reason_codes,
            "risk_score_at_decision": round(self.risk_score_at_decision, 2),
            "risk_level_at_decision": self.risk_level_at_decision,
            "trade_guard_triggered": self.trade_guard_triggered,
            "trade_guard_rule_ids": self.trade_guard_rule_ids,
            "order_id": self.order_id,
            "executed": self.executed,
        }


@dataclass
class TradeGuardIntervention:
    """
    Trade Guard intervention record.
    
    Table: trade_guard_interventions
    Primary Key: intervention_id
    """
    intervention_id: str
    timestamp: datetime
    
    # What was blocked/modified
    decision_id: str
    asset: str
    original_size_usd: float
    modified_size_usd: float
    
    # Rule details
    rule_id: str
    rule_type: TradeGuardRuleType
    rule_name: str
    
    # Threshold vs actual
    threshold_value: float
    actual_value: float
    
    # Impact
    action_taken: str  # blocked, reduced, deferred
    reduction_pct: float
    
    # Context
    explanation: str
    risk_score: float
    
    # Source traceability
    source_module: str = "trade_guard"
    retention_days: int = 365
    
    def to_dict(self) -> dict:
        return {
            "intervention_id": self.intervention_id,
            "timestamp": self.timestamp.isoformat(),
            "decision_id": self.decision_id,
            "asset": self.asset,
            "original_size_usd": self.original_size_usd,
            "modified_size_usd": self.modified_size_usd,
            "rule_id": self.rule_id,
            "rule_type": self.rule_type.value,
            "rule_name": self.rule_name,
            "threshold_value": self.threshold_value,
            "actual_value": round(self.actual_value, 4),
            "action_taken": self.action_taken,
            "reduction_pct": round(self.reduction_pct, 1),
            "explanation": self.explanation,
            "risk_score": round(self.risk_score, 2),
        }


@dataclass
class TradeGuardRule:
    """
    Trade Guard rule configuration.
    
    Table: trade_guard_rules
    Primary Key: rule_id
    """
    rule_id: str
    rule_type: TradeGuardRuleType
    rule_name: str
    description: str
    
    # Configuration
    is_enabled: bool
    threshold_value: float
    threshold_unit: str  # pct, usd, ratio
    
    # Scope
    applies_to_assets: List[str] = field(default_factory=list)  # Empty = all
    applies_to_strategies: List[str] = field(default_factory=list)
    
    # Action
    action_on_breach: str  # block, reduce, alert
    reduction_factor: float = 1.0  # For "reduce" action
    
    # Stats
    triggers_24h: int = 0
    triggers_7d: int = 0
    last_triggered: Optional[datetime] = None
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "trade_guard"


@dataclass
class DecisionAuditLog:
    """
    Detailed audit log for decisions.
    
    Table: decision_audit_log
    Primary Key: id
    """
    id: Optional[int]
    decision_id: str
    timestamp: datetime
    
    # Full context snapshot
    risk_components: Dict[str, float] = field(default_factory=dict)
    market_conditions: Dict[str, any] = field(default_factory=dict)
    position_state: Dict[str, any] = field(default_factory=dict)
    
    # Input parameters
    strategy_parameters: Dict[str, any] = field(default_factory=dict)
    signal_data: Dict[str, any] = field(default_factory=dict)
    
    # Calculation trace
    calculation_steps: List[Dict] = field(default_factory=list)
    
    # Source traceability
    source_module: str = "decision_audit"
    retention_days: int = 365


# =============================================================
# SQL TABLE DEFINITIONS
# =============================================================

TRADE_DECISIONS_TABLE = """
CREATE TABLE IF NOT EXISTS trade_decisions (
    decision_id VARCHAR(100) PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    asset VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    requested_size_usd FLOAT NOT NULL,
    strategy_id VARCHAR(100) NOT NULL,
    signal_id VARCHAR(100),
    decision_type VARCHAR(20) NOT NULL,
    approved_size_usd FLOAT DEFAULT 0,
    size_reduction_pct FLOAT DEFAULT 0,
    primary_reason TEXT,
    reason_codes JSONB,
    risk_score_at_decision FLOAT,
    risk_level_at_decision VARCHAR(20),
    position_capacity_at_decision FLOAT,
    trade_guard_triggered BOOLEAN DEFAULT false,
    trade_guard_rule_ids JSONB,
    order_id VARCHAR(100),
    executed BOOLEAN DEFAULT false,
    source_module VARCHAR(100) DEFAULT 'trade_decision_engine'
);

CREATE INDEX IF NOT EXISTS idx_decisions_time ON trade_decisions(timestamp);
CREATE INDEX IF NOT EXISTS idx_decisions_asset ON trade_decisions(asset);
CREATE INDEX IF NOT EXISTS idx_decisions_type ON trade_decisions(decision_type);
CREATE INDEX IF NOT EXISTS idx_decisions_strategy ON trade_decisions(strategy_id);
"""

TRADE_GUARD_INTERVENTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS trade_guard_interventions (
    intervention_id VARCHAR(100) PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    decision_id VARCHAR(100) NOT NULL,
    asset VARCHAR(20) NOT NULL,
    original_size_usd FLOAT NOT NULL,
    modified_size_usd FLOAT DEFAULT 0,
    rule_id VARCHAR(100) NOT NULL,
    rule_type VARCHAR(50) NOT NULL,
    rule_name VARCHAR(200),
    threshold_value FLOAT,
    actual_value FLOAT,
    action_taken VARCHAR(50),
    reduction_pct FLOAT DEFAULT 0,
    explanation TEXT,
    risk_score FLOAT,
    source_module VARCHAR(100) DEFAULT 'trade_guard',
    FOREIGN KEY (decision_id) REFERENCES trade_decisions(decision_id)
);

CREATE INDEX IF NOT EXISTS idx_interventions_time ON trade_guard_interventions(timestamp);
CREATE INDEX IF NOT EXISTS idx_interventions_rule ON trade_guard_interventions(rule_id);
CREATE INDEX IF NOT EXISTS idx_interventions_decision ON trade_guard_interventions(decision_id);
"""

TRADE_GUARD_RULES_TABLE = """
CREATE TABLE IF NOT EXISTS trade_guard_rules (
    rule_id VARCHAR(100) PRIMARY KEY,
    rule_type VARCHAR(50) NOT NULL,
    rule_name VARCHAR(200) NOT NULL,
    description TEXT,
    is_enabled BOOLEAN DEFAULT true,
    threshold_value FLOAT NOT NULL,
    threshold_unit VARCHAR(20),
    applies_to_assets JSONB,
    applies_to_strategies JSONB,
    action_on_breach VARCHAR(50) DEFAULT 'block',
    reduction_factor FLOAT DEFAULT 1.0,
    triggers_24h INTEGER DEFAULT 0,
    triggers_7d INTEGER DEFAULT 0,
    last_triggered TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'trade_guard'
);

CREATE INDEX IF NOT EXISTS idx_rules_type ON trade_guard_rules(rule_type);
CREATE INDEX IF NOT EXISTS idx_rules_enabled ON trade_guard_rules(is_enabled);
"""

DECISION_AUDIT_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS decision_audit_log (
    id SERIAL PRIMARY KEY,
    decision_id VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    risk_components JSONB,
    market_conditions JSONB,
    position_state JSONB,
    strategy_parameters JSONB,
    signal_data JSONB,
    calculation_steps JSONB,
    source_module VARCHAR(100) DEFAULT 'decision_audit',
    FOREIGN KEY (decision_id) REFERENCES trade_decisions(decision_id)
);

CREATE INDEX IF NOT EXISTS idx_audit_decision ON decision_audit_log(decision_id);
CREATE INDEX IF NOT EXISTS idx_audit_time ON decision_audit_log(timestamp);
"""

ALL_DECISION_TABLES = [
    TRADE_DECISIONS_TABLE,
    TRADE_GUARD_INTERVENTIONS_TABLE,
    TRADE_GUARD_RULES_TABLE,
    DECISION_AUDIT_LOG_TABLE,
]
