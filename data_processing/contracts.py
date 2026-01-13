"""
Internal Data Contracts for Processed Market State.

============================================================
PURPOSE
============================================================
Defines the canonical data structure for processed market state
that can be consumed by downstream modules:
- RiskScoringEngine
- StrategyEngine

============================================================
CONTRACT GUARANTEES
============================================================
- All fields have explicit types
- Enums for categorical values (trend_state, volatility_level)
- Immutable (frozen dataclass)
- Serializable to dict/JSON
- Convertible to database model

============================================================
USAGE
============================================================
>>> state = ProcessedMarketState(
...     symbol="BTC",
...     timeframe="1h",
...     trend_state=TrendState.UPTREND,
...     volatility_level=VolatilityLevel.NORMAL,
...     liquidity_score=0.85,
... )
>>> # Use in RiskScoringEngine
>>> risk_engine.score(build_risk_input(state))
>>> # Use in StrategyEngine
>>> strategy_engine.evaluate(build_strategy_input(state))

============================================================
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


# ============================================================
# ENUMERATIONS
# ============================================================


class TrendState(str, Enum):
    """
    Discrete trend classification.
    
    Used by StrategyEngine for directional bias.
    Used by RiskScoringEngine for market regime detection.
    """
    STRONG_UPTREND = "strong_uptrend"      # Clear bullish momentum
    UPTREND = "uptrend"                     # Bullish bias
    NEUTRAL = "neutral"                     # No clear direction
    DOWNTREND = "downtrend"                 # Bearish bias
    STRONG_DOWNTREND = "strong_downtrend"  # Clear bearish momentum
    RANGING = "ranging"                     # Sideways consolidation
    
    @property
    def is_bullish(self) -> bool:
        return self in (TrendState.STRONG_UPTREND, TrendState.UPTREND)
    
    @property
    def is_bearish(self) -> bool:
        return self in (TrendState.STRONG_DOWNTREND, TrendState.DOWNTREND)
    
    @property
    def is_neutral(self) -> bool:
        return self in (TrendState.NEUTRAL, TrendState.RANGING)
    
    @property
    def direction_score(self) -> float:
        """
        Numeric representation for calculations.
        Returns: -1.0 to +1.0
        """
        mapping = {
            TrendState.STRONG_UPTREND: 1.0,
            TrendState.UPTREND: 0.5,
            TrendState.NEUTRAL: 0.0,
            TrendState.RANGING: 0.0,
            TrendState.DOWNTREND: -0.5,
            TrendState.STRONG_DOWNTREND: -1.0,
        }
        return mapping.get(self, 0.0)


class VolatilityLevel(str, Enum):
    """
    Discrete volatility classification.
    
    Used by RiskScoringEngine for volatility risk dimension.
    Used by StrategyEngine for confidence adjustment.
    """
    VERY_LOW = "very_low"      # Unusually calm (percentile < 10)
    LOW = "low"                # Below average (percentile 10-30)
    NORMAL = "normal"          # Average conditions (percentile 30-70)
    HIGH = "high"              # Above average (percentile 70-90)
    EXTREME = "extreme"        # Dangerous (percentile > 90)
    
    @property
    def risk_multiplier(self) -> float:
        """
        Risk adjustment multiplier.
        Higher = more risky.
        """
        mapping = {
            VolatilityLevel.VERY_LOW: 0.7,
            VolatilityLevel.LOW: 0.85,
            VolatilityLevel.NORMAL: 1.0,
            VolatilityLevel.HIGH: 1.3,
            VolatilityLevel.EXTREME: 2.0,
        }
        return mapping.get(self, 1.0)
    
    @property
    def confidence_adjustment(self) -> float:
        """
        Confidence adjustment for strategy decisions.
        Extreme volatility reduces confidence.
        """
        mapping = {
            VolatilityLevel.VERY_LOW: 0.9,   # Slightly reduce (may break out)
            VolatilityLevel.LOW: 1.0,
            VolatilityLevel.NORMAL: 1.0,
            VolatilityLevel.HIGH: 0.85,
            VolatilityLevel.EXTREME: 0.6,
        }
        return mapping.get(self, 1.0)


class LiquidityGrade(str, Enum):
    """
    Discrete liquidity classification.
    
    Derived from liquidity_score for categorical use.
    """
    EXCELLENT = "excellent"    # score >= 0.9
    GOOD = "good"              # score >= 0.7
    ADEQUATE = "adequate"      # score >= 0.5
    POOR = "poor"              # score >= 0.3
    CRITICAL = "critical"      # score < 0.3
    
    @classmethod
    def from_score(cls, score: float) -> "LiquidityGrade":
        """Derive grade from numeric score."""
        if score >= 0.9:
            return cls.EXCELLENT
        elif score >= 0.7:
            return cls.GOOD
        elif score >= 0.5:
            return cls.ADEQUATE
        elif score >= 0.3:
            return cls.POOR
        else:
            return cls.CRITICAL
    
    @property
    def allows_trading(self) -> bool:
        """Check if liquidity is sufficient for trading."""
        return self in (LiquidityGrade.EXCELLENT, LiquidityGrade.GOOD, LiquidityGrade.ADEQUATE)


# ============================================================
# PRIMARY DATA CONTRACT
# ============================================================


@dataclass(frozen=True)
class ProcessedMarketState:
    """
    Canonical processed market state contract.
    
    ============================================================
    CONSUMERS
    ============================================================
    - RiskScoringEngine: Uses trend_state, volatility_level, 
      liquidity_score for environmental risk assessment
    - StrategyEngine: Uses trend_state for directional bias,
      volatility_level for confidence adjustment,
      liquidity_score for execution feasibility
    
    ============================================================
    PRODUCERS
    ============================================================
    - ProcessingPipelineModule: Computes from ProcessedMarketData
    
    ============================================================
    GUARANTEES
    ============================================================
    - symbol: Always present, uppercase (e.g., "BTC", "ETH")
    - timeframe: Always present (e.g., "1h", "4h", "24h")
    - trend_state: Always a valid TrendState enum
    - volatility_level: Always a valid VolatilityLevel enum
    - liquidity_score: Always 0.0 to 1.0
    
    ============================================================
    """
    
    # ---- Required Identification ----
    symbol: str                             # e.g., "BTC", "ETH"
    timeframe: str                          # e.g., "1h", "4h", "24h"
    
    # ---- Core State Fields ----
    trend_state: TrendState                 # Categorical trend classification
    volatility_level: VolatilityLevel       # Categorical volatility classification
    liquidity_score: float                  # 0.0 to 1.0 (higher = more liquid)
    
    # ---- Supporting Metrics (for transparency) ----
    current_price: Optional[float] = None
    price_change_pct: Optional[float] = None       # Return over timeframe
    volatility_raw: Optional[float] = None         # Raw volatility value
    volatility_percentile: Optional[float] = None  # 0-100 percentile
    volume_ratio: Optional[float] = None           # vs average
    spread_pct: Optional[float] = None             # Bid-ask spread
    
    # ---- Trend Details ----
    trend_strength: Optional[float] = None         # 0.0 to 1.0
    trend_duration_periods: Optional[int] = None   # How long in this trend
    
    # ---- Additional Context ----
    exchange: str = "binance"
    data_quality_score: Optional[float] = None     # 0.0 to 1.0
    
    # ---- Timestamps ----
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    calculated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    
    # ---- Tracking ----
    state_id: UUID = field(default_factory=uuid4)
    source_module: str = "ProcessingPipelineModule"
    version: str = "1.0.0"
    
    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------
    
    def __post_init__(self) -> None:
        """Validate invariants after initialization."""
        # Validate liquidity_score range
        if not 0.0 <= self.liquidity_score <= 1.0:
            raise ValueError(
                f"liquidity_score must be 0.0-1.0, got {self.liquidity_score}"
            )
        
        # Validate symbol format
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        
        # Validate timeframe
        valid_timeframes = {"1m", "5m", "15m", "30m", "1h", "4h", "24h", "1d", "7d"}
        if self.timeframe not in valid_timeframes:
            raise ValueError(
                f"Invalid timeframe '{self.timeframe}', must be one of {valid_timeframes}"
            )
    
    # --------------------------------------------------------
    # DERIVED PROPERTIES
    # --------------------------------------------------------
    
    @property
    def liquidity_grade(self) -> LiquidityGrade:
        """Categorical liquidity classification."""
        return LiquidityGrade.from_score(self.liquidity_score)
    
    @property
    def is_tradeable(self) -> bool:
        """
        Quick check if conditions allow trading.
        
        Returns False if:
        - Extreme volatility
        - Critical liquidity
        """
        return (
            self.volatility_level != VolatilityLevel.EXTREME and
            self.liquidity_grade.allows_trading
        )
    
    @property
    def risk_score_hint(self) -> float:
        """
        Preliminary risk indicator (0-100).
        
        Used as input hint for RiskScoringEngine.
        NOT a replacement for full risk scoring.
        """
        base = 50.0
        
        # Volatility contribution
        vol_contribution = {
            VolatilityLevel.VERY_LOW: -10,
            VolatilityLevel.LOW: -5,
            VolatilityLevel.NORMAL: 0,
            VolatilityLevel.HIGH: 15,
            VolatilityLevel.EXTREME: 35,
        }.get(self.volatility_level, 0)
        
        # Liquidity contribution
        liq_contribution = (1.0 - self.liquidity_score) * 20
        
        return min(100.0, max(0.0, base + vol_contribution + liq_contribution))
    
    @property
    def trend_direction_numeric(self) -> float:
        """Numeric trend direction for calculations (-1.0 to +1.0)."""
        return self.trend_state.direction_score
    
    # --------------------------------------------------------
    # SERIALIZATION
    # --------------------------------------------------------
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for persistence or API response.
        
        Handles enum conversion and datetime serialization.
        """
        result = asdict(self)
        
        # Convert enums to strings
        result["trend_state"] = self.trend_state.value
        result["volatility_level"] = self.volatility_level.value
        result["liquidity_grade"] = self.liquidity_grade.value
        
        # Convert UUID to string
        result["state_id"] = str(self.state_id)
        
        # Convert datetimes to ISO strings
        for key in ["window_start", "window_end", "calculated_at"]:
            if result.get(key) is not None:
                result[key] = result[key].isoformat()
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcessedMarketState":
        """
        Reconstruct from dictionary.
        
        Handles enum and datetime parsing.
        """
        from datetime import datetime
        from uuid import UUID
        
        # Parse enums
        if "trend_state" in data and isinstance(data["trend_state"], str):
            data["trend_state"] = TrendState(data["trend_state"])
        if "volatility_level" in data and isinstance(data["volatility_level"], str):
            data["volatility_level"] = VolatilityLevel(data["volatility_level"])
        
        # Remove derived fields that aren't constructor args
        data.pop("liquidity_grade", None)
        
        # Parse UUID
        if "state_id" in data and isinstance(data["state_id"], str):
            data["state_id"] = UUID(data["state_id"])
        
        # Parse datetimes
        for key in ["window_start", "window_end", "calculated_at"]:
            if key in data and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key])
        
        return cls(**data)
    
    # --------------------------------------------------------
    # BUILDER METHODS FOR DOWNSTREAM CONSUMERS
    # --------------------------------------------------------
    
    def to_risk_market_input(self) -> Dict[str, Any]:
        """
        Convert to format expected by RiskScoringEngine.MarketDataInput.
        
        Returns dict that can be used to construct MarketDataInput.
        """
        return {
            "btc_price_change_24h_pct": self.price_change_pct if self.symbol == "BTC" else None,
            "eth_price_change_24h_pct": self.price_change_pct if self.symbol == "ETH" else None,
            "data_timestamp": self.calculated_at,
        }
    
    def to_strategy_market_structure(self) -> Dict[str, Any]:
        """
        Convert to format expected by StrategyEngine.MarketStructureInput.
        
        Returns dict that can be used to construct MarketStructureInput.
        """
        # Map trend state to direction
        if self.trend_state in (TrendState.STRONG_UPTREND, TrendState.UPTREND):
            direction = 1.0 if self.trend_state == TrendState.STRONG_UPTREND else 0.5
        elif self.trend_state in (TrendState.STRONG_DOWNTREND, TrendState.DOWNTREND):
            direction = -1.0 if self.trend_state == TrendState.STRONG_DOWNTREND else -0.5
        else:
            direction = 0.0
        
        return {
            "current_price": self.current_price,
            "trend_direction_1h": direction if self.timeframe == "1h" else None,
            "trend_direction_4h": direction if self.timeframe == "4h" else None,
            "trend_strength": self.trend_strength,
            "data_timestamp": self.calculated_at,
        }


# ============================================================
# COLLECTION FOR MULTIPLE SYMBOLS
# ============================================================


@dataclass
class ProcessedMarketStateBundle:
    """
    Bundle of processed states for multiple symbols.
    
    Used when evaluating portfolio-level decisions.
    """
    
    states: Dict[str, ProcessedMarketState] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def add(self, state: ProcessedMarketState) -> None:
        """Add a state to the bundle."""
        key = f"{state.symbol}_{state.timeframe}"
        self.states[key] = state
    
    def get(self, symbol: str, timeframe: str) -> Optional[ProcessedMarketState]:
        """Retrieve a specific state."""
        key = f"{symbol}_{timeframe}"
        return self.states.get(key)
    
    def get_all_for_symbol(self, symbol: str) -> Dict[str, ProcessedMarketState]:
        """Get all timeframes for a symbol."""
        return {
            k: v for k, v in self.states.items()
            if k.startswith(f"{symbol}_")
        }
    
    @property
    def symbols(self) -> set:
        """Get all unique symbols in bundle."""
        return {s.symbol for s in self.states.values()}
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize bundle to dict."""
        return {
            "states": {k: v.to_dict() for k, v in self.states.items()},
            "timestamp": self.timestamp.isoformat(),
            "symbol_count": len(self.symbols),
        }


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    # Enums
    "TrendState",
    "VolatilityLevel",
    "LiquidityGrade",
    # Main contract
    "ProcessedMarketState",
    "ProcessedMarketStateBundle",
]
