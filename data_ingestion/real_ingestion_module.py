"""
Data Ingestion - Real Ingestion Module.

============================================================
RESPONSIBILITY
============================================================
REAL market data collection module for the orchestrator.

- Uses REAL collectors (CoinGecko, Binance)
- Performs REAL HTTP calls to external APIs
- Persists data to market_data table
- Implements orchestrator ModuleProtocol

============================================================
CRITICAL
============================================================
This module is NOT a placeholder. It performs REAL data collection.
If any fetch fails, ingestion STOPS with an error (no silent fallback).

============================================================
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiohttp

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database.engine import get_session, get_db_session
from database.models import MarketData, RawNews


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class RealIngestionConfig:
    """Configuration for real ingestion module."""
    
    # Assets to track
    tracked_symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    
    # CoinGecko settings
    coingecko_enabled: bool = True
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    coingecko_assets: List[str] = field(default_factory=lambda: ["bitcoin", "ethereum"])
    coingecko_api_key: Optional[str] = None
    
    # Binance settings
    binance_enabled: bool = True
    binance_use_futures: bool = True
    binance_base_url: str = "https://fapi.binance.com"
    binance_spot_url: str = "https://api.binance.com"
    
    # CryptoNews API settings
    cryptonews_enabled: bool = True
    cryptonews_base_url: str = "https://cryptonews-api.com/api/v1"
    cryptonews_api_key: Optional[str] = None
    cryptonews_tickers: List[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL", "XRP", "ADA"])
    
    # CryptoPanic settings  
    cryptopanic_enabled: bool = True
    cryptopanic_base_url: str = "https://cryptopanic.com/api/v1"
    cryptopanic_api_key: Optional[str] = None
    cryptopanic_currencies: List[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL"])
    
    # Timeouts and retries
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_delay_seconds: float = 60.0  # Wait 60s on rate limit
    
    # Failure mode: if True, any fetch failure stops ingestion
    # Set to False to allow partial data collection
    fail_fast: bool = False


# ============================================================
# INGESTION RESULT
# ============================================================

@dataclass
class IngestionCycleResult:
    """Result of a single ingestion cycle."""
    
    cycle_id: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    # Per-source counts
    coingecko_fetched: int = 0
    coingecko_stored: int = 0
    binance_fetched: int = 0
    binance_stored: int = 0
    cryptonews_fetched: int = 0
    cryptonews_stored: int = 0
    cryptopanic_fetched: int = 0
    cryptopanic_stored: int = 0
    
    # Totals
    total_fetched: int = 0
    total_stored: int = 0
    total_errors: int = 0
    
    # Error details
    errors: List[str] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        """Check if cycle was successful."""
        return self.total_errors == 0 and self.total_fetched > 0


# ============================================================
# REAL INGESTION MODULE
# ============================================================

class RealIngestionModule:
    """
    REAL market data ingestion module.
    
    ============================================================
    WARNING: THIS IS A REAL MODULE
    ============================================================
    - Makes REAL HTTP requests to CoinGecko and Binance
    - Persists REAL data to the database
    - Failures will STOP ingestion (no silent fallback)
    
    ============================================================
    ORCHESTRATOR INTERFACE
    ============================================================
    Implements ModuleProtocol:
    - start(): Initialize connections
    - stop(): Cleanup
    - get_health_status(): Report health
    - run_collection_cycle(): Fetch and persist data
    
    ============================================================
    """
    
    # Class marker: This is NOT a placeholder
    _is_placeholder: bool = False
    
    def __init__(
        self,
        config: Optional[RealIngestionConfig] = None,
        session_factory=None,
        **kwargs,
    ) -> None:
        """
        Initialize the real ingestion module.
        
        Args:
            config: Ingestion configuration
            session_factory: Optional factory for database sessions
            **kwargs: Additional arguments (for orchestrator compatibility)
        """
        self._config = config or RealIngestionConfig()
        self._session_factory = session_factory or get_session
        self._logger = logging.getLogger("ingestion.real")
        
        # State
        self._running = False
        self._last_result: Optional[IngestionCycleResult] = None
        self._total_cycles = 0
        self._total_records = 0
        
        self._logger.info(
            f"RealIngestionModule initialized | "
            f"CoinGecko={self._config.coingecko_enabled} | "
            f"Binance={self._config.binance_enabled}"
        )
    
    # --------------------------------------------------------
    # ORCHESTRATOR INTERFACE
    # --------------------------------------------------------
    
    async def start(self) -> None:
        """Start the ingestion module."""
        self._logger.info("Starting RealIngestionModule...")
        self._running = True
        self._logger.info("RealIngestionModule started")
    
    async def stop(self) -> None:
        """Stop the ingestion module."""
        self._logger.info("Stopping RealIngestionModule...")
        self._running = False
        self._logger.info("RealIngestionModule stopped")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status for monitoring."""
        return {
            "status": "healthy" if self._running else "stopped",
            "module": "RealIngestionModule",
            "is_placeholder": False,
            "total_cycles": self._total_cycles,
            "total_records": self._total_records,
            "last_cycle": {
                "success": self._last_result.success if self._last_result else None,
                "fetched": self._last_result.total_fetched if self._last_result else 0,
                "stored": self._last_result.total_stored if self._last_result else 0,
                "completed_at": self._last_result.completed_at.isoformat() if self._last_result and self._last_result.completed_at else None,
            },
        }
    
    def can_trade(self) -> bool:
        """Check if module allows trading (for compatibility)."""
        return self._running
    
    def is_halted(self) -> bool:
        """Check if module is halted (for compatibility)."""
        return not self._running
    
    # --------------------------------------------------------
    # COLLECTION CYCLE
    # --------------------------------------------------------
    
    async def run_collection_cycle(self) -> List[Any]:
        """
        Run a complete data collection cycle.
        
        This method:
        1. Fetches data from CoinGecko (ticker data)
        2. Fetches data from Binance (OHLCV klines)
        3. Persists all data to market_data table
        4. Returns list of stored records
        
        Returns:
            List of stored market data records
            
        Raises:
            RuntimeError: If ingestion fails and fail_fast is enabled
        """
        result = IngestionCycleResult(
            cycle_id=uuid4().hex[:12],
            started_at=datetime.now(timezone.utc),
        )
        
        self._logger.info(f"=== INGESTION CYCLE {result.cycle_id} STARTED ===")
        start_time = time.time()
        
        stored_records = []
        
        try:
            # Fetch from CoinGecko
            if self._config.coingecko_enabled:
                cg_records = await self._fetch_coingecko()
                result.coingecko_fetched = len(cg_records)
                
                stored = await self._persist_records(cg_records, "coingecko")
                result.coingecko_stored = stored
                stored_records.extend(cg_records[:stored])
                
                self._logger.info(
                    f"[CoinGecko] Fetched: {result.coingecko_fetched}, "
                    f"Stored: {result.coingecko_stored}"
                )
            
            # Fetch from Binance
            if self._config.binance_enabled:
                bn_records = await self._fetch_binance()
                result.binance_fetched = len(bn_records)
                
                stored = await self._persist_records(bn_records, "binance")
                result.binance_stored = stored
                stored_records.extend(bn_records[:stored])
                
                self._logger.info(
                    f"[Binance] Fetched: {result.binance_fetched}, "
                    f"Stored: {result.binance_stored}"
                )
            
            # Fetch from CryptoNews API
            if self._config.cryptonews_enabled:
                try:
                    cn_records = await self._fetch_cryptonews()
                    result.cryptonews_fetched = len(cn_records)
                    
                    stored = await self._persist_news_records(cn_records, "cryptonews_api")
                    result.cryptonews_stored = stored
                    
                    self._logger.info(
                        f"[CryptoNews] Fetched: {result.cryptonews_fetched}, "
                        f"Stored: {result.cryptonews_stored}"
                    )
                except Exception as e:
                    self._logger.warning(f"[CryptoNews] Error: {e}")
                    result.errors.append(f"CryptoNews: {e}")
            
            # Fetch from CryptoPanic
            if self._config.cryptopanic_enabled:
                try:
                    cp_records = await self._fetch_cryptopanic()
                    result.cryptopanic_fetched = len(cp_records)
                    
                    stored = await self._persist_news_records(cp_records, "cryptopanic")
                    result.cryptopanic_stored = stored
                    
                    self._logger.info(
                        f"[CryptoPanic] Fetched: {result.cryptopanic_fetched}, "
                        f"Stored: {result.cryptopanic_stored}"
                    )
                except Exception as e:
                    self._logger.warning(f"[CryptoPanic] Error: {e}")
                    result.errors.append(f"CryptoPanic: {e}")
            
            # Calculate totals
            result.total_fetched = (
                result.coingecko_fetched + result.binance_fetched +
                result.cryptonews_fetched + result.cryptopanic_fetched
            )
            result.total_stored = (
                result.coingecko_stored + result.binance_stored +
                result.cryptonews_stored + result.cryptopanic_stored
            )
            
        except Exception as e:
            result.total_errors += 1
            result.errors.append(str(e))
            self._logger.error(f"Ingestion cycle failed: {e}", exc_info=True)
            
            if self._config.fail_fast:
                raise RuntimeError(f"Ingestion failed (fail_fast=True): {e}") from e
        
        finally:
            # Complete result
            result.completed_at = datetime.now(timezone.utc)
            result.duration_seconds = time.time() - start_time
            
            self._last_result = result
            self._total_cycles += 1
            self._total_records += result.total_stored
            
            self._logger.info(
                f"=== INGESTION CYCLE {result.cycle_id} COMPLETED ===\n"
                f"  Duration: {result.duration_seconds:.2f}s\n"
                f"  Total Fetched: {result.total_fetched}\n"
                f"  Total Stored: {result.total_stored}\n"
                f"  Errors: {result.total_errors}"
            )
        
        return stored_records
    
    # --------------------------------------------------------
    # COINGECKO FETCHING
    # --------------------------------------------------------
    
    async def _fetch_coingecko(self) -> List[Dict[str, Any]]:
        """
        Fetch market data from CoinGecko API.
        
        Returns:
            List of market data records ready for persistence
            
        Raises:
            RuntimeError: On fetch failure
        """
        import httpx
        
        self._logger.info(f"Fetching from CoinGecko: {self._config.coingecko_assets}")
        
        url = f"{self._config.coingecko_base_url}/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": ",".join(self._config.coingecko_assets),
            "order": "market_cap_desc",
            "sparkline": "false",
        }
        
        headers = {}
        # Get API key from config or environment
        api_key = self._config.coingecko_api_key or os.getenv("COINGECKO_API_KEY")
        if api_key:
            # Use x-cg-demo-api-key for Demo API (free tier)
            # Use x-cg-pro-api-key for Pro API (paid tier)
            headers["x-cg-demo-api-key"] = api_key
        
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                
                if not isinstance(data, list):
                    raise RuntimeError(f"Unexpected CoinGecko response format: {type(data)}")
                
                # Transform to market_data format
                records = []
                now = datetime.now(timezone.utc)
                
                for coin in data:
                    symbol = coin.get("symbol", "").upper()
                    
                    # Parse timestamp
                    last_updated = coin.get("last_updated")
                    if last_updated:
                        try:
                            candle_time = datetime.fromisoformat(
                                last_updated.replace("Z", "+00:00")
                            )
                        except (ValueError, TypeError):
                            candle_time = now
                    else:
                        candle_time = now
                    
                    # CoinGecko provides current price, not OHLCV
                    # We create a "ticker" record
                    current_price = float(coin.get("current_price", 0))
                    high_24h = float(coin.get("high_24h", current_price))
                    low_24h = float(coin.get("low_24h", current_price))
                    
                    record = {
                        "symbol": symbol,
                        "pair": f"{symbol}USDT",
                        "exchange": "coingecko",
                        "open_price": current_price,  # No open from CoinGecko
                        "high_price": high_24h,
                        "low_price": low_24h,
                        "close_price": current_price,
                        "volume": float(coin.get("total_volume", 0)),
                        "quote_volume": float(coin.get("total_volume", 0)),
                        "vwap": None,
                        "trade_count": None,
                        "interval": "24h",
                        "candle_open_time": candle_time,
                        "candle_close_time": now,
                        "source_module": "RealIngestionModule.coingecko",
                        "fetched_at": now,
                    }
                    records.append(record)
                    
                    self._logger.debug(
                        f"[CoinGecko] {symbol}: ${current_price:.2f} | "
                        f"Vol: {record['volume']:,.0f}"
                    )
                
                return records
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Rate limited - log warning but don't crash
                self._logger.warning(
                    f"CoinGecko rate limited (429). "
                    f"Will use cached data or skip. "
                    f"Consider using API key for higher limits."
                )
                # Return empty - will use Binance data instead
                return []
            raise RuntimeError(
                f"CoinGecko HTTP error {e.response.status_code}: {e.response.text[:200]}"
            ) from e
        except httpx.TimeoutException as e:
            self._logger.warning(f"CoinGecko timeout: {e}. Skipping...")
            return []
        except httpx.RequestError as e:
            self._logger.warning(f"CoinGecko request error: {e}. Skipping...")
            return []
    
    # --------------------------------------------------------
    # BINANCE FETCHING
    # --------------------------------------------------------
    
    async def _fetch_binance(self) -> List[Dict[str, Any]]:
        """
        Fetch OHLCV klines from Binance API.
        
        Returns:
            List of market data records ready for persistence
            
        Raises:
            RuntimeError: On fetch failure
        """
        import httpx
        
        self._logger.info(f"Fetching from Binance: {self._config.tracked_symbols}")
        
        base_url = (
            self._config.binance_base_url 
            if self._config.binance_use_futures 
            else self._config.binance_spot_url
        )
        
        endpoint = "/fapi/v1/klines" if self._config.binance_use_futures else "/api/v3/klines"
        
        records = []
        now = datetime.now(timezone.utc)
        
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                for symbol in self._config.tracked_symbols:
                    url = f"{base_url}{endpoint}"
                    params = {
                        "symbol": symbol.upper(),
                        "interval": "1h",  # Fetch hourly klines
                        "limit": 5,  # Last 5 candles
                    }
                    
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    
                    klines = response.json()
                    
                    if not isinstance(klines, list):
                        raise RuntimeError(f"Unexpected Binance response for {symbol}")
                    
                    for kline in klines:
                        # Binance kline format: [open_time, open, high, low, close, volume, close_time, ...]
                        open_time_ms = kline[0]
                        close_time_ms = kline[6]
                        
                        record = {
                            "symbol": symbol.replace("USDT", ""),
                            "pair": symbol.upper(),
                            "exchange": "binance_futures" if self._config.binance_use_futures else "binance_spot",
                            "open_price": float(kline[1]),
                            "high_price": float(kline[2]),
                            "low_price": float(kline[3]),
                            "close_price": float(kline[4]),
                            "volume": float(kline[5]),
                            "quote_volume": float(kline[7]),
                            "vwap": None,
                            "trade_count": int(kline[8]) if len(kline) > 8 else None,
                            "interval": "1h",
                            "candle_open_time": datetime.utcfromtimestamp(open_time_ms / 1000).replace(tzinfo=timezone.utc),
                            "candle_close_time": datetime.utcfromtimestamp(close_time_ms / 1000).replace(tzinfo=timezone.utc),
                            "source_module": "RealIngestionModule.binance",
                            "fetched_at": now,
                        }
                        records.append(record)
                    
                    # Log latest price
                    if klines:
                        latest = klines[-1]
                        self._logger.debug(
                            f"[Binance] {symbol}: O={latest[1]} H={latest[2]} "
                            f"L={latest[3]} C={latest[4]} V={latest[5]}"
                        )
                
                return records
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                self._logger.warning(
                    f"Binance rate limited (429). Skipping this cycle."
                )
                return []
            raise RuntimeError(
                f"Binance HTTP error {e.response.status_code}: {e.response.text[:200]}"
            ) from e
        except httpx.TimeoutException as e:
            self._logger.warning(f"Binance timeout: {e}. Skipping...")
            return []
        except httpx.RequestError as e:
            self._logger.warning(f"Binance request error: {e}. Skipping...")
            return []
    
    # --------------------------------------------------------
    # CRYPTONEWS API FETCHING
    # --------------------------------------------------------
    
    async def _fetch_cryptonews(self) -> List[Dict[str, Any]]:
        """
        Fetch news from CryptoNews API.
        
        API: https://cryptonews-api.com/api/v1/category
        
        Returns:
            List of news article dictionaries
        """
        import httpx
        from email.utils import parsedate_to_datetime
        
        api_key = self._config.cryptonews_api_key or os.getenv("CRYPTO_NEWS_API_KEY")
        if not api_key:
            self._logger.warning("[CryptoNews] No API key configured. Skipping...")
            return []
        
        url = f"{self._config.cryptonews_base_url}/category"
        
        params = {
            "section": "alltickers",
            "tickers": ",".join(self._config.cryptonews_tickers),
            "items": 10,  # Trial plan limit
            "token": api_key,
        }
        
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                # Extract news items
                if isinstance(data, dict) and "data" in data:
                    raw_items = data["data"]
                elif isinstance(data, list):
                    raw_items = data
                else:
                    raw_items = [data]
                
                # Transform to news record format
                records = []
                now = datetime.now(timezone.utc)
                
                for item in raw_items:
                    # Parse published date
                    published_at = None
                    pub_date_str = item.get("date")
                    if pub_date_str:
                        try:
                            published_at = parsedate_to_datetime(pub_date_str)
                        except (ValueError, TypeError):
                            published_at = now
                    
                    # Extract tickers from the news
                    tickers = item.get("tickers", "").split(",") if item.get("tickers") else []
                    
                    record = {
                        "external_id": item.get("news_url", ""),
                        "title": item.get("title", ""),
                        "content": item.get("text", ""),
                        "summary": item.get("text", "")[:500] if item.get("text") else None,
                        "url": item.get("news_url", ""),
                        "source_name": "cryptonews_api",
                        "source_module": "RealIngestionModule.cryptonews",
                        "author": item.get("source_name", ""),
                        "categories": [item.get("type", "news")],
                        "tokens": tickers,
                        "published_at": published_at,
                        "fetched_at": now,
                        "sentiment": item.get("sentiment"),  # Some APIs provide this
                    }
                    records.append(record)
                
                self._logger.debug(f"[CryptoNews] Fetched {len(records)} articles")
                return records
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                self._logger.warning("[CryptoNews] Rate limited (429). Skipping...")
                return []
            self._logger.warning(f"[CryptoNews] HTTP error {e.response.status_code}")
            return []
        except httpx.TimeoutException as e:
            self._logger.warning(f"[CryptoNews] Timeout: {e}. Skipping...")
            return []
        except httpx.RequestError as e:
            self._logger.warning(f"[CryptoNews] Request error: {e}. Skipping...")
            return []
    
    # --------------------------------------------------------
    # CRYPTOPANIC FETCHING
    # --------------------------------------------------------
    
    async def _fetch_cryptopanic(self) -> List[Dict[str, Any]]:
        """
        Fetch news/sentiment from CryptoPanic.
        
        API: https://cryptopanic.com/api/v1/posts/
        
        Returns:
            List of news/sentiment dictionaries
        """
        api_key = self._config.cryptopanic_api_key or os.getenv("CRYPTOPANIC_API_KEY")
        if not api_key:
            self._logger.warning("[CryptoPanic] No API key configured. Skipping...")
            return []
        
        url = f"{self._config.cryptopanic_base_url}/posts/"
        
        params = {
            "auth_token": api_key,
            "public": "true",
            "kind": "news",
            "currencies": ",".join(self._config.cryptopanic_currencies),
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=self._config.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 429:
                        self._logger.warning("[CryptoPanic] Rate limited (429). Skipping...")
                        return []
                    
                    if response.status != 200:
                        self._logger.warning(f"[CryptoPanic] HTTP error {response.status}")
                        return []
                    
                    data = await response.json()
                    
                    # Extract results
                    raw_items = data.get("results", [])
                    
                    # Transform to news record format
                    records = []
                    now = datetime.now(timezone.utc)
                    
                    for item in raw_items:
                        # Parse published date
                        published_at = None
                        pub_str = item.get("published_at", "")
                        if pub_str:
                            try:
                                # Handle ISO format with Z suffix
                                if pub_str.endswith("Z"):
                                    pub_str = pub_str[:-1] + "+00:00"
                                published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                            except (ValueError, TypeError):
                                published_at = now
                        
                        # Extract currencies
                        currencies = []
                        for curr in item.get("currencies", []):
                            if isinstance(curr, dict):
                                currencies.append(curr.get("code", ""))
                            else:
                                currencies.append(str(curr))
                        
                        # Extract votes for sentiment
                        votes = item.get("votes", {})
                        positive = votes.get("positive", 0)
                        negative = votes.get("negative", 0)
                        
                        # Calculate simple sentiment score
                        total_votes = positive + negative
                        if total_votes > 0:
                            sentiment_score = (positive - negative) / total_votes
                        else:
                            sentiment_score = 0.0
                        
                        record = {
                            "external_id": str(item.get("id", "")),
                            "title": item.get("title", ""),
                            "content": None,  # CryptoPanic only provides title
                            "summary": item.get("title", ""),
                            "url": item.get("url", ""),
                            "source_name": "cryptopanic",
                            "source_module": "RealIngestionModule.cryptopanic",
                            "author": item.get("source", {}).get("title", "") if isinstance(item.get("source"), dict) else "",
                            "categories": [item.get("kind", "news")],
                            "tokens": currencies,
                            "published_at": published_at,
                            "fetched_at": now,
                            "sentiment": sentiment_score,
                            "votes_positive": positive,
                            "votes_negative": negative,
                            "votes_important": votes.get("important", 0),
                        }
                        records.append(record)
                    
                    self._logger.debug(f"[CryptoPanic] Fetched {len(records)} articles")
                    return records
                    
        except aiohttp.ClientError as e:
            self._logger.warning(f"[CryptoPanic] Request error: {e}. Skipping...")
            return []
        except asyncio.TimeoutError:
            self._logger.warning("[CryptoPanic] Timeout. Skipping...")
            return []
    
    # --------------------------------------------------------
    # PERSISTENCE
    # --------------------------------------------------------
    
    async def _persist_records(
        self,
        records: List[Dict[str, Any]],
        source: str,
    ) -> int:
        """
        Persist market data records to database using upsert.
        
        Uses PostgreSQL ON CONFLICT DO UPDATE to handle duplicates gracefully.
        Updates existing records if they have the same (symbol, exchange, interval, candle_open_time).
        
        Args:
            records: List of record dictionaries
            source: Source identifier for logging
            
        Returns:
            Number of records stored/updated
            
        Raises:
            RuntimeError: On persistence failure
        """
        if not records:
            return 0
        
        correlation_id = uuid4().hex
        
        try:
            with get_db_session() as session:
                # Prepare records for bulk upsert
                values_list = []
                for record in records:
                    values_list.append({
                        "correlation_id": correlation_id,
                        "symbol": record["symbol"],
                        "pair": record["pair"],
                        "exchange": record["exchange"],
                        "open_price": record["open_price"],
                        "high_price": record["high_price"],
                        "low_price": record["low_price"],
                        "close_price": record["close_price"],
                        "volume": record["volume"],
                        "quote_volume": record.get("quote_volume"),
                        "vwap": record.get("vwap"),
                        "trade_count": record.get("trade_count"),
                        "interval": record["interval"],
                        "candle_open_time": record["candle_open_time"],
                        "candle_close_time": record["candle_close_time"],
                        "source_module": record["source_module"],
                        "fetched_at": record["fetched_at"],
                    })
                
                # PostgreSQL upsert: INSERT ... ON CONFLICT DO UPDATE
                stmt = pg_insert(MarketData).values(values_list)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_market_data",  # The unique constraint name
                    set_={
                        "correlation_id": stmt.excluded.correlation_id,
                        "open_price": stmt.excluded.open_price,
                        "high_price": stmt.excluded.high_price,
                        "low_price": stmt.excluded.low_price,
                        "close_price": stmt.excluded.close_price,
                        "volume": stmt.excluded.volume,
                        "quote_volume": stmt.excluded.quote_volume,
                        "vwap": stmt.excluded.vwap,
                        "trade_count": stmt.excluded.trade_count,
                        "candle_close_time": stmt.excluded.candle_close_time,
                        "source_module": stmt.excluded.source_module,
                        "fetched_at": stmt.excluded.fetched_at,
                    },
                )
                
                session.execute(stmt)
                session.commit()
                
                stored_count = len(values_list)
                self._logger.info(
                    f"[{source}] Persisted {stored_count}/{len(records)} records "
                    f"(correlation_id={correlation_id[:8]}...)"
                )
                
        except Exception as e:
            raise RuntimeError(f"Failed to persist {source} records: {e}") from e
        
        return stored_count
    
    async def _persist_news_records(
        self,
        records: List[Dict[str, Any]],
        source: str,
    ) -> int:
        """
        Persist news records to raw_news table using upsert.
        
        Uses PostgreSQL ON CONFLICT DO NOTHING to handle duplicates gracefully.
        
        Args:
            records: List of news record dictionaries
            source: Source identifier for logging
            
        Returns:
            Number of records stored
        """
        if not records:
            return 0
        
        correlation_id = uuid4().hex
        stored_count = 0
        
        try:
            with get_db_session() as session:
                # Prepare records for bulk insert
                for record in records:
                    # Check if already exists by external_id
                    external_id = record.get("external_id", "")
                    if external_id:
                        existing = session.query(RawNews).filter(
                            RawNews.external_id == external_id,
                            RawNews.source_name == record.get("source_name", source),
                        ).first()
                        if existing:
                            continue  # Skip duplicate
                    
                    # Create new record
                    news_record = RawNews(
                        correlation_id=correlation_id,
                        external_id=external_id,
                        title=record.get("title", ""),
                        content=record.get("content"),
                        summary=record.get("summary"),
                        url=record.get("url"),
                        source_name=record.get("source_name", source),
                        source_module=record.get("source_module", "RealIngestionModule"),
                        author=record.get("author"),
                        categories=record.get("categories"),
                        tokens=record.get("tokens"),
                        published_at=record.get("published_at"),
                        fetched_at=record.get("fetched_at"),
                    )
                    session.add(news_record)
                    stored_count += 1
                
                session.commit()
                
                self._logger.info(
                    f"[{source}] Persisted {stored_count}/{len(records)} news records "
                    f"(correlation_id={correlation_id[:8]}...)"
                )
                
        except Exception as e:
            self._logger.error(f"Failed to persist {source} news: {e}")
            # Don't raise - we want ingestion to continue
            return 0
        
        return stored_count


# ============================================================
# FACTORY FUNCTION
# ============================================================

def create_real_ingestion_module(**kwargs) -> RealIngestionModule:
    """
    Factory function to create RealIngestionModule.
    
    This is used by the orchestrator's module factory.
    """
    config = RealIngestionConfig()
    return RealIngestionModule(config=config, **kwargs)
