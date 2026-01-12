"""
System Risk Controller - Type Definitions.

============================================================
ABSOLUTE AUTHORITY
============================================================
This module has the highest authority in the entire system.
When it says HALT, everything stops. No exceptions.

============================================================
CORE PRINCIPLE
============================================================
If the system cannot TRUST its own data, state, or execution,
IT MUST STOP.

Profit is irrelevant.
Continuity is irrelevant.
Safety is absolute.

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Optional, List, Dict, Any


# ============================================================
# SYSTEM STATES
# ============================================================

class SystemState(str, Enum):
    """
    System operational states.
    
    Transitions are strictly controlled:
    - RUNNING → DEGRADED → HALTED_SOFT → HALTED_HARD → EMERGENCY_LOCKDOWN
    - Reverse transitions require manual intervention for HARD/EMERGENCY
    """
    
    RUNNING = "RUNNING"
    """
    Normal operation.
    All systems functional.
    Trading allowed.
    """
    
    DEGRADED = "DEGRADED"
    """
    Reduced functionality.
    Non-critical issues detected.
    Trading allowed with caution.
    """
    
    HALTED_SOFT = "HALTED_SOFT"
    """
    Level 1: Soft Halt.
    - Pause new trades
    - Allow position management
    - Notify operators
    Auto-resume possible after conditions clear.
    """
    
    HALTED_HARD = "HALTED_HARD"
    """
    Level 2: Hard Halt.
    - Cancel all pending orders
    - Freeze trading
    - Lock strategy execution
    MANUAL INTERVENTION REQUIRED to resume.
    """
    
    EMERGENCY_LOCKDOWN = "EMERGENCY_LOCKDOWN"
    """
    Level 3: Emergency.
    - Close positions if possible
    - Disable execution engine
    - Full system lockdown
    MANUAL INTERVENTION REQUIRED to resume.
    """
    
    def allows_new_trades(self) -> bool:
        """Check if state allows new trades."""
        return self in (SystemState.RUNNING, SystemState.DEGRADED)
    
    def allows_position_management(self) -> bool:
        """Check if state allows position management."""
        return self in (SystemState.RUNNING, SystemState.DEGRADED, SystemState.HALTED_SOFT)
    
    def requires_manual_resume(self) -> bool:
        """Check if manual intervention is required to resume."""
        return self in (SystemState.HALTED_HARD, SystemState.EMERGENCY_LOCKDOWN)
    
    def is_halted(self) -> bool:
        """Check if system is in any halt state."""
        return self in (
            SystemState.HALTED_SOFT,
            SystemState.HALTED_HARD,
            SystemState.EMERGENCY_LOCKDOWN,
        )


# ============================================================
# HALT LEVELS
# ============================================================

class HaltLevel(IntEnum):
    """
    Halt severity levels.
    
    Higher levels are more severe.
    System escalates to highest triggered level.
    """
    
    NONE = 0
    """No halt."""
    
    SOFT = 1
    """
    Level 1: Soft Halt.
    Pause new trades, allow position management.
    """
    
    HARD = 2
    """
    Level 2: Hard Halt.
    Cancel pending orders, freeze trading.
    """
    
    EMERGENCY = 3
    """
    Level 3: Emergency.
    Close positions, full lockdown.
    """
    
    def to_system_state(self) -> SystemState:
        """Convert halt level to system state."""
        mapping = {
            HaltLevel.NONE: SystemState.RUNNING,
            HaltLevel.SOFT: SystemState.HALTED_SOFT,
            HaltLevel.HARD: SystemState.HALTED_HARD,
            HaltLevel.EMERGENCY: SystemState.EMERGENCY_LOCKDOWN,
        }
        return mapping[self]


# ============================================================
# HALT TRIGGER CATEGORIES
# ============================================================

class TriggerCategory(str, Enum):
    """
    Categories of halt triggers.
    """
    
    DATA_INTEGRITY = "DATA_INTEGRITY"
    """Data-related failures."""
    
    PROCESSING = "PROCESSING"
    """Processing pipeline failures."""
    
    EXECUTION = "EXECUTION"
    """Execution anomalies."""
    
    CONTROL = "CONTROL"
    """Risk/control limit violations."""
    
    INFRASTRUCTURE = "INFRASTRUCTURE"
    """Infrastructure failures."""
    
    MANUAL = "MANUAL"
    """Manual operator intervention."""
    
    INTERNAL = "INTERNAL"
    """Internal controller errors."""


# ============================================================
# HALT TRIGGERS
# ============================================================

class HaltTrigger(str, Enum):
    """
    Specific halt triggers with category prefixes.
    
    Naming convention:
    - DI_ = Data Integrity
    - PR_ = Processing
    - EX_ = Execution
    - CT_ = Control
    - IF_ = Infrastructure
    - MN_ = Manual
    - IN_ = Internal
    """
    
    # === DATA INTEGRITY ===
    DI_MISSING_CRITICAL_DATA = "DI_MISSING_CRITICAL_DATA"
    """Critical data inputs are missing."""
    
    DI_STALE_DATA = "DI_STALE_DATA"
    """Data is stale beyond allowed thresholds."""
    
    DI_SCHEMA_MISMATCH = "DI_SCHEMA_MISMATCH"
    """Schema mismatch or corrupted payloads."""
    
    DI_INGESTION_FAILURE = "DI_INGESTION_FAILURE"
    """Repeated data ingestion failures."""
    
    DI_CORRUPTED_PAYLOAD = "DI_CORRUPTED_PAYLOAD"
    """Corrupted or invalid data detected."""
    
    DI_PRICE_DEVIATION = "DI_PRICE_DEVIATION"
    """
    Stored price deviates significantly from live reference.
    Triggered by DataRealityGuard when deviation exceeds threshold.
    """
    
    DI_DATA_REALITY_FAILURE = "DI_DATA_REALITY_FAILURE"
    """
    DataRealityGuard check failed.
    System cannot trust its market data.
    """
    
    # === PROCESSING ===
    PR_FEATURE_PIPELINE_ERROR = "PR_FEATURE_PIPELINE_ERROR"
    """Feature pipeline processing errors."""
    
    PR_INCONSISTENT_STATE = "PR_INCONSISTENT_STATE"
    """Inconsistent processing states."""
    
    PR_NON_DETERMINISTIC_OUTPUT = "PR_NON_DETERMINISTIC_OUTPUT"
    """Non-deterministic outputs detected."""
    
    PR_VERSION_MISMATCH = "PR_VERSION_MISMATCH"
    """Version mismatch between data and models."""
    
    PR_PROCESSING_TIMEOUT = "PR_PROCESSING_TIMEOUT"
    """Processing exceeded timeout."""
    
    # === EXECUTION ===
    EX_REPEATED_REJECTIONS = "EX_REPEATED_REJECTIONS"
    """Orders rejected repeatedly."""
    
    EX_SLIPPAGE_EXCEEDED = "EX_SLIPPAGE_EXCEEDED"
    """Slippage beyond hard limits."""
    
    EX_POSITION_MISMATCH = "EX_POSITION_MISMATCH"
    """Position mismatch with exchange."""
    
    EX_UNCONFIRMED_EXECUTION = "EX_UNCONFIRMED_EXECUTION"
    """Unconfirmed order executions."""
    
    EX_EXCHANGE_ERROR = "EX_EXCHANGE_ERROR"
    """Exchange API errors."""
    
    EX_ORDER_STUCK = "EX_ORDER_STUCK"
    """Orders stuck in pending state."""
    
    # === CONTROL ===
    CT_RISK_LIMIT_VIOLATED = "CT_RISK_LIMIT_VIOLATED"
    """Risk limits violated."""
    
    CT_LEVERAGE_EXCEEDED = "CT_LEVERAGE_EXCEEDED"
    """Unexpected leverage exposure."""
    
    CT_DRAWDOWN_EXCEEDED = "CT_DRAWDOWN_EXCEEDED"
    """Drawdown beyond absolute threshold."""
    
    CT_STRATEGY_DEVIATION = "CT_STRATEGY_DEVIATION"
    """Strategy behavior deviates from backtested envelope."""
    
    CT_LOSS_LIMIT_BREACHED = "CT_LOSS_LIMIT_BREACHED"
    """Daily/hourly loss limit breached."""
    
    CT_EXPOSURE_LIMIT_BREACHED = "CT_EXPOSURE_LIMIT_BREACHED"
    """Exposure limits breached."""
    
    # === INFRASTRUCTURE ===
    IF_VPS_UNSTABLE = "IF_VPS_UNSTABLE"
    """VPS instability detected."""
    
    IF_NETWORK_LATENCY = "IF_NETWORK_LATENCY"
    """Network latency spikes."""
    
    IF_SERVICE_CRASH = "IF_SERVICE_CRASH"
    """Service crash or deadlock."""
    
    IF_CLOCK_DESYNC = "IF_CLOCK_DESYNC"
    """Clock desynchronization."""
    
    IF_MEMORY_EXHAUSTED = "IF_MEMORY_EXHAUSTED"
    """Memory exhaustion."""
    
    IF_DISK_EXHAUSTED = "IF_DISK_EXHAUSTED"
    """Disk space exhausted."""
    
    IF_DATABASE_ERROR = "IF_DATABASE_ERROR"
    """Database connection/operation failure."""
    
    # === MANUAL ===
    MN_OPERATOR_HALT = "MN_OPERATOR_HALT"
    """Operator-initiated halt."""
    
    MN_EMERGENCY_STOP = "MN_EMERGENCY_STOP"
    """Emergency stop button pressed."""
    
    MN_MAINTENANCE = "MN_MAINTENANCE"
    """Scheduled maintenance."""
    
    MN_COMMITTEE_BLOCK = "MN_COMMITTEE_BLOCK"
    """Risk Committee issued BLOCK decision."""
    
    MN_COMMITTEE_HOLD = "MN_COMMITTEE_HOLD"
    """Risk Committee issued HOLD decision."""
    
    # === INTERNAL ===
    IN_CONTROLLER_ERROR = "IN_CONTROLLER_ERROR"
    """Internal controller error."""
    
    IN_STATE_CORRUPTION = "IN_STATE_CORRUPTION"
    """Controller state corruption."""
    
    IN_UNKNOWN_ERROR = "IN_UNKNOWN_ERROR"
    """Unknown/unhandled error."""
    
    def get_category(self) -> TriggerCategory:
        """Get the category for this trigger."""
        prefix = self.value.split("_")[0]
        mapping = {
            "DI": TriggerCategory.DATA_INTEGRITY,
            "PR": TriggerCategory.PROCESSING,
            "EX": TriggerCategory.EXECUTION,
            "CT": TriggerCategory.CONTROL,
            "IF": TriggerCategory.INFRASTRUCTURE,
            "MN": TriggerCategory.MANUAL,
            "IN": TriggerCategory.INTERNAL,
        }
        return mapping.get(prefix, TriggerCategory.INTERNAL)
    
    def get_default_halt_level(self) -> HaltLevel:
        """Get the default halt level for this trigger."""
        # Emergency level triggers
        emergency_triggers = {
            HaltTrigger.EX_POSITION_MISMATCH,
            HaltTrigger.CT_DRAWDOWN_EXCEEDED,
            HaltTrigger.CT_LEVERAGE_EXCEEDED,
            HaltTrigger.IN_STATE_CORRUPTION,
            HaltTrigger.MN_EMERGENCY_STOP,
            HaltTrigger.IF_SERVICE_CRASH,
        }
        
        # Hard halt triggers
        hard_triggers = {
            HaltTrigger.DI_MISSING_CRITICAL_DATA,
            HaltTrigger.DI_CORRUPTED_PAYLOAD,
            HaltTrigger.PR_NON_DETERMINISTIC_OUTPUT,
            HaltTrigger.EX_REPEATED_REJECTIONS,
            HaltTrigger.EX_SLIPPAGE_EXCEEDED,
            HaltTrigger.EX_UNCONFIRMED_EXECUTION,
            HaltTrigger.CT_RISK_LIMIT_VIOLATED,
            HaltTrigger.CT_LOSS_LIMIT_BREACHED,
            HaltTrigger.IF_DATABASE_ERROR,
            HaltTrigger.IN_CONTROLLER_ERROR,
            HaltTrigger.MN_OPERATOR_HALT,
        }
        
        if self in emergency_triggers:
            return HaltLevel.EMERGENCY
        elif self in hard_triggers:
            return HaltLevel.HARD
        else:
            return HaltLevel.SOFT


# ============================================================
# HALT EVENT
# ============================================================

@dataclass
class HaltEvent:
    """
    A single halt trigger event.
    
    Captures everything needed for audit and alerting.
    """
    
    event_id: str
    """Unique event identifier."""
    
    trigger: HaltTrigger
    """The trigger that caused this event."""
    
    halt_level: HaltLevel
    """The halt level for this event."""
    
    timestamp: datetime
    """When the event occurred."""
    
    source_monitor: str
    """Which monitor detected the issue."""
    
    message: str
    """Human-readable description."""
    
    details: Dict[str, Any] = field(default_factory=dict)
    """Additional context and metrics."""
    
    acknowledged: bool = False
    """Whether the event has been acknowledged."""
    
    acknowledged_by: Optional[str] = None
    """Who acknowledged the event."""
    
    acknowledged_at: Optional[datetime] = None
    """When the event was acknowledged."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "trigger": self.trigger.value,
            "category": self.trigger.get_category().value,
            "halt_level": self.halt_level.name,
            "timestamp": self.timestamp.isoformat(),
            "source_monitor": self.source_monitor,
            "message": self.message,
            "details": self.details,
            "acknowledged": self.acknowledged,
        }
    
    def format_alert_message(self) -> str:
        """Format for Telegram alert."""
        level_emoji = {
            HaltLevel.SOFT: "🟡",
            HaltLevel.HARD: "🔴",
            HaltLevel.EMERGENCY: "🚨",
        }
        emoji = level_emoji.get(self.halt_level, "⚠️")
        
        lines = [
            f"{emoji} **SYSTEM HALT - {self.halt_level.name}** {emoji}",
            "",
            f"**Trigger:** `{self.trigger.value}`",
            f"**Category:** {self.trigger.get_category().value}",
            f"**Source:** {self.source_monitor}",
            "",
            f"**Message:**",
            self.message,
            "",
            f"**Time:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC",
            f"**Event ID:** `{self.event_id}`",
        ]
        
        if self.halt_level in (HaltLevel.HARD, HaltLevel.EMERGENCY):
            lines.extend([
                "",
                "⚠️ **MANUAL INTERVENTION REQUIRED** ⚠️",
            ])
        
        return "\n".join(lines)


# ============================================================
# STATE TRANSITION
# ============================================================

@dataclass
class StateTransition:
    """
    Record of a state transition.
    """
    
    from_state: SystemState
    """Previous state."""
    
    to_state: SystemState
    """New state."""
    
    timestamp: datetime
    """When the transition occurred."""
    
    reason: str = ""
    """Reason for the transition."""
    
    transition_id: Optional[str] = None
    """Unique transition identifier."""
    
    trigger_event_id: Optional[str] = None
    """Event that caused the transition (if any)."""
    
    trigger: Optional[str] = None
    """Trigger that caused the transition."""
    
    initiated_by: Optional[str] = None
    """Who/what initiated the transition."""
    
    is_automatic: bool = False
    """Whether this was an automatic transition."""
    
    def __post_init__(self):
        """Generate transition_id if not provided."""
        if self.transition_id is None:
            self.transition_id = f"trans_{self.timestamp.strftime('%Y%m%d_%H%M%S')}_{id(self) % 10000:04d}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "transition_id": self.transition_id,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "trigger_event_id": self.trigger_event_id,
            "trigger": self.trigger,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "initiated_by": self.initiated_by,
            "is_automatic": self.is_automatic,
        }


# ============================================================
# MONITOR RESULT
# ============================================================

@dataclass
class MonitorResult:
    """
    Result from a health monitor check.
    """
    
    monitor_name: str
    """Name of the monitor."""
    
    is_healthy: bool
    """Whether the monitored component is healthy."""
    
    halt_event: Optional[HaltEvent] = None
    """Halt event if unhealthy."""
    
    metrics: Dict[str, Any] = field(default_factory=dict)
    """Monitored metrics."""
    
    check_time_ms: float = 0.0
    """Time taken for the check."""
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """When the check was performed."""


# ============================================================
# SYSTEM HEALTH SNAPSHOT
# ============================================================

@dataclass
class SystemHealthSnapshot:
    """
    Complete snapshot of system health.
    
    Used for status queries and dashboards.
    """
    
    current_state: SystemState
    """Current system state."""
    
    halt_level: HaltLevel
    """Current halt level."""
    
    active_halt_events: List[HaltEvent]
    """Active (unacknowledged) halt events."""
    
    monitor_results: Dict[str, MonitorResult]
    """Latest result from each monitor."""
    
    timestamp: datetime
    """When the snapshot was taken."""
    
    uptime_seconds: float
    """Controller uptime."""
    
    last_state_change: Optional[datetime]
    """When state last changed."""
    
    total_halts_today: int = 0
    """Number of halts today."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "current_state": self.current_state.value,
            "halt_level": self.halt_level.name,
            "active_halt_events": len(self.active_halt_events),
            "monitors": {
                name: {
                    "healthy": result.is_healthy,
                    "check_time_ms": result.check_time_ms,
                }
                for name, result in self.monitor_results.items()
            },
            "timestamp": self.timestamp.isoformat(),
            "uptime_seconds": self.uptime_seconds,
        }


# ============================================================
# RESUME REQUEST
# ============================================================

@dataclass
class ResumeRequest:
    """
    Request to resume from a halt state.
    """
    
    request_id: str
    """Unique request identifier."""
    
    requested_by: str
    """Who is requesting the resume."""
    
    target_state: SystemState
    """State to resume to."""
    
    reason: str
    """Reason for the resume."""
    
    acknowledgments: List[str] = field(default_factory=list)
    """Event IDs being acknowledged."""
    
    force: bool = False
    """Force resume (dangerous)."""
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """When the request was made."""


# ============================================================
# ERRORS
# ============================================================

class SystemRiskControllerError(Exception):
    """Base exception for System Risk Controller."""
    pass


class InvalidStateTransitionError(SystemRiskControllerError):
    """Raised when an invalid state transition is attempted."""
    
    def __init__(
        self,
        from_state: SystemState,
        to_state: SystemState,
        reason: str = "",
    ):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition from {from_state.value} to {to_state.value}: {reason}"
        )


class ResumeNotAllowedError(SystemRiskControllerError):
    """Raised when resume is not allowed."""
    pass


class MonitorError(SystemRiskControllerError):
    """Raised when a monitor fails."""
    pass
