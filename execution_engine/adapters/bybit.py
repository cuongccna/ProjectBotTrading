"""
Bybit Exchange Adapter.

============================================================
PURPOSE
============================================================
Production adapter for Bybit V5 Unified API.

EXCHANGE SPECIFICS:
- Uses V5 Unified API (linear, inverse, spot, option)
- HMAC-SHA256 signing
- Symbol format: BTCUSDT (linear perpetual)
- Unified account structure
- Category-based endpoints

============================================================
API DOCUMENTATION
============================================================
https://bybit-exchange.github.io/docs/v5/intro

============================================================
"""

import os
import hmac
import hashlib
import time
import logging
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List

import aiohttp

from .base import (
    ExchangeAdapter,
    SubmitOrderRequest,
    SubmitOrderResponse,
    QueryOrderRequest,
    QueryOrderResponse,
    CancelOrderRequest,
    CancelOrderResponse,
    FillInfo,
    SymbolRules,
    AccountState,
    BalanceInfo,
    PositionInfo,
    RateLimitStatus,
    map_exchange_status_to_order_state,
)
from .errors import (
    ExchangeError,
    ExchangeException,
    ErrorCategory,
    map_bybit_error,
    create_network_error,
    create_timeout_error,
)
from .metrics import AdapterMetrics, get_global_aggregator
from .logging_utils import AdapterLogger


logger = logging.getLogger(__name__)


# ============================================================
# CONSTANTS
# ============================================================

BYBIT_REST_URL = "https://api.bybit.com"
BYBIT_TESTNET_URL = "https://api-testnet.bybit.com"

# Categories
BYBIT_CAT_LINEAR = "linear"      # USDT perpetual
BYBIT_CAT_INVERSE = "inverse"    # Inverse perpetual
BYBIT_CAT_SPOT = "spot"
BYBIT_CAT_OPTION = "option"

# Order sides
BYBIT_SIDE_BUY = "Buy"
BYBIT_SIDE_SELL = "Sell"

# Order types
BYBIT_ORDER_MARKET = "Market"
BYBIT_ORDER_LIMIT = "Limit"

# Time in force
BYBIT_TIF_GTC = "GTC"
BYBIT_TIF_IOC = "IOC"
BYBIT_TIF_FOK = "FOK"
BYBIT_TIF_POST_ONLY = "PostOnly"

# Position index
BYBIT_POS_ONE_WAY = 0
BYBIT_POS_HEDGE_BUY = 1
BYBIT_POS_HEDGE_SELL = 2

# Order status mapping
BYBIT_STATUS_MAP = {
    "New": "NEW",
    "Created": "NEW",
    "PartiallyFilled": "PARTIALLY_FILLED",
    "Filled": "FILLED",
    "Cancelled": "CANCELED",
    "Rejected": "REJECTED",
    "PartiallyFilledCanceled": "CANCELED",
    "Deactivated": "CANCELED",
    "Triggered": "NEW",
    "Active": "NEW",
}


# ============================================================
# BYBIT ADAPTER
# ============================================================

class BybitAdapter(ExchangeAdapter):
    """
    Bybit V5 Unified API adapter.
    
    Implements ExchangeAdapter interface for Bybit's unified trading API.
    
    Features:
    - Linear (USDT) and inverse perpetual support
    - Unified account structure
    - One-way and hedge mode positions
    """
    
    def __init__(
        self,
        api_key: str = None,
        api_secret: str = None,
        testnet: bool = False,
        category: str = BYBIT_CAT_LINEAR,
        recv_window: int = 5000,
        timeout_seconds: float = 30.0,
    ):
        """
        Initialize Bybit adapter.
        
        Args:
            api_key: Bybit API key (or from BYBIT_API_KEY env)
            api_secret: Bybit API secret (or from BYBIT_API_SECRET env)
            testnet: Use testnet
            category: Trading category (linear, inverse)
            recv_window: Request validity window in ms
            timeout_seconds: Request timeout
        """
        self._api_key = api_key or os.environ.get("BYBIT_API_KEY", "")
        self._api_secret = api_secret or os.environ.get("BYBIT_API_SECRET", "")
        
        self._testnet = testnet
        self._category = category
        self._recv_window = recv_window
        self._timeout = timeout_seconds
        
        # Select base URL
        self._base_url = BYBIT_TESTNET_URL if testnet else BYBIT_REST_URL
        
        # Session
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected = False
        
        # Symbol rules cache
        self._symbol_rules: Dict[str, SymbolRules] = {}
        self._rules_loaded = False
        
        # Rate limit tracking
        self._rate_limit_used = 0
        self._rate_limit_max = 120  # Default limit
        self._last_request_time = 0.0
        
        # Metrics and logging
        self._metrics = AdapterMetrics("bybit")
        self._logger = AdapterLogger("bybit")
        get_global_aggregator().register("bybit", self._metrics)
    
    # --------------------------------------------------------
    # PROPERTIES
    # --------------------------------------------------------
    
    @property
    def exchange_id(self) -> str:
        """Exchange identifier."""
        return "bybit"
    
    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected and self._session is not None
    
    # --------------------------------------------------------
    # CONNECTION
    # --------------------------------------------------------
    
    async def connect(self) -> None:
        """Establish connection."""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        
        # Validate credentials
        try:
            await self._request("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
            self._connected = True
            self._logger.info("Connected to Bybit")
            
            # Load symbol rules
            await self._load_instruments()
            
        except Exception as e:
            self._connected = False
            self._logger.error(f"Connection failed: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Close connection."""
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False
        self._logger.info("Disconnected from Bybit")
    
    # --------------------------------------------------------
    # SIGNING
    # --------------------------------------------------------
    
    def _sign_request(
        self,
        timestamp: str,
        params: str,
    ) -> str:
        """
        Create request signature.
        
        Bybit V5 signature: HMAC-SHA256(timestamp + api_key + recv_window + params)
        
        Args:
            timestamp: Millisecond timestamp
            params: Query string or JSON body
            
        Returns:
            Hex signature
        """
        param_str = f"{timestamp}{self._api_key}{self._recv_window}{params}"
        signature = hmac.new(
            self._api_secret.encode(),
            param_str.encode(),
            hashlib.sha256,
        ).hexdigest()
        return signature
    
    def _get_timestamp(self) -> str:
        """Get millisecond timestamp."""
        return str(int(time.time() * 1000))
    
    # --------------------------------------------------------
    # REQUEST HANDLING
    # --------------------------------------------------------
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, Any] = None,
        body: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Make signed request to Bybit API.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            body: Request body
            
        Returns:
            Response data
        """
        if not self._session:
            raise ExchangeException(
                create_network_error("bybit", "Not connected")
            )
        
        # Build URL
        url = f"{self._base_url}{endpoint}"
        
        # Timestamp
        timestamp = self._get_timestamp()
        
        # Prepare params/body string for signing
        if method == "GET":
            param_str = "&".join(f"{k}={v}" for k, v in (params or {}).items())
        else:
            import json
            param_str = json.dumps(body) if body else ""
        
        # Create signature
        signature = self._sign_request(timestamp, param_str)
        
        # Headers
        headers = {
            "Content-Type": "application/json",
            "X-BAPI-API-KEY": self._api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": str(self._recv_window),
        }
        
        # Log request
        request_id = self._logger.log_request(
            operation=endpoint.split("/")[-1],
            method=method,
            endpoint=endpoint,
            headers=headers,
            params=params,
            body=body,
        )
        
        start_time = time.time()
        
        try:
            if method == "GET":
                if params:
                    url = f"{url}?{param_str}"
                async with self._session.get(url, headers=headers) as resp:
                    return await self._handle_response(
                        resp, request_id, endpoint, start_time
                    )
            elif method == "POST":
                async with self._session.post(
                    url, headers=headers, json=body
                ) as resp:
                    return await self._handle_response(
                        resp, request_id, endpoint, start_time
                    )
        except aiohttp.ClientError as e:
            latency_ms = (time.time() - start_time) * 1000
            self._metrics.record_request(
                endpoint=endpoint,
                latency_ms=latency_ms,
                success=False,
                error_code="NETWORK_ERROR",
            )
            raise ExchangeException(
                create_network_error("bybit", str(e), endpoint)
            )
        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            self._metrics.record_request(
                endpoint=endpoint,
                latency_ms=latency_ms,
                success=False,
                error_code="TIMEOUT",
            )
            raise ExchangeException(
                create_timeout_error("bybit", int(self._timeout * 1000), endpoint)
            )
    
    async def _handle_response(
        self,
        response: aiohttp.ClientResponse,
        request_id: str,
        endpoint: str,
        start_time: float,
    ) -> Dict[str, Any]:
        """Handle API response."""
        latency_ms = (time.time() - start_time) * 1000
        
        # Track rate limits from headers
        if "X-Bapi-Limit-Status" in response.headers:
            self._rate_limit_used = int(response.headers.get("X-Bapi-Limit-Status", 0))
        if "X-Bapi-Limit" in response.headers:
            self._rate_limit_max = int(response.headers.get("X-Bapi-Limit", 120))
        
        try:
            data = await response.json()
        except Exception:
            data = {"retCode": -1, "retMsg": await response.text()}
        
        # Bybit returns retCode 0 for success
        ret_code = data.get("retCode", 0)
        ret_msg = data.get("retMsg", "")
        
        if ret_code != 0:
            error = map_bybit_error(ret_code, ret_msg, response.status)
            
            self._metrics.record_request(
                endpoint=endpoint,
                latency_ms=latency_ms,
                success=False,
                status_code=response.status,
                error_code=error.code,
            )
            
            self._logger.log_response(
                operation=endpoint.split("/")[-1],
                request_id=request_id,
                status_code=response.status,
                latency_ms=latency_ms,
                success=False,
                error_code=error.code,
                error_message=ret_msg,
            )
            
            raise ExchangeException(error)
        
        # Success
        self._metrics.record_request(
            endpoint=endpoint,
            latency_ms=latency_ms,
            success=True,
            status_code=response.status,
        )
        
        self._logger.log_response(
            operation=endpoint.split("/")[-1],
            request_id=request_id,
            status_code=response.status,
            latency_ms=latency_ms,
            success=True,
            response_body=data,
        )
        
        return data.get("result", {})
    
    # --------------------------------------------------------
    # ACCOUNT OPERATIONS
    # --------------------------------------------------------
    
    async def get_account_state(self) -> AccountState:
        """Get account state."""
        data = await self._request(
            "GET",
            "/v5/account/wallet-balance",
            {"accountType": "UNIFIED"},
        )
        
        account_list = data.get("list", [])
        if not account_list:
            return AccountState(equity=Decimal("0"), available_margin=Decimal("0"))
        
        account = account_list[0]
        
        return AccountState(
            equity=Decimal(account.get("totalEquity", "0")),
            available_margin=Decimal(account.get("totalAvailableBalance", "0")),
            used_margin=Decimal(account.get("totalInitialMargin", "0")),
            unrealized_pnl=Decimal(account.get("totalPerpUPL", "0")),
        )
    
    async def get_balance(self, asset: str = "USDT") -> BalanceInfo:
        """Get asset balance."""
        data = await self._request(
            "GET",
            "/v5/account/wallet-balance",
            {"accountType": "UNIFIED"},
        )
        
        account_list = data.get("list", [])
        if not account_list:
            return BalanceInfo(
                asset=asset,
                total=Decimal("0"),
                available=Decimal("0"),
                locked=Decimal("0"),
            )
        
        coins = account_list[0].get("coin", [])
        coin_data = next(
            (c for c in coins if c.get("coin") == asset),
            {},
        )
        
        total = Decimal(coin_data.get("walletBalance", "0"))
        available = Decimal(coin_data.get("availableToWithdraw", "0"))
        
        return BalanceInfo(
            asset=asset,
            total=total,
            available=available,
            locked=total - available,
        )
    
    async def get_position(self, symbol: str) -> Optional[PositionInfo]:
        """Get position for symbol."""
        data = await self._request(
            "GET",
            "/v5/position/list",
            {"category": self._category, "symbol": symbol},
        )
        
        positions = data.get("list", [])
        if not positions:
            return None
        
        pos = positions[0]
        
        size = Decimal(pos.get("size", "0"))
        if size == 0:
            return None
        
        side = pos.get("side", "")
        
        return PositionInfo(
            symbol=symbol,
            side="LONG" if side == "Buy" else "SHORT",
            quantity=size,
            entry_price=Decimal(pos.get("avgPrice", "0")),
            unrealized_pnl=Decimal(pos.get("unrealisedPnl", "0")),
            leverage=int(float(pos.get("leverage", "1"))),
            margin=Decimal(pos.get("positionIM", "0")),
            liquidation_price=Decimal(pos.get("liqPrice", "0")) if pos.get("liqPrice") else None,
        )
    
    async def get_all_positions(self) -> List[PositionInfo]:
        """Get all positions."""
        data = await self._request(
            "GET",
            "/v5/position/list",
            {"category": self._category, "settleCoin": "USDT"},
        )
        
        positions = []
        for pos in data.get("list", []):
            size = Decimal(pos.get("size", "0"))
            if size == 0:
                continue
            
            side = pos.get("side", "")
            
            positions.append(PositionInfo(
                symbol=pos.get("symbol", ""),
                side="LONG" if side == "Buy" else "SHORT",
                quantity=size,
                entry_price=Decimal(pos.get("avgPrice", "0")),
                unrealized_pnl=Decimal(pos.get("unrealisedPnl", "0")),
                leverage=int(float(pos.get("leverage", "1"))),
                margin=Decimal(pos.get("positionIM", "0")),
            ))
        
        return positions
    
    # --------------------------------------------------------
    # ORDER OPERATIONS
    # --------------------------------------------------------
    
    async def submit_order(self, request: SubmitOrderRequest) -> SubmitOrderResponse:
        """Submit order."""
        start_time = time.time()
        
        # Build order body
        order_body = {
            "category": self._category,
            "symbol": request.symbol,
            "side": "Buy" if request.side.upper() == "BUY" else "Sell",
            "orderType": "Market" if request.order_type.upper() == "MARKET" else "Limit",
            "qty": str(request.quantity),
        }
        
        # Time in force
        tif = (request.time_in_force or "GTC").upper()
        if request.order_type.upper() == "LIMIT":
            if tif == "IOC":
                order_body["timeInForce"] = BYBIT_TIF_IOC
            elif tif == "FOK":
                order_body["timeInForce"] = BYBIT_TIF_FOK
            elif tif in ("GTX", "POST_ONLY"):
                order_body["timeInForce"] = BYBIT_TIF_POST_ONLY
            else:
                order_body["timeInForce"] = BYBIT_TIF_GTC
        else:
            order_body["timeInForce"] = BYBIT_TIF_IOC  # Market orders use IOC
        
        # Price for limit orders
        if request.price and request.order_type.upper() != "MARKET":
            order_body["price"] = str(request.price)
        
        # Client order ID
        if request.client_order_id:
            order_body["orderLinkId"] = request.client_order_id
        
        # Reduce only
        if request.reduce_only:
            order_body["reduceOnly"] = True
        
        try:
            data = await self._request("POST", "/v5/order/create", body=order_body)
            
            latency_ms = (time.time() - start_time) * 1000
            
            self._metrics.record_order_submitted()
            
            self._logger.log_order(
                operation="submit",
                client_order_id=request.client_order_id or "",
                exchange_order_id=data.get("orderId", ""),
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                quantity=str(request.quantity),
                price=str(request.price) if request.price else None,
                status="NEW",
                latency_ms=latency_ms,
            )
            
            return SubmitOrderResponse(
                success=True,
                exchange_order_id=data.get("orderId", ""),
                client_order_id=data.get("orderLinkId", request.client_order_id),
                status="NEW",
                exchange_timestamp=int(time.time() * 1000),
            )
            
        except ExchangeException as e:
            latency_ms = (time.time() - start_time) * 1000
            
            self._metrics.record_order_rejected(e.error.code)
            
            self._logger.log_order(
                operation="submit",
                client_order_id=request.client_order_id or "",
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                quantity=str(request.quantity),
                price=str(request.price) if request.price else None,
                error_code=e.error.code,
                error_message=e.error.message,
                latency_ms=latency_ms,
            )
            
            return SubmitOrderResponse(
                success=False,
                exchange_order_id=None,
                client_order_id=request.client_order_id,
                status="REJECTED",
                error_code=e.error.code,
                error_message=e.error.message,
                exchange_timestamp=int(time.time() * 1000),
            )
        except Exception as e:
            self._metrics.record_order_rejected("EXCEPTION")
            
            return SubmitOrderResponse(
                success=False,
                exchange_order_id=None,
                client_order_id=request.client_order_id,
                status="REJECTED",
                error_code="EXCEPTION",
                error_message=str(e),
                exchange_timestamp=int(time.time() * 1000),
            )
    
    async def query_order(self, request: QueryOrderRequest) -> QueryOrderResponse:
        """Query order status."""
        params = {
            "category": self._category,
            "symbol": request.symbol,
        }
        
        if request.exchange_order_id:
            params["orderId"] = request.exchange_order_id
        elif request.client_order_id:
            params["orderLinkId"] = request.client_order_id
        else:
            return QueryOrderResponse(
                success=False,
                exchange_order_id=request.exchange_order_id,
                client_order_id=request.client_order_id,
                status="UNKNOWN",
                error_code="MISSING_ID",
                error_message="Either exchange_order_id or client_order_id required",
            )
        
        try:
            data = await self._request("GET", "/v5/order/realtime", params)
            
            orders = data.get("list", [])
            if not orders:
                # Try history
                data = await self._request("GET", "/v5/order/history", params)
                orders = data.get("list", [])
            
            if not orders:
                return QueryOrderResponse(
                    success=False,
                    exchange_order_id=request.exchange_order_id,
                    client_order_id=request.client_order_id,
                    status="UNKNOWN",
                    error_code="ORDER_NOT_FOUND",
                    error_message="Order not found",
                )
            
            order = orders[0]
            
            bybit_status = order.get("orderStatus", "")
            status = BYBIT_STATUS_MAP.get(bybit_status, bybit_status.upper())
            
            return QueryOrderResponse(
                success=True,
                exchange_order_id=order.get("orderId", ""),
                client_order_id=order.get("orderLinkId", ""),
                status=status,
                filled_quantity=Decimal(order.get("cumExecQty", "0")),
                remaining_quantity=Decimal(order.get("leavesQty", "0")),
                average_price=Decimal(order.get("avgPrice", "0")) if order.get("avgPrice") else None,
                exchange_timestamp=int(order.get("updatedTime", 0)),
            )
            
        except ExchangeException as e:
            return QueryOrderResponse(
                success=False,
                exchange_order_id=request.exchange_order_id,
                client_order_id=request.client_order_id,
                status="UNKNOWN",
                error_code=e.error.code,
                error_message=e.error.message,
            )
    
    async def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResponse:
        """Cancel order."""
        cancel_body = {
            "category": self._category,
            "symbol": request.symbol,
        }
        
        if request.exchange_order_id:
            cancel_body["orderId"] = request.exchange_order_id
        elif request.client_order_id:
            cancel_body["orderLinkId"] = request.client_order_id
        else:
            return CancelOrderResponse(
                success=False,
                exchange_order_id=request.exchange_order_id,
                client_order_id=request.client_order_id,
                error_code="MISSING_ID",
                error_message="Either exchange_order_id or client_order_id required",
            )
        
        try:
            data = await self._request("POST", "/v5/order/cancel", body=cancel_body)
            
            self._metrics.record_order_canceled()
            
            return CancelOrderResponse(
                success=True,
                exchange_order_id=data.get("orderId", ""),
                client_order_id=data.get("orderLinkId", ""),
            )
            
        except ExchangeException as e:
            return CancelOrderResponse(
                success=False,
                exchange_order_id=request.exchange_order_id,
                client_order_id=request.client_order_id,
                error_code=e.error.code,
                error_message=e.error.message,
            )
    
    async def cancel_all_orders(self, symbol: str = None) -> int:
        """Cancel all open orders."""
        cancel_body = {"category": self._category}
        
        if symbol:
            cancel_body["symbol"] = symbol
        else:
            # Need settleCoin for batch cancel
            cancel_body["settleCoin"] = "USDT"
        
        try:
            data = await self._request("POST", "/v5/order/cancel-all", body=cancel_body)
            
            # Response contains list of canceled orders
            canceled = len(data.get("list", []))
            return canceled
            
        except Exception as e:
            logger.error(f"Error in cancel_all_orders: {e}")
            return 0
    
    async def get_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Get open orders."""
        params = {"category": self._category}
        
        if symbol:
            params["symbol"] = symbol
        
        data = await self._request("GET", "/v5/order/realtime", params)
        
        orders = []
        for order in data.get("list", []):
            bybit_status = order.get("orderStatus", "")
            orders.append({
                "exchange_order_id": order.get("orderId"),
                "client_order_id": order.get("orderLinkId"),
                "symbol": order.get("symbol"),
                "side": "BUY" if order.get("side") == "Buy" else "SELL",
                "order_type": order.get("orderType", "").upper(),
                "quantity": Decimal(order.get("qty", "0")),
                "price": Decimal(order.get("price", "0")) if order.get("price") else None,
                "filled_quantity": Decimal(order.get("cumExecQty", "0")),
                "status": BYBIT_STATUS_MAP.get(bybit_status, bybit_status.upper()),
                "created_time": int(order.get("createdTime", 0)),
            })
        
        return orders
    
    # --------------------------------------------------------
    # SYMBOL RULES
    # --------------------------------------------------------
    
    async def _load_instruments(self) -> None:
        """Load instrument info."""
        data = await self._request(
            "GET",
            "/v5/market/instruments-info",
            {"category": self._category},
        )
        
        for inst in data.get("list", []):
            symbol = inst.get("symbol", "")
            
            lot_filter = inst.get("lotSizeFilter", {})
            price_filter = inst.get("priceFilter", {})
            
            qty_step = Decimal(lot_filter.get("qtyStep", "1"))
            tick_size = Decimal(price_filter.get("tickSize", "0.01"))
            min_qty = Decimal(lot_filter.get("minOrderQty", "1"))
            max_qty = Decimal(lot_filter.get("maxOrderQty", "100000"))
            
            self._symbol_rules[symbol] = SymbolRules(
                symbol=symbol,
                base_asset=inst.get("baseCoin", ""),
                quote_asset=inst.get("quoteCoin", "USDT"),
                price_precision=self._get_precision(tick_size),
                quantity_precision=self._get_precision(qty_step),
                min_quantity=min_qty,
                max_quantity=max_qty,
                min_notional=Decimal("1"),  # Bybit doesn't expose this directly
                tick_size=tick_size,
                step_size=qty_step,
            )
        
        self._rules_loaded = True
        self._logger.info(f"Loaded {len(self._symbol_rules)} instruments")
    
    def _get_precision(self, value: Decimal) -> int:
        """Get decimal precision from step size."""
        if value >= 1:
            return 0
        s = str(value)
        if "." in s:
            return len(s.split(".")[1].rstrip("0"))
        return 0
    
    async def get_symbol_rules(self, symbol: str) -> Optional[SymbolRules]:
        """Get rules for symbol."""
        if not self._rules_loaded:
            await self._load_instruments()
        return self._symbol_rules.get(symbol)
    
    async def get_all_symbol_rules(self) -> Dict[str, SymbolRules]:
        """Get all symbol rules."""
        if not self._rules_loaded:
            await self._load_instruments()
        return dict(self._symbol_rules)
    
    # --------------------------------------------------------
    # MARKET DATA
    # --------------------------------------------------------
    
    async def get_current_price(self, symbol: str) -> Decimal:
        """Get current price."""
        data = await self._request(
            "GET",
            "/v5/market/tickers",
            {"category": self._category, "symbol": symbol},
        )
        
        tickers = data.get("list", [])
        if not tickers:
            return Decimal("0")
        
        return Decimal(tickers[0].get("lastPrice", "0"))
    
    # --------------------------------------------------------
    # RATE LIMITING
    # --------------------------------------------------------
    
    async def get_rate_limit_status(self) -> RateLimitStatus:
        """Get rate limit status."""
        return RateLimitStatus(
            used=self._rate_limit_used,
            max=self._rate_limit_max,
            reset_time=int(time.time() * 1000) + 60000,
        )
    
    async def wait_for_rate_limit(self) -> None:
        """Wait if approaching rate limit."""
        if self._rate_limit_used >= self._rate_limit_max * 0.9:
            await asyncio.sleep(1.0)
            self._rate_limit_used = max(0, self._rate_limit_used - 10)
