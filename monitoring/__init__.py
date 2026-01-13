"""
Monitoring & Dashboard Package.

============================================================
PURPOSE
============================================================
Strictly observational monitoring subsystem for the trading system.

PRINCIPLES:
1. READ-ONLY - No state mutation, no trading decisions
2. OBSERVATIONAL - Mirror, not brain
3. DETERMINISTIC - Explicit rules, no predictions
4. TRACEABLE - Full audit trail from signal to fill
5. RESILIENT - Dashboard unavailable = trading continues

============================================================
WHAT THIS SUBSYSTEM MUST NOT DO
============================================================
- Generate trading decisions
- Modify risk parameters
- Trigger executions
- Auto-correct system behavior

============================================================
WHAT THIS SUBSYSTEM MUST DO
============================================================
- Provide read-only access to all internal states
- Display UNKNOWN when data is unavailable (never guess)
- Use deterministic, explicit alert rules
- Maintain full audit trail
- Send notifications via Telegram

============================================================
"""

from .models import (
    # Enums
    SystemMode,
    ModuleStatus,
    AlertTier,
    DataFreshness,
    
    # Snapshots
    SystemStateSnapshot,
    DataSourceStatus,
    PositionSnapshot,
    RiskExposureSnapshot,
    
    # Records
    SignalRecord,
    OrderRecord,
    ModuleHealth,
    Alert,
    
    # Views
    DashboardOverview,
    ExecutionView,
    SignalView,
    AuditTrail,
    
    # Markers
    ReadOnlyAccess,
    
    # Constants
    FRESHNESS_THRESHOLDS,
    HEARTBEAT_THRESHOLDS,
    ALERT_THRESHOLDS,
)

from .collectors import (
    BaseCollector,
    SystemStateCollector,
    DataPipelineCollector,
    ModuleHealthCollector,
    RiskExposureCollector,
    PositionCollector,
    SignalCollector,
    OrderCollector,
    ExecutionMetricsCollector,
)

from .alerts import (
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
    AlertHistory,
    AlertManager,
    AlertDispatcher,
    # Signal tier filtering
    SubscriptionLevel,
    SignalTierFilter,
    create_signal_filter,
    filter_signals_for_user,
)

from .notifications import (
    TelegramFormatter,
    TelegramRateLimiter,
    TelegramNotifier,
    create_telegram_handler,
    telegram_alert_handler,
)

from .dashboard_service import (
    DashboardService,
    create_dashboard_service,
)

from .api import (
    DashboardAPI,
    create_dashboard_router,
    setup_dashboard_routes,
)


__all__ = [
    # --------------------------------------------------------
    # Models
    # --------------------------------------------------------
    
    # Enums
    "SystemMode",
    "ModuleStatus",
    "AlertTier",
    "DataFreshness",
    
    # Snapshots
    "SystemStateSnapshot",
    "DataSourceStatus",
    "PositionSnapshot",
    "RiskExposureSnapshot",
    
    # Records
    "SignalRecord",
    "OrderRecord",
    "ModuleHealth",
    "Alert",
    
    # Views
    "DashboardOverview",
    "ExecutionView",
    "SignalView",
    "AuditTrail",
    
    # Markers
    "ReadOnlyAccess",
    
    # Constants
    "FRESHNESS_THRESHOLDS",
    "HEARTBEAT_THRESHOLDS",
    "ALERT_THRESHOLDS",
    
    # --------------------------------------------------------
    # Collectors
    # --------------------------------------------------------
    "BaseCollector",
    "SystemStateCollector",
    "DataPipelineCollector",
    "ModuleHealthCollector",
    "RiskExposureCollector",
    "PositionCollector",
    "SignalCollector",
    "OrderCollector",
    "ExecutionMetricsCollector",
    
    # --------------------------------------------------------
    # Alerts
    # --------------------------------------------------------
    "AlertCategory",
    "AlertRuleConfig",
    "AlertRule",
    
    # Rules
    "SystemModeChangeRule",
    "TradingHaltedRule",
    "DrawdownThresholdRule",
    "ExposureLimitRule",
    "MarginWarningRule",
    "ModuleUnhealthyRule",
    "HeartbeatMissedRule",
    "DataStaleRule",
    "DataErrorRateRule",
    "get_default_rules",
    
    # Manager
    "AlertHistory",
    "AlertManager",
    "AlertDispatcher",
    
    # Signal Tier Filter
    "SubscriptionLevel",
    "SignalTierFilter",
    "create_signal_filter",
    "filter_signals_for_user",
    
    # --------------------------------------------------------
    # Notifications
    # --------------------------------------------------------
    "TelegramFormatter",
    "TelegramRateLimiter",
    "TelegramNotifier",
    "create_telegram_handler",
    "telegram_alert_handler",
    
    # --------------------------------------------------------
    # Service
    # --------------------------------------------------------
    "DashboardService",
    "create_dashboard_service",
    
    # --------------------------------------------------------
    # API
    # --------------------------------------------------------
    "DashboardAPI",
    "create_dashboard_router",
    "setup_dashboard_routes",
]
