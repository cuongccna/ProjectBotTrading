"""
Smart Money Confidence Weighting Engine.

============================================================
INSTITUTIONAL-GRADE WHALE SIGNAL PROCESSING
============================================================

This module converts raw smart money/whale signals into 
usable risk context. It PREVENTS overreaction to whale activity.

CORE PRINCIPLE:
- Not all whales are equal
- One transaction is NOT information
- Confidence is built from consistency, attribution, and context
- Smart money modifies risk, never triggers trades

============================================================
RESPONSIBILITIES
============================================================

1. Assign confidence weights to each wallet
2. Evaluate reliability of observed activity
3. Filter out noise and misleading whale behavior
4. Produce a final Smart Money Confidence Score

============================================================
OUTPUT
============================================================

- smart_money_confidence_score (0-100)
- confidence_level (LOW / MEDIUM / HIGH)
- dominant_behavior (accumulation / distribution / neutral)
- explanation (human-readable)

============================================================
INTEGRATION
============================================================

- Consumes: Smart Money Tracking, Wallet Registry, Market Condition
- Produces: Feeds into Flow Scoring module
- Flow Scoring adjusts Risk Scoring Engine
- Cannot bypass Trade Guard or Risk Budget Manager

============================================================
USAGE
============================================================

```python
from smart_money_confidence import (
    ConfidenceEngine,
    ActivityRecord,
    ActivityType,
    EntityType,
    ConfidenceLevel,
)
from datetime import datetime

# Create engine
engine = ConfidenceEngine()

# Register known wallets
engine.register_wallet(
    address="0x742d35Cc6634C0532925a3b844Bc9e7595f9e17a",
    entity_type=EntityType.FUND,
    entity_name="Example Fund",
    verified=True,
)

# Create activity records
activities = [
    ActivityRecord(
        wallet_address="0x742d35Cc6634C0532925a3b844Bc9e7595f9e17a",
        activity_type=ActivityType.BUY,
        token="BTC",
        amount_usd=1_000_000,
        timestamp=datetime.utcnow(),
    ),
    # ... more activities
]

# Calculate confidence
result = engine.calculate_confidence(token="BTC", activities=activities)

print(f"Score: {result.score}")
print(f"Level: {result.level.value}")
print(f"Behavior: {result.dominant_behavior.value}")
print(f"Explanation: {result.explanation}")
```

============================================================
"""

from .models import (
    EntityType,
    ConfidenceLevel,
    BehaviorType,
    ActivityType,
    DataSource,
    WalletProfile,
    ActivityRecord,
    ClusterSignal,
    ConfidenceOutput,
    MarketContext,
)
from .config import (
    ConfidenceConfig,
    EntityWeights,
    NoiseFilterConfig,
    ClusterConfig,
    HistoricalAccuracyConfig,
    ContextAlignmentConfig,
    ConfidenceThresholds,
    get_default_config,
    load_config,
)
from .exceptions import (
    SmartMoneyConfidenceError,
    WalletNotFoundError,
    InsufficientDataError,
    InvalidActivityError,
    InvalidWalletError,
    ConfigurationError,
    CalculationError,
    NoiseFilterError,
    ClusterAnalysisError,
    DataSourceError,
    CacheError,
)
from .wallet_model import WalletConfidenceModel
from .noise_filter import NoiseFilter, NoiseResult, FilterStats
from .cluster_analyzer import ClusterAnalyzer
from .calculator import ConfidenceWeightCalculator, CalculationComponents
from .engine import ConfidenceEngine, create_engine, calculate_confidence


__all__ = [
    # Models
    "EntityType",
    "ConfidenceLevel",
    "BehaviorType",
    "ActivityType",
    "DataSource",
    "WalletProfile",
    "ActivityRecord",
    "ClusterSignal",
    "ConfidenceOutput",
    "MarketContext",
    # Config
    "ConfidenceConfig",
    "EntityWeights",
    "NoiseFilterConfig",
    "ClusterConfig",
    "HistoricalAccuracyConfig",
    "ContextAlignmentConfig",
    "ConfidenceThresholds",
    "get_default_config",
    "load_config",
    # Exceptions
    "SmartMoneyConfidenceError",
    "WalletNotFoundError",
    "InsufficientDataError",
    "InvalidActivityError",
    "InvalidWalletError",
    "ConfigurationError",
    "CalculationError",
    "NoiseFilterError",
    "ClusterAnalysisError",
    "DataSourceError",
    "CacheError",
    # Core Components
    "WalletConfidenceModel",
    "NoiseFilter",
    "NoiseResult",
    "FilterStats",
    "ClusterAnalyzer",
    "ConfidenceWeightCalculator",
    "CalculationComponents",
    "ConfidenceEngine",
    "create_engine",
    "calculate_confidence",
]

__version__ = "1.0.0"
