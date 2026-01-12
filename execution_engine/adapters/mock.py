"""
Execution Engine - Mock Exchange Adapter.

============================================================
PURPOSE
============================================================
Mock adapter for testing execution engine.

FEATURES:
- Configurable latency
- Configurable error injection
- Configurable fill behavior
- Full state tracking

============================================================
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from decimal import Decimal
import uuid

from ..types import (
    OrderSide,
    OrderType,
    TimeInForce,
    PositionSide,
    AccountState,
    AccountBalance,
    PositionInfo,
    SymbolRules,
    ExchangeError,
)
from .base import (
    ExchangeAdapter,
    SubmitOrderRequest,
    SubmitOrderResponse,
    QueryOrderRequest,
    QueryOrderResponse,
    CancelOrderRequest,
    CancelOrderResponse,
    FillInfo,
)


logger = logging.getLogger(__name__)


# ============================================================
# MOCK CONFIGURATION
# ============================================================

@dataclass
class MockConfig:
    """Configuration for mock adapter."""
    
    # Latency simulation
    min_latency_ms: float = 10.0
    """Minimum simulated latency."""
    
    max_latency_ms: float = 100.0
    """Maximum simulated latency."""
    
    # Initial state
    initial_balance: Decimal = Decimal("1500.0")
    """Initial USDT balance."""
    
    initial_positions: Dict[str, Decimal] = field(default_factory=dict)
    """Initial positions by symbol."""
    
    # Fill behavior
    immediate_fill: bool = True
    """Whether market orders fill immediately."""
    
    partial_fill_probability: float = 0.0
    """Probability of partial fill (0.0 to 1.0)."""
    
    partial_fill_ratio: float = 0.5
    """Ratio for partial fills."""
    
    # Error injection
    rejection_probability: float = 0.0
    """Probability of order rejection."""
    
    timeout_probability: float = 0.0
    """Probability of timeout."""
    
    network_error_probability: float = 0.0
    """Probability of network error."""
    
    # Pricing
    default_price: Decimal = Decimal("50000.0")
    """Default price for all symbols."""
    
    slippage_bps: int = 5
    """Slippage in basis points."""


# ============================================================
# MOCK ORDER
# ============================================================

@dataclass
class MockOrder:
    """Mock order state."""
    
    order_id: str
    client_order_id: Optional[str]
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal]
    stop_price: Optional[Decimal]
    time_in_force: TimeInForce
    position_side: PositionSide
    reduce_only: bool
    
    status: str = "NEW"
    filled_quantity: Decimal = Decimal("0")
    average_price: Optional[Decimal] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


# ============================================================
# MOCK EXCHANGE ADAPTER
# ============================================================

class MockExchangeAdapter(ExchangeAdapter):
    """
    Mock exchange adapter for testing.
    
    Simulates exchange behavior including:
    - Order submission and fills
    - Position tracking
    - Balance management
    - Error injection
    """
    
    def __init__(self, config: Optional[MockConfig] = None):
        """
        Initialize mock adapter.
        
        Args:
            config: Mock configuration
        """
        self._config = config or MockConfig()
        self._connected = False
        
        # State
        self._balances: Dict[str, AccountBalance] = {}
        self._positions: Dict[str, PositionInfo] = {}
        self._orders: Dict[str, MockOrder] = {}
        self._fills: List[FillInfo] = []
        
        # Symbol rules cache
        self._symbol_rules: Dict[str, SymbolRules] = {}
        
        # Current prices
        self._prices: Dict[str, Decimal] = {}
        
        # Error injection hooks
        self._on_submit: Optional[Callable[[SubmitOrderRequest], None]] = None
        self._force_next_error: Optional[str] = None
        
        # Initialize state
        self._init_state()
    
    def _init_state(self) -> None:
        """Initialize mock state."""
        # Initialize USDT balance
        self._balances["USDT"] = AccountBalance(
            asset="USDT",
            free=self._config.initial_balance,
            locked=Decimal("0"),
        )
        
        # Initialize positions
        for symbol, qty in self._config.initial_positions.items():
            self._positions[symbol] = PositionInfo(
                symbol=symbol,
                side=PositionSide.LONG if qty > 0 else PositionSide.SHORT,
                quantity=qty,
                entry_price=self._config.default_price,
            )
        
        # Initialize default symbol rules
        for symbol in ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]:
            self._symbol_rules[symbol] = SymbolRules(
                symbol=symbol,
                status="TRADING",
                base_asset=symbol.replace("USDT", ""),
                quote_asset="USDT",
                min_quantity=Decimal("0.001"),
                max_quantity=Decimal("1000"),
                quantity_step=Decimal("0.001"),
                quantity_precision=3,
                min_price=Decimal("0.01"),
                max_price=Decimal("1000000"),
                price_step=Decimal("0.01"),
                price_precision=2,
                min_notional=Decimal("10"),
                max_leverage=125,
            )
    
    @property
    def exchange_id(self) -> str:
        return "mock"
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    # --------------------------------------------------------
    # CONNECTION
    # --------------------------------------------------------
    
    async def connect(self) -> None:
        """Connect to mock exchange."""
        await self._simulate_latency()
        self._connected = True
        logger.info("MockExchangeAdapter connected")
    
    async def disconnect(self) -> None:
        """Disconnect from mock exchange."""
        self._connected = False
        logger.info("MockExchangeAdapter disconnected")
    
    # --------------------------------------------------------
    # ACCOUNT OPERATIONS
    # --------------------------------------------------------
    
    async def get_account_state(self) -> AccountState:
        await self._simulate_latency()
        
        total_balance = sum(b.total for b in self._balances.values())
        available = sum(b.free for b in self._balances.values())
        
        return AccountState(
            timestamp=datetime.utcnow(),
            exchange_id=self.exchange_id,
            balances=dict(self._balances),
            positions=dict(self._positions),
            total_margin_balance=total_balance,
            available_margin=available,
            used_margin=total_balance - available,
        )
    
    async def get_balance(self, asset: str) -> AccountBalance:
        await self._simulate_latency()
        return self._balances.get(asset, AccountBalance(asset=asset))
    
    async def get_position(self, symbol: str) -> Optional[PositionInfo]:
        await self._simulate_latency()
        return self._positions.get(symbol)
    
    async def get_all_positions(self) -> List[PositionInfo]:
        await self._simulate_latency()
        return list(self._positions.values())
    
    # --------------------------------------------------------
    # ORDER OPERATIONS
    # --------------------------------------------------------
    
    async def submit_order(
        self,
        request: SubmitOrderRequest,
    ) -> SubmitOrderResponse:
        await self._simulate_latency()
        
        # Check for injected errors
        if self._force_next_error:
            error = self._force_next_error
            self._force_next_error = None
            return SubmitOrderResponse(
                success=False,
                error_code=error,
                error_message=f"Injected error: {error}",
            )
        
        # Simulate random errors
        import random
        if random.random() < self._config.rejection_probability:
            return SubmitOrderResponse(
                success=False,
                error_code="EXC_INSUFFICIENT_MARGIN",
                error_message="Simulated rejection",
            )
        
        if random.random() < self._config.timeout_probability:
            raise ExchangeError("Simulated timeout", code="TMO_READ", is_retryable=True)
        
        if random.random() < self._config.network_error_probability:
            raise ExchangeError("Simulated network error", code="NET_CONNECTION_FAILED", is_retryable=True)
        
        # Create order
        order_id = str(uuid.uuid4())
        client_order_id = request.client_order_id or str(uuid.uuid4())
        
        order = MockOrder(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            price=request.price,
            stop_price=request.stop_price,
            time_in_force=request.time_in_force,
            position_side=request.position_side,
            reduce_only=request.reduce_only,
        )
        
        self._orders[order_id] = order
        
        # Immediate fill for market orders
        filled_qty = Decimal("0")
        avg_price = None
        
        if self._config.immediate_fill and request.order_type == OrderType.MARKET:
            # Check for partial fill
            if random.random() < self._config.partial_fill_probability:
                filled_qty = request.quantity * Decimal(str(self._config.partial_fill_ratio))
                order.status = "PARTIALLY_FILLED"
            else:
                filled_qty = request.quantity
                order.status = "FILLED"
            
            # Calculate fill price with slippage
            base_price = self._get_price(request.symbol)
            slippage = base_price * Decimal(str(self._config.slippage_bps)) / Decimal("10000")
            
            if request.side == OrderSide.BUY:
                avg_price = base_price + slippage
            else:
                avg_price = base_price - slippage
            
            order.filled_quantity = filled_qty
            order.average_price = avg_price
            order.updated_at = datetime.utcnow()
            
            # Update position
            self._update_position(request.symbol, request.side, filled_qty, avg_price)
            
            # Record fill
            self._fills.append(FillInfo(
                trade_id=str(uuid.uuid4()),
                order_id=order_id,
                symbol=request.symbol,
                side=request.side,
                quantity=filled_qty,
                price=avg_price,
            ))
        
        return SubmitOrderResponse(
            success=True,
            exchange_order_id=order_id,
            client_order_id=client_order_id,
            status=order.status,
            filled_quantity=filled_qty,
            average_price=avg_price,
            exchange_timestamp=datetime.utcnow(),
        )
    
    async def query_order(
        self,
        request: QueryOrderRequest,
    ) -> QueryOrderResponse:
        await self._simulate_latency()
        
        # Find order
        order = None
        
        if request.exchange_order_id:
            order = self._orders.get(request.exchange_order_id)
        elif request.client_order_id:
            for o in self._orders.values():
                if o.client_order_id == request.client_order_id:
                    order = o
                    break
        
        if not order:
            return QueryOrderResponse(found=False)
        
        return QueryOrderResponse(
            found=True,
            exchange_order_id=order.order_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            status=order.status,
            quantity=order.quantity,
            filled_quantity=order.filled_quantity,
            remaining_quantity=order.quantity - order.filled_quantity,
            price=order.price,
            average_price=order.average_price,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
    
    async def cancel_order(
        self,
        request: CancelOrderRequest,
    ) -> CancelOrderResponse:
        await self._simulate_latency()
        
        # Find order
        order = None
        order_id = request.exchange_order_id
        
        if order_id:
            order = self._orders.get(order_id)
        elif request.client_order_id:
            for oid, o in self._orders.items():
                if o.client_order_id == request.client_order_id:
                    order = o
                    order_id = oid
                    break
        
        if not order:
            return CancelOrderResponse(
                success=False,
                error_code="EXC_ORDER_NOT_FOUND",
                error_message="Order not found",
            )
        
        if order.status in {"FILLED", "CANCELED", "EXPIRED", "REJECTED"}:
            return CancelOrderResponse(
                success=False,
                error_code="EXC_ORDER_NOT_FOUND",
                error_message=f"Order already in terminal state: {order.status}",
            )
        
        order.status = "CANCELED"
        order.updated_at = datetime.utcnow()
        
        return CancelOrderResponse(
            success=True,
            exchange_order_id=order_id,
            status="CANCELED",
        )
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        await self._simulate_latency()
        
        count = 0
        for order in self._orders.values():
            if symbol and order.symbol != symbol:
                continue
            if order.status not in {"FILLED", "CANCELED", "EXPIRED", "REJECTED"}:
                order.status = "CANCELED"
                order.updated_at = datetime.utcnow()
                count += 1
        
        return count
    
    async def get_open_orders(
        self,
        symbol: Optional[str] = None,
    ) -> List[QueryOrderResponse]:
        await self._simulate_latency()
        
        results = []
        for order in self._orders.values():
            if symbol and order.symbol != symbol:
                continue
            if order.status in {"NEW", "PARTIALLY_FILLED"}:
                results.append(QueryOrderResponse(
                    found=True,
                    exchange_order_id=order.order_id,
                    client_order_id=order.client_order_id,
                    symbol=order.symbol,
                    side=order.side,
                    order_type=order.order_type,
                    status=order.status,
                    quantity=order.quantity,
                    filled_quantity=order.filled_quantity,
                    remaining_quantity=order.quantity - order.filled_quantity,
                    price=order.price,
                    average_price=order.average_price,
                    created_at=order.created_at,
                    updated_at=order.updated_at,
                ))
        
        return results
    
    # --------------------------------------------------------
    # SYMBOL RULES
    # --------------------------------------------------------
    
    async def get_symbol_rules(self, symbol: str) -> SymbolRules:
        await self._simulate_latency()
        
        if symbol not in self._symbol_rules:
            # Create default rules
            self._symbol_rules[symbol] = SymbolRules(
                symbol=symbol,
                status="TRADING",
                base_asset=symbol.replace("USDT", ""),
                quote_asset="USDT",
                min_quantity=Decimal("0.001"),
                max_quantity=Decimal("1000"),
                quantity_step=Decimal("0.001"),
                quantity_precision=3,
                min_price=Decimal("0.01"),
                max_price=Decimal("1000000"),
                price_step=Decimal("0.01"),
                price_precision=2,
                min_notional=Decimal("10"),
            )
        
        return self._symbol_rules[symbol]
    
    async def get_all_symbol_rules(self) -> Dict[str, SymbolRules]:
        await self._simulate_latency()
        return dict(self._symbol_rules)
    
    # --------------------------------------------------------
    # MARKET DATA
    # --------------------------------------------------------
    
    async def get_current_price(self, symbol: str) -> Decimal:
        await self._simulate_latency()
        return self._get_price(symbol)
    
    def _get_price(self, symbol: str) -> Decimal:
        """Get price for symbol."""
        if symbol in self._prices:
            return self._prices[symbol]
        
        # Default prices
        default_prices = {
            "BTCUSDT": Decimal("50000"),
            "ETHUSDT": Decimal("3000"),
            "BNBUSDT": Decimal("400"),
            "SOLUSDT": Decimal("100"),
        }
        
        return default_prices.get(symbol, self._config.default_price)
    
    def set_price(self, symbol: str, price: Decimal) -> None:
        """Set price for testing."""
        self._prices[symbol] = price
    
    # --------------------------------------------------------
    # RATE LIMITING
    # --------------------------------------------------------
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        return {
            "orders_remaining": 100,
            "weight_remaining": 1200,
            "reset_at": datetime.utcnow(),
        }
    
    async def wait_for_rate_limit(self) -> None:
        pass  # No rate limiting in mock
    
    # --------------------------------------------------------
    # TEST HELPERS
    # --------------------------------------------------------
    
    def set_balance(self, asset: str, free: Decimal, locked: Decimal = Decimal("0")) -> None:
        """Set balance for testing."""
        self._balances[asset] = AccountBalance(
            asset=asset,
            free=free,
            locked=locked,
        )
    
    def set_position(
        self,
        symbol: str,
        quantity: Decimal,
        entry_price: Decimal,
    ) -> None:
        """Set position for testing."""
        self._positions[symbol] = PositionInfo(
            symbol=symbol,
            side=PositionSide.LONG if quantity > 0 else PositionSide.SHORT,
            quantity=quantity,
            entry_price=entry_price,
        )
    
    def inject_error(self, error_code: str) -> None:
        """Inject error for next submission."""
        self._force_next_error = error_code
    
    def get_fills(self) -> List[FillInfo]:
        """Get all fills."""
        return list(self._fills)
    
    def reset(self) -> None:
        """Reset mock state."""
        self._orders.clear()
        self._fills.clear()
        self._init_state()
    
    # --------------------------------------------------------
    # INTERNAL
    # --------------------------------------------------------
    
    async def _simulate_latency(self) -> None:
        """Simulate network latency."""
        import random
        latency_ms = random.uniform(
            self._config.min_latency_ms,
            self._config.max_latency_ms,
        )
        await asyncio.sleep(latency_ms / 1000)
    
    def _update_position(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        """Update position after fill."""
        current = self._positions.get(symbol)
        
        if side == OrderSide.BUY:
            delta = quantity
        else:
            delta = -quantity
        
        if current is None:
            if delta != 0:
                self._positions[symbol] = PositionInfo(
                    symbol=symbol,
                    side=PositionSide.LONG if delta > 0 else PositionSide.SHORT,
                    quantity=delta,
                    entry_price=price,
                )
        else:
            new_qty = current.quantity + delta
            if new_qty == 0:
                del self._positions[symbol]
            else:
                current.quantity = new_qty
                current.side = PositionSide.LONG if new_qty > 0 else PositionSide.SHORT
