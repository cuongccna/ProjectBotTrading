"""
Strategy Engine Module.

============================================================
INSTITUTIONAL-GRADE CRYPTO TRADING SYSTEM
Strategy Engine - Hypothesis Generator
============================================================

PURPOSE
-------
Generate trade intent proposals based on market structure, volume flow,
and sentiment analysis. This module acts as a hypothesis generator,
NOT a decision maker.

DESIGN PRINCIPLES
-----------------
1. Capital-Agnostic: No dollar amounts, no position sizing
2. Deterministic: Rule-based logic, no ML, no adaptive behavior
3. Quality Over Quantity: Fewer, higher-confidence intents preferred
4. Explicit Outputs: Always returns TradeIntent OR NoTradeResult

SIGNAL CATEGORIES
-----------------
Three independent signal categories combine to generate intents:

1. Market Structure (PRIMARY)
   - Trend direction and strength
   - Support/resistance context
   - Breakout detection
   - Price action patterns

2. Volume Flow (PRIMARY)
   - Directional volume bias
   - Absorption patterns
   - Exhaustion detection
   - Volume expansion/contraction

3. Sentiment (MODIFIER ONLY)
   - Can STRENGTHEN or WEAKEN confidence
   - Can DELAY intent generation
   - NEVER creates intent by itself

ALIGNMENT RULES
---------------
A trade intent may ONLY be generated when:
1. Market Structure and Volume Flow signals ALIGN directionally
2. Both primary signals meet minimum strength threshold
3. Environmental risk is NOT CRITICAL
4. Sufficient data is available for all signals

============================================================
USAGE EXAMPLE
============================================================

```python
from strategy_engine import (
    StrategyEngine,
    StrategyInput,
    MarketStructureInput,
    VolumeFlowInput,
    SentimentInput,
    EnvironmentalContext,
    get_default_config,
)

# Create engine with configuration
config = get_default_config()
engine = StrategyEngine(config)

# Prepare input data
market_structure = MarketStructureInput(
    trend_strength_1h=0.65,
    trend_direction_1h="BULLISH",
    trend_strength_4h=0.55,
    trend_direction_4h="BULLISH",
    # ... additional fields
)

volume_flow = VolumeFlowInput(
    volume_ratio=1.5,
    buy_volume_dominance=0.62,
    volume_delta=0.35,
    # ... additional fields
)

sentiment = SentimentInput(
    sentiment_score=0.55,
    fear_greed_index=58,
    # ... additional fields
)

environment = EnvironmentalContext(
    risk_level="MODERATE",
    risk_score=0.45,
    is_trading_allowed=True,
)

# Build strategy input
strategy_input = StrategyInput(
    symbol="BTC/USDT",
    exchange="binance",
    timeframe="1h",
    market_structure=market_structure,
    volume_flow=volume_flow,
    sentiment=sentiment,
    environment=environment,
)

# Evaluate and get output
output = engine.evaluate(strategy_input)

if output.has_intent:
    intent = output.trade_intent
    print(f"Intent: {intent.direction.value} with {intent.confidence.name} confidence")
    print(f"Reason: {intent.reason_code.value}")
else:
    no_trade = output.no_trade
    print(f"No Trade: {no_trade.reason.value}")
    print(f"Explanation: {no_trade.explanation}")
```

============================================================
COMPONENTS
============================================================

Types (types.py)
----------------
- TradeDirection: LONG, SHORT, NEUTRAL
- ConfidenceLevel: LOW, MEDIUM, HIGH
- SignalStrength: NONE, WEAK, MODERATE, STRONG
- TradeIntent: Generated intent with all context
- NoTradeResult: Explicit rejection with reason
- StrategyEngineOutput: Unified output container

Configuration (config.py)
-------------------------
- MarketStructureConfig: Trend and breakout thresholds
- VolumeFlowConfig: Volume and delta thresholds
- SentimentConfig: Sentiment modifier rules
- SignalCombinationConfig: Alignment and weight rules
- Presets: get_default_config(), get_conservative_config()

Signal Generators (signals/)
----------------------------
- MarketStructureSignalGenerator: Trend and structure analysis
- VolumeFlowSignalGenerator: Volume and flow analysis
- SentimentModifierGenerator: Sentiment modifier (not signal)

Engine (engine.py)
------------------
- StrategyEngine: Main orchestrator

Persistence (models.py, repository.py)
--------------------------------------
- TradeIntentRecord: ORM model for intents
- NoTradeRecord: ORM model for rejections
- StrategyEvaluation: Unified evaluation record
- StrategyEngineRepository: Database operations

============================================================
"""

# ============================================================
# TYPE EXPORTS
# ============================================================

from .types import (
    # Direction and Levels
    TradeDirection,
    ConfidenceLevel,
    SignalStrength,
    
    # Outcome tracking
    SignalOutcome,
    
    # Regimes
    MarketRegime,
    VolatilityRegime,
    
    # Status and Reasons
    IntentStatus,
    NoTradeReason,
    StrategyReasonCode,
    
    # Signal types (NEW)
    SignalType,
    SignalTier,
    StrategySignal,
    SignalBundle,
    
    # Input Types
    MarketStructureInput,
    VolumeFlowInput,
    SentimentInput,
    EnvironmentalContext,
    StrategyInput,
    
    # Output Types
    SignalOutput,
    SentimentModifierOutput,
    MarketContextSnapshot,
    TradeIntent,
    NoTradeResult,
    StrategyEngineOutput,
    
    # Errors
    StrategyEngineError,
    InsufficientDataError,
    SignalGenerationError,
)

# ============================================================
# CONFIGURATION EXPORTS
# ============================================================

from .config import (
    # Individual Configs
    MarketStructureConfig,
    VolumeFlowConfig,
    SentimentConfig,
    SignalCombinationConfig,
    IntentLifecycleConfig,
    
    # Master Config
    StrategyEngineConfig,
    
    # Presets
    get_default_config,
    get_conservative_config,
    get_aggressive_config,
)

# ============================================================
# SIGNAL GENERATOR EXPORTS
# ============================================================

from .signals import (
    BaseSignalGenerator,
    MarketStructureSignalGenerator,
    VolumeFlowSignalGenerator,
    SentimentModifierGenerator,
)

# ============================================================
# ENGINE EXPORTS
# ============================================================

from .engine import (
    StrategyEngine,
    format_intent_summary,
)

# ============================================================
# MODEL EXPORTS
# ============================================================

from .models import (
    TradeIntentRecord,
    NoTradeRecord,
    StrategyEvaluation,
)

# ============================================================
# REPOSITORY EXPORTS
# ============================================================

from .repository import (
    StrategyEngineRepository,
)

# ============================================================
# OUTCOME TRACKER EXPORTS
# ============================================================

from .outcome_tracker import (
    OutcomeEvaluationConfig,
    evaluate_pending_signals,
    get_outcome_stats,
    get_signals_by_outcome,
    get_accuracy_by_tier,
)


# ============================================================
# ALL EXPORTS
# ============================================================

__all__ = [
    # Types
    "TradeDirection",
    "ConfidenceLevel",
    "SignalStrength",
    "SignalOutcome",
    "MarketRegime",
    "VolatilityRegime",
    "IntentStatus",
    "NoTradeReason",
    "StrategyReasonCode",
    # Signal types (NEW)
    "SignalType",
    "SignalTier",
    "StrategySignal",
    "SignalBundle",
    # Input types
    "MarketStructureInput",
    "VolumeFlowInput",
    "SentimentInput",
    "EnvironmentalContext",
    "StrategyInput",
    "SignalOutput",
    "SentimentModifierOutput",
    "MarketContextSnapshot",
    "TradeIntent",
    "NoTradeResult",
    "StrategyEngineOutput",
    "StrategyEngineError",
    "InsufficientDataError",
    "SignalGenerationError",
    
    # Config
    "MarketStructureConfig",
    "VolumeFlowConfig",
    "SentimentConfig",
    "SignalCombinationConfig",
    "IntentLifecycleConfig",
    "StrategyEngineConfig",
    "get_default_config",
    "get_conservative_config",
    "get_aggressive_config",
    
    # Signals
    "BaseSignalGenerator",
    "MarketStructureSignalGenerator",
    "VolumeFlowSignalGenerator",
    "SentimentModifierGenerator",
    
    # Engine
    "StrategyEngine",
    "format_intent_summary",
    
    # Models
    "TradeIntentRecord",
    "NoTradeRecord",
    "StrategyEvaluation",
    
    # Repository
    "StrategyEngineRepository",
    
    # Outcome Tracker
    "OutcomeEvaluationConfig",
    "evaluate_pending_signals",
    "get_outcome_stats",
    "get_signals_by_outcome",
    "get_accuracy_by_tier",
]


# ============================================================
# MODULE VERSION
# ============================================================

__version__ = "1.0.0"
