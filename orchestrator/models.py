"""
Orchestrator - Models.

============================================================
RESPONSIBILITY
============================================================
Defines data models for the system orchestrator.

- Runtime modes (ingest, process, risk, trade, backtest, monitor, full)
- Execution stages with strict ordering
- Module status and health
- Configuration dataclasses

============================================================
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set
import os


# ============================================================
# RUNTIME MODES
# ============================================================

class RuntimeMode(Enum):
    """
    Runtime execution modes.
    
    Each mode defines which modules are active.
    
    CRITICAL: SCAFFOLD mode is the ONLY mode that allows placeholder modules.
    All other modes REQUIRE real module implementations.
    """
    
    SCAFFOLD = "scaffold"
    """Development scaffolding mode. ONLY mode that allows placeholder modules."""
    
    INGEST = "ingest"
    """Run data ingestion only. No processing, no trading."""
    
    PROCESS = "process"
    """Run data processing only. No ingestion, no trading."""
    
    RISK = "risk"
    """Run risk aggregation and scoring only. No execution."""
    
    TRADE = "trade"
    """Full pipeline including execution. Subject to guards."""
    
    BACKTEST = "backtest"
    """Replay historical data with identical logic."""
    
    MONITOR = "monitor"
    """Run monitoring and alerting only."""
    
    FULL = "full"
    """Run full live system in correct order."""
    
    @property
    def allows_ingestion(self) -> bool:
        """Check if mode runs ingestion."""
        return self in (RuntimeMode.INGEST, RuntimeMode.FULL, RuntimeMode.TRADE)
    
    @property
    def allows_processing(self) -> bool:
        """Check if mode runs processing."""
        return self in (RuntimeMode.PROCESS, RuntimeMode.FULL, RuntimeMode.TRADE, RuntimeMode.BACKTEST)
    
    @property
    def allows_risk_scoring(self) -> bool:
        """Check if mode runs risk scoring."""
        return self in (RuntimeMode.RISK, RuntimeMode.FULL, RuntimeMode.TRADE, RuntimeMode.BACKTEST)
    
    @property
    def allows_trading(self) -> bool:
        """Check if mode can execute trades."""
        return self in (RuntimeMode.TRADE, RuntimeMode.FULL)
    
    @property
    def allows_backtest(self) -> bool:
        """Check if mode is backtesting."""
        return self == RuntimeMode.BACKTEST
    
    @property
    def is_monitoring_only(self) -> bool:
        """Check if mode is monitoring only."""
        return self == RuntimeMode.MONITOR
    
    @property
    def allows_placeholders(self) -> bool:
        """
        Check if mode allows placeholder modules.
        
        CRITICAL: Only SCAFFOLD mode allows placeholders.
        All other modes REQUIRE real implementations.
        """
        return self == RuntimeMode.SCAFFOLD
    
    @property
    def requires_real_modules(self) -> bool:
        """
        Check if mode requires real (non-placeholder) modules.
        
        Returns True for all production-like modes.
        """
        return self != RuntimeMode.SCAFFOLD


# ============================================================
# EXECUTION STAGES
# ============================================================

class ExecutionStage(Enum):
    """
    Execution stages in strict order.
    
    When running in "full" or "trade" mode, stages execute
    in this exact sequence. Failure short-circuits downstream.
    """
    
    # Initialization (1-4)
    LOAD_CONFIG = (1, "load_config", "Load configuration and environment")
    INIT_LOGGING = (2, "init_logging", "Initialize logging and correlation IDs")
    INIT_DATABASE = (3, "init_database", "Initialize database connections")
    INIT_HEALTH = (4, "init_health", "Initialize system health checks")
    
    # Data Collection (5-6)
    INIT_COLLECTORS = (5, "init_collectors", "Initialize data collectors")
    RUN_INGESTION = (6, "run_ingestion", "Run ingestion modules")
    
    # Processing (7-8)
    RUN_PROCESSING = (7, "run_processing", "Run data processing pipelines")
    RUN_MARKET_CLASSIFICATION = (8, "run_market_classification", "Run market condition classification")
    
    # Risk (9-11)
    RUN_RISK_SCORING = (9, "run_risk_scoring", "Run risk aggregation and scoring")
    RUN_RISK_BUDGET = (10, "run_risk_budget", "Run risk budget manager")
    RUN_COMMITTEE_REVIEW = (11, "run_committee_review", "Run institutional risk committee review")
    
    # Trading (12-15)
    RUN_STRATEGY = (12, "run_strategy", "Run strategy engine")
    RUN_TRADE_GUARD = (13, "run_trade_guard", "Run trade guard absolute")
    RUN_RISK_CONTROLLER = (14, "run_risk_controller", "Run system risk controller")
    RUN_EXECUTION = (15, "run_execution", "Run execution engine")
    
    # Finalization (16-18)
    SEND_NOTIFICATIONS = (16, "send_notifications", "Send notifications")
    PERSIST_RESULTS = (17, "persist_results", "Persist all results")
    UPDATE_MONITORING = (18, "update_monitoring", "Update monitoring state")
    
    def __init__(self, order: int, stage_id: str, description: str):
        self._order = order
        self._stage_id = stage_id
        self._description = description
    
    @property
    def order(self) -> int:
        """Get execution order."""
        return self._order
    
    @property
    def stage_id(self) -> str:
        """Get stage identifier."""
        return self._stage_id
    
    @property
    def description(self) -> str:
        """Get stage description."""
        return self._description
    
    @classmethod
    def get_ordered_stages(cls) -> List["ExecutionStage"]:
        """Get all stages in execution order."""
        return sorted(cls, key=lambda s: s.order)
    
    @classmethod
    def get_stages_for_mode(cls, mode: RuntimeMode) -> List["ExecutionStage"]:
        """Get stages that should run for a given mode."""
        # Always run initialization
        init_stages = [
            cls.LOAD_CONFIG,
            cls.INIT_LOGGING,
            cls.INIT_DATABASE,
            cls.INIT_HEALTH,
        ]
        
        if mode == RuntimeMode.MONITOR:
            return init_stages + [cls.UPDATE_MONITORING]
        
        if mode == RuntimeMode.INGEST:
            return init_stages + [
                cls.INIT_COLLECTORS,
                cls.RUN_INGESTION,
                cls.PERSIST_RESULTS,
                cls.UPDATE_MONITORING,
            ]
        
        if mode == RuntimeMode.PROCESS:
            return init_stages + [
                cls.RUN_PROCESSING,
                cls.RUN_MARKET_CLASSIFICATION,
                cls.PERSIST_RESULTS,
                cls.UPDATE_MONITORING,
            ]
        
        if mode == RuntimeMode.RISK:
            return init_stages + [
                cls.RUN_RISK_SCORING,
                cls.RUN_RISK_BUDGET,
                cls.PERSIST_RESULTS,
                cls.UPDATE_MONITORING,
            ]
        
        if mode in (RuntimeMode.TRADE, RuntimeMode.FULL, RuntimeMode.BACKTEST):
            return cls.get_ordered_stages()
        
        return init_stages


# ============================================================
# MODULE STATUS
# ============================================================

class ModuleStatus(Enum):
    """Module lifecycle status."""
    
    NOT_STARTED = "not_started"
    """Module has not been started."""
    
    STARTING = "starting"
    """Module is starting up."""
    
    RUNNING = "running"
    """Module is running normally."""
    
    STOPPING = "stopping"
    """Module is shutting down."""
    
    STOPPED = "stopped"
    """Module has stopped cleanly."""
    
    ERROR = "error"
    """Module encountered an error."""
    
    DISABLED = "disabled"
    """Module is disabled by configuration."""
    
    @property
    def is_active(self) -> bool:
        """Check if module is active."""
        return self in (ModuleStatus.STARTING, ModuleStatus.RUNNING)
    
    @property
    def is_healthy(self) -> bool:
        """Check if module is healthy."""
        return self in (ModuleStatus.RUNNING, ModuleStatus.STOPPED, ModuleStatus.DISABLED)


# ============================================================
# STAGE RESULT
# ============================================================

@dataclass
class StageResult:
    """Result of executing a stage."""
    
    stage: ExecutionStage
    success: bool
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    error: Optional[str] = None
    error_type: Optional[str] = None
    recoverable: bool = True
    context: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration(self) -> timedelta:
        """Get duration as timedelta."""
        return timedelta(seconds=self.duration_seconds)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "stage": self.stage.stage_id,
            "success": self.success,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "error_type": self.error_type,
            "recoverable": self.recoverable,
            "context": self.context,
        }


@dataclass
class CycleResult:
    """Result of a complete execution cycle."""
    
    cycle_id: str
    mode: RuntimeMode
    started_at: datetime
    completed_at: Optional[datetime] = None
    success: bool = False
    stage_results: List[StageResult] = field(default_factory=list)
    failed_stage: Optional[ExecutionStage] = None
    error: Optional[str] = None
    
    @property
    def duration_seconds(self) -> float:
        """Get total duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0
    
    @property
    def stages_completed(self) -> int:
        """Get number of completed stages."""
        return len([r for r in self.stage_results if r.success])
    
    def add_stage_result(self, result: StageResult) -> None:
        """Add a stage result."""
        self.stage_results.append(result)
        if not result.success:
            self.failed_stage = result.stage
            self.error = result.error
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "cycle_id": self.cycle_id,
            "mode": self.mode.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "stages_completed": self.stages_completed,
            "failed_stage": self.failed_stage.stage_id if self.failed_stage else None,
            "error": self.error,
            "stage_results": [r.to_dict() for r in self.stage_results],
        }


# ============================================================
# MODULE DEFINITION
# ============================================================

@dataclass
class ModuleDefinition:
    """Definition of a module for registration."""
    
    name: str
    """Unique module name."""
    
    module_class: type
    """Module class to instantiate."""
    
    dependencies: List[str] = field(default_factory=list)
    """Names of modules this depends on."""
    
    required_stages: List[ExecutionStage] = field(default_factory=list)
    """Stages where this module is active."""
    
    config_key: Optional[str] = None
    """Configuration key for module settings."""
    
    enabled: bool = True
    """Whether module is enabled."""
    
    critical: bool = False
    """Whether module failure is critical (stops system)."""
    
    timeout_seconds: float = 60.0
    """Timeout for module operations."""


@dataclass
class ModuleInstance:
    """Runtime instance of a module."""
    
    definition: ModuleDefinition
    instance: Any
    status: ModuleStatus = ModuleStatus.NOT_STARTED
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    error: Optional[str] = None
    health_checks_passed: int = 0
    health_checks_failed: int = 0
    
    @property
    def name(self) -> str:
        """Get module name."""
        return self.definition.name
    
    @property
    def is_healthy(self) -> bool:
        """Check if module is healthy."""
        if self.status != ModuleStatus.RUNNING:
            return False
        # Require at least one health check passed
        if self.health_checks_passed == 0:
            return True  # Not yet checked
        # Check failure ratio
        total = self.health_checks_passed + self.health_checks_failed
        if total >= 3:
            failure_ratio = self.health_checks_failed / total
            return failure_ratio < 0.5
        return True


# ============================================================
# ORCHESTRATOR CONFIGURATION
# ============================================================

@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""
    
    # Runtime settings
    mode: RuntimeMode = RuntimeMode.FULL
    """Runtime mode."""
    
    tick_interval_seconds: int = 3600
    """Main loop tick interval (default 1 hour)."""
    
    max_concurrent_tasks: int = 10
    """Maximum concurrent async tasks."""
    
    # Shutdown settings
    shutdown_timeout_seconds: int = 30
    """Timeout for graceful shutdown."""
    
    drain_timeout_seconds: int = 10
    """Timeout for draining pending operations."""
    
    # Health settings
    health_check_interval_seconds: int = 30
    """Interval between health checks."""
    
    health_failure_threshold: int = 3
    """Consecutive failures before escalation."""
    
    # State persistence
    state_persistence_enabled: bool = True
    """Enable state persistence."""
    
    state_persistence_path: Optional[str] = None
    """Path for state persistence file."""
    
    # Logging
    log_level: str = "INFO"
    """Logging level."""
    
    correlation_id_prefix: str = "cycle"
    """Prefix for correlation IDs."""
    
    # Safety
    dry_run: bool = False
    """Dry run mode (no actual trades)."""
    
    require_confirmation: bool = False
    """Require confirmation before trading."""
    
    # Backtest settings
    backtest_start_date: Optional[str] = None
    """Backtest start date (ISO format)."""
    
    backtest_end_date: Optional[str] = None
    """Backtest end date (ISO format)."""
    
    backtest_speed_multiplier: float = 1.0
    """Backtest replay speed."""
    
    @classmethod
    def from_env(cls) -> "OrchestratorConfig":
        """Load configuration from environment variables."""
        return cls(
            mode=RuntimeMode(os.getenv("RUNTIME_MODE", "full")),
            tick_interval_seconds=int(os.getenv("TICK_INTERVAL_SECONDS", "3600")),
            max_concurrent_tasks=int(os.getenv("MAX_CONCURRENT_TASKS", "10")),
            shutdown_timeout_seconds=int(os.getenv("SHUTDOWN_TIMEOUT_SECONDS", "30")),
            health_check_interval_seconds=int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", "30")),
            health_failure_threshold=int(os.getenv("HEALTH_FAILURE_THRESHOLD", "3")),
            state_persistence_enabled=os.getenv("STATE_PERSISTENCE_ENABLED", "true").lower() == "true",
            state_persistence_path=os.getenv("STATE_PERSISTENCE_PATH"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
            require_confirmation=os.getenv("REQUIRE_CONFIRMATION", "false").lower() == "true",
            backtest_start_date=os.getenv("BACKTEST_START_DATE"),
            backtest_end_date=os.getenv("BACKTEST_END_DATE"),
            backtest_speed_multiplier=float(os.getenv("BACKTEST_SPEED_MULTIPLIER", "1.0")),
        )
    
    def validate(self) -> List[str]:
        """Validate configuration, return list of errors."""
        errors = []
        
        if self.tick_interval_seconds < 1:
            errors.append("tick_interval_seconds must be at least 1")
        
        if self.shutdown_timeout_seconds < 1:
            errors.append("shutdown_timeout_seconds must be at least 1")
        
        if self.mode == RuntimeMode.BACKTEST:
            if not self.backtest_start_date:
                errors.append("backtest_start_date required for backtest mode")
            if not self.backtest_end_date:
                errors.append("backtest_end_date required for backtest mode")
        
        return errors


# ============================================================
# SAFETY CONTEXT
# ============================================================

@dataclass
class SafetyContext:
    """Context for safety decisions."""
    
    risk_state_high: bool = False
    trade_guard_blocked: bool = False
    risk_controller_halted: bool = False
    data_stale: bool = False
    system_unhealthy: bool = False
    emergency_stop_active: bool = False
    
    @property
    def can_trade(self) -> bool:
        """Check if trading is allowed."""
        return not any([
            self.risk_state_high,
            self.trade_guard_blocked,
            self.risk_controller_halted,
            self.data_stale,
            self.system_unhealthy,
            self.emergency_stop_active,
        ])
    
    @property
    def block_reason(self) -> Optional[str]:
        """Get reason for trade block."""
        if self.emergency_stop_active:
            return "Emergency stop active"
        if self.risk_controller_halted:
            return "System risk controller halted"
        if self.trade_guard_blocked:
            return "Trade guard blocked"
        if self.risk_state_high:
            return "Risk state is high"
        if self.data_stale:
            return "Data is stale"
        if self.system_unhealthy:
            return "System is unhealthy"
        return None


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    # Enums
    "RuntimeMode",
    "ExecutionStage",
    "ModuleStatus",
    
    # Results
    "StageResult",
    "CycleResult",
    
    # Module
    "ModuleDefinition",
    "ModuleInstance",
    
    # Configuration
    "OrchestratorConfig",
    
    # Safety
    "SafetyContext",
]
