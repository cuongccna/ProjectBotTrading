"""
OKX Market Data Source - Public API adapter.

Implements market data fetching from OKX public API.
No authentication required for public endpoints.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import aiohttp

from data_sources.base import BaseMarketDataSource
from data_sources.exceptions import (
    FetchError,
    HealthCheckError,
    NormalizationError,
)
from data_sources.models import (
    DataType,
    FetchRequest,
    Interval,
    NormalizedMarketData,
    SourceHealth,
    SourceMetadata,
    SourceStatus,
)


logger = logging.getLogger(__name__)


class OKXMarketSource(BaseMarketDataSource):
    """
    OKX public API data source.
    
    Endpoints used:
    - /api/v5/market/candles - Kline/candlestick data
    - /api/v5/market/ticker - Ticker data
    - /api/v5/public/funding-rate - Funding rate
    - /api/v5/public/open-interest - Open interest
    - /api/v5/public/time - Health check
    
    Rate limits:
    - 20 requests/2s for most public endpoints
    - IP-based rate limiting
    """
    
    BASE_URL = "https://www.okx.com"
    
    # Interval mapping: our enum -> OKX format
    # OKX uses different format: 1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 12H, 1D, 1W, 1M
    INTERVAL_MAP = {
        Interval.M1: "1m",
        Interval.M3: "3m",
        Interval.M5: "5m",
        Interval.M15: "15m",
        Interval.M30: "30m",
        Interval.H1: "1H",
        Interval.H2: "2H",
        Interval.H4: "4H",
        Interval.H6: "6H",
        Interval.H12: "12H",
        Interval.D1: "1D",
        Interval.D3: "3D",  # Note: OKX might not support 3D
        Interval.W1: "1W",
        Interval.MO1: "1M",
    }
    
    # OKX instrument types
    INST_TYPE_SWAP = "SWAP"  # Perpetual futures
    INST_TYPE_FUTURES = "FUTURES"  # Delivery futures
    INST_TYPE_SPOT = "SPOT"
    
    def __init__(
        self,
        inst_type: str = INST_TYPE_SWAP,
        timeout: float = 30.0,
        max_retries: int = 3,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        super().__init__(timeout, max_retries, session)
        self._inst_type = inst_type
    
    @property
    def name(self) -> str:
        """Unique identifier."""
        return f"okx_{self._inst_type.lower()}"
    
    def metadata(self) -> SourceMetadata:
        """Return provider metadata."""
        return SourceMetadata(
            name=self.name,
            display_name=f"OKX {self._inst_type.title()}",
            version="1.0.0",
            supported_symbols=[],  # All symbols supported
            supported_intervals=list(self.INTERVAL_MAP.keys()),
            supported_data_types=[
                DataType.KLINE,
                DataType.TICKER,
                DataType.FUNDING_RATE,
                DataType.OPEN_INTEREST,
            ],
            rate_limit_per_minute=600,
            rate_limit_per_second=10,
            requires_auth=False,
            base_url=self.BASE_URL,
            documentation_url="https://www.okx.com/docs-v5/en/",
            priority=2,  # Secondary source (fallback)
            tags=["futures", "crypto", "okx"],
        )
    
    def _convert_symbol(self, symbol: str) -> str:
        """
        Convert symbol to OKX format.
        
        Binance: BTCUSDT
        OKX SWAP: BTC-USDT-SWAP
        OKX SPOT: BTC-USDT
        """
        # If already in OKX format, return as-is
        if "-" in symbol:
            return symbol
        
        # Try to split common patterns
        symbol = symbol.upper()
        
        # Common quote currencies
        for quote in ["USDT", "USDC", "USD", "BTC", "ETH"]:
            if symbol.endswith(quote):
                base = symbol[:-len(quote)]
                if self._inst_type == self.INST_TYPE_SWAP:
                    return f"{base}-{quote}-SWAP"
                elif self._inst_type == self.INST_TYPE_SPOT:
                    return f"{base}-{quote}"
                else:
                    return f"{base}-{quote}-{self._inst_type}"
        
        # Default: assume USDT quote
        if self._inst_type == self.INST_TYPE_SWAP:
            return f"{symbol}-USDT-SWAP"
        return f"{symbol}-USDT"
    
    async def fetch_raw(
        self,
        request: FetchRequest,
    ) -> list[dict[str, Any]]:
        """Fetch raw data from OKX API."""
        if request.data_type == DataType.KLINE:
            return await self._fetch_klines(request)
        elif request.data_type == DataType.TICKER:
            return await self._fetch_ticker(request)
        elif request.data_type == DataType.FUNDING_RATE:
            return await self._fetch_funding_rate(request)
        elif request.data_type == DataType.OPEN_INTEREST:
            return await self._fetch_open_interest(request)
        else:
            raise FetchError(
                message=f"Unsupported data type: {request.data_type}",
                source_name=self.name,
            )
    
    async def _make_okx_request(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Make OKX API request with response unwrapping."""
        url = f"{self.BASE_URL}{endpoint}"
        response = await self._make_request("GET", url, params=params)
        
        # OKX wraps responses in {"code": "0", "data": [...], "msg": ""}
        if isinstance(response, dict):
            code = response.get("code", "0")
            if code != "0":
                raise FetchError(
                    message=f"OKX API error: {response.get('msg', 'Unknown error')}",
                    source_name=self.name,
                    response_body=str(response),
                )
            return response.get("data", [])
        
        return response
    
    async def _fetch_klines(
        self,
        request: FetchRequest,
    ) -> list[dict[str, Any]]:
        """Fetch kline/candlestick data."""
        inst_id = self._convert_symbol(request.symbol)
        
        params: dict[str, Any] = {
            "instId": inst_id,
            "bar": self.INTERVAL_MAP[request.interval],
            "limit": str(min(request.limit, 300)),  # OKX max is 300
        }
        
        if request.end_time:
            # OKX uses 'after' for pagination (older data)
            params["after"] = str(int(request.end_time.timestamp() * 1000))
        if request.start_time:
            # OKX uses 'before' for newer data
            params["before"] = str(int(request.start_time.timestamp() * 1000))
        
        data = await self._make_okx_request("/api/v5/market/candles", params)
        
        # OKX returns array of arrays: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        result = []
        for kline in data:
            result.append({
                "timestamp": int(kline[0]),
                "open": kline[1],
                "high": kline[2],
                "low": kline[3],
                "close": kline[4],
                "volume": kline[5],
                "volume_ccy": kline[6],
                "volume_ccy_quote": kline[7],
                "confirm": kline[8],
            })
        
        return result
    
    async def _fetch_ticker(
        self,
        request: FetchRequest,
    ) -> list[dict[str, Any]]:
        """Fetch ticker data."""
        inst_id = self._convert_symbol(request.symbol)
        
        params = {"instId": inst_id}
        return await self._make_okx_request("/api/v5/market/ticker", params)
    
    async def _fetch_funding_rate(
        self,
        request: FetchRequest,
    ) -> list[dict[str, Any]]:
        """Fetch funding rate."""
        if self._inst_type == self.INST_TYPE_SPOT:
            raise FetchError(
                message="Funding rate not available for spot",
                source_name=self.name,
            )
        
        inst_id = self._convert_symbol(request.symbol)
        params = {"instId": inst_id}
        
        return await self._make_okx_request("/api/v5/public/funding-rate", params)
    
    async def _fetch_open_interest(
        self,
        request: FetchRequest,
    ) -> list[dict[str, Any]]:
        """Fetch open interest."""
        if self._inst_type == self.INST_TYPE_SPOT:
            raise FetchError(
                message="Open interest not available for spot",
                source_name=self.name,
            )
        
        inst_id = self._convert_symbol(request.symbol)
        
        # OKX requires instType for open-interest
        params = {
            "instType": self._inst_type,
            "instId": inst_id,
        }
        
        return await self._make_okx_request("/api/v5/public/open-interest", params)
    
    def normalize(
        self,
        raw_data: list[dict[str, Any]],
        request: FetchRequest,
    ) -> list[NormalizedMarketData]:
        """Normalize OKX data to standard format."""
        try:
            if request.data_type == DataType.KLINE:
                return self._normalize_klines(raw_data, request)
            elif request.data_type == DataType.TICKER:
                return self._normalize_ticker(raw_data, request)
            elif request.data_type == DataType.FUNDING_RATE:
                return self._normalize_funding_rate(raw_data, request)
            elif request.data_type == DataType.OPEN_INTEREST:
                return self._normalize_open_interest(raw_data, request)
            else:
                return []
        except Exception as e:
            raise NormalizationError(
                message=f"Failed to normalize data: {e}",
                source_name=self.name,
                raw_data=raw_data[:2] if raw_data else None,
                original_error=e,
            )
    
    def _normalize_klines(
        self,
        raw_data: list[dict[str, Any]],
        request: FetchRequest,
    ) -> list[NormalizedMarketData]:
        """Normalize kline data."""
        result = []
        for kline in raw_data:
            result.append(NormalizedMarketData(
                symbol=request.symbol.upper(),
                timestamp=datetime.utcfromtimestamp(int(kline["timestamp"]) / 1000),
                open=Decimal(str(kline["open"])),
                high=Decimal(str(kline["high"])),
                low=Decimal(str(kline["low"])),
                close=Decimal(str(kline["close"])),
                volume=Decimal(str(kline["volume"])),
                funding_rate=None,
                open_interest=None,
                source_name=self.name,
                quote_volume=Decimal(str(kline.get("volume_ccy_quote", 0))) if kline.get("volume_ccy_quote") else None,
                interval=request.interval.value,
            ))
        return result
    
    def _normalize_ticker(
        self,
        raw_data: list[dict[str, Any]],
        request: FetchRequest,
    ) -> list[NormalizedMarketData]:
        """Normalize ticker data."""
        result = []
        for ticker in raw_data:
            result.append(NormalizedMarketData(
                symbol=request.symbol.upper(),
                timestamp=datetime.utcfromtimestamp(int(ticker.get("ts", 0)) / 1000) if ticker.get("ts") else datetime.utcnow(),
                open=Decimal(str(ticker.get("open24h", 0))),
                high=Decimal(str(ticker.get("high24h", 0))),
                low=Decimal(str(ticker.get("low24h", 0))),
                close=Decimal(str(ticker.get("last", 0))),
                volume=Decimal(str(ticker.get("vol24h", 0))),
                funding_rate=None,
                open_interest=None,
                source_name=self.name,
                quote_volume=Decimal(str(ticker.get("volCcy24h", 0))) if ticker.get("volCcy24h") else None,
            ))
        return result
    
    def _normalize_funding_rate(
        self,
        raw_data: list[dict[str, Any]],
        request: FetchRequest,
    ) -> list[NormalizedMarketData]:
        """Normalize funding rate data."""
        result = []
        for fr in raw_data:
            result.append(NormalizedMarketData(
                symbol=request.symbol.upper(),
                timestamp=datetime.utcfromtimestamp(int(fr.get("fundingTime", 0)) / 1000) if fr.get("fundingTime") else datetime.utcnow(),
                open=Decimal("0"),
                high=Decimal("0"),
                low=Decimal("0"),
                close=Decimal("0"),
                volume=Decimal("0"),
                funding_rate=Decimal(str(fr.get("fundingRate", 0))),
                open_interest=None,
                source_name=self.name,
            ))
        return result
    
    def _normalize_open_interest(
        self,
        raw_data: list[dict[str, Any]],
        request: FetchRequest,
    ) -> list[NormalizedMarketData]:
        """Normalize open interest data."""
        result = []
        for oi in raw_data:
            result.append(NormalizedMarketData(
                symbol=request.symbol.upper(),
                timestamp=datetime.utcfromtimestamp(int(oi.get("ts", 0)) / 1000) if oi.get("ts") else datetime.utcnow(),
                open=Decimal("0"),
                high=Decimal("0"),
                low=Decimal("0"),
                close=Decimal("0"),
                volume=Decimal("0"),
                funding_rate=None,
                open_interest=Decimal(str(oi.get("oi", 0))),
                source_name=self.name,
            ))
        return result
    
    async def health_check(self) -> SourceHealth:
        """Check OKX API health."""
        import time
        
        url = f"{self.BASE_URL}/api/v5/public/time"
        
        start_time = time.time()
        try:
            await self._make_request("GET", url)
            latency_ms = (time.time() - start_time) * 1000
            
            self._health.status = SourceStatus.HEALTHY
            self._health.last_check = datetime.utcnow()
            self._health.latency_ms = latency_ms
            
            logger.debug(f"[{self.name}] Health check OK, latency={latency_ms:.1f}ms")
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            
            self._health.status = SourceStatus.UNAVAILABLE
            self._health.last_check = datetime.utcnow()
            self._health.latency_ms = latency_ms
            self._health.last_error = str(e)
            self._health.last_error_time = datetime.utcnow()
            
            logger.warning(f"[{self.name}] Health check FAILED: {e}")
        
        return self._health
    
    async def get_instruments(self, inst_type: Optional[str] = None) -> list[dict[str, Any]]:
        """Get available instruments."""
        params = {"instType": inst_type or self._inst_type}
        return await self._make_okx_request("/api/v5/public/instruments", params)
    
    async def get_available_symbols(self) -> list[str]:
        """Get list of available trading symbols."""
        instruments = await self.get_instruments()
        return [inst["instId"] for inst in instruments]
