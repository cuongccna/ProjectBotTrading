"""
Trade Guard Absolute.

============================================================
THE FINAL EXECUTION GATE
============================================================

This module is the highest authority in the trading pipeline.
It sits between the Risk Budget Manager and the Execution Engine.

NO OTHER MODULE MAY OVERRIDE ITS DECISIONS.

============================================================
DECISION FLOW
============================================================

Strategy Engine → Risk Budget Manager → TRADE GUARD ABSOLUTE → Execution Engine
                                              ↑
                                    YOU ARE HERE

============================================================
OUTPUT
============================================================

Binary decisions only:
- EXECUTE: Trade may proceed to Execution Engine
- BLOCK: Trade is rejected. No further action.

No modifications. No retries. No deferrals.

============================================================
FAIL-SAFE BEHAVIOR
============================================================

- Any error → BLOCK
- Any timeout → BLOCK
- Any missing data → BLOCK

When in doubt, BLOCK.

============================================================
USAGE
============================================================

```python
from trade_guard_absolute import TradeGuardAbsolute, TradeGuardConfig
from trade_guard_absolute import GuardInput, GuardDecision

# Create guard
config = TradeGuardConfig()
guard = TradeGuardAbsolute(config)

# Build input (gather from system state)
guard_input = GuardInput(
    trade_intent=trade_intent,
    system_state=system_state,
    execution_health=execution_health,
    halt_state=halt_state,
    account_state=account_state,
    environmental_context=environmental_context,
)

# Evaluate
result = guard.evaluate(guard_input)

if result.decision == GuardDecision.EXECUTE:
    # Proceed to Execution Engine
    execution_engine.execute(order)
else:
    # Trade blocked - log and alert (done automatically)
    logger.warning(f"Trade blocked: {result.reason}")
```

============================================================
"""

# Types
from .types import (
    # Decision
    GuardDecision,
    BlockReason,
    BlockSeverity,
    BlockCategory,
    # Input types
    TradeIntent,
    SystemStateSnapshot,
    ExecutionHealthMetrics,
    GlobalHaltState,
    AccountState,
    EnvironmentalContext,
    GuardInput,
    # Output types
    ValidationResult,
    GuardDecisionOutput,
    # Errors
    TradeGuardError,
    ValidationError,
    InputError,
    TimeoutError,
)

# Configuration
from .config import (
    SystemIntegrityConfig,
    ExecutionSafetyConfig,
    StateConsistencyConfig,
    RuleConfig,
    EnvironmentalConfig,
    GuardAlertingConfig,
    TimingConfig,
    TradeGuardConfig,
    get_default_config,
    get_strict_config,
    get_testing_config,
    load_config_from_dict,
)

# Engine
from .engine import (
    TradeGuardAbsolute,
    create_guard,
    evaluate_trade,
    is_trade_allowed,
)

# Validators
from .validators import (
    BaseValidator,
    ValidatorMeta,
    SystemIntegrityValidator,
    ExecutionSafetyValidator,
    StateConsistencyValidator,
    RuleValidator,
    EnvironmentValidator,
)

# Models
from .models import (
    GuardDecisionLog,
    GuardBlockAlertLog,
    GuardDailyStats,
)

# Repository
from .repository import GuardRepository

# Alerting
from .alerting import (
    GuardAlert,
    GuardAlertFormatter,
    AlertRateLimiter,
    TelegramAlertSender,
    GuardAlerter,
)


__all__ = [
    # Decision Types
    "GuardDecision",
    "BlockReason",
    "BlockSeverity",
    "BlockCategory",
    # Input Types
    "TradeIntent",
    "SystemStateSnapshot",
    "ExecutionHealthMetrics",
    "GlobalHaltState",
    "AccountState",
    "EnvironmentalContext",
    "GuardInput",
    # Output Types
    "ValidationResult",
    "GuardDecisionOutput",
    # Errors
    "TradeGuardError",
    "ValidationError",
    "InputError",
    "TimeoutError",
    # Configuration
    "SystemIntegrityConfig",
    "ExecutionSafetyConfig",
    "StateConsistencyConfig",
    "RuleConfig",
    "EnvironmentalConfig",
    "GuardAlertingConfig",
    "TimingConfig",
    "TradeGuardConfig",
    "get_default_config",
    "get_strict_config",
    "get_testing_config",
    "load_config_from_dict",
    # Engine
    "TradeGuardAbsolute",
    "create_guard",
    "evaluate_trade",
    "is_trade_allowed",
    # Validators
    "BaseValidator",
    "ValidatorMeta",
    "SystemIntegrityValidator",
    "ExecutionSafetyValidator",
    "StateConsistencyValidator",
    "RuleValidator",
    "EnvironmentValidator",
    # Models
    "GuardDecisionLog",
    "GuardBlockAlertLog",
    "GuardDailyStats",
    # Repository
    "GuardRepository",
    # Alerting
    "GuardAlert",
    "GuardAlertFormatter",
    "AlertRateLimiter",
    "TelegramAlertSender",
    "GuardAlerter",
]


__version__ = "1.0.0"
