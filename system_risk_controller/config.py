"""
System Risk Controller - Configuration.

============================================================
PURPOSE
============================================================
Configuration for all halt thresholds and controller behavior.

These thresholds are CONSERVATIVE by design.
When in doubt, the system halts.

============================================================
CONFIGURATION PHILOSOPHY
============================================================
1. All thresholds are explicit and documented
2. Safety over performance
3. Default to halt on uncertainty
4. No auto-tuning

============================================================
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


# ============================================================
# DATA INTEGRITY THRESHOLDS
# ============================================================

@dataclass
class DataIntegrityConfig:
    """
    Thresholds for data integrity monitoring.
    """
    
    # Market Data
    max_market_data_age_seconds: float = 60.0
    """Maximum age of market data before HALT."""
    
    market_data_missing_halt_threshold: int = 3
    """
    Number of consecutive missing data checks before HALT.
    Prevents transient issues from causing halt.
    """
    
    # Ingestion Failures
    max_ingestion_failures_per_hour: int = 5
    """Maximum ingestion failures before HALT."""
    
    max_consecutive_ingestion_failures: int = 3
    """Maximum consecutive failures before HALT."""
    
    # Schema Validation
    enforce_schema_validation: bool = True
    """Whether to enforce strict schema validation."""
    
    # Data Quality
    min_data_completeness_pct: float = 95.0
    """Minimum data completeness percentage."""
    
    # Price Anomalies
    max_price_deviation_pct: float = 50.0
    """
    Maximum price deviation from previous value.
    Detects obviously corrupted data.
    """


# ============================================================
# DATA REALITY GUARD THRESHOLDS
# ============================================================

@dataclass
class DataRealityGuardConfig:
    """
    Thresholds for Data Reality Guard.
    
    This guard CANNOT BE BYPASSED.
    It validates data freshness and accuracy before any trading.
    """
    
    # Freshness Check
    reference_interval_seconds: int = 3600
    """Reference interval in seconds (default: 1 hour)."""
    
    max_intervals_stale: int = 2
    """
    Maximum number of intervals data can be stale.
    With 1h interval: max 2 hours old.
    """
    
    # Price Deviation Check
    max_price_deviation_pct: float = 3.0
    """
    Maximum allowed deviation from live reference price.
    Default: 3% - any higher suggests data integrity issue.
    """
    
    reference_symbol: str = "BTC"
    """Symbol to check for price deviation."""
    
    # Behavior
    enabled: bool = True
    """Whether the guard is enabled."""
    
    halt_on_failure: bool = True
    """Whether to halt on guard failure (True = cannot bypass)."""
    
    check_on_startup: bool = True
    """Whether to run guard check on system startup."""
    
    check_before_execution: bool = True
    """Whether to run guard check before any execution."""


# ============================================================
# PROCESSING THRESHOLDS
# ============================================================

@dataclass
class ProcessingConfig:
    """
    Thresholds for processing pipeline monitoring.
    """
    
    # Feature Pipeline
    max_feature_pipeline_lag_seconds: float = 120.0
    """Maximum lag in feature pipeline before HALT."""
    
    max_feature_pipeline_errors_per_hour: int = 3
    """Maximum feature pipeline errors per hour."""
    
    # Processing Time
    max_processing_time_seconds: float = 30.0
    """Maximum processing time before timeout."""
    
    # Consistency
    check_determinism: bool = True
    """Whether to check for non-deterministic outputs."""
    
    determinism_check_interval_minutes: int = 60
    """How often to run determinism checks."""
    
    # Version Control
    enforce_version_match: bool = True
    """Whether to enforce version matching."""


# ============================================================
# EXECUTION THRESHOLDS
# ============================================================

@dataclass
class ExecutionConfig:
    """
    Thresholds for execution monitoring.
    """
    
    # Order Rejections
    max_rejections_per_hour: int = 5
    """Maximum order rejections before HALT."""
    
    max_consecutive_rejections: int = 3
    """Maximum consecutive rejections before HALT."""
    
    # Slippage
    max_slippage_pct: float = 2.0
    """Maximum slippage percentage before HALT."""
    
    slippage_halt_threshold: int = 3
    """Number of slippage violations before HALT."""
    
    # Position Mismatch
    position_mismatch_tolerance_pct: float = 0.5
    """
    Tolerance for position mismatch.
    Any mismatch beyond this = EMERGENCY HALT.
    """
    
    # Unconfirmed Executions
    max_unconfirmed_seconds: float = 120.0
    """Maximum time for unconfirmed executions."""
    
    max_unconfirmed_orders: int = 2
    """Maximum unconfirmed orders before HALT."""
    
    # Stuck Orders
    max_pending_order_age_seconds: float = 300.0
    """Maximum age for pending orders."""
    
    # Exchange Errors
    max_exchange_errors_per_hour: int = 10
    """Maximum exchange errors before HALT."""


# ============================================================
# CONTROL THRESHOLDS
# ============================================================

@dataclass
class ControlConfig:
    """
    Thresholds for risk/control monitoring.
    """
    
    # Drawdown
    max_daily_drawdown_pct: float = 5.0
    """Maximum daily drawdown percentage before EMERGENCY HALT."""
    
    max_total_drawdown_pct: float = 15.0
    """Maximum total drawdown from peak before EMERGENCY HALT."""
    
    drawdown_warning_pct: float = 3.0
    """Drawdown level that triggers SOFT HALT (warning)."""
    
    # Loss Limits
    max_daily_loss_usd: float = 100.0
    """Maximum daily loss in USD."""
    
    max_hourly_loss_usd: float = 50.0
    """Maximum hourly loss in USD."""
    
    # Leverage
    max_leverage: float = 5.0
    """Maximum allowed leverage."""
    
    leverage_warning_threshold: float = 3.0
    """Leverage level that triggers warning."""
    
    # Exposure
    max_total_exposure_pct: float = 80.0
    """Maximum total portfolio exposure."""
    
    max_single_position_pct: float = 25.0
    """Maximum single position as % of portfolio."""
    
    # Strategy Deviation
    check_strategy_deviation: bool = True
    """Whether to monitor strategy deviation."""
    
    max_win_rate_deviation_pct: float = 30.0
    """
    Maximum deviation from expected win rate.
    Detects if strategy behavior has changed.
    """


# ============================================================
# INFRASTRUCTURE THRESHOLDS
# ============================================================

@dataclass
class InfrastructureConfig:
    """
    Thresholds for infrastructure monitoring.
    """
    
    # Network
    max_network_latency_ms: float = 2000.0
    """Maximum network latency to exchange."""
    
    latency_spike_threshold_ms: float = 5000.0
    """Latency considered a spike."""
    
    max_latency_spikes_per_hour: int = 5
    """Maximum latency spikes before HALT."""
    
    # Clock
    max_clock_drift_ms: float = 1000.0
    """Maximum acceptable clock drift."""
    
    ntp_sync_required: bool = True
    """Whether NTP sync is required."""
    
    # Memory
    max_memory_usage_pct: float = 85.0
    """Maximum memory usage before HALT."""
    
    memory_warning_pct: float = 70.0
    """Memory usage warning threshold."""
    
    # Disk
    min_disk_space_mb: float = 1000.0
    """Minimum disk space required."""
    
    disk_warning_mb: float = 5000.0
    """Disk space warning threshold."""
    
    # Database
    max_db_connection_failures: int = 3
    """Maximum database connection failures."""
    
    db_query_timeout_seconds: float = 30.0
    """Database query timeout."""
    
    # CPU
    max_cpu_usage_pct: float = 90.0
    """Maximum CPU usage before HALT."""
    
    cpu_warning_pct: float = 75.0
    """CPU usage warning threshold."""


# ============================================================
# ALERTING CONFIGURATION
# ============================================================

@dataclass
class AlertingConfig:
    """
    Configuration for halt alerting.
    """
    
    enabled: bool = True
    """Whether alerting is enabled."""
    
    telegram_enabled: bool = True
    """Whether to send Telegram alerts."""
    
    # Alert on all halts
    alert_on_soft_halt: bool = True
    """Alert on SOFT HALT."""
    
    alert_on_hard_halt: bool = True
    """Alert on HARD HALT."""
    
    alert_on_emergency: bool = True
    """Alert on EMERGENCY (always True effectively)."""
    
    # Rate limiting
    min_alert_interval_seconds: int = 30
    """Minimum time between similar alerts."""
    
    max_alerts_per_hour: int = 60
    """Maximum alerts per hour."""
    
    # Escalation
    repeat_critical_alert_minutes: int = 5
    """Repeat critical alerts every N minutes until acknowledged."""


# ============================================================
# MONITOR TIMING
# ============================================================

@dataclass
class MonitorTimingConfig:
    """
    Configuration for monitor execution timing.
    """
    
    check_interval_seconds: float = 30.0
    """How often monitors run (default: 30s to reduce log spam)."""
    
    monitor_timeout_seconds: float = 10.0
    """Timeout for individual monitors."""
    
    health_snapshot_interval_seconds: float = 60.0
    """How often to generate health snapshots."""
    
    stale_monitor_threshold_seconds: float = 60.0
    """When to consider a monitor result stale."""


# ============================================================
# RESUME CONFIGURATION
# ============================================================

@dataclass
class ResumeConfig:
    """
    Configuration for resume behavior.
    """
    
    allow_soft_auto_resume: bool = True
    """Whether SOFT HALT can auto-resume when conditions clear."""
    
    soft_auto_resume_delay_seconds: float = 60.0
    """Delay before auto-resuming from SOFT HALT."""
    
    require_acknowledgment_for_hard: bool = True
    """Whether HARD HALT requires event acknowledgment."""
    
    require_acknowledgment_for_emergency: bool = True
    """Whether EMERGENCY requires acknowledgment."""
    
    cooldown_after_halt_seconds: float = 300.0
    """Cooldown period after resuming from halt."""
    
    max_halts_before_lockout: int = 5
    """
    Maximum halts in a period before requiring extended cooldown.
    Prevents rapid halt/resume cycles.
    """
    
    lockout_window_hours: int = 1
    """Window for counting halts toward lockout."""
    
    lockout_duration_minutes: int = 30
    """Duration of lockout period."""


# ============================================================
# MASTER CONFIGURATION
# ============================================================

@dataclass
class SystemRiskControllerConfig:
    """
    Master configuration for System Risk Controller.
    """
    
    data_integrity: DataIntegrityConfig = field(
        default_factory=DataIntegrityConfig
    )
    """Data integrity thresholds."""
    
    data_reality_guard: DataRealityGuardConfig = field(
        default_factory=DataRealityGuardConfig
    )
    """Data Reality Guard configuration - CANNOT BE BYPASSED."""
    
    processing: ProcessingConfig = field(
        default_factory=ProcessingConfig
    )
    """Processing thresholds."""
    
    execution: ExecutionConfig = field(
        default_factory=ExecutionConfig
    )
    """Execution thresholds."""
    
    control: ControlConfig = field(
        default_factory=ControlConfig
    )
    """Risk/control thresholds."""
    
    infrastructure: InfrastructureConfig = field(
        default_factory=InfrastructureConfig
    )
    """Infrastructure thresholds."""
    
    alerting: AlertingConfig = field(
        default_factory=AlertingConfig
    )
    """Alerting configuration."""
    
    timing: MonitorTimingConfig = field(
        default_factory=MonitorTimingConfig
    )
    """Monitor timing configuration."""
    
    resume: ResumeConfig = field(
        default_factory=ResumeConfig
    )
    """Resume configuration."""
    
    # Fail-Safe Behavior
    halt_on_monitor_error: bool = True
    """Whether to HALT if a monitor itself fails."""
    
    halt_on_unknown_error: bool = True
    """Whether to HALT on any unknown error."""
    
    default_halt_level_on_error: str = "HARD"
    """Default halt level for unclassified errors."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "data_integrity": {
                "max_market_data_age_seconds": self.data_integrity.max_market_data_age_seconds,
                "max_ingestion_failures_per_hour": self.data_integrity.max_ingestion_failures_per_hour,
            },
            "control": {
                "max_daily_drawdown_pct": self.control.max_daily_drawdown_pct,
                "max_daily_loss_usd": self.control.max_daily_loss_usd,
                "max_leverage": self.control.max_leverage,
            },
            "execution": {
                "max_slippage_pct": self.execution.max_slippage_pct,
                "max_rejections_per_hour": self.execution.max_rejections_per_hour,
            },
            "timing": {
                "check_interval_seconds": self.timing.check_interval_seconds,
            },
        }


# ============================================================
# PRESET FACTORIES
# ============================================================

def get_default_config() -> SystemRiskControllerConfig:
    """
    Get default configuration.
    
    Conservative defaults suitable for production.
    """
    return SystemRiskControllerConfig()


def get_strict_config() -> SystemRiskControllerConfig:
    """
    Get strict configuration.
    
    Even more conservative for high-risk periods.
    """
    config = SystemRiskControllerConfig()
    
    # Tighter data thresholds
    config.data_integrity.max_market_data_age_seconds = 30.0
    config.data_integrity.max_consecutive_ingestion_failures = 2
    
    # Stricter control limits
    config.control.max_daily_drawdown_pct = 3.0
    config.control.max_daily_loss_usd = 50.0
    config.control.max_leverage = 3.0
    
    # Faster checks
    config.timing.check_interval_seconds = 2.0
    
    # No auto-resume
    config.resume.allow_soft_auto_resume = False
    
    return config


def get_testing_config() -> SystemRiskControllerConfig:
    """
    Get testing configuration.
    
    Relaxed thresholds for testing.
    NOT FOR PRODUCTION.
    """
    config = SystemRiskControllerConfig()
    
    # Relaxed for testing
    config.data_integrity.max_market_data_age_seconds = 3600.0
    config.data_integrity.max_ingestion_failures_per_hour = 100
    
    config.control.max_daily_drawdown_pct = 50.0
    config.control.max_daily_loss_usd = 10000.0
    
    config.execution.max_rejections_per_hour = 100
    
    config.alerting.enabled = False
    
    config.halt_on_monitor_error = False
    
    return config


def load_config_from_dict(data: Dict[str, Any]) -> SystemRiskControllerConfig:
    """
    Load configuration from dictionary.
    
    Args:
        data: Configuration dictionary
        
    Returns:
        SystemRiskControllerConfig instance
    """
    config = get_default_config()
    
    if "data_integrity" in data:
        di = data["data_integrity"]
        config.data_integrity.max_market_data_age_seconds = di.get(
            "max_market_data_age_seconds",
            config.data_integrity.max_market_data_age_seconds,
        )
    
    if "control" in data:
        ctrl = data["control"]
        config.control.max_daily_drawdown_pct = ctrl.get(
            "max_daily_drawdown_pct",
            config.control.max_daily_drawdown_pct,
        )
        config.control.max_daily_loss_usd = ctrl.get(
            "max_daily_loss_usd",
            config.control.max_daily_loss_usd,
        )
    
    if "execution" in data:
        ex = data["execution"]
        config.execution.max_slippage_pct = ex.get(
            "max_slippage_pct",
            config.execution.max_slippage_pct,
        )
    
    return config
