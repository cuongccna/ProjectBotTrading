"""
Trade Guard Absolute - Validators Package.

============================================================
VALIDATORS
============================================================
Each validator covers one category of blocking conditions:

- SystemIntegrityValidator: Data freshness, sync, clock
- ExecutionSafetyValidator: Exchange health, rate limits
- StateConsistencyValidator: Position/balance matching
- RuleValidator: Trading hours, halt state, cooldowns
- EnvironmentValidator: Risk levels, volatility, liquidity

============================================================
"""

from .base import (
    BaseValidator,
    ValidatorMeta,
    create_pass_result,
    create_block_result,
    check_field_present,
    check_timestamp_valid,
)
from .system_integrity import SystemIntegrityValidator
from .execution_safety import ExecutionSafetyValidator
from .state_consistency import StateConsistencyValidator
from .rule_validator import RuleValidator
from .environment import EnvironmentValidator

__all__ = [
    # Base
    "BaseValidator",
    "ValidatorMeta",
    "create_pass_result",
    "create_block_result",
    "check_field_present",
    "check_timestamp_valid",
    # Validators
    "SystemIntegrityValidator",
    "ExecutionSafetyValidator",
    "StateConsistencyValidator",
    "RuleValidator",
    "EnvironmentValidator",
]
