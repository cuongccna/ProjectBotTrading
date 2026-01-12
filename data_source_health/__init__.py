"""
Data Source Health Scoring Module.

============================================================
INSTITUTIONAL-GRADE DATA QUALITY MANAGEMENT
============================================================

This module evaluates the reliability and operational health
of all external data sources in real time.

CORE PHILOSOPHY:
- Data quality > data quantity
- A trading system must distrust data by default
- No single data source is ever fully trusted
- Degraded data must automatically reduce system risk appetite

============================================================
HEALTH DIMENSIONS
============================================================

1. Availability  - API uptime, timeout frequency, retry success
2. Freshness     - Data delay, timestamp drift, stale detection
3. Consistency   - Value jumps, cross-source deviation, schema
4. Completeness  - Missing fields, partial records, empty responses
5. Error Rate    - HTTP errors, parsing failures, validation errors

============================================================
HEALTH STATES
============================================================

- HEALTHY  (score >= 85): Normal operation
- DEGRADED (65 <= score < 85): Reduce risk appetite
- CRITICAL (score < 65): Disable source, notify Risk Controller

============================================================
USAGE
============================================================

```python
from data_source_health import (
    HealthManager,
    HealthRegistry,
    HealthState,
)

# Initialize manager
manager = HealthManager()

# Register data source
manager.register_source("binance", source_type="market_data")

# Record metrics
manager.record_request("binance", latency_ms=150, success=True)
manager.record_data("binance", timestamp=now, fields_received=10)

# Get health score
health = manager.get_health("binance")
print(f"Score: {health.score}, State: {health.state}")

# Check if source is usable
if manager.is_source_healthy("binance"):
    # Use source normally
    pass
elif manager.is_source_degraded("binance"):
    # Reduce position sizing
    pass
else:
    # Source is CRITICAL - use fallback
    pass
```

============================================================
"""

from .models import (
    HealthState,
    HealthScore,
    DimensionScore,
    DimensionType,
    SourceHealthRecord,
    HealthTransition,
    SourceType,
)
from .config import (
    HealthConfig,
    DimensionWeights,
    HealthThresholds,
    get_config,
    set_config,
)
from .exceptions import (
    HealthScoringError,
    SourceNotFoundError,
    MetricRecordError,
    EvaluationError,
    ConfigurationError,
)
from .base import (
    BaseHealthScorer,
    MarketDataHealthScorer,
    OnChainHealthScorer,
    SentimentHealthScorer,
    NewsHealthScorer,
    HealthScorerFactory,
)
from .registry import HealthRegistry
from .manager import HealthManager, get_manager, set_manager
from .metrics import MetricsCollector, SourceMetrics
from .scorers import (
    AvailabilityScorer,
    FreshnessScorer,
    ConsistencyScorer,
    CompletenessScorer,
    ErrorRateScorer,
    DimensionScorerFactory,
)


__all__ = [
    # Models
    "HealthState",
    "HealthScore",
    "DimensionScore",
    "DimensionType",
    "SourceHealthRecord",
    "HealthTransition",
    "SourceType",
    # Config
    "HealthConfig",
    "DimensionWeights",
    "HealthThresholds",
    "get_config",
    "set_config",
    # Exceptions
    "HealthScoringError",
    "SourceNotFoundError",
    "MetricRecordError",
    "EvaluationError",
    "ConfigurationError",
    # Core
    "BaseHealthScorer",
    "MarketDataHealthScorer",
    "OnChainHealthScorer",
    "SentimentHealthScorer",
    "NewsHealthScorer",
    "HealthScorerFactory",
    "HealthRegistry",
    "HealthManager",
    "get_manager",
    "set_manager",
    # Metrics
    "MetricsCollector",
    "SourceMetrics",
    # Scorers
    "AvailabilityScorer",
    "FreshnessScorer",
    "ConsistencyScorer",
    "CompletenessScorer",
    "ErrorRateScorer",
    "DimensionScorerFactory",
]
