"""
Binance Market Data Source - Public API adapter.

Implements market data fetching from Binance Futures public API.
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


class BinanceMarketSource(BaseMarketDataSource):
    """
    Binance Futures public API data source.
    
    Endpoints used:
    - /fapi/v1/klines - Kline/candlestick data
    - /fapi/v1/ticker/24hr - 24h ticker
    - /fapi/v1/fundingRate - Funding rate history
    - /fapi/v1/openInterest - Open interest
    - /fapi/v1/ping - Health check
    
    Rate limits:
    - 1200 requests/minute for /fapi endpoints
    - IP-based rate limiting
    """
    
    BASE_URL = "https://fapi.binance.com"
    SPOT_BASE_URL = "https://api.binance.com"
    
    # Interval mapping: our enum -> Binance format
    INTERVAL_MAP = {
        Interval.M1: "1m",
        Interval.M3: "3m",
        Interval.M5: "5m",
        Interval.M15: "15m",
        Interval.M30: "30m",
        Interval.H1: "1h",
        Interval.H2: "2h",
        Interval.H4: "4h",
        Interval.H6: "6h",
        Interval.H8: "8h",
        Interval.H12: "12h",
        Interval.D1: "1d",
        Interval.D3: "3d",
        Interval.W1: "1w",
        Interval.MO1: "1M",
    }
    
    def __init__(
        self,
        use_futures: bool = True,
        timeout: float = 30.0,
        max_retries: int = 3,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        super().__init__(timeout, max_retries, session)
        self._use_futures = use_futures
        self._base_url = self.BASE_URL if use_futures else self.SPOT_BASE_URL
    
    @property
    def name(self) -> str:
        """Unique identifier."""
        return "binance_futures" if self._use_futures else "binance_spot"
    
    def metadata(self) -> SourceMetadata:
        """Return provider metadata."""
        return SourceMetadata(
            name=self.name,
            display_name="Binance Futures" if self._use_futures else "Binance Spot",
            version="1.0.0",
            supported_symbols=[],  # All symbols supported
            supported_intervals=list(self.INTERVAL_MAP.keys()),
            supported_data_types=[
                DataType.KLINE,
                DataType.TICKER,
                DataType.FUNDING_RATE,
                DataType.OPEN_INTEREST,
            ],
            rate_limit_per_minute=1200,
            rate_limit_per_second=20,
            requires_auth=False,
            base_url=self._base_url,
            documentation_url="https://binance-docs.github.io/apidocs/futures/en/",
            priority=1,  # High priority (primary source)
            tags=["futures", "crypto", "binance"],
        )
    
    async def fetch_raw(
        self,
        request: FetchRequest,
    ) -> list[dict[str, Any]]:
        """Fetch raw data from Binance API."""
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
    
    async def _fetch_klines(
        self,
        request: FetchRequest,
    ) -> list[dict[str, Any]]:
        """Fetch kline/candlestick data."""
        endpoint = "/fapi/v1/klines" if self._use_futures else "/api/v3/klines"
        url = f"{self._base_url}{endpoint}"
        
        params: dict[str, Any] = {
            "symbol": request.symbol.upper(),
            "interval": self.INTERVAL_MAP[request.interval],
            "limit": min(request.limit, 1500),
        }
        
        if request.start_time:
            params["startTime"] = int(request.start_time.timestamp() * 1000)
        if request.end_time:
            params["endTime"] = int(request.end_time.timestamp() * 1000)
        
        data = await self._make_request("GET", url, params=params)
        
        # Binance returns array of arrays, convert to dicts
        result = []
        for kline in data:
            result.append({
                "open_time": kline[0],
                "open": kline[1],
                "high": kline[2],
                "low": kline[3],
                "close": kline[4],
                "volume": kline[5],
                "close_time": kline[6],
                "quote_volume": kline[7],
                "trades_count": kline[8],
                "taker_buy_volume": kline[9],
                "taker_buy_quote_volume": kline[10],
            })
        
        return result
    
    async def _fetch_ticker(
        self,
        request: FetchRequest,
    ) -> list[dict[str, Any]]:
        """Fetch 24hr ticker."""
        endpoint = "/fapi/v1/ticker/24hr" if self._use_futures else "/api/v3/ticker/24hr"
        url = f"{self._base_url}{endpoint}"
        
        params = {"symbol": request.symbol.upper()}
        data = await self._make_request("GET", url, params=params)
        
        return [data] if isinstance(data, dict) else data
    
    async def _fetch_funding_rate(
        self,
        request: FetchRequest,
    ) -> list[dict[str, Any]]:
        """Fetch funding rate history."""
        if not self._use_futures:
            raise FetchError(
                message="Funding rate only available for futures",
                source_name=self.name,
            )
        
        url = f"{self._base_url}/fapi/v1/fundingRate"
        
        params: dict[str, Any] = {
            "symbol": request.symbol.upper(),
            "limit": min(request.limit, 1000),
        }
        
        if request.start_time:
            params["startTime"] = int(request.start_time.timestamp() * 1000)
        if request.end_time:
            params["endTime"] = int(request.end_time.timestamp() * 1000)
        
        return await self._make_request("GET", url, params=params)
    
    async def _fetch_open_interest(
        self,
        request: FetchRequest,
    ) -> list[dict[str, Any]]:
        """Fetch open interest."""
        if not self._use_futures:
            raise FetchError(
                message="Open interest only available for futures",
                source_name=self.name,
            )
        
        url = f"{self._base_url}/fapi/v1/openInterest"
        params = {"symbol": request.symbol.upper()}
        
        data = await self._make_request("GET", url, params=params)
        return [data] if isinstance(data, dict) else data
    
    def normalize(
        self,
        raw_data: list[dict[str, Any]],
        request: FetchRequest,
    ) -> list[NormalizedMarketData]:
        """Normalize Binance data to standard format."""
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
                timestamp=datetime.utcfromtimestamp(kline["open_time"] / 1000),
                open=Decimal(str(kline["open"])),
                high=Decimal(str(kline["high"])),
                low=Decimal(str(kline["low"])),
                close=Decimal(str(kline["close"])),
                volume=Decimal(str(kline["volume"])),
                funding_rate=None,
                open_interest=None,
                source_name=self.name,
                quote_volume=Decimal(str(kline["quote_volume"])),
                trades_count=int(kline["trades_count"]),
                taker_buy_volume=Decimal(str(kline["taker_buy_volume"])),
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
                symbol=ticker.get("symbol", request.symbol.upper()),
                timestamp=datetime.utcfromtimestamp(ticker.get("closeTime", 0) / 1000) if ticker.get("closeTime") else datetime.utcnow(),
                open=Decimal(str(ticker["openPrice"])),
                high=Decimal(str(ticker["highPrice"])),
                low=Decimal(str(ticker["lowPrice"])),
                close=Decimal(str(ticker["lastPrice"])),
                volume=Decimal(str(ticker["volume"])),
                funding_rate=None,
                open_interest=None,
                source_name=self.name,
                quote_volume=Decimal(str(ticker.get("quoteVolume", 0))),
                trades_count=int(ticker.get("count", 0)),
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
                symbol=fr.get("symbol", request.symbol.upper()),
                timestamp=datetime.utcfromtimestamp(fr["fundingTime"] / 1000),
                open=Decimal("0"),
                high=Decimal("0"),
                low=Decimal("0"),
                close=Decimal("0"),
                volume=Decimal("0"),
                funding_rate=Decimal(str(fr["fundingRate"])),
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
                symbol=oi.get("symbol", request.symbol.upper()),
                timestamp=datetime.utcfromtimestamp(oi.get("time", 0) / 1000) if oi.get("time") else datetime.utcnow(),
                open=Decimal("0"),
                high=Decimal("0"),
                low=Decimal("0"),
                close=Decimal("0"),
                volume=Decimal("0"),
                funding_rate=None,
                open_interest=Decimal(str(oi["openInterest"])),
                source_name=self.name,
            ))
        return result
    
    async def health_check(self) -> SourceHealth:
        """Check Binance API health."""
        import time
        
        endpoint = "/fapi/v1/ping" if self._use_futures else "/api/v3/ping"
        url = f"{self._base_url}{endpoint}"
        
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
    
    async def get_exchange_info(self) -> dict[str, Any]:
        """Get exchange information including all symbols."""
        endpoint = "/fapi/v1/exchangeInfo" if self._use_futures else "/api/v3/exchangeInfo"
        url = f"{self._base_url}{endpoint}"
        return await self._make_request("GET", url)
    
    async def get_available_symbols(self) -> list[str]:
        """Get list of available trading symbols."""
        info = await self.get_exchange_info()
        return [s["symbol"] for s in info.get("symbols", [])]
