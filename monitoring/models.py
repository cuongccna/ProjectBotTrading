"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    MONITORING & DASHBOARD SUBSYSTEM                          ║
║                                                                              ║
║  This subsystem is STRICTLY OBSERVATIONAL.                                   ║
║  It provides visibility into system state without influencing it.            ║
║                                                                              ║
║  THE DASHBOARD IS A MIRROR, NOT A BRAIN.                                     ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

============================================================
CORE PRINCIPLES
============================================================

1. READ-ONLY ACCESS
   - No state mutations
   - No trading decisions
   - No parameter modifications
   - No auto-corrections

2. DETERMINISTIC DISPLAY
   - What is shown is exactly what exists
   - No derived assumptions
   - No predictive analytics
   - No hidden logic

3. OBSERVATIONAL ONLY
   - Answers: What is happening? What has happened?
   - Never answers: What should we do? What will happen?

============================================================
PROHIBITED ACTIONS
============================================================

This subsystem MUST NOT:
- Generate trading decisions
- Modify risk parameters
- Trigger executions
- Auto-correct system behavior
- Infer missing data
- Predict future states

============================================================
"""

from enum import Enum, auto
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field


# ============================================================
# SYSTEM STATE DEFINITIONS
# ============================================================

class SystemMode(Enum):
    """
    Current operational mode of the system.
    
    These are the ONLY valid states.
    """
    
    RUNNING = "RUNNING"
    PAUSED_MANUAL = "PAUSED_MANUAL"      # Operator paused
    PAUSED_RISK = "PAUSED_RISK"          # Risk controller paused
    HALTED_SYSTEM = "HALTED_SYSTEM"      # System-initiated halt
    DEGRADED = "DEGRADED"                # Partial failure
    INITIALIZING = "INITIALIZING"        # Starting up
    SHUTTING_DOWN = "SHUTTING_DOWN"      # Graceful shutdown


class ModuleStatus(Enum):
    """Status of individual modules."""
    
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"
    STOPPED = "STOPPED"


class AlertTier(Enum):
    """Alert severity tiers."""
    
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class DataFreshness(Enum):
    """Data freshness indicators."""
    
    FRESH = "FRESH"           # Within expected interval
    STALE = "STALE"           # Beyond threshold
    MISSING = "MISSING"       # No data available
    UNKNOWN = "UNKNOWN"       # Cannot determine


# ============================================================
# SYSTEM STATE SNAPSHOT
# ============================================================

@dataclass
class SystemStateSnapshot:
    """
    Complete snapshot of system state.
    
    This is the primary read-only view of the system.
    """
    
    # Current mode
    mode: SystemMode
    mode_changed_at: datetime
    mode_changed_by: str  # Module that triggered
    mode_reason: str      # Explicit reason code
    
    # Timestamps
    snapshot_time: datetime
    system_uptime_seconds: float
    
    # Health summary
    healthy_modules: int
    degraded_modules: int
    unhealthy_modules: int
    
    # Trading state
    trading_enabled: bool
    active_orders_count: int
    open_positions_count: int


@dataclass
class DataSourceStatus:
    """Status of a data source."""
    
    source_name: str
    source_type: str  # exchange, news, market_data
    
    # Timing
    last_successful_fetch: Optional[datetime]
    last_fetch_latency_ms: Optional[float]
    
    # Health
    freshness: DataFreshness
    error_count_1m: int
    error_count_5m: int
    error_count_1h: int
    
    # Flags
    is_stale: bool
    has_missing_fields: bool
    has_abnormal_volume: bool
    
    # Last error
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None


@dataclass
class PositionSnapshot:
    """Snapshot of a single position."""
    
    symbol: str
    exchange_id: str
    side: str  # LONG, SHORT
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    leverage: int
    margin_used: Decimal
    liquidation_price: Optional[Decimal]
    
    # Timing
    opened_at: datetime
    last_updated: datetime


@dataclass
class RiskExposureSnapshot:
    """Snapshot of risk and exposure."""
    
    # Account
    account_balance: Decimal
    available_margin: Decimal
    used_margin: Decimal
    margin_ratio: Decimal
    
    # Positions
    positions: List[PositionSnapshot]
    total_exposure_usd: Decimal
    
    # Per-asset exposure
    exposure_by_asset: Dict[str, Decimal]
    
    # Drawdown
    session_drawdown_pct: Decimal
    daily_drawdown_pct: Decimal
    rolling_drawdown_pct: Decimal
    max_drawdown_threshold_pct: Decimal
    
    # Risk budget
    risk_budget_used_pct: Decimal
    risk_budget_remaining_pct: Decimal
    max_loss_threshold_usd: Decimal
    current_loss_usd: Decimal
    remaining_loss_allowance_usd: Decimal
    
    # Timestamp
    snapshot_time: datetime


@dataclass
class SignalRecord:
    """Record of a generated signal."""
    
    signal_id: str
    timestamp: datetime
    
    # Source
    strategy_id: str
    strategy_name: str
    
    # Signal details
    symbol: str
    direction: str  # BUY, SELL
    signal_strength: Decimal
    risk_score: Decimal
    
    # Data reference
    input_data_snapshot_id: str
    
    # Decision
    decision_outcome: str  # APPROVED, REJECTED
    rejection_reason: Optional[str] = None
    
    # If approved, execution reference
    execution_id: Optional[str] = None


@dataclass
class OrderRecord:
    """Record of an order."""
    
    order_id: str
    client_order_id: str
    timestamp: datetime
    
    # Intent
    symbol: str
    side: str
    order_type: str
    intended_quantity: Decimal
    intended_price: Optional[Decimal]
    
    # Exchange response
    exchange_order_id: Optional[str]
    exchange_response_time: Optional[datetime]
    exchange_status: str
    
    # Fill status
    fill_status: str  # PENDING, PARTIAL, FILLED, REJECTED, CANCELED
    filled_quantity: Decimal
    average_fill_price: Optional[Decimal]
    
    # Metrics
    slippage_pct: Optional[Decimal]
    execution_latency_ms: Optional[float]
    
    # Errors
    has_error: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class ModuleHealth:
    """Health status of a module."""
    
    module_name: str
    module_type: str
    
    # Status
    status: ModuleStatus
    status_reason: Optional[str]
    
    # Heartbeat
    last_heartbeat: Optional[datetime]
    heartbeat_interval_seconds: int
    heartbeat_missed: bool
    
    # Resources
    cpu_usage_pct: Optional[float]
    memory_usage_mb: Optional[float]
    memory_limit_mb: Optional[float]
    
    # Queues
    queue_backlog: Optional[int]
    queue_max_size: Optional[int]
    
    # Metrics
    requests_per_minute: Optional[int]
    errors_per_minute: Optional[int]


@dataclass
class Alert:
    """An alert record."""
    
    alert_id: str
    timestamp: datetime
    
    # Classification
    tier: AlertTier
    category: str  # SYSTEM, RISK, EXECUTION, DATA
    
    # Content
    title: str
    message: str
    
    # Source
    source_module: str
    source_component: Optional[str]
    
    # Context
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Status
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    
    # Notifications
    sent_to_dashboard: bool = False
    sent_to_telegram: bool = False


# ============================================================
# DASHBOARD VIEW MODELS
# ============================================================

@dataclass
class DashboardOverview:
    """
    Primary dashboard view.
    
    This is what an operator sees first.
    """
    
    # System state (most important)
    system_state: SystemStateSnapshot
    
    # Risk exposure
    risk_exposure: RiskExposureSnapshot
    
    # Active positions
    active_positions: List[PositionSnapshot]
    
    # Recent errors
    recent_errors: List[Alert]
    
    # Module health summary
    module_health: Dict[str, ModuleHealth]
    
    # Data source status
    data_sources: List[DataSourceStatus]
    
    # Timestamp
    generated_at: datetime


@dataclass
class ExecutionView:
    """Execution and order tracking view."""
    
    # Open orders
    open_orders: List[OrderRecord]
    
    # Recent orders
    recent_orders: List[OrderRecord]
    
    # Execution metrics
    orders_today: int
    fills_today: int
    rejections_today: int
    avg_latency_ms: float
    avg_slippage_pct: Decimal
    
    # Timestamp
    generated_at: datetime


@dataclass
class SignalView:
    """Signal and strategy visibility view."""
    
    # Recent signals
    recent_signals: List[SignalRecord]
    
    # Signal metrics
    signals_today: int
    approved_today: int
    rejected_today: int
    
    # By strategy
    signals_by_strategy: Dict[str, int]
    approval_rate_by_strategy: Dict[str, Decimal]
    
    # Timestamp
    generated_at: datetime


@dataclass
class AuditTrail:
    """Audit trail for traceability."""
    
    # Trade chain
    trade_id: str
    signal_record: Optional[SignalRecord]
    order_record: Optional[OrderRecord]
    position_impact: Optional[Dict[str, Any]]
    
    # Data references
    data_snapshot_id: str
    raw_input_reference: str
    
    # Timeline
    events: List[Dict[str, Any]]  # Ordered list of events


# ============================================================
# READ-ONLY ACCESS MARKERS
# ============================================================

class ReadOnlyAccess:
    """
    Marker for read-only data access.
    
    All monitoring data access MUST use this pattern.
    """
    
    @staticmethod
    def verify_read_only(operation: str) -> bool:
        """Verify operation is read-only."""
        prohibited = [
            "insert", "update", "delete", "create",
            "modify", "mutate", "write", "set", "change",
            "execute", "submit", "cancel", "halt",
        ]
        operation_lower = operation.lower()
        for word in prohibited:
            if word in operation_lower:
                return False
        return True


# ============================================================
# CONSTANTS
# ============================================================

# Data freshness thresholds (seconds)
FRESHNESS_THRESHOLDS = {
    "exchange_price": 5,
    "exchange_balance": 30,
    "exchange_position": 10,
    "news_feed": 300,
    "market_data": 60,
}

# Heartbeat thresholds (seconds)
HEARTBEAT_THRESHOLDS = {
    "execution_engine": 5,
    "risk_controller": 5,
    "data_pipeline": 10,
    "signal_generator": 30,
    "reconciliation": 60,
}

# Alert thresholds
ALERT_THRESHOLDS = {
    "error_rate_per_minute": 10,
    "latency_warning_ms": 5000,
    "latency_critical_ms": 30000,
    "queue_backlog_warning": 100,
    "queue_backlog_critical": 1000,
}
