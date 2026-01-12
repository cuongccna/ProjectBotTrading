"""
Execution Engine - Binance Futures Adapter.

============================================================
PURPOSE
============================================================
Production adapter for Binance Futures API.

SAFETY FEATURES:
- Rate limit tracking
- Request signing
- Error mapping
- Connection management

============================================================
"""

import asyncio
import hashlib
import hmac
import logging
import os
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from decimal import Decimal
from urllib.parse import urlencode

import aiohttp

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
from ..errors import map_binance_error, get_error_info
from ..config import ExchangeConfig, TimeoutConfig, RateLimitConfig
from .base import (
    ExchangeAdapter,
    SubmitOrderRequest,
    SubmitOrderResponse,
    QueryOrderRequest,
    QueryOrderResponse,
    CancelOrderRequest,
    CancelOrderResponse,
)


logger = logging.getLogger(__name__)


# ============================================================
# BINANCE FUTURES ADAPTER
# ============================================================

class BinanceAdapter(ExchangeAdapter):
    """
    Binance Futures exchange adapter.
    
    Implements the ExchangeAdapter interface for Binance Futures API.
    """
    
    def __init__(
        self,
        config: ExchangeConfig,
        timeout_config: Optional[TimeoutConfig] = None,
        rate_limit_config: Optional[RateLimitConfig] = None,
    ):
        """
        Initialize Binance adapter.
        
        Args:
            config: Exchange configuration
            timeout_config: Timeout configuration
            rate_limit_config: Rate limit configuration
        """
        self._config = config
        self._timeout_config = timeout_config or TimeoutConfig()
        self._rate_limit_config = rate_limit_config or RateLimitConfig()
        
        # Credentials
        self._api_key = os.environ.get(config.api_key_env, "")
        self._api_secret = os.environ.get(config.api_secret_env, "")
        
        # URLs
        if config.testnet:
            self._rest_url = "https://testnet.binancefuture.com"
            self._ws_url = "wss://stream.binancefuture.com"
        else:
            self._rest_url = config.rest_url
            self._ws_url = config.ws_url
        
        # Session
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected = False
        
        # Rate limiting
        self._order_count_minute = 0
        self._weight_used = 0
        self._rate_limit_reset = time.time() + 60
        
        # Symbol rules cache
        self._symbol_rules: Dict[str, SymbolRules] = {}
        self._rules_loaded = False
    
    @property
    def exchange_id(self) -> str:
        return "binance_futures"
    
    @property
    def is_connected(self) -> bool:
        return self._connected and self._session is not None
    
    # --------------------------------------------------------
    # CONNECTION
    # --------------------------------------------------------
    
    async def connect(self) -> None:
        """Connect to Binance."""
        if self._session is not None:
            await self.disconnect()
        
        timeout = aiohttp.ClientTimeout(
            connect=self._timeout_config.connection_timeout_seconds,
            total=self._timeout_config.read_timeout_seconds,
        )
        
        self._session = aiohttp.ClientSession(timeout=timeout)
        
        # Test connection
        try:
            await self._request("GET", "/fapi/v1/ping", signed=False)
            self._connected = True
            logger.info(f"Connected to Binance Futures ({'testnet' if self._config.testnet else 'mainnet'})")
        except Exception as e:
            await self.disconnect()
            raise ExchangeError(f"Failed to connect: {e}", is_retryable=True)
    
    async def disconnect(self) -> None:
        """Disconnect from Binance."""
        self._connected = False
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Disconnected from Binance Futures")
    
    # --------------------------------------------------------
    # ACCOUNT OPERATIONS
    # --------------------------------------------------------
    
    async def get_account_state(self) -> AccountState:
        """Get current account state."""
        data = await self._request("GET", "/fapi/v2/account", signed=True)
        
        balances = {}
        for asset in data.get("assets", []):
            balances[asset["asset"]] = AccountBalance(
                asset=asset["asset"],
                free=Decimal(asset["availableBalance"]),
                locked=Decimal(asset["initialMargin"]),
            )
        
        positions = {}
        for pos in data.get("positions", []):
            qty = Decimal(pos["positionAmt"])
            if qty != 0:
                positions[pos["symbol"]] = PositionInfo(
                    symbol=pos["symbol"],
                    side=PositionSide.LONG if qty > 0 else PositionSide.SHORT,
                    quantity=abs(qty),
                    entry_price=Decimal(pos["entryPrice"]),
                    unrealized_pnl=Decimal(pos["unrealizedProfit"]),
                    leverage=int(pos["leverage"]),
                    margin_type=pos.get("marginType", "cross").upper(),
                    liquidation_price=Decimal(pos["liquidationPrice"]) if pos.get("liquidationPrice") else None,
                )
        
        return AccountState(
            timestamp=datetime.utcnow(),
            exchange_id=self.exchange_id,
            balances=balances,
            positions=positions,
            total_margin_balance=Decimal(data["totalMarginBalance"]),
            available_margin=Decimal(data["availableBalance"]),
            used_margin=Decimal(data["totalInitialMargin"]),
            margin_ratio=Decimal(data.get("totalMaintMargin", "0")) / Decimal(data["totalMarginBalance"]) if Decimal(data["totalMarginBalance"]) > 0 else Decimal("0"),
        )
    
    async def get_balance(self, asset: str) -> AccountBalance:
        """Get balance for specific asset."""
        data = await self._request("GET", "/fapi/v2/balance", signed=True)
        
        for item in data:
            if item["asset"] == asset:
                return AccountBalance(
                    asset=asset,
                    free=Decimal(item["availableBalance"]),
                    locked=Decimal(item["balance"]) - Decimal(item["availableBalance"]),
                )
        
        return AccountBalance(asset=asset)
    
    async def get_position(self, symbol: str) -> Optional[PositionInfo]:
        """Get position for symbol."""
        data = await self._request(
            "GET",
            "/fapi/v2/positionRisk",
            params={"symbol": symbol},
            signed=True,
        )
        
        for pos in data:
            qty = Decimal(pos["positionAmt"])
            if qty != 0:
                return PositionInfo(
                    symbol=pos["symbol"],
                    side=PositionSide.LONG if qty > 0 else PositionSide.SHORT,
                    quantity=abs(qty),
                    entry_price=Decimal(pos["entryPrice"]),
                    unrealized_pnl=Decimal(pos["unRealizedProfit"]),
                    leverage=int(pos["leverage"]),
                    margin_type=pos.get("marginType", "cross").upper(),
                    liquidation_price=Decimal(pos["liquidationPrice"]) if pos.get("liquidationPrice") else None,
                )
        
        return None
    
    async def get_all_positions(self) -> List[PositionInfo]:
        """Get all open positions."""
        data = await self._request("GET", "/fapi/v2/positionRisk", signed=True)
        
        positions = []
        for pos in data:
            qty = Decimal(pos["positionAmt"])
            if qty != 0:
                positions.append(PositionInfo(
                    symbol=pos["symbol"],
                    side=PositionSide.LONG if qty > 0 else PositionSide.SHORT,
                    quantity=abs(qty),
                    entry_price=Decimal(pos["entryPrice"]),
                    unrealized_pnl=Decimal(pos["unRealizedProfit"]),
                    leverage=int(pos["leverage"]),
                ))
        
        return positions
    
    # --------------------------------------------------------
    # ORDER OPERATIONS
    # --------------------------------------------------------
    
    async def submit_order(
        self,
        request: SubmitOrderRequest,
    ) -> SubmitOrderResponse:
        """Submit an order to Binance."""
        params = {
            "symbol": request.symbol,
            "side": request.side.value,
            "type": request.order_type.value,
            "quantity": str(request.quantity),
        }
        
        if request.price is not None:
            params["price"] = str(request.price)
        
        if request.stop_price is not None:
            params["stopPrice"] = str(request.stop_price)
        
        if request.order_type != OrderType.MARKET:
            params["timeInForce"] = request.time_in_force.value
        
        if self._config.hedge_mode:
            params["positionSide"] = request.position_side.value
        
        if request.reduce_only:
            params["reduceOnly"] = "true"
        
        if request.client_order_id:
            params["newClientOrderId"] = request.client_order_id
        
        params["recvWindow"] = str(request.recv_window)
        
        try:
            data = await self._request("POST", "/fapi/v1/order", params=params, signed=True)
            
            return SubmitOrderResponse(
                success=True,
                exchange_order_id=str(data["orderId"]),
                client_order_id=data.get("clientOrderId"),
                status=data["status"],
                filled_quantity=Decimal(data.get("executedQty", "0")),
                average_price=Decimal(data["avgPrice"]) if data.get("avgPrice") else None,
                exchange_timestamp=datetime.fromtimestamp(data["updateTime"] / 1000),
                raw_response=data,
            )
            
        except ExchangeError as e:
            return SubmitOrderResponse(
                success=False,
                error_code=e.code,
                error_message=str(e),
            )
    
    async def query_order(
        self,
        request: QueryOrderRequest,
    ) -> QueryOrderResponse:
        """Query order status."""
        params = {"symbol": request.symbol}
        
        if request.exchange_order_id:
            params["orderId"] = request.exchange_order_id
        elif request.client_order_id:
            params["origClientOrderId"] = request.client_order_id
        else:
            return QueryOrderResponse(found=False, error_message="No order ID provided")
        
        try:
            data = await self._request("GET", "/fapi/v1/order", params=params, signed=True)
            
            return QueryOrderResponse(
                found=True,
                exchange_order_id=str(data["orderId"]),
                client_order_id=data.get("clientOrderId"),
                symbol=data["symbol"],
                side=OrderSide(data["side"]),
                order_type=OrderType(data["type"]),
                status=data["status"],
                quantity=Decimal(data["origQty"]),
                filled_quantity=Decimal(data["executedQty"]),
                remaining_quantity=Decimal(data["origQty"]) - Decimal(data["executedQty"]),
                price=Decimal(data["price"]) if data.get("price") else None,
                average_price=Decimal(data["avgPrice"]) if data.get("avgPrice") else None,
                created_at=datetime.fromtimestamp(data["time"] / 1000),
                updated_at=datetime.fromtimestamp(data["updateTime"] / 1000),
                raw_response=data,
            )
            
        except ExchangeError as e:
            if "Order does not exist" in str(e):
                return QueryOrderResponse(found=False)
            raise
    
    async def cancel_order(
        self,
        request: CancelOrderRequest,
    ) -> CancelOrderResponse:
        """Cancel an order."""
        params = {"symbol": request.symbol}
        
        if request.exchange_order_id:
            params["orderId"] = request.exchange_order_id
        elif request.client_order_id:
            params["origClientOrderId"] = request.client_order_id
        else:
            return CancelOrderResponse(
                success=False,
                error_message="No order ID provided",
            )
        
        try:
            data = await self._request("DELETE", "/fapi/v1/order", params=params, signed=True)
            
            return CancelOrderResponse(
                success=True,
                exchange_order_id=str(data["orderId"]),
                status=data["status"],
                raw_response=data,
            )
            
        except ExchangeError as e:
            return CancelOrderResponse(
                success=False,
                error_code=e.code,
                error_message=str(e),
            )
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """Cancel all open orders."""
        if symbol:
            data = await self._request(
                "DELETE",
                "/fapi/v1/allOpenOrders",
                params={"symbol": symbol},
                signed=True,
            )
            return data.get("code", 0) == 200
        else:
            # Need to get all symbols with open orders first
            open_orders = await self.get_open_orders()
            symbols = set(o.symbol for o in open_orders)
            
            count = 0
            for sym in symbols:
                await self._request(
                    "DELETE",
                    "/fapi/v1/allOpenOrders",
                    params={"symbol": sym},
                    signed=True,
                )
                count += 1
            
            return count
    
    async def get_open_orders(
        self,
        symbol: Optional[str] = None,
    ) -> List[QueryOrderResponse]:
        """Get all open orders."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        data = await self._request("GET", "/fapi/v1/openOrders", params=params, signed=True)
        
        results = []
        for order in data:
            results.append(QueryOrderResponse(
                found=True,
                exchange_order_id=str(order["orderId"]),
                client_order_id=order.get("clientOrderId"),
                symbol=order["symbol"],
                side=OrderSide(order["side"]),
                order_type=OrderType(order["type"]),
                status=order["status"],
                quantity=Decimal(order["origQty"]),
                filled_quantity=Decimal(order["executedQty"]),
                remaining_quantity=Decimal(order["origQty"]) - Decimal(order["executedQty"]),
                price=Decimal(order["price"]) if order.get("price") else None,
                average_price=Decimal(order["avgPrice"]) if order.get("avgPrice") else None,
                created_at=datetime.fromtimestamp(order["time"] / 1000),
                updated_at=datetime.fromtimestamp(order["updateTime"] / 1000),
            ))
        
        return results
    
    # --------------------------------------------------------
    # SYMBOL RULES
    # --------------------------------------------------------
    
    async def get_symbol_rules(self, symbol: str) -> SymbolRules:
        """Get trading rules for symbol."""
        if not self._rules_loaded:
            await self._load_exchange_info()
        
        if symbol not in self._symbol_rules:
            raise ExchangeError(f"Symbol not found: {symbol}", code="VAL_INVALID_SYMBOL")
        
        return self._symbol_rules[symbol]
    
    async def get_all_symbol_rules(self) -> Dict[str, SymbolRules]:
        """Get all symbol rules."""
        if not self._rules_loaded:
            await self._load_exchange_info()
        return dict(self._symbol_rules)
    
    async def _load_exchange_info(self) -> None:
        """Load exchange info and symbol rules."""
        data = await self._request("GET", "/fapi/v1/exchangeInfo", signed=False)
        
        for sym in data.get("symbols", []):
            rules = SymbolRules(
                symbol=sym["symbol"],
                status=sym["status"],
                base_asset=sym["baseAsset"],
                quote_asset=sym["quoteAsset"],
            )
            
            for filt in sym.get("filters", []):
                if filt["filterType"] == "PRICE_FILTER":
                    rules.min_price = Decimal(filt["minPrice"])
                    rules.max_price = Decimal(filt["maxPrice"])
                    rules.price_step = Decimal(filt["tickSize"])
                elif filt["filterType"] == "LOT_SIZE":
                    rules.min_quantity = Decimal(filt["minQty"])
                    rules.max_quantity = Decimal(filt["maxQty"])
                    rules.quantity_step = Decimal(filt["stepSize"])
                elif filt["filterType"] == "MIN_NOTIONAL":
                    rules.min_notional = Decimal(filt.get("notional", filt.get("minNotional", "0")))
            
            # Calculate precision
            if rules.quantity_step > 0:
                rules.quantity_precision = abs(rules.quantity_step.as_tuple().exponent)
            if rules.price_step > 0:
                rules.price_precision = abs(rules.price_step.as_tuple().exponent)
            
            self._symbol_rules[sym["symbol"]] = rules
        
        self._rules_loaded = True
        logger.info(f"Loaded {len(self._symbol_rules)} symbol rules")
    
    # --------------------------------------------------------
    # MARKET DATA
    # --------------------------------------------------------
    
    async def get_current_price(self, symbol: str) -> Decimal:
        """Get current price for symbol."""
        data = await self._request(
            "GET",
            "/fapi/v1/ticker/price",
            params={"symbol": symbol},
            signed=False,
        )
        return Decimal(data["price"])
    
    # --------------------------------------------------------
    # RATE LIMITING
    # --------------------------------------------------------
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        return {
            "orders_used": self._order_count_minute,
            "orders_limit": self._rate_limit_config.orders_per_minute,
            "weight_used": self._weight_used,
            "weight_limit": self._rate_limit_config.weight_per_minute,
            "reset_at": datetime.fromtimestamp(self._rate_limit_reset),
        }
    
    async def wait_for_rate_limit(self) -> None:
        """Wait if approaching rate limit."""
        now = time.time()
        
        # Reset counters if window expired
        if now >= self._rate_limit_reset:
            self._order_count_minute = 0
            self._weight_used = 0
            self._rate_limit_reset = now + 60
        
        # Check if we need to wait
        if self._order_count_minute >= self._rate_limit_config.orders_per_minute:
            wait_time = self._rate_limit_reset - now
            if wait_time > 0:
                logger.warning(f"Rate limit reached, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
        
        if self._weight_used >= self._rate_limit_config.weight_per_minute:
            wait_time = self._rate_limit_reset - now
            if wait_time > 0:
                logger.warning(f"Weight limit reached, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
    
    # --------------------------------------------------------
    # INTERNAL
    # --------------------------------------------------------
    
    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Any:
        """Make API request."""
        if not self._session:
            raise ExchangeError("Not connected")
        
        await self.wait_for_rate_limit()
        
        url = f"{self._rest_url}{path}"
        headers = {"X-MBX-APIKEY": self._api_key}
        
        params = params or {}
        
        if signed:
            params["timestamp"] = str(int(time.time() * 1000))
            query_string = urlencode(params)
            signature = hmac.new(
                self._api_secret.encode(),
                query_string.encode(),
                hashlib.sha256,
            ).hexdigest()
            params["signature"] = signature
        
        try:
            async with self._session.request(
                method,
                url,
                params=params if method == "GET" else None,
                data=params if method != "GET" else None,
                headers=headers,
            ) as response:
                # Update rate limit counters from headers
                self._update_rate_limits(response.headers)
                
                data = await response.json()
                
                if response.status != 200:
                    code = data.get("code", -1)
                    msg = data.get("msg", "Unknown error")
                    internal_code = map_binance_error(code)
                    error_info = get_error_info(internal_code)
                    
                    raise ExchangeError(
                        msg,
                        code=internal_code,
                        is_retryable=error_info.is_retryable,
                    )
                
                return data
                
        except aiohttp.ClientError as e:
            raise ExchangeError(
                f"Network error: {e}",
                code="NET_CONNECTION_FAILED",
                is_retryable=True,
            )
        except asyncio.TimeoutError:
            raise ExchangeError(
                "Request timeout",
                code="TMO_READ",
                is_retryable=True,
            )
    
    def _update_rate_limits(self, headers: Dict[str, str]) -> None:
        """Update rate limit counters from response headers."""
        if "X-MBX-USED-WEIGHT-1M" in headers:
            self._weight_used = int(headers["X-MBX-USED-WEIGHT-1M"])
        
        if "X-MBX-ORDER-COUNT-1M" in headers:
            self._order_count_minute = int(headers["X-MBX-ORDER-COUNT-1M"])
