"""
Strategy Engine - Configuration.

============================================================
PURPOSE
============================================================
Defines all configuration and thresholds for the Strategy Engine.

All thresholds are:
- Capital-agnostic (no dollar amounts)
- Deterministic (no probabilities)
- Documented with rationale

============================================================
CONFIGURATION PHILOSOPHY
============================================================
- Conservative defaults (fewer, higher-quality signals)
- Clear threshold documentation
- Immutable configurations

============================================================
"""

from dataclasses import dataclass, field
from typing import Dict, Any


# ============================================================
# MARKET STRUCTURE SIGNAL CONFIGURATION
# ============================================================


@dataclass(frozen=True)
class MarketStructureConfig:
    """
    Configuration for Market Structure signal generation.
    
    ============================================================
    THRESHOLDS
    ============================================================
    Trend direction thresholds determine when a trend is "clear":
    - Values are -1 to +1 from feature pipeline
    - Higher thresholds = stricter trend requirements
    
    ============================================================
    """
    
    # Trend direction thresholds (absolute value)
    # Trend is considered "clear" if direction >= threshold
    trend_clear_threshold: float = 0.3            # 0.3 = 30% directional bias
    trend_strong_threshold: float = 0.6           # 0.6 = 60% directional bias
    
    # Trend strength thresholds (0 to 1)
    trend_strength_weak: float = 0.3              # Below = no trend
    trend_strength_moderate: float = 0.5          # Clear trend
    trend_strength_strong: float = 0.7            # Strong trend
    
    # Breakout thresholds
    breakout_strength_weak: float = 0.3
    breakout_strength_moderate: float = 0.5
    breakout_strength_strong: float = 0.7
    
    # Support/resistance proximity (% distance)
    sr_near_threshold_pct: float = 1.0            # Within 1% = "near"
    sr_close_threshold_pct: float = 0.5           # Within 0.5% = "very close"
    
    # Moving average thresholds
    ma_slope_bullish_threshold: float = 0.001     # Positive slope
    ma_slope_bearish_threshold: float = -0.001    # Negative slope
    ma_slope_strong_threshold: float = 0.003      # Strong slope
    
    # Price vs MA thresholds (%)
    price_above_ma_bullish: float = 0.5           # 0.5% above MA = bullish
    price_below_ma_bearish: float = -0.5          # 0.5% below MA = bearish
    price_extended_threshold: float = 3.0         # 3% from MA = extended
    
    # Data freshness (seconds)
    max_data_age_seconds: float = 300.0           # 5 minutes
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trend_clear_threshold": self.trend_clear_threshold,
            "trend_strong_threshold": self.trend_strong_threshold,
            "trend_strength_weak": self.trend_strength_weak,
            "trend_strength_moderate": self.trend_strength_moderate,
            "trend_strength_strong": self.trend_strength_strong,
            "breakout_strength_weak": self.breakout_strength_weak,
            "breakout_strength_moderate": self.breakout_strength_moderate,
            "breakout_strength_strong": self.breakout_strength_strong,
            "sr_near_threshold_pct": self.sr_near_threshold_pct,
            "sr_close_threshold_pct": self.sr_close_threshold_pct,
            "max_data_age_seconds": self.max_data_age_seconds,
        }


# ============================================================
# VOLUME FLOW SIGNAL CONFIGURATION
# ============================================================


@dataclass(frozen=True)
class VolumeFlowConfig:
    """
    Configuration for Volume/Flow signal generation.
    
    ============================================================
    THRESHOLDS
    ============================================================
    Volume ratio thresholds determine "expansion" vs "contraction":
    - Ratio = current volume / average volume
    - Values > 1 = expansion, < 1 = contraction
    
    ============================================================
    """
    
    # Volume ratio thresholds (current / average)
    volume_contraction_threshold: float = 0.7     # Below = low volume
    volume_normal_min: float = 0.7                # Normal range min
    volume_normal_max: float = 1.3                # Normal range max
    volume_expansion_threshold: float = 1.3       # Above = high volume
    volume_spike_threshold: float = 2.0           # Above = volume spike
    
    # Directional volume thresholds
    buy_dominance_threshold: float = 0.55         # 55% buy = bullish
    sell_dominance_threshold: float = 0.55        # 55% sell = bearish
    strong_dominance_threshold: float = 0.65      # 65% = strong bias
    
    # Volume delta thresholds (-1 to +1)
    delta_bullish_threshold: float = 0.2          # Positive delta
    delta_bearish_threshold: float = -0.2         # Negative delta
    delta_strong_threshold: float = 0.4           # Strong delta
    
    # Absorption score thresholds (-1 to +1)
    absorption_threshold: float = 0.3             # Significant absorption
    absorption_strong_threshold: float = 0.6      # Strong absorption
    
    # Data freshness (seconds)
    max_data_age_seconds: float = 180.0           # 3 minutes
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "volume_contraction_threshold": self.volume_contraction_threshold,
            "volume_expansion_threshold": self.volume_expansion_threshold,
            "volume_spike_threshold": self.volume_spike_threshold,
            "buy_dominance_threshold": self.buy_dominance_threshold,
            "sell_dominance_threshold": self.sell_dominance_threshold,
            "strong_dominance_threshold": self.strong_dominance_threshold,
            "delta_bullish_threshold": self.delta_bullish_threshold,
            "delta_bearish_threshold": self.delta_bearish_threshold,
            "delta_strong_threshold": self.delta_strong_threshold,
            "absorption_threshold": self.absorption_threshold,
            "absorption_strong_threshold": self.absorption_strong_threshold,
            "max_data_age_seconds": self.max_data_age_seconds,
        }


# ============================================================
# SENTIMENT MODIFIER CONFIGURATION
# ============================================================


@dataclass(frozen=True)
class SentimentConfig:
    """
    Configuration for Sentiment modifier.
    
    ============================================================
    IMPORTANT
    ============================================================
    Sentiment is a MODIFIER only - it NEVER creates a signal.
    It can:
    - Strengthen conviction
    - Weaken conviction
    - Suggest delay
    
    ============================================================
    """
    
    # Sentiment score thresholds (-1 to +1)
    sentiment_positive_threshold: float = 0.2     # Above = positive
    sentiment_negative_threshold: float = -0.2    # Below = negative
    sentiment_strong_threshold: float = 0.5       # Strong sentiment
    
    # News shock impact
    news_shock_high_impact: float = 0.7           # High impact threshold
    news_shock_delay_threshold: float = 0.8       # Suggest delay
    
    # Divergence detection
    divergence_significant: bool = True           # Use divergence
    
    # Fear/greed thresholds (0 to 100)
    fear_threshold: float = 25.0                  # Below = fear
    greed_threshold: float = 75.0                 # Above = greed
    extreme_fear_threshold: float = 10.0          # Extreme fear
    extreme_greed_threshold: float = 90.0         # Extreme greed
    
    # Modifier magnitude
    strengthen_magnitude: float = 0.5             # How much to strengthen
    weaken_magnitude: float = 0.3                 # How much to weaken
    delay_magnitude: float = 0.8                  # Delay strength
    
    # Data freshness (seconds)
    max_data_age_seconds: float = 600.0           # 10 minutes
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sentiment_positive_threshold": self.sentiment_positive_threshold,
            "sentiment_negative_threshold": self.sentiment_negative_threshold,
            "sentiment_strong_threshold": self.sentiment_strong_threshold,
            "news_shock_high_impact": self.news_shock_high_impact,
            "news_shock_delay_threshold": self.news_shock_delay_threshold,
            "fear_threshold": self.fear_threshold,
            "greed_threshold": self.greed_threshold,
            "extreme_fear_threshold": self.extreme_fear_threshold,
            "extreme_greed_threshold": self.extreme_greed_threshold,
            "strengthen_magnitude": self.strengthen_magnitude,
            "weaken_magnitude": self.weaken_magnitude,
            "delay_magnitude": self.delay_magnitude,
            "max_data_age_seconds": self.max_data_age_seconds,
        }


# ============================================================
# SIGNAL COMBINATION CONFIGURATION
# ============================================================


@dataclass(frozen=True)
class SignalCombinationConfig:
    """
    Configuration for combining signals into trade intents.
    
    ============================================================
    COMBINATION RULES
    ============================================================
    1. Market structure + Volume must align
    2. Both must be at least WEAK strength
    3. Sentiment modifies but never creates
    4. Risk level CRITICAL blocks all intents
    
    ============================================================
    """
    
    # Minimum signal requirements
    min_structure_strength: int = 1               # At least WEAK
    min_volume_strength: int = 1                  # At least WEAK
    
    # Confidence calculation weights
    structure_weight: float = 0.5                 # 50% weight
    volume_weight: float = 0.4                    # 40% weight
    sentiment_weight: float = 0.1                 # 10% weight (modifier)
    
    # Confidence thresholds
    low_confidence_min: float = 0.0
    low_confidence_max: float = 0.4
    medium_confidence_min: float = 0.4
    medium_confidence_max: float = 0.7
    high_confidence_min: float = 0.7
    
    # Alignment requirements
    require_direction_alignment: bool = True       # Signals must agree
    allow_neutral_volume: bool = True              # Allow neutral volume with structure
    
    # Risk level constraints
    block_on_critical: bool = True                 # Block on CRITICAL risk
    reduce_confidence_on_high: bool = True         # Reduce on HIGH risk
    high_risk_confidence_reduction: float = 0.2    # Reduce by 20%
    
    # Sentiment constraints
    sentiment_can_strengthen: bool = True
    sentiment_can_weaken: bool = True
    sentiment_can_delay: bool = True
    max_sentiment_boost: float = 0.2              # Max 20% boost
    max_sentiment_reduction: float = 0.3          # Max 30% reduction
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_structure_strength": self.min_structure_strength,
            "min_volume_strength": self.min_volume_strength,
            "structure_weight": self.structure_weight,
            "volume_weight": self.volume_weight,
            "sentiment_weight": self.sentiment_weight,
            "low_confidence_max": self.low_confidence_max,
            "medium_confidence_max": self.medium_confidence_max,
            "high_confidence_min": self.high_confidence_min,
            "require_direction_alignment": self.require_direction_alignment,
            "block_on_critical": self.block_on_critical,
            "reduce_confidence_on_high": self.reduce_confidence_on_high,
        }


# ============================================================
# INTENT LIFECYCLE CONFIGURATION
# ============================================================


@dataclass(frozen=True)
class IntentLifecycleConfig:
    """
    Configuration for trade intent lifecycle.
    """
    
    # Expiration
    default_expiration_minutes: int = 60          # 1 hour (1 candle)
    max_expiration_minutes: int = 240             # 4 hours
    
    # Deduplication
    min_interval_between_intents_minutes: int = 5  # Minimum 5 min between intents
    
    # Logging
    log_all_evaluations: bool = True              # Log NO_TRADE too
    log_signal_details: bool = True               # Include raw signals
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "default_expiration_minutes": self.default_expiration_minutes,
            "max_expiration_minutes": self.max_expiration_minutes,
            "min_interval_between_intents_minutes": self.min_interval_between_intents_minutes,
            "log_all_evaluations": self.log_all_evaluations,
            "log_signal_details": self.log_signal_details,
        }


# ============================================================
# MASTER CONFIGURATION
# ============================================================


@dataclass(frozen=True)
class StrategyEngineConfig:
    """
    Master configuration for the Strategy Engine.
    """
    
    # Signal configurations
    market_structure: MarketStructureConfig = field(default_factory=MarketStructureConfig)
    volume_flow: VolumeFlowConfig = field(default_factory=VolumeFlowConfig)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)
    
    # Combination configuration
    combination: SignalCombinationConfig = field(default_factory=SignalCombinationConfig)
    
    # Lifecycle configuration
    lifecycle: IntentLifecycleConfig = field(default_factory=IntentLifecycleConfig)
    
    # Engine metadata
    engine_version: str = "1.0.0"
    primary_timeframe: str = "1H"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_structure": self.market_structure.to_dict(),
            "volume_flow": self.volume_flow.to_dict(),
            "sentiment": self.sentiment.to_dict(),
            "combination": self.combination.to_dict(),
            "lifecycle": self.lifecycle.to_dict(),
            "engine_version": self.engine_version,
            "primary_timeframe": self.primary_timeframe,
        }


# ============================================================
# PRESET CONFIGURATIONS
# ============================================================


def get_default_config() -> StrategyEngineConfig:
    """
    Return default Strategy Engine configuration.
    
    Conservative defaults suitable for production.
    """
    return StrategyEngineConfig()


def get_conservative_config() -> StrategyEngineConfig:
    """
    Return conservative configuration.
    
    Stricter thresholds = fewer, higher-quality signals.
    """
    return StrategyEngineConfig(
        market_structure=MarketStructureConfig(
            trend_clear_threshold=0.4,
            trend_strong_threshold=0.7,
            breakout_strength_moderate=0.6,
        ),
        volume_flow=VolumeFlowConfig(
            volume_expansion_threshold=1.5,
            buy_dominance_threshold=0.6,
            sell_dominance_threshold=0.6,
        ),
        combination=SignalCombinationConfig(
            min_structure_strength=2,  # Require MODERATE
            min_volume_strength=2,     # Require MODERATE
            high_confidence_min=0.8,
        ),
    )


def get_aggressive_config() -> StrategyEngineConfig:
    """
    Return aggressive configuration.
    
    Lower thresholds = more signals.
    Use with caution.
    """
    return StrategyEngineConfig(
        market_structure=MarketStructureConfig(
            trend_clear_threshold=0.2,
            trend_strong_threshold=0.5,
        ),
        volume_flow=VolumeFlowConfig(
            volume_expansion_threshold=1.2,
            buy_dominance_threshold=0.52,
            sell_dominance_threshold=0.52,
        ),
        combination=SignalCombinationConfig(
            low_confidence_max=0.3,
            medium_confidence_max=0.6,
            high_confidence_min=0.6,
        ),
    )
