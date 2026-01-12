"""
Dashboard Database Models - Risk State.

============================================================
RISK STATE TABLES
============================================================

Tables for tracking risk levels, components, and aggregation.
This is the CRITICAL panel for explaining trade decisions.

Source: Risk Scoring Engine, Trade Guard
Update Frequency: Every 10 seconds
Retention: 90 days

============================================================
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict
from dataclasses import dataclass, field


class RiskLevel(str, Enum):
    """Global risk level."""
    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"
    HIGH = "high"
    EXTREME = "extreme"


class TradingState(str, Enum):
    """Current trading state."""
    ACTIVE = "active"
    REDUCED = "reduced"  # Reduced position sizing
    PAUSED = "paused"    # No new trades
    BLOCKED = "blocked"  # All trading stopped


@dataclass
class GlobalRiskState:
    """
    Current global risk state.
    
    Table: global_risk_state
    Primary Key: id (single row, updated in place)
    """
    id: int = 1  # Single row
    
    # Overall risk
    risk_level: RiskLevel = RiskLevel.MODERATE
    risk_score: float = 50.0  # 0-100
    trading_state: TradingState = TradingState.ACTIVE
    
    # Trading capacity
    position_capacity_pct: float = 100.0  # 0-100, how much we can trade
    max_position_size_pct: float = 100.0  # Max single position size
    
    # State explanation
    primary_risk_factor: str = ""
    state_reason: str = ""
    
    # Timestamps
    last_calculation: datetime = field(default_factory=datetime.utcnow)
    state_changed_at: Optional[datetime] = None
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "risk_scoring_engine"
    update_frequency_seconds: int = 10
    
    def to_dict(self) -> dict:
        return {
            "risk_level": self.risk_level.value,
            "risk_score": round(self.risk_score, 2),
            "trading_state": self.trading_state.value,
            "position_capacity_pct": round(self.position_capacity_pct, 1),
            "max_position_size_pct": round(self.max_position_size_pct, 1),
            "primary_risk_factor": self.primary_risk_factor,
            "state_reason": self.state_reason,
            "last_calculation": self.last_calculation.isoformat(),
            "state_changed_at": self.state_changed_at.isoformat() if self.state_changed_at else None,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class RiskComponent:
    """
    Individual risk component.
    
    Table: risk_components
    Primary Key: component_name
    """
    component_name: str  # sentiment, flow, smart_money, market_condition, volatility
    
    # Raw values
    raw_value: float
    raw_min: float
    raw_max: float
    
    # Normalized values (0-100)
    normalized_value: float
    
    # Contribution to final score
    weight: float  # 0-1
    weighted_contribution: float
    
    # Status
    is_healthy: bool
    data_age_seconds: int
    last_update: datetime
    
    # Explanation
    interpretation: str  # e.g., "Bearish sentiment detected"
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "risk_scoring_engine"
    update_frequency_seconds: int = 10
    
    def to_dict(self) -> dict:
        return {
            "component_name": self.component_name,
            "raw_value": round(self.raw_value, 4),
            "raw_min": self.raw_min,
            "raw_max": self.raw_max,
            "normalized_value": round(self.normalized_value, 2),
            "weight": round(self.weight, 3),
            "weighted_contribution": round(self.weighted_contribution, 2),
            "is_healthy": self.is_healthy,
            "data_age_seconds": self.data_age_seconds,
            "last_update": self.last_update.isoformat(),
            "interpretation": self.interpretation,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class RiskHistory:
    """
    Risk score history.
    
    Table: risk_history
    Primary Key: id
    """
    id: Optional[int]
    timestamp: datetime
    risk_score: float
    risk_level: RiskLevel
    trading_state: TradingState
    
    # Component snapshots
    sentiment_score: float
    flow_score: float
    smart_money_score: float
    market_condition_score: float
    volatility_score: float
    
    # What triggered change (if any)
    trigger: Optional[str] = None
    
    # Source traceability
    source_module: str = "risk_scoring_engine"
    retention_days: int = 90


@dataclass
class MarketConditionState:
    """
    Current market condition assessment.
    
    Table: market_condition_state
    Primary Key: asset
    """
    asset: str  # BTC, ETH, or GLOBAL
    
    # Trend
    trend_direction: str  # up, down, sideways
    trend_strength: float  # 0-100
    
    # Volatility
    volatility_percentile: float  # 0-100
    volatility_regime: str  # low, normal, high, extreme
    
    # Momentum
    momentum_score: float  # -100 to 100
    
    # Support/Resistance
    near_support: bool
    near_resistance: bool
    distance_to_support_pct: float
    distance_to_resistance_pct: float
    
    # Market structure
    market_phase: str  # accumulation, markup, distribution, markdown
    
    last_price: float
    price_change_1h: float
    price_change_24h: float
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "market_analyzer"
    update_frequency_seconds: int = 30
    
    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "trend_direction": self.trend_direction,
            "trend_strength": round(self.trend_strength, 1),
            "volatility_percentile": round(self.volatility_percentile, 1),
            "volatility_regime": self.volatility_regime,
            "momentum_score": round(self.momentum_score, 1),
            "near_support": self.near_support,
            "near_resistance": self.near_resistance,
            "market_phase": self.market_phase,
            "last_price": self.last_price,
            "price_change_1h": round(self.price_change_1h, 2),
            "price_change_24h": round(self.price_change_24h, 2),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class SentimentState:
    """
    Current sentiment state.
    
    Table: sentiment_state
    Primary Key: asset
    """
    asset: str
    
    # Aggregate sentiment
    aggregate_score: float  # -100 to 100
    sentiment_label: str  # very_bearish, bearish, neutral, bullish, very_bullish
    
    # By source
    news_sentiment: float
    social_sentiment: float
    onchain_sentiment: float
    
    # Metrics
    news_volume_1h: int
    social_volume_1h: int
    sentiment_volatility: float  # How much sentiment is changing
    
    # Confidence
    confidence_score: float  # 0-100
    sample_size: int
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "sentiment_aggregator"
    update_frequency_seconds: int = 60
    
    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "aggregate_score": round(self.aggregate_score, 2),
            "sentiment_label": self.sentiment_label,
            "news_sentiment": round(self.news_sentiment, 2),
            "social_sentiment": round(self.social_sentiment, 2),
            "onchain_sentiment": round(self.onchain_sentiment, 2),
            "news_volume_1h": self.news_volume_1h,
            "social_volume_1h": self.social_volume_1h,
            "sentiment_volatility": round(self.sentiment_volatility, 2),
            "confidence_score": round(self.confidence_score, 1),
            "sample_size": self.sample_size,
            "updated_at": self.updated_at.isoformat(),
        }


# =============================================================
# SQL TABLE DEFINITIONS
# =============================================================

GLOBAL_RISK_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS global_risk_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    risk_level VARCHAR(20) NOT NULL DEFAULT 'moderate',
    risk_score FLOAT DEFAULT 50,
    trading_state VARCHAR(20) NOT NULL DEFAULT 'active',
    position_capacity_pct FLOAT DEFAULT 100,
    max_position_size_pct FLOAT DEFAULT 100,
    primary_risk_factor VARCHAR(200),
    state_reason TEXT,
    last_calculation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    state_changed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'risk_scoring_engine',
    update_frequency_seconds INTEGER DEFAULT 10,
    CONSTRAINT single_row CHECK (id = 1)
);
"""

RISK_COMPONENTS_TABLE = """
CREATE TABLE IF NOT EXISTS risk_components (
    component_name VARCHAR(100) PRIMARY KEY,
    raw_value FLOAT NOT NULL,
    raw_min FLOAT DEFAULT 0,
    raw_max FLOAT DEFAULT 100,
    normalized_value FLOAT NOT NULL,
    weight FLOAT DEFAULT 0,
    weighted_contribution FLOAT DEFAULT 0,
    is_healthy BOOLEAN DEFAULT true,
    data_age_seconds INTEGER DEFAULT 0,
    last_update TIMESTAMP NOT NULL,
    interpretation TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'risk_scoring_engine',
    update_frequency_seconds INTEGER DEFAULT 10
);
"""

RISK_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS risk_history (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    risk_score FLOAT NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    trading_state VARCHAR(20) NOT NULL,
    sentiment_score FLOAT,
    flow_score FLOAT,
    smart_money_score FLOAT,
    market_condition_score FLOAT,
    volatility_score FLOAT,
    trigger TEXT,
    source_module VARCHAR(100) DEFAULT 'risk_scoring_engine'
);

CREATE INDEX IF NOT EXISTS idx_risk_history_time ON risk_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_risk_history_level ON risk_history(risk_level);
"""

MARKET_CONDITION_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS market_condition_state (
    asset VARCHAR(20) PRIMARY KEY,
    trend_direction VARCHAR(20),
    trend_strength FLOAT DEFAULT 0,
    volatility_percentile FLOAT DEFAULT 50,
    volatility_regime VARCHAR(20) DEFAULT 'normal',
    momentum_score FLOAT DEFAULT 0,
    near_support BOOLEAN DEFAULT false,
    near_resistance BOOLEAN DEFAULT false,
    distance_to_support_pct FLOAT DEFAULT 0,
    distance_to_resistance_pct FLOAT DEFAULT 0,
    market_phase VARCHAR(50),
    last_price FLOAT,
    price_change_1h FLOAT DEFAULT 0,
    price_change_24h FLOAT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'market_analyzer',
    update_frequency_seconds INTEGER DEFAULT 30
);
"""

SENTIMENT_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS sentiment_state (
    asset VARCHAR(20) PRIMARY KEY,
    aggregate_score FLOAT DEFAULT 0,
    sentiment_label VARCHAR(20) DEFAULT 'neutral',
    news_sentiment FLOAT DEFAULT 0,
    social_sentiment FLOAT DEFAULT 0,
    onchain_sentiment FLOAT DEFAULT 0,
    news_volume_1h INTEGER DEFAULT 0,
    social_volume_1h INTEGER DEFAULT 0,
    sentiment_volatility FLOAT DEFAULT 0,
    confidence_score FLOAT DEFAULT 0,
    sample_size INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'sentiment_aggregator',
    update_frequency_seconds INTEGER DEFAULT 60
);
"""

ALL_RISK_TABLES = [
    GLOBAL_RISK_STATE_TABLE,
    RISK_COMPONENTS_TABLE,
    RISK_HISTORY_TABLE,
    MARKET_CONDITION_STATE_TABLE,
    SENTIMENT_STATE_TABLE,
]
