"""
Execution Engine - Types.

============================================================
PURPOSE
============================================================
All type definitions for the Execution Engine.

CRITICAL PRINCIPLE:
    "Execution Engine is REACTIVE, not decision-making."
    "It executes only after Trade Guard Absolute returns EXECUTE."

============================================================
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from decimal import Decimal
import uuid


# ============================================================
# ORDER TYPES
# ============================================================

class OrderSide(Enum):
    """Order side."""
    
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order type."""
    
    MARKET = "MARKET"
    """Execute at current market price."""
    
    LIMIT = "LIMIT"
    """Execute at specified price or better."""
    
    STOP_MARKET = "STOP_MARKET"
    """Market order triggered at stop price."""
    
    STOP_LIMIT = "STOP_LIMIT"
    """Limit order triggered at stop price."""
    
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    """Market order triggered at take profit price."""
    
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
    """Limit order triggered at take profit price."""


class TimeInForce(Enum):
    """Time in force for orders."""
    
    GTC = "GTC"
    """Good Till Canceled."""
    
    IOC = "IOC"
    """Immediate Or Cancel."""
    
    FOK = "FOK"
    """Fill Or Kill."""
    
    GTD = "GTD"
    """Good Till Date."""


class PositionSide(Enum):
    """Position side for hedge mode."""
    
    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"  # One-way mode


# ============================================================
# ORDER LIFECYCLE STATES
# ============================================================

class OrderState(Enum):
    """
    Order lifecycle state.
    
    State Machine:
    
    PENDING_VALIDATION
           │
           ▼
    PENDING_SUBMISSION ──────► REJECTED
           │                      │
           ▼                      │
    SUBMITTED ────────────────────┤
           │                      │
           ├──► PARTIALLY_FILLED  │
           │         │            │
           │         ▼            │
           └──► FILLED ◄──────────┘
                  │
                  ▼
              COMPLETED
           
    Any state can transition to:
    - CANCELED (by user/system)
    - EXPIRED (by exchange)
    - FAILED (internal error)
    """
    
    # Initial states
    PENDING_VALIDATION = "PENDING_VALIDATION"
    """Awaiting pre-execution validation."""
    
    PENDING_SUBMISSION = "PENDING_SUBMISSION"
    """Validated, awaiting submission to exchange."""
    
    # Active states
    SUBMITTED = "SUBMITTED"
    """Submitted to exchange, awaiting confirmation."""
    
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    """Order partially executed."""
    
    # Terminal states
    FILLED = "FILLED"
    """Order fully executed."""
    
    COMPLETED = "COMPLETED"
    """Order completed and reconciled."""
    
    CANCELED = "CANCELED"
    """Order canceled (by user or system)."""
    
    REJECTED = "REJECTED"
    """Order rejected by exchange."""
    
    EXPIRED = "EXPIRED"
    """Order expired (time-based)."""
    
    FAILED = "FAILED"
    """Internal execution failure."""
    
    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in {
            OrderState.FILLED,
            OrderState.COMPLETED,
            OrderState.CANCELED,
            OrderState.REJECTED,
            OrderState.EXPIRED,
            OrderState.FAILED,
        }
    
    def is_active(self) -> bool:
        """Check if order is still active."""
        return self in {
            OrderState.PENDING_VALIDATION,
            OrderState.PENDING_SUBMISSION,
            OrderState.SUBMITTED,
            OrderState.PARTIALLY_FILLED,
        }
    
    def allows_cancel(self) -> bool:
        """Check if order can be canceled."""
        return self in {
            OrderState.PENDING_SUBMISSION,
            OrderState.SUBMITTED,
            OrderState.PARTIALLY_FILLED,
        }


# ============================================================
# EXECUTION RESULT TYPES
# ============================================================

class ExecutionResultCode(Enum):
    """Execution result codes."""
    
    # Success
    SUCCESS = "SUCCESS"
    """Order executed successfully."""
    
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    """Order partially filled."""
    
    # Rejections
    REJECTED_INSUFFICIENT_BALANCE = "REJECTED_INSUFFICIENT_BALANCE"
    """Rejected due to insufficient balance."""
    
    REJECTED_INVALID_SYMBOL = "REJECTED_INVALID_SYMBOL"
    """Rejected due to invalid symbol."""
    
    REJECTED_INVALID_QUANTITY = "REJECTED_INVALID_QUANTITY"
    """Rejected due to invalid quantity."""
    
    REJECTED_INVALID_PRICE = "REJECTED_INVALID_PRICE"
    """Rejected due to invalid price."""
    
    REJECTED_RATE_LIMITED = "REJECTED_RATE_LIMITED"
    """Rejected due to rate limiting."""
    
    REJECTED_MARKET_CLOSED = "REJECTED_MARKET_CLOSED"
    """Rejected because market is closed."""
    
    REJECTED_POSITION_LIMIT = "REJECTED_POSITION_LIMIT"
    """Rejected due to position limit."""
    
    REJECTED_BY_EXCHANGE = "REJECTED_BY_EXCHANGE"
    """Generic rejection by exchange."""
    
    # Failures
    FAILED_TIMEOUT = "FAILED_TIMEOUT"
    """Request timed out."""
    
    FAILED_NETWORK = "FAILED_NETWORK"
    """Network error."""
    
    FAILED_AUTHENTICATION = "FAILED_AUTHENTICATION"
    """Authentication failed."""
    
    FAILED_INTERNAL = "FAILED_INTERNAL"
    """Internal error."""
    
    FAILED_VALIDATION = "FAILED_VALIDATION"
    """Pre-execution validation failed."""
    
    # Blocked
    BLOCKED_HALT_STATE = "BLOCKED_HALT_STATE"
    """Blocked by System Risk Controller HALT."""
    
    BLOCKED_NO_APPROVAL = "BLOCKED_NO_APPROVAL"
    """Blocked due to missing Trade Guard approval."""
    
    BLOCKED_EXPIRED_APPROVAL = "BLOCKED_EXPIRED_APPROVAL"
    """Blocked due to expired approval."""
    
    def is_success(self) -> bool:
        """Check if this is a success code."""
        return self in {
            ExecutionResultCode.SUCCESS,
            ExecutionResultCode.PARTIAL_SUCCESS,
        }
    
    def is_retryable(self) -> bool:
        """Check if this error is retryable."""
        return self in {
            ExecutionResultCode.FAILED_TIMEOUT,
            ExecutionResultCode.FAILED_NETWORK,
            ExecutionResultCode.REJECTED_RATE_LIMITED,
        }


# ============================================================
# ORDER INTENT
# ============================================================

@dataclass
class OrderIntent:
    """
    Approved trade intent from Trade Guard Absolute.
    
    This is the INPUT to Execution Engine.
    It has already been approved by Trade Guard.
    """
    
    # Identifiers
    intent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Unique intent identifier."""
    
    approval_token: str = ""
    """Trade Guard Absolute approval token."""
    
    approval_timestamp: datetime = field(default_factory=datetime.utcnow)
    """When approval was granted."""
    
    approval_expires_at: datetime = field(default_factory=datetime.utcnow)
    """When approval expires."""
    
    # Order parameters (from Risk Budget Manager)
    symbol: str = ""
    """Trading symbol (e.g., BTCUSDT)."""
    
    side: OrderSide = OrderSide.BUY
    """Order side."""
    
    order_type: OrderType = OrderType.MARKET
    """Order type."""
    
    quantity: Decimal = Decimal("0")
    """Order quantity in base currency."""
    
    price: Optional[Decimal] = None
    """Limit price (for LIMIT orders)."""
    
    stop_price: Optional[Decimal] = None
    """Stop/trigger price."""
    
    time_in_force: TimeInForce = TimeInForce.GTC
    """Time in force."""
    
    position_side: PositionSide = PositionSide.BOTH
    """Position side (for hedge mode)."""
    
    reduce_only: bool = False
    """Whether this is a reduce-only order."""
    
    # Metadata
    strategy_id: str = ""
    """Source strategy identifier."""
    
    signal_id: str = ""
    """Source signal identifier."""
    
    client_order_id: Optional[str] = None
    """Client-specified order ID for idempotency."""
    
    def is_approval_valid(self) -> bool:
        """Check if approval is still valid."""
        return (
            self.approval_token != "" and
            datetime.utcnow() < self.approval_expires_at
        )


# ============================================================
# EXECUTION RESULT
# ============================================================

@dataclass
class ExecutionResult:
    """
    Execution result from order submission.
    
    This is the OUTPUT from Execution Engine.
    """
    
    # Identifiers
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Unique execution identifier."""
    
    intent_id: str = ""
    """Related intent ID."""
    
    order_id: str = ""
    """Internal order ID."""
    
    exchange_order_id: Optional[str] = None
    """Exchange-assigned order ID."""
    
    client_order_id: Optional[str] = None
    """Client-specified order ID."""
    
    # Result
    result_code: ExecutionResultCode = ExecutionResultCode.SUCCESS
    """Execution result code."""
    
    order_state: OrderState = OrderState.PENDING_VALIDATION
    """Final order state."""
    
    # Execution details
    symbol: str = ""
    """Trading symbol."""
    
    side: OrderSide = OrderSide.BUY
    """Order side."""
    
    order_type: OrderType = OrderType.MARKET
    """Order type."""
    
    requested_quantity: Decimal = Decimal("0")
    """Originally requested quantity."""
    
    filled_quantity: Decimal = Decimal("0")
    """Actually filled quantity."""
    
    average_fill_price: Optional[Decimal] = None
    """Average fill price."""
    
    commission: Decimal = Decimal("0")
    """Total commission paid."""
    
    commission_asset: str = ""
    """Commission asset."""
    
    # Timestamps
    submitted_at: Optional[datetime] = None
    """When order was submitted."""
    
    filled_at: Optional[datetime] = None
    """When order was filled."""
    
    completed_at: Optional[datetime] = None
    """When execution completed."""
    
    # Error details
    error_message: Optional[str] = None
    """Error message if failed."""
    
    error_code: Optional[str] = None
    """Exchange error code."""
    
    # Retry info
    retry_count: int = 0
    """Number of retries attempted."""
    
    @property
    def is_success(self) -> bool:
        """Check if execution was successful."""
        return self.result_code.is_success()
    
    @property
    def fill_ratio(self) -> Decimal:
        """Get fill ratio (0.0 to 1.0)."""
        if self.requested_quantity == 0:
            return Decimal("0")
        return self.filled_quantity / self.requested_quantity


# ============================================================
# ORDER RECORD
# ============================================================

@dataclass
class OrderRecord:
    """
    Internal order record with full lifecycle tracking.
    """
    
    # Identifiers
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Internal order ID."""
    
    intent_id: str = ""
    """Related intent ID."""
    
    exchange_order_id: Optional[str] = None
    """Exchange-assigned order ID."""
    
    client_order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Client order ID for idempotency."""
    
    # State
    state: OrderState = OrderState.PENDING_VALIDATION
    """Current order state."""
    
    previous_state: Optional[OrderState] = None
    """Previous state (for audit)."""
    
    # Order parameters
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    quantity: Decimal = Decimal("0")
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: TimeInForce = TimeInForce.GTC
    position_side: PositionSide = PositionSide.BOTH
    reduce_only: bool = False
    
    # Fill tracking
    filled_quantity: Decimal = Decimal("0")
    remaining_quantity: Decimal = Decimal("0")
    average_fill_price: Optional[Decimal] = None
    commission: Decimal = Decimal("0")
    commission_asset: str = ""
    
    # Fills history
    fills: List[Dict[str, Any]] = field(default_factory=list)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    submitted_at: Optional[datetime] = None
    last_update_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Execution tracking
    retry_count: int = 0
    last_error: Optional[str] = None
    exchange_error_code: Optional[str] = None
    
    # Metadata
    strategy_id: str = ""
    exchange_id: str = ""
    
    def update_remaining(self) -> None:
        """Update remaining quantity."""
        self.remaining_quantity = self.quantity - self.filled_quantity


# ============================================================
# ACCOUNT STATE
# ============================================================

@dataclass
class AccountBalance:
    """Account balance for an asset."""
    
    asset: str = ""
    """Asset symbol (e.g., USDT)."""
    
    free: Decimal = Decimal("0")
    """Free (available) balance."""
    
    locked: Decimal = Decimal("0")
    """Locked (in orders) balance."""
    
    @property
    def total(self) -> Decimal:
        """Get total balance."""
        return self.free + self.locked


@dataclass
class PositionInfo:
    """Current position information."""
    
    symbol: str = ""
    """Trading symbol."""
    
    side: PositionSide = PositionSide.BOTH
    """Position side."""
    
    quantity: Decimal = Decimal("0")
    """Position size (positive for long, negative for short)."""
    
    entry_price: Decimal = Decimal("0")
    """Average entry price."""
    
    unrealized_pnl: Decimal = Decimal("0")
    """Unrealized PnL."""
    
    leverage: int = 1
    """Position leverage."""
    
    margin_type: str = "CROSS"
    """Margin type (CROSS or ISOLATED)."""
    
    liquidation_price: Optional[Decimal] = None
    """Estimated liquidation price."""


@dataclass
class AccountState:
    """
    Current account state snapshot.
    
    Used for pre-execution validation.
    """
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """When snapshot was taken."""
    
    exchange_id: str = ""
    """Exchange identifier."""
    
    # Balances
    balances: Dict[str, AccountBalance] = field(default_factory=dict)
    """Balances by asset."""
    
    # Positions
    positions: Dict[str, PositionInfo] = field(default_factory=dict)
    """Open positions by symbol."""
    
    # Margin info
    total_margin_balance: Decimal = Decimal("0")
    """Total margin balance."""
    
    available_margin: Decimal = Decimal("0")
    """Available margin for new positions."""
    
    used_margin: Decimal = Decimal("0")
    """Margin used by open positions."""
    
    margin_ratio: Decimal = Decimal("0")
    """Current margin ratio."""
    
    def get_balance(self, asset: str) -> AccountBalance:
        """Get balance for an asset."""
        return self.balances.get(asset, AccountBalance(asset=asset))
    
    def get_position(self, symbol: str) -> Optional[PositionInfo]:
        """Get position for a symbol."""
        return self.positions.get(symbol)


# ============================================================
# EXCHANGE RULES
# ============================================================

@dataclass
class SymbolRules:
    """Exchange rules for a trading symbol."""
    
    symbol: str = ""
    """Trading symbol."""
    
    status: str = "TRADING"
    """Symbol status."""
    
    base_asset: str = ""
    """Base asset (e.g., BTC)."""
    
    quote_asset: str = ""
    """Quote asset (e.g., USDT)."""
    
    # Quantity rules
    min_quantity: Decimal = Decimal("0")
    """Minimum order quantity."""
    
    max_quantity: Decimal = Decimal("0")
    """Maximum order quantity."""
    
    quantity_step: Decimal = Decimal("0")
    """Quantity step size."""
    
    quantity_precision: int = 0
    """Quantity decimal precision."""
    
    # Price rules
    min_price: Decimal = Decimal("0")
    """Minimum price."""
    
    max_price: Decimal = Decimal("0")
    """Maximum price."""
    
    price_step: Decimal = Decimal("0")
    """Price tick size."""
    
    price_precision: int = 0
    """Price decimal precision."""
    
    # Notional rules
    min_notional: Decimal = Decimal("0")
    """Minimum notional value."""
    
    # Leverage
    max_leverage: int = 125
    """Maximum leverage allowed."""
    
    def round_quantity(self, quantity: Decimal) -> Decimal:
        """Round quantity to valid step size."""
        if self.quantity_step == 0:
            return quantity
        return (quantity // self.quantity_step) * self.quantity_step
    
    def round_price(self, price: Decimal) -> Decimal:
        """Round price to valid tick size."""
        if self.price_step == 0:
            return price
        return (price // self.price_step) * self.price_step
    
    def is_quantity_valid(self, quantity: Decimal) -> bool:
        """Check if quantity is valid."""
        if quantity < self.min_quantity:
            return False
        if self.max_quantity > 0 and quantity > self.max_quantity:
            return False
        return True
    
    def is_price_valid(self, price: Decimal) -> bool:
        """Check if price is valid."""
        if price < self.min_price:
            return False
        if self.max_price > 0 and price > self.max_price:
            return False
        return True


# ============================================================
# EXCEPTIONS
# ============================================================

class ExecutionEngineError(Exception):
    """Base exception for Execution Engine."""
    pass


class ValidationError(ExecutionEngineError):
    """Pre-execution validation failed."""
    pass


class SubmissionError(ExecutionEngineError):
    """Order submission failed."""
    pass


class ReconciliationError(ExecutionEngineError):
    """State reconciliation failed."""
    pass


class ExchangeError(ExecutionEngineError):
    """Exchange communication error."""
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        is_retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.is_retryable = is_retryable


class HaltStateError(ExecutionEngineError):
    """System is in HALT state."""
    pass


class ApprovalError(ExecutionEngineError):
    """Trade Guard approval missing or expired."""
    pass
