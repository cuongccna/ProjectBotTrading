"""
OKX Exchange Adapter.

============================================================
PURPOSE
============================================================
Production adapter for OKX Futures/Perpetual API.

EXCHANGE SPECIFICS:
- Uses V5 REST API
- HMAC-SHA256 signing with passphrase
- Different symbol format (e.g., BTC-USDT-SWAP)
- Instrument types: SWAP (perpetual), FUTURES
- Position modes: Long/short mode, Net mode

============================================================
API DOCUMENTATION
============================================================
https://www.okx.com/docs-v5/

============================================================
"""

import os
import hmac
import base64
import hashlib
import time
import logging
import asyncio
from datetime import datetime, timezone
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
    map_okx_error,
    create_network_error,
    create_timeout_error,
)
from .metrics import AdapterMetrics, get_global_aggregator
from .logging_utils import AdapterLogger


logger = logging.getLogger(__name__)


# ============================================================
# CONSTANTS
# ============================================================

OKX_REST_URL = "https://www.okx.com"
OKX_TESTNET_URL = "https://www.okx.com"  # OKX uses simulated trading flag
OKX_AWS_URL = "https://aws.okx.com"  # AWS endpoint (lower latency in some regions)

# Order sides
OKX_SIDE_BUY = "buy"
OKX_SIDE_SELL = "sell"

# Position sides (for futures)
OKX_POS_LONG = "long"
OKX_POS_SHORT = "short"
OKX_POS_NET = "net"

# Order types
OKX_ORDER_MARKET = "market"
OKX_ORDER_LIMIT = "limit"
OKX_ORDER_POST_ONLY = "post_only"
OKX_ORDER_FOK = "fok"
OKX_ORDER_IOC = "ioc"

# Instrument types
OKX_INST_SWAP = "SWAP"
OKX_INST_FUTURES = "FUTURES"
OKX_INST_SPOT = "SPOT"
OKX_INST_MARGIN = "MARGIN"

# Trade modes
OKX_TRADE_CROSS = "cross"
OKX_TRADE_ISOLATED = "isolated"
OKX_TRADE_CASH = "cash"

# Order status mapping
OKX_STATUS_MAP = {
    "live": "NEW",
    "partially_filled": "PARTIALLY_FILLED",
    "filled": "FILLED",
    "canceled": "CANCELED",
    "mmp_canceled": "CANCELED",
}


# ============================================================
# OKX ADAPTER
# ============================================================

class OKXAdapter(ExchangeAdapter):
    """
    OKX Futures/Perpetual adapter.
    
    Implements ExchangeAdapter interface for OKX V5 API.
    
    Features:
    - SWAP (perpetual) and FUTURES support
    - Cross/isolated margin modes
    - Long/short and net position modes
    """
    
    def __init__(
        self,
        api_key: str = None,
        api_secret: str = None,
        passphrase: str = None,
        simulated: bool = False,
        use_aws: bool = False,
        inst_type: str = OKX_INST_SWAP,
        trade_mode: str = OKX_TRADE_CROSS,
        timeout_seconds: float = 30.0,
    ):
        """
        Initialize OKX adapter.
        
        Args:
            api_key: OKX API key (or from OKX_API_KEY env)
            api_secret: OKX API secret (or from OKX_API_SECRET env)
            passphrase: OKX passphrase (or from OKX_PASSPHRASE env)
            simulated: Use simulated trading (demo mode)
            use_aws: Use AWS endpoint
            inst_type: Instrument type (SWAP, FUTURES)
            trade_mode: Trade mode (cross, isolated)
            timeout_seconds: Request timeout
        """
        self._api_key = api_key or os.environ.get("OKX_API_KEY", "")
        self._api_secret = api_secret or os.environ.get("OKX_API_SECRET", "")
        self._passphrase = passphrase or os.environ.get("OKX_PASSPHRASE", "")
        
        self._simulated = simulated
        self._inst_type = inst_type
        self._trade_mode = trade_mode
        self._timeout = timeout_seconds
        
        # Select base URL
        self._base_url = OKX_AWS_URL if use_aws else OKX_REST_URL
        
        # Session
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected = False
        
        # Symbol rules cache
        self._symbol_rules: Dict[str, SymbolRules] = {}
        self._rules_loaded = False
        
        # Rate limit tracking
        self._rate_limit_used = 0
        self._rate_limit_max = 60  # Default per endpoint limit
        self._last_request_time = 0.0
        
        # Metrics and logging
        self._metrics = AdapterMetrics("okx")
        self._logger = AdapterLogger("okx")
        get_global_aggregator().register("okx", self._metrics)
    
    # --------------------------------------------------------
    # PROPERTIES
    # --------------------------------------------------------
    
    @property
    def exchange_id(self) -> str:
        """Exchange identifier."""
        return "okx"
    
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
        
        # Validate credentials by fetching account config
        try:
            await self._request("GET", "/api/v5/account/config")
            self._connected = True
            self._logger.info("Connected to OKX")
            
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
        self._logger.info("Disconnected from OKX")
    
    # --------------------------------------------------------
    # SIGNING
    # --------------------------------------------------------
    
    def _sign_request(
        self,
        timestamp: str,
        method: str,
        path: str,
        body: str = "",
    ) -> str:
        """
        Create request signature.
        
        OKX signature: BASE64(HMAC-SHA256(timestamp + method + path + body))
        
        Args:
            timestamp: ISO timestamp
            method: HTTP method
            path: Request path with query string
            body: Request body (JSON string)
            
        Returns:
            Base64 encoded signature
        """
        message = f"{timestamp}{method.upper()}{path}{body}"
        signature = hmac.new(
            self._api_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(signature).decode()
    
    def _get_timestamp(self) -> str:
        """Get ISO timestamp for signing."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    
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
        Make signed request to OKX API.
        
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
                create_network_error("okx", "Not connected")
            )
        
        # Build URL and path
        url = f"{self._base_url}{endpoint}"
        path = endpoint
        
        if params:
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query_string}"
            path = f"{path}?{query_string}"
        
        # Prepare body
        body_str = ""
        if body:
            import json
            body_str = json.dumps(body)
        
        # Create signature
        timestamp = self._get_timestamp()
        signature = self._sign_request(timestamp, method, path, body_str)
        
        # Headers
        headers = {
            "Content-Type": "application/json",
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self._passphrase,
        }
        
        # Simulated trading flag
        if self._simulated:
            headers["x-simulated-trading"] = "1"
        
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
                async with self._session.get(url, headers=headers) as resp:
                    return await self._handle_response(
                        resp, request_id, endpoint, start_time
                    )
            elif method == "POST":
                async with self._session.post(
                    url, headers=headers, data=body_str
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
                create_network_error("okx", str(e), endpoint)
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
                create_timeout_error("okx", int(self._timeout * 1000), endpoint)
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
        
        try:
            data = await response.json()
        except Exception:
            data = {"error": await response.text()}
        
        # OKX returns code "0" for success
        code = data.get("code", "0")
        msg = data.get("msg", "")
        
        if code != "0":
            error = map_okx_error(code, msg, response.status)
            
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
                error_message=msg,
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
        
        return data.get("data", [])
    
    # --------------------------------------------------------
    # ACCOUNT OPERATIONS
    # --------------------------------------------------------
    
    async def get_account_state(self) -> AccountState:
        """Get account state."""
        data = await self._request("GET", "/api/v5/account/balance")
        
        if not data:
            return AccountState(equity=Decimal("0"), available_margin=Decimal("0"))
        
        details = data[0].get("details", [])
        
        # Find USDT balance
        usdt_balance = next(
            (d for d in details if d.get("ccy") == "USDT"),
            {},
        )
        
        return AccountState(
            equity=Decimal(data[0].get("totalEq", "0")),
            available_margin=Decimal(usdt_balance.get("availBal", "0")),
            used_margin=Decimal(data[0].get("imr", "0")),
            unrealized_pnl=Decimal(data[0].get("upl", "0")),
        )
    
    async def get_balance(self, asset: str = "USDT") -> BalanceInfo:
        """Get asset balance."""
        data = await self._request("GET", "/api/v5/account/balance")
        
        if not data:
            return BalanceInfo(
                asset=asset,
                total=Decimal("0"),
                available=Decimal("0"),
                locked=Decimal("0"),
            )
        
        details = data[0].get("details", [])
        asset_balance = next(
            (d for d in details if d.get("ccy") == asset),
            {},
        )
        
        total = Decimal(asset_balance.get("eq", "0"))
        available = Decimal(asset_balance.get("availBal", "0"))
        
        return BalanceInfo(
            asset=asset,
            total=total,
            available=available,
            locked=total - available,
        )
    
    async def get_position(self, symbol: str) -> Optional[PositionInfo]:
        """Get position for symbol."""
        inst_id = self._to_okx_symbol(symbol)
        
        data = await self._request(
            "GET",
            "/api/v5/account/positions",
            params={"instId": inst_id, "instType": self._inst_type},
        )
        
        if not data:
            return None
        
        pos = data[0]
        
        pos_amt = Decimal(pos.get("pos", "0"))
        pos_side = pos.get("posSide", "net")
        
        # Determine position side
        if pos_side == "long":
            side = "LONG"
        elif pos_side == "short":
            side = "SHORT"
        else:
            side = "LONG" if pos_amt > 0 else "SHORT" if pos_amt < 0 else "NONE"
        
        return PositionInfo(
            symbol=symbol,
            side=side,
            quantity=abs(pos_amt),
            entry_price=Decimal(pos.get("avgPx", "0")),
            unrealized_pnl=Decimal(pos.get("upl", "0")),
            leverage=int(float(pos.get("lever", "1"))),
            margin=Decimal(pos.get("margin", "0")),
            liquidation_price=Decimal(pos.get("liqPx", "0")) if pos.get("liqPx") else None,
        )
    
    async def get_all_positions(self) -> List[PositionInfo]:
        """Get all positions."""
        data = await self._request(
            "GET",
            "/api/v5/account/positions",
            params={"instType": self._inst_type},
        )
        
        positions = []
        for pos in data:
            pos_amt = Decimal(pos.get("pos", "0"))
            if pos_amt == 0:
                continue
            
            pos_side = pos.get("posSide", "net")
            if pos_side == "long":
                side = "LONG"
            elif pos_side == "short":
                side = "SHORT"
            else:
                side = "LONG" if pos_amt > 0 else "SHORT"
            
            positions.append(PositionInfo(
                symbol=self._from_okx_symbol(pos.get("instId", "")),
                side=side,
                quantity=abs(pos_amt),
                entry_price=Decimal(pos.get("avgPx", "0")),
                unrealized_pnl=Decimal(pos.get("upl", "0")),
                leverage=int(float(pos.get("lever", "1"))),
                margin=Decimal(pos.get("margin", "0")),
            ))
        
        return positions
    
    # --------------------------------------------------------
    # ORDER OPERATIONS
    # --------------------------------------------------------
    
    async def submit_order(self, request: SubmitOrderRequest) -> SubmitOrderResponse:
        """Submit order."""
        start_time = time.time()
        
        inst_id = self._to_okx_symbol(request.symbol)
        
        # Build order params
        order_body = {
            "instId": inst_id,
            "tdMode": self._trade_mode,
            "side": request.side.lower(),
            "ordType": self._map_order_type(request.order_type, request.time_in_force),
            "sz": str(request.quantity),
        }
        
        # Client order ID
        if request.client_order_id:
            order_body["clOrdId"] = request.client_order_id
        
        # Price for limit orders
        if request.price and request.order_type != "MARKET":
            order_body["px"] = str(request.price)
        
        # Reduce only
        if request.reduce_only:
            order_body["reduceOnly"] = True
        
        try:
            data = await self._request("POST", "/api/v5/trade/order", body=order_body)
            
            if not data:
                raise ExchangeException(
                    map_okx_error("51000", "Empty response", 200)
                )
            
            result = data[0]
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Check for order-level error
            order_code = result.get("sCode", "0")
            if order_code != "0":
                self._metrics.record_order_rejected(f"OKX_{order_code}")
                
                self._logger.log_order(
                    operation="submit",
                    client_order_id=request.client_order_id or "",
                    symbol=request.symbol,
                    side=request.side,
                    order_type=request.order_type,
                    quantity=str(request.quantity),
                    price=str(request.price) if request.price else None,
                    error_code=f"OKX_{order_code}",
                    error_message=result.get("sMsg", ""),
                    latency_ms=latency_ms,
                )
                
                return SubmitOrderResponse(
                    success=False,
                    exchange_order_id=None,
                    client_order_id=request.client_order_id,
                    status="REJECTED",
                    error_code=f"OKX_{order_code}",
                    error_message=result.get("sMsg", "Unknown error"),
                    exchange_timestamp=int(time.time() * 1000),
                )
            
            # Success
            self._metrics.record_order_submitted()
            
            self._logger.log_order(
                operation="submit",
                client_order_id=request.client_order_id or "",
                exchange_order_id=result.get("ordId", ""),
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
                exchange_order_id=result.get("ordId", ""),
                client_order_id=result.get("clOrdId", request.client_order_id),
                status="NEW",
                exchange_timestamp=int(time.time() * 1000),
            )
            
        except ExchangeException:
            raise
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
        inst_id = self._to_okx_symbol(request.symbol)
        
        params = {"instId": inst_id}
        
        if request.exchange_order_id:
            params["ordId"] = request.exchange_order_id
        elif request.client_order_id:
            params["clOrdId"] = request.client_order_id
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
            data = await self._request("GET", "/api/v5/trade/order", params=params)
            
            if not data:
                return QueryOrderResponse(
                    success=False,
                    exchange_order_id=request.exchange_order_id,
                    client_order_id=request.client_order_id,
                    status="UNKNOWN",
                    error_code="ORDER_NOT_FOUND",
                    error_message="Order not found",
                )
            
            order = data[0]
            
            okx_status = order.get("state", "")
            status = OKX_STATUS_MAP.get(okx_status, okx_status.upper())
            
            return QueryOrderResponse(
                success=True,
                exchange_order_id=order.get("ordId", ""),
                client_order_id=order.get("clOrdId", ""),
                status=status,
                filled_quantity=Decimal(order.get("accFillSz", "0")),
                remaining_quantity=Decimal(order.get("sz", "0")) - Decimal(order.get("accFillSz", "0")),
                average_price=Decimal(order.get("avgPx", "0")) if order.get("avgPx") else None,
                exchange_timestamp=int(order.get("uTime", 0)),
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
        inst_id = self._to_okx_symbol(request.symbol)
        
        cancel_body = {"instId": inst_id}
        
        if request.exchange_order_id:
            cancel_body["ordId"] = request.exchange_order_id
        elif request.client_order_id:
            cancel_body["clOrdId"] = request.client_order_id
        else:
            return CancelOrderResponse(
                success=False,
                exchange_order_id=request.exchange_order_id,
                client_order_id=request.client_order_id,
                error_code="MISSING_ID",
                error_message="Either exchange_order_id or client_order_id required",
            )
        
        try:
            data = await self._request("POST", "/api/v5/trade/cancel-order", body=cancel_body)
            
            if not data:
                return CancelOrderResponse(
                    success=False,
                    exchange_order_id=request.exchange_order_id,
                    client_order_id=request.client_order_id,
                    error_code="EMPTY_RESPONSE",
                    error_message="Empty response from exchange",
                )
            
            result = data[0]
            
            cancel_code = result.get("sCode", "0")
            if cancel_code != "0":
                return CancelOrderResponse(
                    success=False,
                    exchange_order_id=result.get("ordId", request.exchange_order_id),
                    client_order_id=result.get("clOrdId", request.client_order_id),
                    error_code=f"OKX_{cancel_code}",
                    error_message=result.get("sMsg", ""),
                )
            
            self._metrics.record_order_canceled()
            
            return CancelOrderResponse(
                success=True,
                exchange_order_id=result.get("ordId", ""),
                client_order_id=result.get("clOrdId", ""),
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
        # Get open orders first
        open_orders = await self.get_open_orders(symbol)
        
        if not open_orders:
            return 0
        
        # Build batch cancel request
        cancel_list = []
        for order in open_orders:
            cancel_list.append({
                "instId": self._to_okx_symbol(order.get("symbol", symbol)),
                "ordId": order.get("exchange_order_id"),
            })
        
        try:
            data = await self._request(
                "POST",
                "/api/v5/trade/cancel-batch-orders",
                body=cancel_list,
            )
            
            canceled = sum(1 for r in data if r.get("sCode") == "0")
            return canceled
            
        except Exception as e:
            logger.error(f"Error in cancel_all_orders: {e}")
            return 0
    
    async def get_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Get open orders."""
        params = {"instType": self._inst_type}
        
        if symbol:
            params["instId"] = self._to_okx_symbol(symbol)
        
        data = await self._request("GET", "/api/v5/trade/orders-pending", params=params)
        
        orders = []
        for order in data:
            okx_status = order.get("state", "")
            orders.append({
                "exchange_order_id": order.get("ordId"),
                "client_order_id": order.get("clOrdId"),
                "symbol": self._from_okx_symbol(order.get("instId", "")),
                "side": order.get("side", "").upper(),
                "order_type": order.get("ordType", "").upper(),
                "quantity": Decimal(order.get("sz", "0")),
                "price": Decimal(order.get("px", "0")) if order.get("px") else None,
                "filled_quantity": Decimal(order.get("accFillSz", "0")),
                "status": OKX_STATUS_MAP.get(okx_status, okx_status.upper()),
                "created_time": int(order.get("cTime", 0)),
            })
        
        return orders
    
    # --------------------------------------------------------
    # SYMBOL RULES
    # --------------------------------------------------------
    
    async def _load_instruments(self) -> None:
        """Load instrument info."""
        data = await self._request(
            "GET",
            "/api/v5/public/instruments",
            params={"instType": self._inst_type},
        )
        
        for inst in data:
            inst_id = inst.get("instId", "")
            symbol = self._from_okx_symbol(inst_id)
            
            lot_sz = Decimal(inst.get("lotSz", "1"))
            tick_sz = Decimal(inst.get("tickSz", "0.01"))
            min_sz = Decimal(inst.get("minSz", "1"))
            
            self._symbol_rules[symbol] = SymbolRules(
                symbol=symbol,
                base_asset=inst.get("baseCcy", ""),
                quote_asset=inst.get("quoteCcy", "USDT"),
                price_precision=self._get_precision(tick_sz),
                quantity_precision=self._get_precision(lot_sz),
                min_quantity=min_sz,
                max_quantity=Decimal(inst.get("maxLmtSz", "100000")),
                min_notional=Decimal("1"),  # OKX doesn't expose this directly
                tick_size=tick_sz,
                step_size=lot_sz,
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
        inst_id = self._to_okx_symbol(symbol)
        
        data = await self._request(
            "GET",
            "/api/v5/market/ticker",
            params={"instId": inst_id},
        )
        
        if not data:
            return Decimal("0")
        
        return Decimal(data[0].get("last", "0"))
    
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
    
    # --------------------------------------------------------
    # SYMBOL CONVERSION
    # --------------------------------------------------------
    
    def _to_okx_symbol(self, symbol: str) -> str:
        """
        Convert to OKX symbol format.
        
        BTCUSDT -> BTC-USDT-SWAP
        """
        # Already in OKX format
        if "-" in symbol:
            return symbol
        
        # Common USDT pairs
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            return f"{base}-USDT-SWAP"
        elif symbol.endswith("BUSD"):
            base = symbol[:-4]
            return f"{base}-BUSD-SWAP"
        elif symbol.endswith("USD"):
            base = symbol[:-3]
            return f"{base}-USD-SWAP"
        
        return symbol
    
    def _from_okx_symbol(self, inst_id: str) -> str:
        """
        Convert from OKX symbol format.
        
        BTC-USDT-SWAP -> BTCUSDT
        """
        if "-" not in inst_id:
            return inst_id
        
        parts = inst_id.split("-")
        if len(parts) >= 2:
            return f"{parts[0]}{parts[1]}"
        
        return inst_id
    
    def _map_order_type(self, order_type: str, time_in_force: str = None) -> str:
        """Map order type to OKX format."""
        order_type = order_type.upper()
        tif = (time_in_force or "GTC").upper()
        
        if order_type == "MARKET":
            return OKX_ORDER_MARKET
        elif order_type == "LIMIT":
            if tif == "FOK":
                return OKX_ORDER_FOK
            elif tif == "IOC":
                return OKX_ORDER_IOC
            elif tif == "GTX" or tif == "POST_ONLY":
                return OKX_ORDER_POST_ONLY
            return OKX_ORDER_LIMIT
        
        return OKX_ORDER_LIMIT
