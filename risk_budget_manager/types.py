"""
Risk Budget Manager - Type Definitions.

============================================================
PURPOSE
============================================================
Comprehensive type definitions for the Risk Budget Manager module.

This module acts as a GATEKEEPER between Signal Engine and Execution Engine,
enforcing capital preservation through strict risk budget controls.

============================================================
DESIGN PRINCIPLES
============================================================
1. Risk budget = maximum allowable loss (NOT position size)
2. All values expressed as percentage of account equity
3. Capital-agnostic: works from 1500 USD to any scale
4. Deterministic: no ML, no adaptive behavior

============================================================
RISK BUDGET DIMENSIONS
============================================================
1. Per-Trade Risk: Maximum loss allowed on a single trade
2. Daily Risk: Cumulative risk allowed per calendar day
3. Open Position Risk: Total risk across all open positions
4. Drawdown Limit: System-wide emergency halt threshold

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

class TradeDecision(str, Enum):
    """
    Decision outcome for trade requests.
    
    These are the ONLY possible responses from the Risk Budget Manager.
    Every trade request MUST receive one of these decisions.
    """
    
    ALLOW_TRADE = "ALLOW_TRADE"
    """Trade is allowed at requested size."""
    
    REDUCE_SIZE = "REDUCE_SIZE"
    """Trade allowed but size must be reduced to fit budget."""
    
    REJECT_TRADE = "REJECT_TRADE"
    """Trade is rejected - no size would fit current budget."""


class RejectReason(str, Enum):
    """
    Reason codes for trade rejection or size reduction.
    
    Provides clear, actionable feedback on WHY a decision was made.
    """
    
    # Per-Trade Budget Violations
    EXCEEDS_PER_TRADE_LIMIT = "EXCEEDS_PER_TRADE_LIMIT"
    """Proposed risk exceeds maximum per-trade risk budget."""
    
    # Daily Budget Violations
    DAILY_BUDGET_EXHAUSTED = "DAILY_BUDGET_EXHAUSTED"
    """No remaining daily risk budget available."""
    
    EXCEEDS_REMAINING_DAILY = "EXCEEDS_REMAINING_DAILY"
    """Proposed risk exceeds remaining daily budget."""
    
    # Open Position Violations
    OPEN_RISK_LIMIT_REACHED = "OPEN_RISK_LIMIT_REACHED"
    """Maximum concurrent open position risk reached."""
    
    EXCEEDS_REMAINING_OPEN = "EXCEEDS_REMAINING_OPEN"
    """Proposed risk exceeds remaining open position budget."""
    
    # System-Wide Violations
    DRAWDOWN_LIMIT_BREACHED = "DRAWDOWN_LIMIT_BREACHED"
    """System drawdown has exceeded emergency halt threshold."""
    
    TRADING_HALTED = "TRADING_HALTED"
    """Trading is halted by System Risk Controller."""
    
    # Data/System Errors
    STALE_EQUITY_DATA = "STALE_EQUITY_DATA"
    """Account equity data is missing or stale."""
    
    CALCULATION_ERROR = "CALCULATION_ERROR"
    """Error occurred during risk calculation."""
    
    INCONSISTENT_POSITION_STATE = "INCONSISTENT_POSITION_STATE"
    """Position state is inconsistent with expected state."""
    
    MISSING_STOP_LOSS = "MISSING_STOP_LOSS"
    """Trade request missing required stop loss."""
    
    INVALID_PARAMETERS = "INVALID_PARAMETERS"
    """Trade request contains invalid parameters."""
    
    # Concurrent Position Violations
    MAX_POSITIONS_REACHED = "MAX_POSITIONS_REACHED"
    """Maximum number of concurrent positions reached."""
    
    DUPLICATE_SYMBOL_POSITION = "DUPLICATE_SYMBOL_POSITION"
    """Already have an open position on this symbol."""


class RiskBudgetDimension(str, Enum):
    """
    Dimensions of risk budget being checked.
    
    Each dimension operates independently - ALL must pass for ALLOW_TRADE.
    """
    
    PER_TRADE = "PER_TRADE"
    """Single trade risk limit."""
    
    DAILY_CUMULATIVE = "DAILY_CUMULATIVE"
    """Daily cumulative risk limit."""
    
    OPEN_POSITION = "OPEN_POSITION"
    """Total open position risk limit."""
    
    DRAWDOWN = "DRAWDOWN"
    """System-wide drawdown limit."""


class AlertSeverity(str, Enum):
    """Alert severity levels for notifications."""
    
    INFO = "INFO"
    """Informational - normal operations."""
    
    WARNING = "WARNING"
    """Warning - approaching limits."""
    
    CRITICAL = "CRITICAL"
    """Critical - action required immediately."""
    
    EMERGENCY = "EMERGENCY"
    """Emergency - system halt triggered."""


class PositionStatus(str, Enum):
    """Status of a tracked position."""
    
    OPEN = "OPEN"
    """Position is currently open."""
    
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    """Position has been partially closed."""
    
    CLOSED = "CLOSED"
    """Position is fully closed."""
    
    EXPIRED = "EXPIRED"
    """Position expired without closure confirmation."""


class BudgetResetPeriod(str, Enum):
    """Period for budget reset."""
    
    DAILY = "DAILY"
    """Reset at start of each trading day."""
    
    WEEKLY = "WEEKLY"
    """Reset at start of each week."""
    
    MONTHLY = "MONTHLY"
    """Reset at start of each month."""


# ============================================================
# REQUEST TYPES
# ============================================================

@dataclass
class TradeRiskRequest:
    """
    Request to check if a trade is allowed within risk budget.
    
    This is the INPUT to the Risk Budget Manager from the Execution Engine.
    Contains all information needed to calculate proposed risk.
    
    ============================================================
    REQUIRED FIELDS
    ============================================================
    - symbol: Trading pair (e.g., "BTC/USDT")
    - entry_price: Proposed entry price
    - stop_loss_price: Required stop loss price
    - position_size: Proposed position size in base currency
    - direction: LONG or SHORT
    
    ============================================================
    RISK CALCULATION
    ============================================================
    Proposed Risk = |entry_price - stop_loss_price| / entry_price * position_value
    Risk Percentage = Proposed Risk / Account Equity * 100
    
    ============================================================
    """
    
    # Required Fields
    symbol: str
    """Trading pair (e.g., 'BTC/USDT')."""
    
    exchange: str
    """Exchange identifier."""
    
    entry_price: float
    """Proposed entry price."""
    
    stop_loss_price: float
    """Required stop loss price - MANDATORY."""
    
    position_size: float
    """Proposed position size in base currency units."""
    
    direction: str
    """Trade direction: 'LONG' or 'SHORT'."""
    
    # Optional Context
    strategy_id: Optional[str] = None
    """ID of the strategy generating this request."""
    
    intent_id: Optional[str] = None
    """ID of the TradeIntent from Strategy Engine."""
    
    timeframe: Optional[str] = None
    """Timeframe of the trade."""
    
    take_profit_price: Optional[float] = None
    """Optional take profit price."""
    
    # Request Metadata
    request_id: str = field(default_factory=lambda: str(uuid4()))
    """Unique identifier for this request."""
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """When this request was created."""
    
    def calculate_risk_amount(self) -> float:
        """
        Calculate the dollar risk amount for this trade.
        
        Returns:
            Risk amount in quote currency (e.g., USD)
        """
        if self.direction == "LONG":
            risk_per_unit = self.entry_price - self.stop_loss_price
        else:
            risk_per_unit = self.stop_loss_price - self.entry_price
        
        return abs(risk_per_unit * self.position_size)
    
    def calculate_risk_percentage(self, account_equity: float) -> float:
        """
        Calculate risk as percentage of account equity.
        
        Args:
            account_equity: Current account equity in quote currency
        
        Returns:
            Risk as percentage (e.g., 0.5 for 0.5%)
        """
        if account_equity <= 0:
            return float('inf')
        
        risk_amount = self.calculate_risk_amount()
        return (risk_amount / account_equity) * 100
    
    def calculate_position_value(self) -> float:
        """
        Calculate total position value.
        
        Returns:
            Position value in quote currency
        """
        return self.entry_price * self.position_size
    
    def validate(self) -> List[str]:
        """
        Validate the request parameters.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        if not self.symbol:
            errors.append("Symbol is required")
        
        if self.entry_price <= 0:
            errors.append("Entry price must be positive")
        
        if self.stop_loss_price <= 0:
            errors.append("Stop loss price must be positive")
        
        if self.position_size <= 0:
            errors.append("Position size must be positive")
        
        if self.direction not in ("LONG", "SHORT"):
            errors.append("Direction must be 'LONG' or 'SHORT'")
        
        # Validate stop loss makes sense for direction
        if self.direction == "LONG" and self.stop_loss_price >= self.entry_price:
            errors.append("Stop loss must be below entry for LONG")
        
        if self.direction == "SHORT" and self.stop_loss_price <= self.entry_price:
            errors.append("Stop loss must be above entry for SHORT")
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "entry_price": self.entry_price,
            "stop_loss_price": self.stop_loss_price,
            "position_size": self.position_size,
            "direction": self.direction,
            "strategy_id": self.strategy_id,
            "intent_id": self.intent_id,
            "timeframe": self.timeframe,
            "take_profit_price": self.take_profit_price,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class EquityUpdate:
    """
    Account equity update from Account Monitor.
    
    The Risk Budget Manager MUST receive regular equity updates
    to calculate percentage-based risk limits accurately.
    """
    
    account_equity: float
    """Total account equity in quote currency (USD)."""
    
    available_balance: float
    """Available balance for new positions."""
    
    unrealized_pnl: float
    """Unrealized P&L from open positions."""
    
    realized_pnl_today: float
    """Realized P&L for current trading day."""
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """When this update was generated."""
    
    exchange: str = "binance"
    """Exchange this equity belongs to."""
    
    is_valid: bool = True
    """Whether this update is considered valid."""
    
    def calculate_drawdown(self, peak_equity: float) -> float:
        """
        Calculate current drawdown from peak.
        
        Args:
            peak_equity: Historical peak equity value
        
        Returns:
            Drawdown as percentage (e.g., 5.0 for 5%)
        """
        if peak_equity <= 0:
            return 0.0
        
        drawdown = (peak_equity - self.account_equity) / peak_equity * 100
        return max(0.0, drawdown)
    
    def is_stale(self, max_age_seconds: int = 60) -> bool:
        """
        Check if this update is stale.
        
        Args:
            max_age_seconds: Maximum acceptable age
        
        Returns:
            True if update is stale
        """
        age = (datetime.utcnow() - self.timestamp).total_seconds()
        return age > max_age_seconds


# ============================================================
# RESPONSE TYPES
# ============================================================

@dataclass
class BudgetCheckResult:
    """
    Result of checking a single budget dimension.
    
    Each dimension is checked independently and returns this result.
    """
    
    dimension: RiskBudgetDimension
    """Which dimension was checked."""
    
    passed: bool
    """Whether the check passed."""
    
    budget_limit: float
    """The configured limit (percentage)."""
    
    budget_used: float
    """Currently used budget (percentage)."""
    
    budget_remaining: float
    """Remaining budget (percentage)."""
    
    proposed_risk: float
    """The proposed risk (percentage)."""
    
    would_exceed_by: float = 0.0
    """How much the proposed risk exceeds remaining budget."""
    
    max_allowable_risk: float = 0.0
    """Maximum risk that could be allowed."""
    
    reason: Optional[RejectReason] = None
    """Reason if check failed."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "dimension": self.dimension.value,
            "passed": self.passed,
            "budget_limit": self.budget_limit,
            "budget_used": self.budget_used,
            "budget_remaining": self.budget_remaining,
            "proposed_risk": self.proposed_risk,
            "would_exceed_by": self.would_exceed_by,
            "max_allowable_risk": self.max_allowable_risk,
            "reason": self.reason.value if self.reason else None,
        }


@dataclass
class TradeRiskResponse:
    """
    Response from the Risk Budget Manager.
    
    This is the OUTPUT that tells the Execution Engine whether
    to proceed with the trade.
    
    ============================================================
    DECISION LOGIC
    ============================================================
    - ALLOW_TRADE: All budget checks passed
    - REDUCE_SIZE: Some budget exceeded but trade possible at smaller size
    - REJECT_TRADE: No size would fit current budget constraints
    
    ============================================================
    """
    
    # Core Decision
    decision: TradeDecision
    """The decision: ALLOW_TRADE, REDUCE_SIZE, or REJECT_TRADE."""
    
    request_id: str
    """ID of the original request."""
    
    # Budget Check Details
    budget_checks: List[BudgetCheckResult]
    """Results of each budget dimension check."""
    
    primary_reason: Optional[RejectReason] = None
    """Primary reason for REDUCE_SIZE or REJECT_TRADE."""
    
    # Adjusted Values (for REDUCE_SIZE)
    original_risk_pct: float = 0.0
    """Original proposed risk percentage."""
    
    allowed_risk_pct: float = 0.0
    """Maximum allowed risk percentage."""
    
    original_position_size: float = 0.0
    """Original proposed position size."""
    
    allowed_position_size: float = 0.0
    """Adjusted position size (if REDUCE_SIZE)."""
    
    size_reduction_pct: float = 0.0
    """Percentage reduction in size."""
    
    # Current State
    account_equity: float = 0.0
    """Account equity used for calculation."""
    
    daily_risk_used: float = 0.0
    """Daily risk budget consumed (percentage)."""
    
    open_risk_used: float = 0.0
    """Open position risk used (percentage)."""
    
    current_drawdown: float = 0.0
    """Current drawdown percentage."""
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """When this response was generated."""
    
    evaluation_duration_ms: float = 0.0
    """Time taken to evaluate the request."""
    
    def is_allowed(self) -> bool:
        """Check if trade is allowed (at any size)."""
        return self.decision in (TradeDecision.ALLOW_TRADE, TradeDecision.REDUCE_SIZE)
    
    def is_rejected(self) -> bool:
        """Check if trade is rejected."""
        return self.decision == TradeDecision.REJECT_TRADE
    
    def get_failed_dimensions(self) -> List[RiskBudgetDimension]:
        """Get list of failed budget dimensions."""
        return [check.dimension for check in self.budget_checks if not check.passed]
    
    def format_summary(self) -> str:
        """Format a human-readable summary."""
        lines = [
            f"Decision: {self.decision.value}",
            f"Request: {self.request_id}",
        ]
        
        if self.primary_reason:
            lines.append(f"Reason: {self.primary_reason.value}")
        
        lines.extend([
            f"Original Risk: {self.original_risk_pct:.2f}%",
            f"Allowed Risk: {self.allowed_risk_pct:.2f}%",
            f"Daily Used: {self.daily_risk_used:.2f}%",
            f"Open Risk: {self.open_risk_used:.2f}%",
            f"Drawdown: {self.current_drawdown:.2f}%",
        ])
        
        if self.decision == TradeDecision.REDUCE_SIZE:
            lines.append(f"Size Reduced: {self.size_reduction_pct:.1f}%")
        
        return " | ".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "decision": self.decision.value,
            "request_id": self.request_id,
            "primary_reason": self.primary_reason.value if self.primary_reason else None,
            "budget_checks": [check.to_dict() for check in self.budget_checks],
            "original_risk_pct": self.original_risk_pct,
            "allowed_risk_pct": self.allowed_risk_pct,
            "original_position_size": self.original_position_size,
            "allowed_position_size": self.allowed_position_size,
            "size_reduction_pct": self.size_reduction_pct,
            "account_equity": self.account_equity,
            "daily_risk_used": self.daily_risk_used,
            "open_risk_used": self.open_risk_used,
            "current_drawdown": self.current_drawdown,
            "timestamp": self.timestamp.isoformat(),
            "evaluation_duration_ms": self.evaluation_duration_ms,
        }


# ============================================================
# TRACKING TYPES
# ============================================================

@dataclass
class OpenPositionRisk:
    """
    Tracked risk for an open position.
    
    Risk budget is HELD while position is open and RELEASED
    only when position is fully closed.
    """
    
    position_id: str
    """Unique identifier for the position."""
    
    symbol: str
    """Trading pair."""
    
    exchange: str
    """Exchange identifier."""
    
    direction: str
    """Trade direction: 'LONG' or 'SHORT'."""
    
    entry_price: float
    """Entry price."""
    
    stop_loss_price: float
    """Current stop loss price."""
    
    position_size: float
    """Current position size."""
    
    risk_amount: float
    """Risk amount in quote currency."""
    
    risk_percentage: float
    """Risk as percentage of equity at entry."""
    
    equity_at_entry: float
    """Account equity when position was opened."""
    
    status: PositionStatus = PositionStatus.OPEN
    """Current position status."""
    
    opened_at: datetime = field(default_factory=datetime.utcnow)
    """When position was opened."""
    
    closed_at: Optional[datetime] = None
    """When position was closed (if applicable)."""
    
    realized_pnl: Optional[float] = None
    """Realized P&L when closed."""
    
    def update_stop_loss(self, new_stop_loss: float, current_equity: float) -> None:
        """
        Update stop loss and recalculate risk.
        
        Args:
            new_stop_loss: New stop loss price
            current_equity: Current account equity
        """
        self.stop_loss_price = new_stop_loss
        
        if self.direction == "LONG":
            risk_per_unit = self.entry_price - new_stop_loss
        else:
            risk_per_unit = new_stop_loss - self.entry_price
        
        self.risk_amount = abs(risk_per_unit * self.position_size)
        self.risk_percentage = (self.risk_amount / current_equity) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss_price": self.stop_loss_price,
            "position_size": self.position_size,
            "risk_amount": self.risk_amount,
            "risk_percentage": self.risk_percentage,
            "equity_at_entry": self.equity_at_entry,
            "status": self.status.value,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "realized_pnl": self.realized_pnl,
        }


@dataclass
class DailyRiskUsage:
    """
    Daily risk budget usage tracking.
    
    Tracks cumulative risk taken during a trading day.
    Resets at the configured reset time (default: 00:00 UTC).
    """
    
    date: str
    """Date in YYYY-MM-DD format."""
    
    risk_budget_limit: float
    """Configured daily risk limit (percentage)."""
    
    risk_consumed: float = 0.0
    """Risk consumed so far (percentage)."""
    
    trades_taken: int = 0
    """Number of trades taken today."""
    
    trades_rejected: int = 0
    """Number of trades rejected today."""
    
    realized_pnl: float = 0.0
    """Realized P&L for the day."""
    
    peak_open_risk: float = 0.0
    """Peak concurrent open risk during the day."""
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    """When this record was created."""
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    """When this record was last updated."""
    
    @property
    def risk_remaining(self) -> float:
        """Calculate remaining daily risk budget."""
        return max(0.0, self.risk_budget_limit - self.risk_consumed)
    
    @property
    def utilization_pct(self) -> float:
        """Calculate budget utilization percentage."""
        if self.risk_budget_limit <= 0:
            return 0.0
        return (self.risk_consumed / self.risk_budget_limit) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "date": self.date,
            "risk_budget_limit": self.risk_budget_limit,
            "risk_consumed": self.risk_consumed,
            "risk_remaining": self.risk_remaining,
            "utilization_pct": self.utilization_pct,
            "trades_taken": self.trades_taken,
            "trades_rejected": self.trades_rejected,
            "realized_pnl": self.realized_pnl,
            "peak_open_risk": self.peak_open_risk,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class RiskBudgetSnapshot:
    """
    Complete snapshot of current risk budget state.
    
    Used for reporting and monitoring.
    """
    
    # Equity State
    account_equity: float
    """Current account equity."""
    
    peak_equity: float
    """Historical peak equity."""
    
    current_drawdown_pct: float
    """Current drawdown percentage."""
    
    # Budget States
    per_trade_limit_pct: float
    """Per-trade risk limit."""
    
    daily_limit_pct: float
    """Daily risk limit."""
    
    daily_used_pct: float
    """Daily risk used."""
    
    daily_remaining_pct: float
    """Daily risk remaining."""
    
    open_limit_pct: float
    """Open position risk limit."""
    
    open_used_pct: float
    """Open position risk used."""
    
    open_remaining_pct: float
    """Open position risk remaining."""
    
    drawdown_limit_pct: float
    """Drawdown halt threshold."""
    
    # Position Counts
    open_positions: int
    """Number of open positions."""
    
    max_positions: int
    """Maximum allowed positions."""
    
    # Status
    is_trading_allowed: bool
    """Whether new trades are allowed."""
    
    halt_reason: Optional[str] = None
    """Reason if trading is halted."""
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """When snapshot was taken."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "account_equity": self.account_equity,
            "peak_equity": self.peak_equity,
            "current_drawdown_pct": self.current_drawdown_pct,
            "per_trade_limit_pct": self.per_trade_limit_pct,
            "daily_limit_pct": self.daily_limit_pct,
            "daily_used_pct": self.daily_used_pct,
            "daily_remaining_pct": self.daily_remaining_pct,
            "open_limit_pct": self.open_limit_pct,
            "open_used_pct": self.open_used_pct,
            "open_remaining_pct": self.open_remaining_pct,
            "drawdown_limit_pct": self.drawdown_limit_pct,
            "open_positions": self.open_positions,
            "max_positions": self.max_positions,
            "is_trading_allowed": self.is_trading_allowed,
            "halt_reason": self.halt_reason,
            "timestamp": self.timestamp.isoformat(),
        }


# ============================================================
# ERROR TYPES
# ============================================================

class RiskBudgetError(Exception):
    """Base exception for Risk Budget Manager errors."""
    pass


class EquityDataError(RiskBudgetError):
    """Raised when equity data is missing or stale."""
    pass


class PositionStateError(RiskBudgetError):
    """Raised when position state is inconsistent."""
    pass


class BudgetCalculationError(RiskBudgetError):
    """Raised when risk calculation fails."""
    pass


class ConfigurationError(RiskBudgetError):
    """Raised when configuration is invalid."""
    pass
