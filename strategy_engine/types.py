"""
Strategy Engine - Type Definitions.

============================================================
PURPOSE
============================================================
Defines all types, enums, and data contracts for the Strategy Engine.

============================================================
DESIGN PRINCIPLES
============================================================
- Capital-agnostic (no dollar amounts or position sizes)
- Deterministic (no probability distributions)
- Immutable data structures (frozen dataclasses)
- Clear separation between signals and intents

============================================================
CORE CONCEPTS
============================================================
1. SIGNAL: Raw directional indication from a single source
2. TRADE INTENT: Combined hypothesis when signals align
3. NO_TRADE: Explicit decision to not propose anything

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Optional, Dict, Any, List


# ============================================================
# ENUMS
# ============================================================


class TradeDirection(Enum):
    """
    Direction of proposed trade.
    
    LONG: Expecting price to rise
    SHORT: Expecting price to fall
    NEUTRAL: No directional bias
    """
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class ConfidenceLevel(IntEnum):
    """
    Confidence in the trade intent.
    
    Used by downstream Risk Budget Manager to calibrate exposure.
    NOT a probability - purely categorical.
    
    LOW: Signals align but weak confluence
    MEDIUM: Clear signal alignment
    HIGH: Strong confluence with multiple confirmations
    """
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    
    @classmethod
    def from_score(cls, score: float) -> "ConfidenceLevel":
        """
        Convert a numeric score to confidence level.
        
        Args:
            score: Score from 0.0 to 1.0
        
        Returns:
            ConfidenceLevel
        """
        if score >= 0.7:
            return cls.HIGH
        elif score >= 0.4:
            return cls.MEDIUM
        return cls.LOW


class SignalStrength(IntEnum):
    """
    Strength of an individual signal.
    
    NONE: No signal present
    WEAK: Signal present but marginal
    MODERATE: Clear signal
    STRONG: Strong, unambiguous signal
    """
    NONE = 0
    WEAK = 1
    MODERATE = 2
    STRONG = 3


class MarketRegime(Enum):
    """
    Current market structure regime.
    
    TRENDING_UP: Clear uptrend with higher highs/lows
    TRENDING_DOWN: Clear downtrend with lower highs/lows
    RANGING: Sideways, no clear direction
    BREAKOUT: Transitioning, potential new trend
    VOLATILE: High volatility, unclear structure
    """
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    BREAKOUT = "BREAKOUT"
    VOLATILE = "VOLATILE"


class VolatilityRegime(Enum):
    """
    Current volatility environment.
    """
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class IntentStatus(Enum):
    """
    Status of a trade intent.
    
    GENERATED: Intent created, pending consumption
    CONSUMED: Intent consumed by Risk Budget Manager
    EXPIRED: Intent expired without action
    REJECTED: Intent rejected (e.g., by risk controls)
    """
    GENERATED = "GENERATED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class NoTradeReason(Enum):
    """
    Reasons for emitting NO_TRADE.
    
    Provides clarity for logging and debugging.
    """
    SIGNALS_CONFLICTING = "SIGNALS_CONFLICTING"
    SIGNALS_TOO_WEAK = "SIGNALS_TOO_WEAK"
    RISK_LEVEL_CRITICAL = "RISK_LEVEL_CRITICAL"
    MISSING_INPUT_DATA = "MISSING_INPUT_DATA"
    MARKET_STRUCTURE_UNCLEAR = "MARKET_STRUCTURE_UNCLEAR"
    VOLUME_INSUFFICIENT = "VOLUME_INSUFFICIENT"
    SENTIMENT_OVERRIDE = "SENTIMENT_OVERRIDE"
    VOLATILITY_EXTREME = "VOLATILITY_EXTREME"
    NO_ALIGNMENT = "NO_ALIGNMENT"


# ============================================================
# STRATEGY REASON CODES
# ============================================================


class StrategyReasonCode(Enum):
    """
    Explicit reason codes for trade intents.
    
    Each code documents WHY the intent was generated.
    """
    # Trend-following entries
    TREND_CONTINUATION_LONG = "TREND_CONTINUATION_LONG"
    TREND_CONTINUATION_SHORT = "TREND_CONTINUATION_SHORT"
    
    # Breakout entries
    BREAKOUT_LONG = "BREAKOUT_LONG"
    BREAKOUT_SHORT = "BREAKOUT_SHORT"
    
    # Reversal entries
    REVERSAL_LONG = "REVERSAL_LONG"
    REVERSAL_SHORT = "REVERSAL_SHORT"
    
    # Range entries
    RANGE_SUPPORT_LONG = "RANGE_SUPPORT_LONG"
    RANGE_RESISTANCE_SHORT = "RANGE_RESISTANCE_SHORT"
    
    # Volume-confirmed entries
    VOLUME_BREAKOUT_LONG = "VOLUME_BREAKOUT_LONG"
    VOLUME_BREAKOUT_SHORT = "VOLUME_BREAKOUT_SHORT"


# ============================================================
# INPUT DATA CONTRACTS
# ============================================================


@dataclass(frozen=True)
class MarketStructureInput:
    """
    Input data for market structure analysis.
    
    ============================================================
    FIELDS
    ============================================================
    Trend indicators from feature pipeline.
    Price action patterns.
    Support/resistance context.
    
    ============================================================
    """
    # Current price context
    current_price: float
    
    # Trend indicators
    trend_direction_1h: Optional[float] = None   # -1 to +1
    trend_direction_4h: Optional[float] = None   # -1 to +1
    trend_strength: Optional[float] = None       # 0 to 1
    
    # Price action
    higher_high: Optional[bool] = None
    higher_low: Optional[bool] = None
    lower_high: Optional[bool] = None
    lower_low: Optional[bool] = None
    
    # Support/resistance
    near_support: Optional[bool] = None
    near_resistance: Optional[bool] = None
    support_distance_pct: Optional[float] = None
    resistance_distance_pct: Optional[float] = None
    
    # Breakout detection
    breakout_detected: Optional[bool] = None
    breakout_direction: Optional[str] = None     # "UP", "DOWN", None
    breakout_strength: Optional[float] = None    # 0 to 1
    
    # Moving average context
    price_vs_ma_20: Optional[float] = None       # % above/below
    price_vs_ma_50: Optional[float] = None       # % above/below
    ma_20_slope: Optional[float] = None          # Normalized slope
    ma_50_slope: Optional[float] = None          # Normalized slope
    
    # Data freshness
    data_timestamp: Optional[datetime] = None
    
    @property
    def has_minimum_data(self) -> bool:
        """Check if minimum required data is present."""
        return (
            self.current_price is not None and
            self.current_price > 0 and
            (self.trend_direction_1h is not None or 
             self.trend_direction_4h is not None)
        )


@dataclass(frozen=True)
class VolumeFlowInput:
    """
    Input data for volume and flow analysis.
    
    ============================================================
    FIELDS
    ============================================================
    Volume metrics from feature pipeline.
    Order flow indicators.
    
    ============================================================
    """
    # Relative volume
    volume_ratio_vs_average: Optional[float] = None  # Current / 20-period avg
    volume_ratio_1h: Optional[float] = None          # Last 1h / avg 1h
    
    # Directional volume
    buy_volume_ratio: Optional[float] = None         # Buy / Total (0 to 1)
    sell_volume_ratio: Optional[float] = None        # Sell / Total (0 to 1)
    volume_delta: Optional[float] = None             # Buy - Sell (normalized)
    
    # Volume patterns
    volume_expanding: Optional[bool] = None
    volume_contracting: Optional[bool] = None
    volume_spike_detected: Optional[bool] = None
    
    # Absorption / Exhaustion (simplified)
    absorption_score: Optional[float] = None         # -1 (sell absorb) to +1 (buy absorb)
    exhaustion_detected: Optional[bool] = None
    exhaustion_direction: Optional[str] = None       # "BULLISH", "BEARISH", None
    
    # Data freshness
    data_timestamp: Optional[datetime] = None
    
    @property
    def has_minimum_data(self) -> bool:
        """Check if minimum required data is present."""
        return (
            self.volume_ratio_vs_average is not None and
            self.volume_ratio_vs_average > 0
        )


@dataclass(frozen=True)
class SentimentInput:
    """
    Input data for sentiment and news analysis.
    
    ============================================================
    FIELDS
    ============================================================
    Sentiment scores from feature pipeline.
    News event indicators.
    
    Note: Sentiment is a MODIFIER only, never a driver.
    
    ============================================================
    """
    # Overall sentiment
    sentiment_score: Optional[float] = None          # -1 to +1
    sentiment_regime: Optional[str] = None           # "POSITIVE", "NEGATIVE", "NEUTRAL"
    
    # News indicators
    news_shock_detected: Optional[bool] = None
    news_shock_direction: Optional[str] = None       # "POSITIVE", "NEGATIVE", None
    news_impact_score: Optional[float] = None        # 0 to 1
    
    # Divergence detection
    sentiment_price_divergence: Optional[bool] = None
    divergence_type: Optional[str] = None            # "BULLISH", "BEARISH", None
    
    # Social metrics (aggregated)
    social_volume_change: Optional[float] = None     # % change vs baseline
    social_sentiment_change: Optional[float] = None  # Delta from baseline
    
    # Fear/greed context
    fear_greed_index: Optional[float] = None         # 0 to 100
    fear_greed_regime: Optional[str] = None          # "FEAR", "NEUTRAL", "GREED"
    
    # Data freshness
    data_timestamp: Optional[datetime] = None
    
    @property
    def has_minimum_data(self) -> bool:
        """Check if minimum required data is present."""
        return self.sentiment_score is not None


@dataclass(frozen=True)
class EnvironmentalContext:
    """
    Environmental context from Risk Scoring Engine.
    
    ============================================================
    FIELDS
    ============================================================
    Risk levels from Risk Scoring Engine.
    Market regime classification.
    
    ============================================================
    """
    # Risk scoring output
    risk_level: str                                  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    risk_score_total: int                            # 0 to 8
    
    # Individual risk dimensions
    market_risk_state: Optional[str] = None          # "SAFE", "WARNING", "DANGEROUS"
    liquidity_risk_state: Optional[str] = None
    volatility_risk_state: Optional[str] = None
    system_integrity_risk_state: Optional[str] = None
    
    # Market regime
    market_regime: Optional[str] = None              # "TRENDING_UP", etc.
    volatility_regime: Optional[str] = None          # "LOW", "NORMAL", etc.
    
    # Timestamp
    assessment_timestamp: Optional[datetime] = None
    
    @property
    def is_critical(self) -> bool:
        """Check if risk level is CRITICAL."""
        return self.risk_level == "CRITICAL"
    
    @property
    def allows_trading(self) -> bool:
        """Check if environmental conditions allow trading."""
        return self.risk_level in ("LOW", "MEDIUM", "HIGH")


@dataclass(frozen=True)
class StrategyInput:
    """
    Complete input bundle for the Strategy Engine.
    
    Aggregates all input data for a single evaluation cycle.
    """
    # Signal inputs
    market_structure: MarketStructureInput
    volume_flow: VolumeFlowInput
    sentiment: SentimentInput
    
    # Environmental context
    environment: EnvironmentalContext
    
    # Timeframe context
    primary_timeframe: str = "1H"
    
    # Evaluation timestamp
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Symbol being evaluated
    symbol: str = "BTC/USDT"
    exchange: str = "binance"
    
    @property
    def has_minimum_data(self) -> bool:
        """Check if minimum required data for evaluation is present."""
        return (
            self.market_structure.has_minimum_data and
            self.volume_flow.has_minimum_data and
            self.environment is not None
        )


# ============================================================
# SIGNAL OUTPUT CONTRACTS
# ============================================================


@dataclass(frozen=True)
class SignalOutput:
    """
    Output from an individual signal generator.
    
    ============================================================
    FIELDS
    ============================================================
    - direction: Directional bias
    - strength: Signal strength (0-3)
    - reason: Human-readable explanation
    - metrics: Raw metrics used
    
    ============================================================
    """
    direction: TradeDirection
    strength: SignalStrength
    reason: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_actionable(self) -> bool:
        """Check if signal is strong enough to consider."""
        return (
            self.direction != TradeDirection.NEUTRAL and
            self.strength >= SignalStrength.WEAK
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "direction": self.direction.value,
            "strength": self.strength.value,
            "reason": self.reason,
            "metrics": self.metrics,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass(frozen=True)
class SentimentModifierOutput:
    """
    Output from sentiment analysis (modifier, not driver).
    
    ============================================================
    EFFECT
    ============================================================
    - STRENGTHEN: Increase confidence
    - WEAKEN: Decrease confidence
    - DELAY: Suggest waiting
    - NEUTRAL: No modification
    
    ============================================================
    """
    effect: str                                      # "STRENGTHEN", "WEAKEN", "DELAY", "NEUTRAL"
    magnitude: float                                 # 0 to 1
    reason: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "effect": self.effect,
            "magnitude": self.magnitude,
            "reason": self.reason,
            "metrics": self.metrics,
        }


# ============================================================
# MARKET CONTEXT SNAPSHOT
# ============================================================


@dataclass(frozen=True)
class MarketContextSnapshot:
    """
    Snapshot of market context at intent generation time.
    
    Provides full context for auditing and analysis.
    """
    # Price context
    price: float
    price_change_1h_pct: Optional[float] = None
    price_change_24h_pct: Optional[float] = None
    
    # Market regime
    market_regime: Optional[str] = None
    volatility_regime: Optional[str] = None
    
    # Trend context
    trend_direction: Optional[str] = None            # "UP", "DOWN", "NEUTRAL"
    trend_strength: Optional[float] = None
    
    # Volume context
    volume_ratio: Optional[float] = None
    volume_bias: Optional[str] = None                # "BUY", "SELL", "NEUTRAL"
    
    # Sentiment context
    sentiment_regime: Optional[str] = None
    sentiment_score: Optional[float] = None
    
    # Risk context
    risk_level: Optional[str] = None
    risk_score: Optional[int] = None
    
    # Timestamp
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "price": self.price,
            "price_change_1h_pct": self.price_change_1h_pct,
            "price_change_24h_pct": self.price_change_24h_pct,
            "market_regime": self.market_regime,
            "volatility_regime": self.volatility_regime,
            "trend_direction": self.trend_direction,
            "trend_strength": self.trend_strength,
            "volume_ratio": self.volume_ratio,
            "volume_bias": self.volume_bias,
            "sentiment_regime": self.sentiment_regime,
            "sentiment_score": self.sentiment_score,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# ============================================================
# TRADE INTENT OUTPUT
# ============================================================


@dataclass(frozen=True)
class TradeIntent:
    """
    Trade intent proposal from the Strategy Engine.
    
    ============================================================
    WHAT IT IS
    ============================================================
    A hypothesis about potential trade direction.
    Consumed by Risk Budget Manager for sizing.
    NOT an execution decision.
    
    ============================================================
    WHAT IT IS NOT
    ============================================================
    - NOT an order
    - NOT a trade decision
    - NOT sized or priced
    
    ============================================================
    """
    # Direction and confidence
    direction: TradeDirection
    confidence: ConfidenceLevel
    
    # Strategy identification
    reason_code: StrategyReasonCode
    
    # Context
    market_context: MarketContextSnapshot
    
    # Symbol and timing
    symbol: str
    exchange: str
    timeframe: str
    timestamp: datetime
    
    # Signal breakdown (for transparency)
    market_structure_signal: SignalOutput
    volume_flow_signal: SignalOutput
    sentiment_modifier: SentimentModifierOutput
    
    # Status tracking
    status: IntentStatus = IntentStatus.GENERATED
    
    # Expiration
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "direction": self.direction.value,
            "confidence": self.confidence.value,
            "confidence_name": self.confidence.name,
            "reason_code": self.reason_code.value,
            "market_context": self.market_context.to_dict(),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "market_structure_signal": self.market_structure_signal.to_dict(),
            "volume_flow_signal": self.volume_flow_signal.to_dict(),
            "sentiment_modifier": self.sentiment_modifier.to_dict(),
            "status": self.status.value,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass(frozen=True)
class NoTradeResult:
    """
    Explicit NO_TRADE result from the Strategy Engine.
    
    ============================================================
    PURPOSE
    ============================================================
    Documents why no trade intent was generated.
    Provides full transparency for logging and analysis.
    
    ============================================================
    """
    reason: NoTradeReason
    explanation: str
    
    # Context at evaluation time
    market_context: Optional[MarketContextSnapshot] = None
    
    # Signal states (if available)
    market_structure_signal: Optional[SignalOutput] = None
    volume_flow_signal: Optional[SignalOutput] = None
    sentiment_modifier: Optional[SentimentModifierOutput] = None
    
    # Symbol and timing
    symbol: str = "BTC/USDT"
    exchange: str = "binance"
    timeframe: str = "1H"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "reason": self.reason.value,
            "explanation": self.explanation,
            "market_context": self.market_context.to_dict() if self.market_context else None,
            "market_structure_signal": self.market_structure_signal.to_dict() if self.market_structure_signal else None,
            "volume_flow_signal": self.volume_flow_signal.to_dict() if self.volume_flow_signal else None,
            "sentiment_modifier": self.sentiment_modifier.to_dict() if self.sentiment_modifier else None,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
        }


# ============================================================
# STRATEGY ENGINE OUTPUT
# ============================================================


@dataclass(frozen=True)
class StrategyEngineOutput:
    """
    Complete output from a Strategy Engine evaluation.
    
    Contains either a TradeIntent or a NoTradeResult.
    """
    # One of these will be set
    trade_intent: Optional[TradeIntent] = None
    no_trade: Optional[NoTradeResult] = None
    
    # Metadata
    evaluation_id: str = field(default_factory=lambda: "")
    engine_version: str = "1.0.0"
    evaluation_duration_ms: Optional[float] = None
    
    @property
    def has_intent(self) -> bool:
        """Check if a trade intent was generated."""
        return self.trade_intent is not None
    
    @property
    def direction(self) -> Optional[TradeDirection]:
        """Get direction if intent exists."""
        return self.trade_intent.direction if self.trade_intent else None
    
    @property
    def confidence(self) -> Optional[ConfidenceLevel]:
        """Get confidence if intent exists."""
        return self.trade_intent.confidence if self.trade_intent else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "has_intent": self.has_intent,
            "trade_intent": self.trade_intent.to_dict() if self.trade_intent else None,
            "no_trade": self.no_trade.to_dict() if self.no_trade else None,
            "evaluation_id": self.evaluation_id,
            "engine_version": self.engine_version,
            "evaluation_duration_ms": self.evaluation_duration_ms,
        }


# ============================================================
# EXCEPTIONS
# ============================================================


class StrategyEngineError(Exception):
    """Base exception for strategy engine errors."""
    pass


class InsufficientDataError(StrategyEngineError):
    """Raised when input data is insufficient for evaluation."""
    pass


class SignalGenerationError(StrategyEngineError):
    """Raised when signal generation fails."""
    pass


class InvalidInputError(StrategyEngineError):
    """Raised when input data is invalid."""
    pass
