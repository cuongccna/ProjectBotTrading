"""
Parity Validation Package.

============================================================
LIVE vs BACKTEST PARITY VALIDATION
============================================================

PURPOSE:
This module validates that live trading behavior matches backtest behavior.
It detects behavioral drift, hidden assumptions, and protects capital
from false confidence.

KEY PRINCIPLE:
"Backtest is a hypothesis, not truth. Live behavior is the ground truth."

============================================================
VALIDATION DOMAINS
============================================================

1. DATA PARITY
   - OHLCV data consistency
   - Volume accuracy
   - Market snapshot alignment

2. FEATURE PARITY
   - Calculated features match
   - Indicator values consistent
   - Feature versions aligned

3. DECISION PARITY
   - Trade Guard decisions match
   - Entry permission logic consistent
   - Position sizing calculations match

4. EXECUTION PARITY
   - Order behavior consistent
   - Slippage within tolerance
   - Fill behavior matches

5. ACCOUNTING PARITY
   - Post-trade balances match
   - PnL calculations consistent
   - Fee accounting aligned

============================================================
VALIDATION MODES
============================================================

- SHADOW_MODE: Receive live data, run backtest logic, compare
- PAPER_TRADING: Paper trade live, replay backtest, compare
- LIVE_TRADING_OBSERVATION: Observe live trades, replay backtest

============================================================
DRIFT DETECTION
============================================================

Detects four types of drift:
1. PARAMETER_DRIFT - Config/threshold changes
2. BEHAVIOR_DRIFT - Decision pattern changes
3. EXECUTION_DRIFT - Fill/slippage changes
4. RISK_TOLERANCE_DRIFT - Risk acceptance changes

============================================================
STRICT PROHIBITIONS
============================================================

This module NEVER:
1. Modifies trading logic
2. Modifies backtest logic
3. Adjusts parameters automatically
4. Ignores mismatches silently

============================================================
USAGE
============================================================

```python
from parity_validation import (
    create_parity_validator,
    ValidationMode,
    ToleranceConfig,
)

# Create validator with explicit tolerances
validator = create_parity_validator(
    mode=ValidationMode.SHADOW_MODE,
    tolerance_config=ToleranceConfig.strict(),
    live_data_service=data_service,
    live_feature_service=feature_service,
    live_trade_guard=trade_guard,
    live_execution_engine=execution_engine,
    backtest_engine=backtest_engine,
)

# Validate a trading cycle
report = await validator.validate_cycle(
    symbol="BTCUSDT",
    cycle_id="cycle_123",
    timestamp=datetime.utcnow(),
    backtest_state=backtest_state,
)

if not report.overall_match:
    print(f"Parity failure: {report.failure_conditions}")
    print(f"Recommended action: {report.recommended_reaction}")
```

============================================================
"""

# Models
from .models import (
    # Enums
    ValidationMode,
    ParityDomain,
    DriftType,
    MismatchSeverity,
    MismatchCategory,
    FailureCondition,
    SystemReaction,
    # Tolerance Configuration
    ToleranceConfig,
    # Data Models
    OHLCVData,
    MarketSnapshot,
    FeatureSnapshot,
    DecisionSnapshot,
    ExecutionSnapshot,
    # Comparison Results
    FieldMismatch,
    ParityComparisonResult,
    CycleParityReport,
    # Drift Models
    DriftMetric,
    DriftReport,
    # Summary Models
    DailyParitySummary,
    # Audit
    ParityAuditRecord,
)

# Collectors
from .collectors import (
    BaseDataCollector,
    LiveDataCollector,
    BacktestDataCollector,
    SynchronizedCollector,
    create_live_collector,
    create_backtest_collector,
    create_synchronized_collector,
)

# Comparators
from .comparators import (
    BaseComparator,
    DataComparator,
    FeatureComparator,
    DecisionComparator,
    ExecutionComparator,
    AccountingComparator,
    create_comparators,
)

# Drift Detection
from .drift_detector import (
    DriftWindow,
    DriftDetector,
    ContinuousDriftMonitor,
    create_drift_detector,
    create_drift_monitor,
)

# Validator
from .validator import (
    ReactionHandler,
    ParityValidator,
    create_parity_validator,
)

# Reporter
from .reporter import (
    ReportFormatter,
    ReportRepository,
    ReportExporter,
    ParityReportGenerator,
    create_report_formatter,
    create_report_repository,
    create_report_exporter,
    create_report_generator,
)

# Notifications
from .notifications import (
    NotificationType,
    NotificationPriority,
    NotificationRateLimiter,
    TelegramNotifier,
    ParityNotificationManager,
    create_rate_limiter,
    create_telegram_notifier,
    create_notification_manager,
)


__all__ = [
    # Enums
    "ValidationMode",
    "ParityDomain",
    "DriftType",
    "MismatchSeverity",
    "MismatchCategory",
    "FailureCondition",
    "SystemReaction",
    # Tolerance
    "ToleranceConfig",
    # Data Models
    "OHLCVData",
    "MarketSnapshot",
    "FeatureSnapshot",
    "DecisionSnapshot",
    "ExecutionSnapshot",
    # Comparison Results
    "FieldMismatch",
    "ParityComparisonResult",
    "CycleParityReport",
    # Drift Models
    "DriftMetric",
    "DriftReport",
    # Summary
    "DailyParitySummary",
    # Audit
    "ParityAuditRecord",
    # Collectors
    "BaseDataCollector",
    "LiveDataCollector",
    "BacktestDataCollector",
    "SynchronizedCollector",
    "create_live_collector",
    "create_backtest_collector",
    "create_synchronized_collector",
    # Comparators
    "BaseComparator",
    "DataComparator",
    "FeatureComparator",
    "DecisionComparator",
    "ExecutionComparator",
    "AccountingComparator",
    "create_comparators",
    # Drift Detection
    "DriftWindow",
    "DriftDetector",
    "ContinuousDriftMonitor",
    "create_drift_detector",
    "create_drift_monitor",
    # Validator
    "ReactionHandler",
    "ParityValidator",
    "create_parity_validator",
    # Reporter
    "ReportFormatter",
    "ReportRepository",
    "ReportExporter",
    "ParityReportGenerator",
    "create_report_formatter",
    "create_report_repository",
    "create_report_exporter",
    "create_report_generator",
    # Notifications
    "NotificationType",
    "NotificationPriority",
    "NotificationRateLimiter",
    "TelegramNotifier",
    "ParityNotificationManager",
    "create_rate_limiter",
    "create_telegram_notifier",
    "create_notification_manager",
]


# Version
__version__ = "1.0.0"
