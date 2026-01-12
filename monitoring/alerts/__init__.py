"""
Alerts Package.

Alert rules and management for the monitoring subsystem.
"""

from .rules import (
    AlertCategory,
    AlertRuleConfig,
    AlertRule,
    SystemModeChangeRule,
    TradingHaltedRule,
    DrawdownThresholdRule,
    ExposureLimitRule,
    MarginWarningRule,
    ModuleUnhealthyRule,
    HeartbeatMissedRule,
    DataStaleRule,
    DataErrorRateRule,
    get_default_rules,
)
from .manager import (
    AlertHistory,
    AlertManager,
    AlertDispatcher,
    NotificationHandler,
)


__all__ = [
    # Rule types
    "AlertCategory",
    "AlertRuleConfig",
    "AlertRule",
    
    # System rules
    "SystemModeChangeRule",
    "TradingHaltedRule",
    
    # Risk rules
    "DrawdownThresholdRule",
    "ExposureLimitRule",
    "MarginWarningRule",
    
    # Module rules
    "ModuleUnhealthyRule",
    "HeartbeatMissedRule",
    
    # Data rules
    "DataStaleRule",
    "DataErrorRateRule",
    
    # Factory
    "get_default_rules",
    
    # Manager
    "AlertHistory",
    "AlertManager",
    "AlertDispatcher",
    "NotificationHandler",
]
