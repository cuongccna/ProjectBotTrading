"""
Trade Guard Absolute - Type Definitions.

============================================================
PURPOSE
============================================================
Comprehensive type definitions for the Trade Guard Absolute module.

This module is the FINAL, NON-BYPASSABLE execution gate.
It has HIGHER AUTHORITY than Strategy Engine and Risk Budget Manager.
If this module blocks a trade, NO OTHER MODULE may override it.

============================================================
DESIGN PRINCIPLES
============================================================
1. Binary decisions only: EXECUTE or BLOCK
2. No modifications, no retries, no deferrals
3. Default to BLOCK on any uncertainty
4. Deterministic and fully testable

============================================================
BLOCKING CATEGORIES
============================================================
1. System Integrity Violations
2. Execution Safety Violations
3. State Consistency Violations
4. Rule Violations
5. Environmental Emergency Conditions

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Optional, Dict, List, Any
from uuid import uuid4


# ============================================================
# DECISION OUTCOMES
# ============================================================

class GuardDecision(str, Enum):
    """
    Guard decision outcome.
    
    These are the ONLY TWO possible outcomes.
    No middle ground. No modifications.
    """
    
    EXECUTE = "EXECUTE"
    """Trade is cleared for execution."""
    
    BLOCK = "BLOCK"
    """Trade is blocked. Final. No override possible."""


class BlockSeverity(IntEnum):
    """
    Severity level of a block decision.
    
    Higher values indicate more serious conditions.
    """
    
    LOW = 1
    """Minor violation, temporary condition."""
    
    MEDIUM = 2
    """Significant violation, requires attention."""
    
    HIGH = 3
    """Serious violation, system may be compromised."""
    
    CRITICAL = 4
    """Critical violation, immediate action required."""
    
    EMERGENCY = 5
    """Emergency condition, system-wide halt triggered."""


# ============================================================
# BLOCK REASON CODES
# ============================================================

class BlockCategory(str, Enum):
    """Category of blocking condition."""
    
    SYSTEM_INTEGRITY = "SYSTEM_INTEGRITY"
    """System integrity violations."""
    
    EXECUTION_SAFETY = "EXECUTION_SAFETY"
    """Execution safety violations."""
    
    STATE_CONSISTENCY = "STATE_CONSISTENCY"
    """State consistency violations."""
    
    RULE_VIOLATION = "RULE_VIOLATION"
    """Trading rule violations."""
    
    ENVIRONMENTAL = "ENVIRONMENTAL"
    """Environmental emergency conditions."""
    
    INTERNAL_ERROR = "INTERNAL_ERROR"
    """Guard internal error (fail-safe)."""


class BlockReason(str, Enum):
    """
    Specific reason codes for blocking.
    
    Each reason maps to exactly one blocking condition.
    Codes are designed for logging, alerting, and debugging.
    """
    
    # --------------------------------------------------------
    # SYSTEM INTEGRITY VIOLATIONS (SI_xxx)
    # --------------------------------------------------------
    
    SI_MISSING_MARKET_DATA = "SI_MISSING_MARKET_DATA"
    """Market data is missing or unavailable."""
    
    SI_STALE_MARKET_DATA = "SI_STALE_MARKET_DATA"
    """Market data is stale beyond acceptable threshold."""
    
    SI_FEATURE_PIPELINE_DESYNC = "SI_FEATURE_PIPELINE_DESYNC"
    """Feature pipeline is out of sync with market data."""
    
    SI_CLOCK_DRIFT = "SI_CLOCK_DRIFT"
    """System clock drift detected beyond threshold."""
    
    SI_TIMESTAMP_INCONSISTENCY = "SI_TIMESTAMP_INCONSISTENCY"
    """Timestamp inconsistency in request or data."""
    
    SI_DUPLICATE_REQUEST = "SI_DUPLICATE_REQUEST"
    """Duplicate or replayed trade request detected."""
    
    SI_INVALID_REQUEST_SIGNATURE = "SI_INVALID_REQUEST_SIGNATURE"
    """Request signature or checksum invalid."""
    
    # --------------------------------------------------------
    # EXECUTION SAFETY VIOLATIONS (ES_xxx)
    # --------------------------------------------------------
    
    ES_EXCHANGE_API_UNSTABLE = "ES_EXCHANGE_API_UNSTABLE"
    """Exchange API is unstable or degraded."""
    
    ES_EXCHANGE_UNREACHABLE = "ES_EXCHANGE_UNREACHABLE"
    """Exchange API is unreachable."""
    
    ES_ORDER_FAILURE_THRESHOLD = "ES_ORDER_FAILURE_THRESHOLD"
    """Order submission failure rate above threshold."""
    
    ES_RATE_LIMIT_EXHAUSTED = "ES_RATE_LIMIT_EXHAUSTED"
    """API rate limit exhausted or near exhaustion."""
    
    ES_UNCONFIRMED_ORDERS = "ES_UNCONFIRMED_ORDERS"
    """Previous orders remain unconfirmed."""
    
    ES_PENDING_CANCELLATION = "ES_PENDING_CANCELLATION"
    """Orders pending cancellation exist."""
    
    ES_NETWORK_LATENCY_HIGH = "ES_NETWORK_LATENCY_HIGH"
    """Network latency exceeds acceptable threshold."""
    
    # --------------------------------------------------------
    # STATE CONSISTENCY VIOLATIONS (SC_xxx)
    # --------------------------------------------------------
    
    SC_POSITION_STATE_MISMATCH = "SC_POSITION_STATE_MISMATCH"
    """Position state mismatch between system and exchange."""
    
    SC_UNKNOWN_OPEN_ORDERS = "SC_UNKNOWN_OPEN_ORDERS"
    """Open orders exist that are unknown to the system."""
    
    SC_BALANCE_INCONSISTENCY = "SC_BALANCE_INCONSISTENCY"
    """Account balance inconsistency detected."""
    
    SC_MARGIN_STATE_UNDEFINED = "SC_MARGIN_STATE_UNDEFINED"
    """Margin or leverage state is undefined."""
    
    SC_EQUITY_MISMATCH = "SC_EQUITY_MISMATCH"
    """Equity value mismatch between sources."""
    
    SC_POSITION_SYNC_PENDING = "SC_POSITION_SYNC_PENDING"
    """Position synchronization is pending."""
    
    # --------------------------------------------------------
    # RULE VIOLATIONS (RV_xxx)
    # --------------------------------------------------------
    
    RV_OUTSIDE_TRADING_HOURS = "RV_OUTSIDE_TRADING_HOURS"
    """Trading attempted outside allowed hours."""
    
    RV_COOLDOWN_ACTIVE = "RV_COOLDOWN_ACTIVE"
    """Forced cooldown period is active."""
    
    RV_SYSTEM_HALT_STATE = "RV_SYSTEM_HALT_STATE"
    """System Risk Controller is in HALT state."""
    
    RV_MANUAL_INTERVENTION_LOCK = "RV_MANUAL_INTERVENTION_LOCK"
    """Manual intervention lock is active."""
    
    RV_MAINTENANCE_WINDOW = "RV_MAINTENANCE_WINDOW"
    """Exchange or system maintenance window active."""
    
    RV_SYMBOL_NOT_TRADEABLE = "RV_SYMBOL_NOT_TRADEABLE"
    """Symbol is not tradeable or is restricted."""
    
    RV_DIRECTION_RESTRICTED = "RV_DIRECTION_RESTRICTED"
    """Trading direction is restricted (e.g., no shorts)."""
    
    # --------------------------------------------------------
    # ENVIRONMENTAL EMERGENCY (EE_xxx)
    # --------------------------------------------------------
    
    EE_RISK_LEVEL_CRITICAL = "EE_RISK_LEVEL_CRITICAL"
    """Risk level classified as CRITICAL."""
    
    EE_SYSTEM_ESCALATION_ACTIVE = "EE_SYSTEM_ESCALATION_ACTIVE"
    """System Risk Controller escalation is active."""
    
    EE_CIRCUIT_BREAKER_TRIGGERED = "EE_CIRCUIT_BREAKER_TRIGGERED"
    """Exchange circuit breaker has triggered."""
    
    EE_EXTREME_VOLATILITY = "EE_EXTREME_VOLATILITY"
    """Extreme market volatility detected."""
    
    EE_LIQUIDITY_EMERGENCY = "EE_LIQUIDITY_EMERGENCY"
    """Liquidity emergency condition."""
    
    # --------------------------------------------------------
    # INTERNAL ERROR (IE_xxx)
    # --------------------------------------------------------
    
    IE_GUARD_INTERNAL_ERROR = "IE_GUARD_INTERNAL_ERROR"
    """Trade Guard internal error occurred."""
    
    IE_VALIDATOR_EXCEPTION = "IE_VALIDATOR_EXCEPTION"
    """Validator threw an exception."""
    
    IE_TIMEOUT = "IE_TIMEOUT"
    """Guard evaluation timed out."""
    
    IE_MISSING_INPUT = "IE_MISSING_INPUT"
    """Required input data is missing."""
    
    def get_category(self) -> BlockCategory:
        """Get the category for this reason."""
        prefix = self.value.split("_")[0]
        return {
            "SI": BlockCategory.SYSTEM_INTEGRITY,
            "ES": BlockCategory.EXECUTION_SAFETY,
            "SC": BlockCategory.STATE_CONSISTENCY,
            "RV": BlockCategory.RULE_VIOLATION,
            "EE": BlockCategory.ENVIRONMENTAL,
            "IE": BlockCategory.INTERNAL_ERROR,
        }.get(prefix, BlockCategory.INTERNAL_ERROR)
    
    def get_default_severity(self) -> BlockSeverity:
        """Get default severity for this reason."""
        # Critical reasons
        if self in (
            BlockReason.EE_RISK_LEVEL_CRITICAL,
            BlockReason.EE_SYSTEM_ESCALATION_ACTIVE,
            BlockReason.RV_SYSTEM_HALT_STATE,
            BlockReason.IE_GUARD_INTERNAL_ERROR,
        ):
            return BlockSeverity.CRITICAL
        
        # High severity
        if self in (
            BlockReason.SC_POSITION_STATE_MISMATCH,
            BlockReason.SC_BALANCE_INCONSISTENCY,
            BlockReason.ES_EXCHANGE_UNREACHABLE,
            BlockReason.EE_CIRCUIT_BREAKER_TRIGGERED,
        ):
            return BlockSeverity.HIGH
        
        # Medium severity
        if self in (
            BlockReason.SI_STALE_MARKET_DATA,
            BlockReason.ES_ORDER_FAILURE_THRESHOLD,
            BlockReason.SC_UNKNOWN_OPEN_ORDERS,
            BlockReason.RV_COOLDOWN_ACTIVE,
        ):
            return BlockSeverity.MEDIUM
        
        # Default to LOW
        return BlockSeverity.LOW


# ============================================================
# INPUT TYPES
# ============================================================

@dataclass
class TradeIntent:
    """
    Trade intent received from Risk Budget Manager.
    
    This represents a trade that has already passed:
    - Strategy Engine evaluation
    - Risk Budget Manager approval
    
    Trade Guard Absolute is the FINAL gate.
    """
    
    # Identity
    intent_id: str
    """Unique identifier for this intent."""
    
    request_id: str
    """Original request ID from strategy."""
    
    # Trade Details
    symbol: str
    """Trading pair (e.g., 'BTC/USDT')."""
    
    exchange: str
    """Exchange identifier."""
    
    direction: str
    """Trade direction: 'LONG' or 'SHORT'."""
    
    entry_price: float
    """Intended entry price."""
    
    stop_loss_price: float
    """Stop loss price."""
    
    position_size: float
    """Position size in base currency."""
    
    # Context
    strategy_id: Optional[str] = None
    """Strategy that generated this intent."""
    
    timeframe: Optional[str] = None
    """Trading timeframe."""
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    """When intent was created."""
    
    expires_at: Optional[datetime] = None
    """When intent expires."""
    
    # Validation
    checksum: Optional[str] = None
    """Request checksum for integrity validation."""
    
    def is_expired(self) -> bool:
        """Check if intent has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "intent_id": self.intent_id,
            "request_id": self.request_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss_price": self.stop_loss_price,
            "position_size": self.position_size,
            "strategy_id": self.strategy_id,
            "timeframe": self.timeframe,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass
class SystemStateSnapshot:
    """
    Snapshot of current system state.
    
    Provided by system monitoring components.
    """
    
    # Timestamps
    snapshot_time: datetime = field(default_factory=datetime.utcnow)
    """When snapshot was taken."""
    
    # Market Data Health
    market_data_available: bool = True
    """Whether market data is available."""
    
    market_data_age_seconds: float = 0.0
    """Age of most recent market data."""
    
    market_data_symbol_coverage: float = 1.0
    """Percentage of symbols with valid data."""
    
    # Feature Pipeline Health
    feature_pipeline_synced: bool = True
    """Whether feature pipeline is synchronized."""
    
    feature_pipeline_lag_seconds: float = 0.0
    """Feature pipeline lag behind market data."""
    
    # Time Synchronization
    clock_drift_ms: float = 0.0
    """System clock drift in milliseconds."""
    
    ntp_sync_valid: bool = True
    """Whether NTP synchronization is valid."""
    
    # Position State
    position_state_synced: bool = True
    """Whether position state is synchronized."""
    
    last_position_sync_seconds: float = 0.0
    """Seconds since last position sync."""
    
    # Request Tracking
    recent_request_ids: List[str] = field(default_factory=list)
    """Recent request IDs for duplicate detection."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "snapshot_time": self.snapshot_time.isoformat(),
            "market_data_available": self.market_data_available,
            "market_data_age_seconds": self.market_data_age_seconds,
            "feature_pipeline_synced": self.feature_pipeline_synced,
            "clock_drift_ms": self.clock_drift_ms,
            "position_state_synced": self.position_state_synced,
        }


@dataclass
class ExecutionHealthMetrics:
    """
    Health metrics for execution environment.
    
    Provided by Execution Engine monitoring.
    """
    
    # Exchange Connectivity
    exchange_reachable: bool = True
    """Whether exchange API is reachable."""
    
    exchange_latency_ms: float = 0.0
    """Current exchange API latency."""
    
    exchange_status: str = "OPERATIONAL"
    """Exchange operational status."""
    
    # Order Metrics
    order_success_rate_1h: float = 1.0
    """Order success rate in last hour."""
    
    order_failure_count_1h: int = 0
    """Order failure count in last hour."""
    
    pending_orders_count: int = 0
    """Number of pending/unconfirmed orders."""
    
    pending_cancellations: int = 0
    """Number of pending order cancellations."""
    
    # Rate Limits
    rate_limit_remaining: int = 1000
    """Remaining API rate limit."""
    
    rate_limit_utilization: float = 0.0
    """Rate limit utilization (0-1)."""
    
    # Network
    network_latency_ms: float = 0.0
    """Network latency to exchange."""
    
    connection_stable: bool = True
    """Whether connection is stable."""
    
    # Unknown State
    unknown_open_orders: int = 0
    """Orders on exchange not in system state."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "exchange_reachable": self.exchange_reachable,
            "exchange_latency_ms": self.exchange_latency_ms,
            "exchange_status": self.exchange_status,
            "order_success_rate_1h": self.order_success_rate_1h,
            "pending_orders_count": self.pending_orders_count,
            "rate_limit_remaining": self.rate_limit_remaining,
            "rate_limit_utilization": self.rate_limit_utilization,
            "unknown_open_orders": self.unknown_open_orders,
        }


@dataclass
class GlobalHaltState:
    """
    Global halt state from System Risk Controller.
    
    This represents the highest-level system control.
    """
    
    # Halt Status
    is_halted: bool = False
    """Whether trading is globally halted."""
    
    halt_reason: Optional[str] = None
    """Reason for halt if active."""
    
    halted_at: Optional[datetime] = None
    """When halt was initiated."""
    
    # Escalation Status
    escalation_active: bool = False
    """Whether escalation is active."""
    
    escalation_level: int = 0
    """Current escalation level (0-3)."""
    
    # Risk Level
    global_risk_level: str = "MODERATE"
    """Global risk level from Risk Scoring Engine."""
    
    risk_score: float = 0.0
    """Numerical risk score (0-1)."""
    
    # Cooldown
    cooldown_active: bool = False
    """Whether forced cooldown is active."""
    
    cooldown_expires_at: Optional[datetime] = None
    """When cooldown expires."""
    
    # Manual Intervention
    manual_lock_active: bool = False
    """Whether manual intervention lock is active."""
    
    manual_lock_by: Optional[str] = None
    """Who initiated manual lock."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_halted": self.is_halted,
            "halt_reason": self.halt_reason,
            "escalation_active": self.escalation_active,
            "escalation_level": self.escalation_level,
            "global_risk_level": self.global_risk_level,
            "risk_score": self.risk_score,
            "cooldown_active": self.cooldown_active,
            "manual_lock_active": self.manual_lock_active,
        }


@dataclass
class AccountState:
    """
    Current account state for consistency checks.
    """
    
    # Balances
    reported_equity: float = 0.0
    """Equity as reported by exchange."""
    
    calculated_equity: float = 0.0
    """Equity as calculated by system."""
    
    available_balance: float = 0.0
    """Available balance for trading."""
    
    # Positions
    open_positions_exchange: int = 0
    """Open positions count on exchange."""
    
    open_positions_system: int = 0
    """Open positions count in system."""
    
    # Margin
    margin_mode: Optional[str] = None
    """Current margin mode (CROSS/ISOLATED)."""
    
    leverage: Optional[float] = None
    """Current leverage setting."""
    
    margin_ratio: float = 0.0
    """Current margin utilization ratio."""
    
    def has_equity_mismatch(self, tolerance_pct: float = 1.0) -> bool:
        """Check if equity values mismatch beyond tolerance."""
        if self.reported_equity == 0:
            return self.calculated_equity != 0
        
        diff_pct = abs(self.reported_equity - self.calculated_equity) / self.reported_equity * 100
        return diff_pct > tolerance_pct
    
    def has_position_mismatch(self) -> bool:
        """Check if position counts mismatch."""
        return self.open_positions_exchange != self.open_positions_system


@dataclass 
class EnvironmentalContext:
    """
    Environmental context for the trade evaluation.
    """
    
    # Market Conditions
    current_volatility: float = 0.0
    """Current volatility level."""
    
    volatility_regime: str = "NORMAL"
    """Volatility regime classification."""
    
    liquidity_score: float = 1.0
    """Liquidity score (0-1)."""
    
    spread_pct: float = 0.0
    """Current bid-ask spread percentage."""
    
    # Exchange Status
    exchange_maintenance: bool = False
    """Whether exchange maintenance is scheduled."""
    
    circuit_breaker_active: bool = False
    """Whether exchange circuit breaker is active."""
    
    # Trading Hours
    is_trading_hours: bool = True
    """Whether within allowed trading hours."""
    
    hours_restriction_reason: Optional[str] = None
    """Reason if outside trading hours."""
    
    # Symbol Status
    symbol_tradeable: bool = True
    """Whether symbol is tradeable."""
    
    symbol_restriction: Optional[str] = None
    """Restriction reason if not tradeable."""


@dataclass
class GuardInput:
    """
    Complete input package for Trade Guard Absolute.
    
    Aggregates all required inputs for guard evaluation.
    """
    
    trade_intent: TradeIntent
    """Trade intent to evaluate."""
    
    system_state: SystemStateSnapshot
    """Current system state snapshot."""
    
    execution_health: ExecutionHealthMetrics
    """Execution environment health."""
    
    halt_state: GlobalHaltState
    """Global halt state."""
    
    account_state: AccountState
    """Current account state."""
    
    environment: EnvironmentalContext
    """Environmental context."""
    
    # Evaluation Metadata
    evaluation_id: str = field(default_factory=lambda: str(uuid4()))
    """Unique ID for this evaluation."""
    
    received_at: datetime = field(default_factory=datetime.utcnow)
    """When input was received."""


# ============================================================
# OUTPUT TYPES
# ============================================================

@dataclass
class ValidationResult:
    """
    Result of a single validation check.
    """
    
    validator_name: str
    """Name of the validator."""
    
    passed: bool
    """Whether validation passed."""
    
    block_reason: Optional[BlockReason] = None
    """Reason if blocked."""
    
    severity: Optional[BlockSeverity] = None
    """Severity if blocked."""
    
    details: Optional[str] = None
    """Additional details."""
    
    checked_at: datetime = field(default_factory=datetime.utcnow)
    """When check was performed."""
    
    check_duration_ms: float = 0.0
    """Duration of check in milliseconds."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "validator_name": self.validator_name,
            "passed": self.passed,
            "block_reason": self.block_reason.value if self.block_reason else None,
            "severity": self.severity.value if self.severity else None,
            "details": self.details,
            "checked_at": self.checked_at.isoformat(),
            "check_duration_ms": self.check_duration_ms,
        }


@dataclass
class GuardDecisionOutput:
    """
    Output from Trade Guard Absolute.
    
    This is the FINAL decision. No appeals. No overrides.
    """
    
    # Core Decision
    decision: GuardDecision
    """The decision: EXECUTE or BLOCK."""
    
    evaluation_id: str
    """Unique evaluation identifier."""
    
    intent_id: str
    """ID of the trade intent evaluated."""
    
    # Block Details (if blocked)
    block_reason: Optional[BlockReason] = None
    """Primary block reason if blocked."""
    
    block_category: Optional[BlockCategory] = None
    """Category of block reason."""
    
    severity: Optional[BlockSeverity] = None
    """Severity level if blocked."""
    
    block_details: Optional[str] = None
    """Human-readable block details."""
    
    # All Validation Results
    validation_results: List[ValidationResult] = field(default_factory=list)
    """Results of all validation checks."""
    
    failed_validations: List[ValidationResult] = field(default_factory=list)
    """Only the failed validations."""
    
    # Timing
    decision_timestamp: datetime = field(default_factory=datetime.utcnow)
    """When decision was made."""
    
    evaluation_duration_ms: float = 0.0
    """Total evaluation duration."""
    
    # Metadata
    guard_version: str = "1.0.0"
    """Trade Guard version."""
    
    def is_blocked(self) -> bool:
        """Check if trade is blocked."""
        return self.decision == GuardDecision.BLOCK
    
    def is_cleared(self) -> bool:
        """Check if trade is cleared for execution."""
        return self.decision == GuardDecision.EXECUTE
    
    def format_summary(self) -> str:
        """Format a human-readable summary."""
        if self.decision == GuardDecision.EXECUTE:
            return f"✅ EXECUTE | Intent: {self.intent_id} | Evaluation: {self.evaluation_id}"
        else:
            return (
                f"🛑 BLOCK | Intent: {self.intent_id} | "
                f"Reason: {self.block_reason.value if self.block_reason else 'UNKNOWN'} | "
                f"Severity: {self.severity.name if self.severity else 'UNKNOWN'}"
            )
    
    def format_alert_message(self) -> str:
        """Format message for alerting."""
        if self.decision == GuardDecision.EXECUTE:
            return ""
        
        lines = [
            "🛑 *TRADE BLOCKED*",
            "",
            f"Intent: `{self.intent_id}`",
            f"Reason: `{self.block_reason.value if self.block_reason else 'UNKNOWN'}`",
            f"Category: {self.block_category.value if self.block_category else 'UNKNOWN'}",
            f"Severity: {self.severity.name if self.severity else 'UNKNOWN'}",
        ]
        
        if self.block_details:
            lines.extend(["", f"Details: {self.block_details}"])
        
        lines.extend([
            "",
            f"🕐 {self.decision_timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ])
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "decision": self.decision.value,
            "evaluation_id": self.evaluation_id,
            "intent_id": self.intent_id,
            "block_reason": self.block_reason.value if self.block_reason else None,
            "block_category": self.block_category.value if self.block_category else None,
            "severity": self.severity.value if self.severity else None,
            "block_details": self.block_details,
            "validation_results": [v.to_dict() for v in self.validation_results],
            "failed_validations": [v.to_dict() for v in self.failed_validations],
            "decision_timestamp": self.decision_timestamp.isoformat(),
            "evaluation_duration_ms": self.evaluation_duration_ms,
            "guard_version": self.guard_version,
        }


# ============================================================
# ERROR TYPES
# ============================================================

class TradeGuardError(Exception):
    """Base exception for Trade Guard errors."""
    pass


class ValidationError(TradeGuardError):
    """Raised when validation encounters an error."""
    pass


class InputError(TradeGuardError):
    """Raised when input data is invalid or missing."""
    pass


class TimeoutError(TradeGuardError):
    """Raised when evaluation times out."""
    pass
