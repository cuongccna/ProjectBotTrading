"""
Trade Guard Absolute - Configuration.

============================================================
PURPOSE
============================================================
Configuration for all blocking condition thresholds.

These thresholds are CONSERVATIVE by design.
When in doubt, the system blocks the trade.

============================================================
CONFIGURATION PHILOSOPHY
============================================================
1. All thresholds are explicit and documented
2. No auto-adjustment or optimization
3. Conservative defaults that err on safety
4. Externally configurable via dictionary

============================================================
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# ============================================================
# SYSTEM INTEGRITY THRESHOLDS
# ============================================================

@dataclass
class SystemIntegrityConfig:
    """
    Thresholds for system integrity validation.
    
    These protect against stale data, clock drift, and
    data pipeline issues.
    """
    
    # Market Data
    max_market_data_age_seconds: float = 30.0
    """
    Maximum age of market data before blocking.
    Default: 30 seconds
    
    RATIONALE:
    - Crypto markets move fast
    - Stale data leads to bad fills
    - 30 seconds is conservative for active trading
    """
    
    min_symbol_coverage_pct: float = 95.0
    """
    Minimum percentage of symbols with valid data.
    If coverage drops below this, block all trades.
    """
    
    # Feature Pipeline
    max_feature_pipeline_lag_seconds: float = 60.0
    """
    Maximum lag between feature pipeline and market data.
    Features must be computed within this window.
    """
    
    require_feature_sync: bool = True
    """
    Whether feature pipeline sync is required.
    If True, desync blocks trades.
    """
    
    # Clock Synchronization
    max_clock_drift_ms: float = 1000.0
    """
    Maximum acceptable clock drift in milliseconds.
    Default: 1 second
    
    RATIONALE:
    - Exchange timestamps must be accurate
    - Order timing is critical
    - 1 second drift is already concerning
    """
    
    require_ntp_sync: bool = True
    """
    Whether NTP synchronization is required.
    """
    
    # Timestamp Validation
    max_request_age_seconds: float = 300.0
    """
    Maximum age of a trade request.
    Older requests are rejected as potentially replayed.
    Default: 5 minutes
    """
    
    max_future_timestamp_seconds: float = 10.0
    """
    Maximum timestamp in the future allowed.
    Prevents clock issues from accepting bad requests.
    """
    
    # Duplicate Detection
    duplicate_window_seconds: int = 3600
    """
    Window for duplicate request detection.
    Requests with same ID within this window are rejected.
    """


# ============================================================
# EXECUTION SAFETY THRESHOLDS
# ============================================================

@dataclass
class ExecutionSafetyConfig:
    """
    Thresholds for execution environment safety.
    
    These protect against exchange issues, network problems,
    and execution failures.
    """
    
    # Exchange Reachability
    require_exchange_reachable: bool = True
    """
    Whether exchange must be reachable.
    Obvious, but configurable for testing.
    """
    
    max_exchange_latency_ms: float = 2000.0
    """
    Maximum acceptable exchange latency.
    Default: 2 seconds
    
    RATIONALE:
    - High latency = potential timeout
    - Price can move significantly in 2 seconds
    - Orders may fail or fill poorly
    """
    
    allowed_exchange_statuses: List[str] = field(
        default_factory=lambda: ["OPERATIONAL", "NORMAL", "OK"]
    )
    """
    Exchange status values considered healthy.
    """
    
    # Order Success Rate
    min_order_success_rate_1h: float = 0.90
    """
    Minimum order success rate in last hour.
    Below 90% suggests execution problems.
    """
    
    max_order_failures_1h: int = 5
    """
    Maximum order failures in last hour.
    After 5 failures, stop trying.
    """
    
    # Pending Orders
    max_pending_orders: int = 3
    """
    Maximum pending/unconfirmed orders allowed.
    Too many pending orders suggests problems.
    """
    
    max_pending_cancellations: int = 2
    """
    Maximum pending cancellations allowed.
    Pending cancellations block new orders.
    """
    
    # Rate Limits
    min_rate_limit_remaining: int = 100
    """
    Minimum remaining rate limit.
    Reserve buffer for emergency operations.
    """
    
    max_rate_limit_utilization: float = 0.80
    """
    Maximum rate limit utilization.
    At 80%, start rejecting non-critical requests.
    """
    
    # Network
    max_network_latency_ms: float = 1000.0
    """
    Maximum network latency to exchange.
    """
    
    require_stable_connection: bool = True
    """
    Whether stable connection is required.
    Unstable connections block trades.
    """
    
    # Unknown Orders
    max_unknown_open_orders: int = 0
    """
    Maximum orders on exchange not in system.
    Default: 0 (any unknown order is a problem)
    """


# ============================================================
# STATE CONSISTENCY THRESHOLDS
# ============================================================

@dataclass
class StateConsistencyConfig:
    """
    Thresholds for state consistency validation.
    
    These detect mismatches between system state and
    exchange state.
    """
    
    # Position Sync
    require_position_sync: bool = True
    """
    Whether position sync is required.
    """
    
    max_position_sync_age_seconds: float = 120.0
    """
    Maximum time since last position sync.
    Default: 2 minutes
    """
    
    allow_position_mismatch: bool = False
    """
    Whether to allow position count mismatch.
    Default: False (any mismatch blocks trades)
    """
    
    # Equity Validation
    equity_mismatch_tolerance_pct: float = 1.0
    """
    Tolerance for equity mismatch.
    Default: 1% (accounts for unrealized P&L float)
    """
    
    require_equity_match: bool = True
    """
    Whether equity values must match within tolerance.
    """
    
    # Balance Validation
    min_available_balance: float = 10.0
    """
    Minimum available balance for trading.
    Default: $10 (sanity check)
    """
    
    # Margin State
    require_margin_state_defined: bool = True
    """
    Whether margin/leverage state must be defined.
    """
    
    allowed_margin_modes: List[str] = field(
        default_factory=lambda: ["CROSS", "ISOLATED"]
    )
    """
    Allowed margin modes.
    """
    
    max_margin_ratio: float = 0.80
    """
    Maximum margin utilization ratio.
    At 80%, stop opening new positions.
    """


# ============================================================
# RULE THRESHOLDS
# ============================================================

@dataclass
class RuleConfig:
    """
    Configuration for trading rule validation.
    
    These enforce operational rules and restrictions.
    """
    
    # Trading Hours
    enforce_trading_hours: bool = False
    """
    Whether to enforce trading hours.
    Default: False (crypto trades 24/7)
    """
    
    allowed_trading_hours_utc: List[Dict[str, int]] = field(
        default_factory=list
    )
    """
    Allowed trading hours in UTC.
    Format: [{"start_hour": 0, "end_hour": 24}]
    """
    
    # Cooldown
    respect_cooldown: bool = True
    """
    Whether to respect cooldown periods.
    """
    
    # System Halt
    respect_system_halt: bool = True
    """
    Whether to respect System Risk Controller halt.
    This should ALWAYS be True.
    """
    
    # Manual Lock
    respect_manual_lock: bool = True
    """
    Whether to respect manual intervention lock.
    """
    
    # Maintenance
    block_during_maintenance: bool = True
    """
    Whether to block during maintenance windows.
    """
    
    # Symbol Restrictions
    check_symbol_tradeable: bool = True
    """
    Whether to check if symbol is tradeable.
    """
    
    restricted_symbols: List[str] = field(default_factory=list)
    """
    List of symbols that cannot be traded.
    """
    
    # Direction Restrictions
    allow_long: bool = True
    """
    Whether LONG trades are allowed.
    """
    
    allow_short: bool = True
    """
    Whether SHORT trades are allowed.
    """


# ============================================================
# ENVIRONMENTAL THRESHOLDS
# ============================================================

@dataclass
class EnvironmentalConfig:
    """
    Configuration for environmental condition validation.
    
    These protect against extreme market conditions.
    """
    
    # Risk Level
    block_on_critical_risk: bool = True
    """
    Whether to block when risk level is CRITICAL.
    This should ALWAYS be True.
    """
    
    critical_risk_levels: List[str] = field(
        default_factory=lambda: ["CRITICAL", "EXTREME", "EMERGENCY"]
    )
    """
    Risk levels that trigger blocking.
    """
    
    max_risk_score: float = 0.90
    """
    Maximum risk score before blocking.
    Default: 0.90 (leave some headroom below 1.0)
    """
    
    # Escalation
    block_on_escalation: bool = True
    """
    Whether to block during escalation.
    """
    
    min_escalation_level_to_block: int = 2
    """
    Minimum escalation level that blocks trading.
    """
    
    # Circuit Breaker
    respect_circuit_breaker: bool = True
    """
    Whether to respect exchange circuit breakers.
    """
    
    # Volatility
    max_volatility_for_trading: float = 0.10
    """
    Maximum volatility (as decimal) for trading.
    Default: 10% (very high for most markets)
    """
    
    volatility_regimes_blocked: List[str] = field(
        default_factory=lambda: ["EXTREME", "CRISIS"]
    )
    """
    Volatility regimes that block trading.
    """
    
    # Liquidity
    min_liquidity_score: float = 0.3
    """
    Minimum liquidity score for trading.
    Default: 0.3 (somewhat low, but tradeable)
    """
    
    max_spread_pct: float = 1.0
    """
    Maximum bid-ask spread percentage.
    Default: 1% (high for liquid markets)
    """


# ============================================================
# ALERTING CONFIGURATION
# ============================================================

@dataclass
class GuardAlertingConfig:
    """
    Configuration for guard alerting.
    """
    
    enabled: bool = True
    """Whether alerting is enabled."""
    
    telegram_enabled: bool = True
    """Whether to send Telegram alerts."""
    
    # Alert on all blocks
    alert_on_block: bool = True
    """Whether to alert on every block."""
    
    # Severity filtering
    min_severity_for_alert: int = 1
    """
    Minimum severity level for alerting.
    1 = LOW (alert on everything)
    """
    
    # Rate limiting
    min_alert_interval_seconds: int = 60
    """
    Minimum time between similar alerts.
    """
    
    max_alerts_per_hour: int = 30
    """
    Maximum alerts per hour.
    """


# ============================================================
# TIMING CONFIGURATION
# ============================================================

@dataclass
class TimingConfig:
    """
    Configuration for evaluation timing.
    """
    
    max_evaluation_time_ms: float = 100.0
    """
    Maximum time for guard evaluation.
    Default: 100ms (must be fast)
    
    RATIONALE:
    - Guard is in critical path
    - Every millisecond counts
    - If evaluation is slow, BLOCK
    """
    
    validator_timeout_ms: float = 20.0
    """
    Timeout for individual validators.
    Default: 20ms each
    """
    
    strict_timing: bool = True
    """
    Whether to enforce strict timing.
    If True, timeout = BLOCK.
    """


# ============================================================
# MASTER CONFIGURATION
# ============================================================

@dataclass
class TradeGuardConfig:
    """
    Master configuration for Trade Guard Absolute.
    
    Aggregates all configuration sections.
    """
    
    system_integrity: SystemIntegrityConfig = field(
        default_factory=SystemIntegrityConfig
    )
    """System integrity thresholds."""
    
    execution_safety: ExecutionSafetyConfig = field(
        default_factory=ExecutionSafetyConfig
    )
    """Execution safety thresholds."""
    
    state_consistency: StateConsistencyConfig = field(
        default_factory=StateConsistencyConfig
    )
    """State consistency thresholds."""
    
    rules: RuleConfig = field(default_factory=RuleConfig)
    """Trading rule configuration."""
    
    environmental: EnvironmentalConfig = field(
        default_factory=EnvironmentalConfig
    )
    """Environmental thresholds."""
    
    alerting: GuardAlertingConfig = field(
        default_factory=GuardAlertingConfig
    )
    """Alerting configuration."""
    
    timing: TimingConfig = field(default_factory=TimingConfig)
    """Timing configuration."""
    
    # Fail-Safe Behavior
    block_on_internal_error: bool = True
    """
    Whether to BLOCK on any internal error.
    This should ALWAYS be True.
    """
    
    block_on_missing_input: bool = True
    """
    Whether to BLOCK on missing input data.
    This should ALWAYS be True.
    """
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "system_integrity": {
                "max_market_data_age_seconds": self.system_integrity.max_market_data_age_seconds,
                "max_clock_drift_ms": self.system_integrity.max_clock_drift_ms,
                "max_request_age_seconds": self.system_integrity.max_request_age_seconds,
            },
            "execution_safety": {
                "max_exchange_latency_ms": self.execution_safety.max_exchange_latency_ms,
                "min_order_success_rate_1h": self.execution_safety.min_order_success_rate_1h,
                "max_pending_orders": self.execution_safety.max_pending_orders,
            },
            "state_consistency": {
                "max_position_sync_age_seconds": self.state_consistency.max_position_sync_age_seconds,
                "equity_mismatch_tolerance_pct": self.state_consistency.equity_mismatch_tolerance_pct,
            },
            "environmental": {
                "block_on_critical_risk": self.environmental.block_on_critical_risk,
                "max_volatility_for_trading": self.environmental.max_volatility_for_trading,
            },
            "timing": {
                "max_evaluation_time_ms": self.timing.max_evaluation_time_ms,
            },
            "block_on_internal_error": self.block_on_internal_error,
        }


# ============================================================
# PRESET FACTORIES
# ============================================================

def get_default_config() -> TradeGuardConfig:
    """
    Get default configuration.
    
    Conservative defaults suitable for production.
    """
    return TradeGuardConfig()


def get_strict_config() -> TradeGuardConfig:
    """
    Get strict configuration.
    
    Even more conservative for high-risk periods.
    """
    config = TradeGuardConfig()
    
    # Tighter timing
    config.system_integrity.max_market_data_age_seconds = 15.0
    config.system_integrity.max_clock_drift_ms = 500.0
    
    # Stricter execution
    config.execution_safety.max_exchange_latency_ms = 1000.0
    config.execution_safety.min_order_success_rate_1h = 0.95
    config.execution_safety.max_pending_orders = 1
    
    # Tighter state checks
    config.state_consistency.max_position_sync_age_seconds = 60.0
    
    # Lower environmental thresholds
    config.environmental.max_volatility_for_trading = 0.05
    config.environmental.min_liquidity_score = 0.5
    
    return config


def get_testing_config() -> TradeGuardConfig:
    """
    Get testing configuration.
    
    Relaxed thresholds for testing environments.
    NOT FOR PRODUCTION.
    """
    config = TradeGuardConfig()
    
    # Relaxed for testing
    config.system_integrity.max_market_data_age_seconds = 300.0
    config.system_integrity.require_ntp_sync = False
    
    config.execution_safety.require_exchange_reachable = False
    config.execution_safety.min_order_success_rate_1h = 0.0
    
    config.state_consistency.allow_position_mismatch = True
    config.state_consistency.require_equity_match = False
    
    config.alerting.enabled = False
    
    return config


def load_config_from_dict(data: Dict[str, Any]) -> TradeGuardConfig:
    """
    Load configuration from dictionary.
    
    Args:
        data: Configuration dictionary
    
    Returns:
        TradeGuardConfig instance
    """
    config = get_default_config()
    
    if "system_integrity" in data:
        si = data["system_integrity"]
        config.system_integrity.max_market_data_age_seconds = si.get(
            "max_market_data_age_seconds",
            config.system_integrity.max_market_data_age_seconds,
        )
        config.system_integrity.max_clock_drift_ms = si.get(
            "max_clock_drift_ms",
            config.system_integrity.max_clock_drift_ms,
        )
    
    if "execution_safety" in data:
        es = data["execution_safety"]
        config.execution_safety.max_exchange_latency_ms = es.get(
            "max_exchange_latency_ms",
            config.execution_safety.max_exchange_latency_ms,
        )
        config.execution_safety.min_order_success_rate_1h = es.get(
            "min_order_success_rate_1h",
            config.execution_safety.min_order_success_rate_1h,
        )
    
    if "environmental" in data:
        env = data["environmental"]
        config.environmental.max_volatility_for_trading = env.get(
            "max_volatility_for_trading",
            config.environmental.max_volatility_for_trading,
        )
        config.environmental.block_on_critical_risk = env.get(
            "block_on_critical_risk",
            config.environmental.block_on_critical_risk,
        )
    
    if "alerting" in data:
        alert = data["alerting"]
        config.alerting.enabled = alert.get("enabled", config.alerting.enabled)
        config.alerting.telegram_enabled = alert.get(
            "telegram_enabled",
            config.alerting.telegram_enabled,
        )
    
    return config
