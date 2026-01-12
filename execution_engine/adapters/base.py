"""
Execution Engine - Exchange Adapter Base.

============================================================
PURPOSE
============================================================
Abstract interface for exchange adapters.

DESIGN PRINCIPLES:
- Exchange-agnostic interface
- Clean separation from execution logic
- Fully testable with mock adapters

============================================================
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from decimal import Decimal

from ..types import (
    OrderSide,
    OrderType,
    TimeInForce,
    PositionSide,
    OrderState,
    AccountState,
    AccountBalance,
    PositionInfo,
    SymbolRules,
    ExchangeError,
)

# Aliases for backward compatibility
BalanceInfo = AccountBalance


# ============================================================
# RATE LIMIT STATUS
# ============================================================

@dataclass
class RateLimitStatus:
    """Status of rate limiting."""
    
    remaining: int = 100
    """Remaining requests in window."""
    
    limit: int = 100
    """Total limit for window."""
    
    reset_at: Optional[datetime] = None
    """When the limit resets."""
    
    is_limited: bool = False
    """Whether currently rate limited."""


# ============================================================
# STATUS MAPPING
# ============================================================

def map_exchange_status_to_order_state(status: str) -> OrderState:
    """
    Map exchange status string to OrderState.
    
    Args:
        status: Exchange status string
        
    Returns:
        OrderState enum value
    """
    status_upper = status.upper()
    
    mapping = {
        "NEW": OrderState.SUBMITTED,
        "OPEN": OrderState.SUBMITTED,
        "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
        "PARTIAL": OrderState.PARTIALLY_FILLED,
        "FILLED": OrderState.FILLED,
        "CANCELED": OrderState.CANCELED,
        "CANCELLED": OrderState.CANCELED,
        "REJECTED": OrderState.REJECTED,
        "EXPIRED": OrderState.EXPIRED,
    }
    
    return mapping.get(status_upper, OrderState.SUBMITTED)


logger = logging.getLogger(__name__)


# ============================================================
# ADAPTER REQUEST/RESPONSE TYPES
# ============================================================

@dataclass
class SubmitOrderRequest:
    """Request to submit an order."""
    
    symbol: str
    """Trading symbol."""
    
    side: OrderSide
    """Order side."""
    
    order_type: OrderType
    """Order type."""
    
    quantity: Decimal
    """Order quantity."""
    
    price: Optional[Decimal] = None
    """Limit price."""
    
    stop_price: Optional[Decimal] = None
    """Stop/trigger price."""
    
    time_in_force: TimeInForce = TimeInForce.GTC
    """Time in force."""
    
    position_side: PositionSide = PositionSide.BOTH
    """Position side."""
    
    reduce_only: bool = False
    """Reduce only flag."""
    
    client_order_id: Optional[str] = None
    """Client order ID for idempotency."""
    
    # Timeouts
    recv_window: int = 5000
    """Receive window in ms."""


@dataclass
class SubmitOrderResponse:
    """Response from order submission."""
    
    success: bool
    """Whether submission succeeded."""
    
    exchange_order_id: Optional[str] = None
    """Exchange-assigned order ID."""
    
    client_order_id: Optional[str] = None
    """Client order ID."""
    
    status: Optional[str] = None
    """Order status from exchange."""
    
    filled_quantity: Decimal = Decimal("0")
    """Already filled quantity."""
    
    average_price: Optional[Decimal] = None
    """Average fill price."""
    
    # Error info
    error_code: Optional[str] = None
    """Error code if failed."""
    
    error_message: Optional[str] = None
    """Error message if failed."""
    
    # Timestamps
    exchange_timestamp: Optional[datetime] = None
    """Exchange timestamp."""
    
    # Raw response
    raw_response: Dict[str, Any] = field(default_factory=dict)
    """Raw exchange response."""


@dataclass
class QueryOrderRequest:
    """Request to query order status."""
    
    symbol: str
    """Trading symbol."""
    
    exchange_order_id: Optional[str] = None
    """Exchange order ID."""
    
    client_order_id: Optional[str] = None
    """Client order ID."""


@dataclass
class QueryOrderResponse:
    """Response from order query."""
    
    found: bool
    """Whether order was found."""
    
    exchange_order_id: Optional[str] = None
    """Exchange order ID."""
    
    client_order_id: Optional[str] = None
    """Client order ID."""
    
    symbol: str = ""
    """Trading symbol."""
    
    side: Optional[OrderSide] = None
    """Order side."""
    
    order_type: Optional[OrderType] = None
    """Order type."""
    
    status: Optional[str] = None
    """Order status."""
    
    quantity: Decimal = Decimal("0")
    """Original quantity."""
    
    filled_quantity: Decimal = Decimal("0")
    """Filled quantity."""
    
    remaining_quantity: Decimal = Decimal("0")
    """Remaining quantity."""
    
    price: Optional[Decimal] = None
    """Order price."""
    
    average_price: Optional[Decimal] = None
    """Average fill price."""
    
    # Timestamps
    created_at: Optional[datetime] = None
    """When order was created."""
    
    updated_at: Optional[datetime] = None
    """Last update time."""
    
    # Error info
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    
    # Raw response
    raw_response: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CancelOrderRequest:
    """Request to cancel an order."""
    
    symbol: str
    """Trading symbol."""
    
    exchange_order_id: Optional[str] = None
    """Exchange order ID."""
    
    client_order_id: Optional[str] = None
    """Client order ID."""


@dataclass
class CancelOrderResponse:
    """Response from order cancellation."""
    
    success: bool
    """Whether cancellation succeeded."""
    
    exchange_order_id: Optional[str] = None
    """Exchange order ID."""
    
    status: Optional[str] = None
    """Final order status."""
    
    # Error info
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    
    # Raw response
    raw_response: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FillInfo:
    """Information about a fill."""
    
    trade_id: str
    """Trade/fill ID."""
    
    order_id: str
    """Order ID."""
    
    symbol: str
    """Trading symbol."""
    
    side: OrderSide
    """Order side."""
    
    quantity: Decimal
    """Fill quantity."""
    
    price: Decimal
    """Fill price."""
    
    commission: Decimal = Decimal("0")
    """Commission paid."""
    
    commission_asset: str = ""
    """Commission asset."""
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """Fill timestamp."""
    
    is_maker: bool = False
    """Whether this was a maker trade."""


# ============================================================
# ABSTRACT EXCHANGE ADAPTER
# ============================================================

class ExchangeAdapter(ABC):
    """
    Abstract interface for exchange adapters.
    
    Implementations:
    - BinanceAdapter: Real Binance Futures API
    - MockAdapter: For testing
    """
    
    @property
    @abstractmethod
    def exchange_id(self) -> str:
        """Get exchange identifier."""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if adapter is connected."""
        pass
    
    # --------------------------------------------------------
    # CONNECTION
    # --------------------------------------------------------
    
    @abstractmethod
    async def connect(self) -> None:
        """
        Connect to exchange.
        
        Raises:
            ExchangeError: If connection fails
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from exchange."""
        pass
    
    # --------------------------------------------------------
    # ACCOUNT OPERATIONS
    # --------------------------------------------------------
    
    @abstractmethod
    async def get_account_state(self) -> AccountState:
        """
        Get current account state.
        
        Returns:
            AccountState with balances and positions
            
        Raises:
            ExchangeError: If query fails
        """
        pass
    
    @abstractmethod
    async def get_balance(self, asset: str) -> AccountBalance:
        """
        Get balance for specific asset.
        
        Args:
            asset: Asset symbol (e.g., USDT)
            
        Returns:
            AccountBalance
        """
        pass
    
    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[PositionInfo]:
        """
        Get position for symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            PositionInfo or None if no position
        """
        pass
    
    @abstractmethod
    async def get_all_positions(self) -> List[PositionInfo]:
        """Get all open positions."""
        pass
    
    # --------------------------------------------------------
    # ORDER OPERATIONS
    # --------------------------------------------------------
    
    @abstractmethod
    async def submit_order(
        self,
        request: SubmitOrderRequest,
    ) -> SubmitOrderResponse:
        """
        Submit an order to exchange.
        
        Args:
            request: Order submission request
            
        Returns:
            SubmitOrderResponse
            
        Raises:
            ExchangeError: If submission fails
        """
        pass
    
    @abstractmethod
    async def query_order(
        self,
        request: QueryOrderRequest,
    ) -> QueryOrderResponse:
        """
        Query order status.
        
        Args:
            request: Query request
            
        Returns:
            QueryOrderResponse
        """
        pass
    
    @abstractmethod
    async def cancel_order(
        self,
        request: CancelOrderRequest,
    ) -> CancelOrderResponse:
        """
        Cancel an order.
        
        Args:
            request: Cancel request
            
        Returns:
            CancelOrderResponse
        """
        pass
    
    @abstractmethod
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """
        Cancel all open orders.
        
        Args:
            symbol: Specific symbol, or None for all
            
        Returns:
            Number of orders canceled
        """
        pass
    
    @abstractmethod
    async def get_open_orders(
        self,
        symbol: Optional[str] = None,
    ) -> List[QueryOrderResponse]:
        """
        Get all open orders.
        
        Args:
            symbol: Specific symbol, or None for all
            
        Returns:
            List of open orders
        """
        pass
    
    # --------------------------------------------------------
    # SYMBOL RULES
    # --------------------------------------------------------
    
    @abstractmethod
    async def get_symbol_rules(self, symbol: str) -> SymbolRules:
        """
        Get trading rules for symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            SymbolRules
        """
        pass
    
    @abstractmethod
    async def get_all_symbol_rules(self) -> Dict[str, SymbolRules]:
        """Get trading rules for all symbols."""
        pass
    
    # --------------------------------------------------------
    # MARKET DATA
    # --------------------------------------------------------
    
    @abstractmethod
    async def get_current_price(self, symbol: str) -> Decimal:
        """
        Get current price for symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current price
        """
        pass
    
    # --------------------------------------------------------
    # RATE LIMITING
    # --------------------------------------------------------
    
    @abstractmethod
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limit status.
        
        Returns:
            Dict with rate limit info
        """
        pass
    
    @abstractmethod
    async def wait_for_rate_limit(self) -> None:
        """Wait if rate limit is approaching."""
        pass


# ============================================================
# STATUS MAPPING HELPERS
# ============================================================

def map_exchange_status_to_order_state(
    exchange: str,
    status: str,
) -> OrderState:
    """
    Map exchange-specific status to OrderState.
    
    Args:
        exchange: Exchange identifier
        status: Exchange status string
        
    Returns:
        OrderState
    """
    if exchange == "binance_futures":
        return _map_binance_status(status)
    
    # Default mapping
    status_upper = status.upper()
    
    if status_upper in {"NEW", "PENDING", "OPEN"}:
        return OrderState.SUBMITTED
    elif status_upper in {"PARTIALLY_FILLED", "PARTIAL"}:
        return OrderState.PARTIALLY_FILLED
    elif status_upper in {"FILLED", "CLOSED"}:
        return OrderState.FILLED
    elif status_upper in {"CANCELED", "CANCELLED"}:
        return OrderState.CANCELED
    elif status_upper in {"REJECTED"}:
        return OrderState.REJECTED
    elif status_upper in {"EXPIRED"}:
        return OrderState.EXPIRED
    
    logger.warning(f"Unknown order status: {status}")
    return OrderState.SUBMITTED


def _map_binance_status(status: str) -> OrderState:
    """Map Binance order status to OrderState."""
    mapping = {
        "NEW": OrderState.SUBMITTED,
        "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
        "FILLED": OrderState.FILLED,
        "CANCELED": OrderState.CANCELED,
        "REJECTED": OrderState.REJECTED,
        "EXPIRED": OrderState.EXPIRED,
        "EXPIRED_IN_MATCH": OrderState.EXPIRED,
    }
    return mapping.get(status, OrderState.SUBMITTED)
