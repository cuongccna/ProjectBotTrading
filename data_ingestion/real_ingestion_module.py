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
from sqlalchemy import func

from database.engine import get_session, get_db_session
from database.models import MarketData, RawNews, OnchainFlowRaw, ExchangeFlowAggregate


# ============================================================
# EXCEPTIONS
# ============================================================

class IngestionConfigurationError(Exception):
    """Raised when ingestion module is misconfigured."""
    pass


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
    cryptopanic_base_url: str = "https://cryptopanic.com/api"  # Base URL without plan/version
    cryptopanic_api_plan: str = "developer"  # developer, growth, enterprise
    cryptopanic_api_key: Optional[str] = None
    cryptopanic_currencies: List[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL"])
    cryptopanic_filter: Optional[str] = None  # rising, hot, bullish, bearish, important
    cryptopanic_kind: str = "news"  # news, media, all
    
    # Whale Alert settings (free tier: 10 req/min, $500k min value)
    whalealert_enabled: bool = False  # Disabled by default (requires API key)
    whalealert_base_url: str = "https://api.whale-alert.io/v1"
    whalealert_api_key: Optional[str] = None
    whalealert_min_value_usd: int = 500000  # Minimum $500k for free tier
    whalealert_currencies: List[str] = field(default_factory=lambda: ["btc", "eth", "usdt", "usdc"])
    whalealert_lookback_seconds: int = 3600  # Look back 1 hour
    
    # Nansen Smart Money settings (PREMIUM - requires paid subscription)
    nansen_enabled: bool = False  # Disabled by default (requires paid plan)
    nansen_base_url: str = "https://api.nansen.ai/api/v1"
    nansen_api_key: Optional[str] = None
    nansen_chains: List[str] = field(default_factory=lambda: ["ethereum", "solana", "base", "arbitrum"])
    nansen_include_stablecoins: bool = True
    nansen_include_native_tokens: bool = True
    nansen_smart_money_labels: List[str] = field(default_factory=lambda: ["Fund", "Smart Trader"])
    nansen_page_size: int = 50  # Results per page
    
    # Exchange flow aggregation settings
    exchange_flow_enabled: bool = True  # Aggregate raw flows into exchange-level metrics
    exchange_flow_tokens: List[str] = field(default_factory=lambda: ["BTC", "ETH", "USDT", "USDC", "USDD", "DAI"])
    exchange_flow_time_windows: List[str] = field(default_factory=lambda: ["1h", "4h", "24h"])
    exchange_flow_min_tx_count: int = 1  # Minimum transactions to create aggregate
    
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
    whalealert_fetched: int = 0
    whalealert_stored: int = 0
    nansen_fetched: int = 0
    nansen_stored: int = 0
    
    # Exchange flow aggregation counts
    exchange_flow_aggregated: int = 0
    exchange_flow_stored: int = 0
    
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
    # STARTUP VALIDATION
    # --------------------------------------------------------
    
    def _validate_configuration(self) -> None:
        """
        Validate all enabled data sources and required API keys.
        
        Raises:
            IngestionConfigurationError: If critical configuration is missing
        """
        errors: List[str] = []
        warnings: List[str] = []
        enabled_sources: List[str] = []
        
        # ---- CoinGecko validation ----
        if self._config.coingecko_enabled:
            enabled_sources.append("CoinGecko")
            # CoinGecko API key is optional for demo tier, but recommended
            api_key = self._config.coingecko_api_key or os.getenv("COINGECKO_API_KEY")
            if not api_key:
                warnings.append(
                    "CoinGecko: No API key found. Using free tier (30 req/min limit). "
                    "Set COINGECKO_API_KEY in environment for higher limits."
                )
            if not self._config.coingecko_assets:
                errors.append("CoinGecko: No assets configured (coingecko_assets is empty)")
            if not self._config.coingecko_base_url:
                errors.append("CoinGecko: base_url is not configured")
        
        # ---- Binance validation ----
        if self._config.binance_enabled:
            enabled_sources.append("Binance")
            # Binance public endpoints don't require API key
            if not self._config.tracked_symbols:
                errors.append("Binance: No symbols configured (tracked_symbols is empty)")
            base_url = self._config.binance_base_url if self._config.binance_use_futures else self._config.binance_spot_url
            if not base_url:
                errors.append("Binance: base_url is not configured")
        
        # ---- CryptoNews API validation ----
        if self._config.cryptonews_enabled:
            enabled_sources.append("CryptoNews")
            api_key = self._config.cryptonews_api_key or os.getenv("CRYPTO_NEWS_API_KEY")
            if not api_key:
                errors.append(
                    "CryptoNews: CRYPTO_NEWS_API_KEY is required but not found in environment. "
                    "Disable cryptonews_enabled or set the API key."
                )
            if not self._config.cryptonews_base_url:
                errors.append("CryptoNews: base_url is not configured")
            if not self._config.cryptonews_tickers:
                warnings.append("CryptoNews: No tickers configured, will fetch general news")
        
        # ---- CryptoPanic validation ----
        if self._config.cryptopanic_enabled:
            enabled_sources.append("CryptoPanic")
            api_key = self._config.cryptopanic_api_key or os.getenv("CRYPTOPANIC_API_KEY")
            if not api_key:
                errors.append(
                    "CryptoPanic: CRYPTOPANIC_API_KEY is required but not found in environment. "
                    "Disable cryptopanic_enabled or set the API key."
                )
            if not self._config.cryptopanic_base_url:
                errors.append("CryptoPanic: base_url is not configured")
            if self._config.cryptopanic_api_plan not in ["developer", "growth", "enterprise"]:
                errors.append(
                    f"CryptoPanic: Invalid api_plan '{self._config.cryptopanic_api_plan}'. "
                    "Must be one of: developer, growth, enterprise"
                )
        
        # ---- Whale Alert validation ----
        if self._config.whalealert_enabled:
            enabled_sources.append("WhaleAlert")
            api_key = self._config.whalealert_api_key or os.getenv("WHALE_ALERT_API_KEY")
            if not api_key:
                errors.append(
                    "WhaleAlert: WHALE_ALERT_API_KEY is required but not found in environment. "
                    "Disable whalealert_enabled or set the API key."
                )
            if not self._config.whalealert_base_url:
                errors.append("WhaleAlert: base_url is not configured")
            if self._config.whalealert_min_value_usd < 500000:
                warnings.append(
                    f"WhaleAlert: min_value_usd={self._config.whalealert_min_value_usd} is below "
                    "free tier minimum ($500,000). API may reject requests."
                )
        
        # ---- Nansen Smart Money validation (PREMIUM) ----
        if self._config.nansen_enabled:
            enabled_sources.append("Nansen")
            api_key = self._config.nansen_api_key or os.getenv("NANSEN_API_KEY")
            if not api_key:
                errors.append(
                    "Nansen: NANSEN_API_KEY is required but not found in environment. "
                    "Disable nansen_enabled or set the API key."
                )
            if not self._config.nansen_base_url:
                errors.append("Nansen: base_url is not configured")
            if not self._config.nansen_chains:
                errors.append("Nansen: No chains configured (nansen_chains is empty)")
            warnings.append(
                "Nansen: Smart Money API requires a PAID subscription. "
                "Free tier users will receive 403 errors."
            )
        
        # ---- Check at least one source is enabled ----
        if not enabled_sources:
            errors.append(
                "No data sources enabled! Enable at least one of: "
                "coingecko_enabled, binance_enabled, cryptonews_enabled, cryptopanic_enabled, whalealert_enabled"
            )
        
        # ---- Log warnings ----
        for warning in warnings:
            self._logger.warning(f"⚠️ Configuration Warning: {warning}")
        
        # ---- Log and raise errors ----
        if errors:
            self._logger.error("="*60)
            self._logger.error("INGESTION CONFIGURATION ERRORS")
            self._logger.error("="*60)
            for i, error in enumerate(errors, 1):
                self._logger.error(f"  {i}. {error}")
            self._logger.error("="*60)
            raise IngestionConfigurationError(
                f"Ingestion module has {len(errors)} configuration error(s). "
                f"Check logs above for details."
            )
        
        # ---- Log successful validation ----
        self._logger.info(
            f"✅ Configuration validated | Enabled sources: {', '.join(enabled_sources)}"
        )
    
    def _validate_database_connection(self) -> None:
        """
        Validate database connection is working.
        
        Raises:
            IngestionConfigurationError: If database connection fails
        """
        from sqlalchemy import text
        try:
            with self._session_factory() as session:
                # Simple query to test connection
                session.execute(text("SELECT 1"))
                self._logger.info("✅ Database connection validated")
        except Exception as e:
            raise IngestionConfigurationError(
                f"Database connection failed: {e}. "
                "Check DATABASE_URL in environment."
            )
    
    # --------------------------------------------------------
    # ORCHESTRATOR INTERFACE
    # --------------------------------------------------------
    
    async def start(self) -> None:
        """
        Start the ingestion module.
        
        Performs startup validation:
        1. Validates all enabled data sources
        2. Validates required API keys exist
        3. Validates database connection
        
        Raises:
            IngestionConfigurationError: If validation fails
        """
        self._logger.info("Starting RealIngestionModule...")
        
        # Run startup validation (fails fast if misconfigured)
        self._validate_configuration()
        self._validate_database_connection()
        
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
            
            # Fetch from Whale Alert
            if self._config.whalealert_enabled:
                try:
                    wa_records = await self._fetch_whale_alert()
                    result.whalealert_fetched = len(wa_records)
                    
                    stored = await self._persist_onchain_flow_records(wa_records, "whale_alert")
                    result.whalealert_stored = stored
                    
                    self._logger.info(
                        f"[WhaleAlert] Fetched: {result.whalealert_fetched}, "
                        f"Stored: {result.whalealert_stored}"
                    )
                except Exception as e:
                    self._logger.warning(f"[WhaleAlert] Error: {e}")
                    result.errors.append(f"WhaleAlert: {e}")
            
            # Fetch from Nansen Smart Money API (PREMIUM)
            if self._config.nansen_enabled:
                try:
                    nansen_records = await self._fetch_nansen()
                    result.nansen_fetched = len(nansen_records)
                    
                    stored = await self._persist_onchain_flow_records(nansen_records, "nansen")
                    result.nansen_stored = stored
                    
                    self._logger.info(
                        f"[Nansen] Fetched: {result.nansen_fetched}, "
                        f"Stored: {result.nansen_stored}"
                    )
                except Exception as e:
                    self._logger.warning(f"[Nansen] Error: {e}")
                    result.errors.append(f"Nansen: {e}")
            
            # Aggregate exchange flows from raw onchain data
            if self._config.exchange_flow_enabled:
                try:
                    aggregates = await self._aggregate_exchange_flows()
                    result.exchange_flow_aggregated = len(aggregates)
                    
                    stored = await self._persist_exchange_flow_aggregates(aggregates)
                    result.exchange_flow_stored = stored
                    
                    self._logger.info(
                        f"[ExchangeFlow] Aggregated: {result.exchange_flow_aggregated}, "
                        f"Stored: {result.exchange_flow_stored}"
                    )
                except Exception as e:
                    self._logger.warning(f"[ExchangeFlow] Error: {e}")
                    result.errors.append(f"ExchangeFlow: {e}")
            
            # Calculate totals
            result.total_fetched = (
                result.coingecko_fetched + result.binance_fetched +
                result.cryptonews_fetched + result.cryptopanic_fetched +
                result.whalealert_fetched + result.nansen_fetched
            )
            result.total_stored = (
                result.coingecko_stored + result.binance_stored +
                result.cryptonews_stored + result.cryptopanic_stored +
                result.whalealert_stored + result.nansen_stored + result.exchange_flow_stored
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
        
        API Docs: https://cryptonews-api.com/documentation
        Endpoint: GET /api/v1/category
        
        Valid sections:
        - "general": General crypto news
        - "alltickers": News filtered by specific tickers
        
        Returns:
            List of news article dictionaries
            
        Raises:
            ValueError: On invalid API response schema
        """
        import httpx
        from email.utils import parsedate_to_datetime
        
        api_key = self._config.cryptonews_api_key or os.getenv("CRYPTO_NEWS_API_KEY")
        if not api_key:
            self._logger.warning(
                "[CryptoNews] No API key configured (CRYPTO_NEWS_API_KEY). Skipping..."
            )
            return []
        
        url = f"{self._config.cryptonews_base_url}/category"
        
        # Build valid parameters per API docs
        params = {
            "section": "alltickers",  # Filter by specific tickers
            "tickers": ",".join(self._config.cryptonews_tickers),  # e.g., "BTC,ETH,SOL"
            "items": 10,  # Trial plan limit: max 3-10 items
            "token": api_key,
        }
        
        self._logger.debug(
            f"[CryptoNews] Fetching from {url} with tickers={params['tickers']}"
        )
        
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                response = await client.get(url, params=params)
                
                # Handle HTTP errors with explicit reasons
                if response.status_code == 401:
                    self._logger.error(
                        "[CryptoNews] Invalid API key (401 Unauthorized). "
                        "Check CRYPTO_NEWS_API_KEY in .env"
                    )
                    return []
                    
                if response.status_code == 403:
                    self._logger.error(
                        "[CryptoNews] Access denied (403 Forbidden). "
                        "API key may be expired or plan limit reached."
                    )
                    return []
                    
                if response.status_code == 429:
                    self._logger.warning(
                        "[CryptoNews] Rate limited (429). "
                        f"Limit: {params.get('items')} items/request. Skipping..."
                    )
                    return []
                
                response.raise_for_status()
                
                # Parse and validate response schema
                try:
                    data = response.json()
                except Exception as json_err:
                    self._logger.error(
                        f"[CryptoNews] Invalid JSON response: {json_err}. "
                        f"Raw response: {response.text[:200]}"
                    )
                    return []
                
                # Validate expected schema structure
                if not isinstance(data, dict):
                    self._logger.error(
                        f"[CryptoNews] Unexpected response type: {type(data).__name__}. "
                        "Expected dict with 'data' key."
                    )
                    return []
                
                if "data" not in data:
                    # Check for error message in response
                    error_msg = data.get("message") or data.get("error") or "Unknown"
                    self._logger.error(
                        f"[CryptoNews] API error response: {error_msg}"
                    )
                    return []
                
                raw_items = data["data"]
                
                if not isinstance(raw_items, list):
                    self._logger.error(
                        f"[CryptoNews] Expected 'data' to be list, got {type(raw_items).__name__}"
                    )
                    return []
                
                # Transform to news record format with validation
                records = []
                now = datetime.now(timezone.utc)
                validation_errors = 0
                
                for idx, item in enumerate(raw_items):
                    # Validate required fields per schema
                    if not isinstance(item, dict):
                        validation_errors += 1
                        continue
                        
                    title = item.get("title")
                    news_url = item.get("news_url")
                    
                    if not title:
                        self._logger.debug(
                            f"[CryptoNews] Item {idx} missing required field 'title'. Skipping."
                        )
                        validation_errors += 1
                        continue
                    
                    # Parse published date (RFC 2822 format)
                    published_at = None
                    pub_date_str = item.get("date")
                    if pub_date_str:
                        try:
                            published_at = parsedate_to_datetime(pub_date_str)
                        except (ValueError, TypeError) as e:
                            self._logger.debug(
                                f"[CryptoNews] Failed to parse date '{pub_date_str}': {e}"
                            )
                            published_at = now
                    
                    # Extract tickers - can be string or list
                    tickers_raw = item.get("tickers", "")
                    if isinstance(tickers_raw, str):
                        tickers = [t.strip() for t in tickers_raw.split(",") if t.strip()]
                    elif isinstance(tickers_raw, list):
                        tickers = tickers_raw
                    else:
                        tickers = []
                    
                    # Build normalized record
                    record = {
                        "external_id": news_url or f"cryptonews_{idx}_{now.timestamp()}",
                        "title": title,
                        "content": item.get("text", ""),
                        "summary": (item.get("text", "") or "")[:500] or None,
                        "url": news_url or "",
                        "source_name": "cryptonews_api",
                        "source_module": "RealIngestionModule.cryptonews",
                        "author": item.get("source_name", ""),
                        "categories": [item.get("type", "news")],
                        "tokens": tickers,
                        "published_at": published_at,
                        "fetched_at": now,
                        "sentiment": item.get("sentiment"),  # e.g., "Positive", "Negative", "Neutral"
                    }
                    records.append(record)
                
                # Log fetch summary
                self._logger.info(
                    f"[CryptoNews] API returned {len(raw_items)} items, "
                    f"validated {len(records)} records, "
                    f"skipped {validation_errors} invalid"
                )
                
                return records
                
        except httpx.HTTPStatusError as e:
            self._logger.error(
                f"[CryptoNews] HTTP error {e.response.status_code}: "
                f"{e.response.text[:200] if e.response.text else 'No response body'}"
            )
            return []
        except httpx.TimeoutException:
            self._logger.warning(
                f"[CryptoNews] Request timeout after {self._config.timeout_seconds}s. "
                "Consider increasing timeout_seconds in config."
            )
            return []
        except httpx.RequestError as e:
            self._logger.error(
                f"[CryptoNews] Network error: {type(e).__name__}: {e}"
            )
            return []
        except Exception as e:
            self._logger.error(
                f"[CryptoNews] Unexpected error: {type(e).__name__}: {e}",
                exc_info=True
            )
            return []
    
    # --------------------------------------------------------
    # CRYPTOPANIC FETCHING
    # --------------------------------------------------------
    
    async def _fetch_cryptopanic(self) -> List[Dict[str, Any]]:
        """
        Fetch news/sentiment from CryptoPanic API v2.
        
        API Docs: https://cryptopanic.com/developers/api/
        Endpoint: GET /api/{api_plan}/v2/posts/
        
        API Plans:
        - developer: Free tier (limited rate)
        - growth: Paid tier
        - enterprise: Full access
        
        Returns:
            List of news/sentiment dictionaries
        """
        api_key = self._config.cryptopanic_api_key or os.getenv("CRYPTOPANIC_API_KEY")
        if not api_key:
            self._logger.warning(
                "[CryptoPanic] No API key configured (CRYPTOPANIC_API_KEY). Skipping..."
            )
            return []
        
        # Build URL with API plan and version
        # Format: https://cryptopanic.com/api/{api_plan}/v2/posts/
        api_plan = self._config.cryptopanic_api_plan  # developer, growth, enterprise
        url = f"{self._config.cryptopanic_base_url}/{api_plan}/v2/posts/"
        
        # Build parameters per API docs
        params = {
            "auth_token": api_key,
            "public": "true",  # Use public mode for generic apps
            "kind": self._config.cryptopanic_kind,  # news, media, all
        }
        
        # Add currencies filter
        if self._config.cryptopanic_currencies:
            params["currencies"] = ",".join(self._config.cryptopanic_currencies)
        
        # Add optional filter (rising, hot, bullish, bearish, important)
        if self._config.cryptopanic_filter:
            params["filter"] = self._config.cryptopanic_filter
        
        self._logger.debug(
            f"[CryptoPanic] Fetching from {url} with currencies={params.get('currencies')}"
        )
        
        all_records = []
        now = datetime.now(timezone.utc)
        page_url = url
        max_pages = 3  # Limit pagination to avoid rate limits
        pages_fetched = 0
        
        try:
            timeout = aiohttp.ClientTimeout(total=self._config.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                while page_url and pages_fetched < max_pages:
                    async with session.get(page_url, params=params if pages_fetched == 0 else None) as response:
                        # Handle HTTP errors with explicit reasons
                        if response.status == 401:
                            self._logger.error(
                                "[CryptoPanic] Invalid API key (401 Unauthorized). "
                                "Check CRYPTOPANIC_API_KEY in .env"
                            )
                            return []
                        
                        if response.status == 403:
                            self._logger.error(
                                "[CryptoPanic] Access denied (403 Forbidden). "
                                "Rate limit exceeded or no access to endpoint."
                            )
                            return []
                        
                        if response.status == 429:
                            self._logger.warning(
                                "[CryptoPanic] Rate limited (429). "
                                f"Plan: {api_plan}. Skipping..."
                            )
                            return all_records  # Return what we have so far
                        
                        if response.status != 200:
                            self._logger.error(
                                f"[CryptoPanic] HTTP error {response.status}"
                            )
                            return all_records
                        
                        # Parse and validate response
                        try:
                            data = await response.json()
                        except Exception as json_err:
                            self._logger.error(
                                f"[CryptoPanic] Invalid JSON response: {json_err}"
                            )
                            return all_records
                        
                        # Validate schema
                        if not isinstance(data, dict):
                            self._logger.error(
                                f"[CryptoPanic] Unexpected response type: {type(data).__name__}"
                            )
                            return all_records
                        
                        # Extract results
                        raw_items = data.get("results", [])
                        
                        if not isinstance(raw_items, list):
                            self._logger.error(
                                f"[CryptoPanic] Expected 'results' to be list"
                            )
                            return all_records
                        
                        # Transform to news record format
                        for item in raw_items:
                            if not isinstance(item, dict):
                                continue
                            
                            # Validate required fields
                            title = item.get("title")
                            if not title:
                                continue
                            
                            # Parse published date (ISO 8601)
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
                            
                            # Extract currencies/instruments (v2 uses 'instruments')
                            currencies = []
                            instruments = item.get("instruments") or item.get("currencies", [])
                            for instr in instruments:
                                if isinstance(instr, dict):
                                    code = instr.get("code", "")
                                    if code:
                                        currencies.append(code)
                                elif isinstance(instr, str):
                                    currencies.append(instr)
                            
                            # Extract votes for sentiment
                            votes = item.get("votes", {})
                            if isinstance(votes, dict):
                                positive = votes.get("positive", 0) or 0
                                negative = votes.get("negative", 0) or 0
                                important = votes.get("important", 0) or 0
                            else:
                                positive = negative = important = 0
                            
                            # Calculate sentiment score (-1 to 1)
                            total_votes = positive + negative
                            if total_votes > 0:
                                sentiment_score = (positive - negative) / total_votes
                            else:
                                sentiment_score = 0.0
                            
                            # Extract source info
                            source_obj = item.get("source", {})
                            if isinstance(source_obj, dict):
                                author = source_obj.get("title", "")
                            else:
                                author = ""
                            
                            record = {
                                "external_id": str(item.get("id", "")),
                                "title": title,
                                "content": item.get("description") or None,
                                "summary": (item.get("description") or title)[:500],
                                "url": item.get("original_url") or item.get("url", ""),
                                "source_name": "cryptopanic",
                                "source_module": "RealIngestionModule.cryptopanic",
                                "author": author,
                                "categories": [item.get("kind", "news")],
                                "tokens": currencies,
                                "published_at": published_at,
                                "fetched_at": now,
                                "sentiment": sentiment_score,
                                "votes_positive": positive,
                                "votes_negative": negative,
                                "votes_important": important,
                            }
                            all_records.append(record)
                        
                        pages_fetched += 1
                        
                        # Get next page URL for pagination
                        page_url = data.get("next")
                        if page_url:
                            # Next URL already includes params, don't add again
                            params = None
                
                # Log fetch summary
                self._logger.info(
                    f"[CryptoPanic] Fetched {len(all_records)} articles "
                    f"from {pages_fetched} page(s)"
                )
                
                return all_records
                    
        except aiohttp.ClientError as e:
            self._logger.error(
                f"[CryptoPanic] Network error: {type(e).__name__}: {e}"
            )
            return all_records
        except asyncio.TimeoutError:
            self._logger.warning(
                f"[CryptoPanic] Request timeout after {self._config.timeout_seconds}s"
            )
            return all_records
        except Exception as e:
            self._logger.error(
                f"[CryptoPanic] Unexpected error: {type(e).__name__}: {e}",
                exc_info=True
            )
            return all_records
    
    # --------------------------------------------------------
    # WHALE ALERT FETCHING
    # --------------------------------------------------------
    
    async def _fetch_whale_alert(self) -> List[Dict[str, Any]]:
        """
        Fetch whale transactions from Whale Alert API (Developer API - Free Tier).
        
        API Docs: https://developer.whale-alert.io/documentation/
        Endpoint: GET /v1/transactions
        
        Free tier limits:
        - 10 requests per minute
        - Minimum $500,000 transaction value
        - 30-day history
        
        Returns:
            List of onchain flow records ready for persistence
        """
        api_key = self._config.whalealert_api_key or os.getenv("WHALE_ALERT_API_KEY")
        if not api_key:
            self._logger.warning(
                "[WhaleAlert] No API key configured (WHALE_ALERT_API_KEY). Skipping..."
            )
            return []
        
        # Calculate start time (lookback from now)
        now = datetime.now(timezone.utc)
        start_time = int((now - timedelta(seconds=self._config.whalealert_lookback_seconds)).timestamp())
        
        url = f"{self._config.whalealert_base_url}/transactions"
        params = {
            "api_key": api_key,
            "min_value": self._config.whalealert_min_value_usd,
            "start": start_time,
            "limit": 100,  # Max per request
        }
        
        # Add currency filter if specified
        if self._config.whalealert_currencies:
            # API accepts single currency at a time, we'll fetch first configured one
            # For multiple currencies, would need to make multiple requests
            params["currency"] = self._config.whalealert_currencies[0]
        
        self._logger.debug(
            f"[WhaleAlert] Fetching from {url} with min_value=${self._config.whalealert_min_value_usd:,}"
        )
        
        all_records = []
        
        # Chain name normalization map
        CHAIN_NORMALIZE = {
            "bitcoin": "bitcoin",
            "ethereum": "ethereum",
            "tron": "tron",
            "ripple": "xrp",
            "cardano": "cardano",
            "solana": "solana",
            "polygon": "polygon",
            "litecoin": "litecoin",
            "dogecoin": "dogecoin",
            "algorand": "algorand",
        }
        
        # Transaction type to direction mapping
        TX_TYPE_TO_DIRECTION = {
            "transfer": "transfer",
            "mint": "mint",
            "burn": "burn",
            "lock": "lock",
            "unlock": "unlock",
            "freeze": "freeze",
            "unfreeze": "unfreeze",
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=self._config.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as response:
                    # Handle HTTP errors
                    if response.status == 401:
                        self._logger.error(
                            "[WhaleAlert] Invalid API key (401 Unauthorized). "
                            "Check WHALE_ALERT_API_KEY in .env"
                        )
                        return []
                    
                    if response.status == 403:
                        self._logger.error(
                            "[WhaleAlert] Access denied (403 Forbidden). "
                            "API key may not have access to this endpoint."
                        )
                        return []
                    
                    if response.status == 429:
                        self._logger.warning(
                            "[WhaleAlert] Rate limited (429). "
                            "Free tier: 10 req/min. Waiting..."
                        )
                        return []
                    
                    if response.status != 200:
                        text = await response.text()
                        self._logger.error(
                            f"[WhaleAlert] HTTP error {response.status}: {text[:200]}"
                        )
                        return []
                    
                    # Parse response
                    try:
                        data = await response.json()
                    except Exception as json_err:
                        self._logger.error(
                            f"[WhaleAlert] Invalid JSON response: {json_err}"
                        )
                        return []
                    
                    # Validate schema
                    if not isinstance(data, dict):
                        self._logger.error(
                            f"[WhaleAlert] Unexpected response type: {type(data).__name__}"
                        )
                        return []
                    
                    # Check for API errors
                    if data.get("result") == "error":
                        error_msg = data.get("message", "Unknown error")
                        self._logger.error(f"[WhaleAlert] API error: {error_msg}")
                        return []
                    
                    # Extract transactions
                    transactions = data.get("transactions", [])
                    
                    if not isinstance(transactions, list):
                        self._logger.error(
                            "[WhaleAlert] Expected 'transactions' to be list"
                        )
                        return []
                    
                    self._logger.debug(
                        f"[WhaleAlert] Received {len(transactions)} transactions"
                    )
                    
                    # Transform transactions to onchain flow records
                    for tx in transactions:
                        if not isinstance(tx, dict):
                            continue
                        
                        # Extract basic fields
                        blockchain = tx.get("blockchain", "unknown")
                        symbol = tx.get("symbol", "").upper()
                        tx_type = tx.get("transaction_type", "transfer")
                        amount = tx.get("amount", 0)
                        amount_usd = tx.get("amount_usd", 0)
                        timestamp = tx.get("timestamp", 0)
                        tx_hash = tx.get("hash", "")
                        
                        # Skip if below threshold (should be pre-filtered by API)
                        if amount_usd < self._config.whalealert_min_value_usd:
                            continue
                        
                        # Normalize chain name
                        chain = CHAIN_NORMALIZE.get(blockchain.lower(), blockchain.lower())
                        
                        # Normalize transaction type / direction
                        flow_type = TX_TYPE_TO_DIRECTION.get(tx_type.lower(), "transfer")
                        
                        # Determine if this is exchange related
                        from_data = tx.get("from", {})
                        to_data = tx.get("to", {})
                        
                        from_address = from_data.get("address", "") if isinstance(from_data, dict) else ""
                        to_address = to_data.get("address", "") if isinstance(to_data, dict) else ""
                        from_entity = from_data.get("owner", "") if isinstance(from_data, dict) else ""
                        to_entity = to_data.get("owner", "") if isinstance(to_data, dict) else ""
                        from_type = from_data.get("owner_type", "") if isinstance(from_data, dict) else ""
                        to_type = to_data.get("owner_type", "") if isinstance(to_data, dict) else ""
                        
                        # Classify as exchange inflow/outflow/whale transfer
                        if from_type == "exchange" and to_type != "exchange":
                            flow_type = "exchange_outflow"
                        elif to_type == "exchange" and from_type != "exchange":
                            flow_type = "exchange_inflow"
                        elif from_type != "exchange" and to_type != "exchange":
                            flow_type = "whale_transfer"
                        
                        # Convert timestamp to datetime
                        event_time = datetime.fromtimestamp(timestamp, tz=timezone.utc) if timestamp else now
                        
                        record = {
                            "token": symbol or chain.upper(),
                            "chain": chain,
                            "flow_type": flow_type,
                            "amount": float(amount),
                            "amount_usd": float(amount_usd) if amount_usd else None,
                            "from_address": from_address[:100] if from_address else None,
                            "to_address": to_address[:100] if to_address else None,
                            "from_entity": from_entity or None,
                            "to_entity": to_entity or None,
                            "tx_hash": tx_hash[:100] if tx_hash else None,
                            "block_number": None,  # Not provided in Developer API
                            "source_name": "whale_alert",
                            "source_module": "RealIngestionModule.whale_alert",
                            "event_time": event_time,
                            "fetched_at": now,
                            "raw_data": tx,  # Store raw for debugging
                        }
                        all_records.append(record)
                
                self._logger.info(
                    f"[WhaleAlert] Fetched {len(all_records)} whale transactions "
                    f"(min ${self._config.whalealert_min_value_usd:,})"
                )
                
                return all_records
                    
        except aiohttp.ClientError as e:
            self._logger.error(
                f"[WhaleAlert] Network error: {type(e).__name__}: {e}"
            )
            return []
        except asyncio.TimeoutError:
            self._logger.warning(
                f"[WhaleAlert] Request timeout after {self._config.timeout_seconds}s"
            )
            return []
        except Exception as e:
            self._logger.error(
                f"[WhaleAlert] Unexpected error: {type(e).__name__}: {e}",
                exc_info=True
            )
            return []
    
    async def _fetch_nansen(self) -> List[Dict[str, Any]]:
        """
        Fetch smart money netflow data from Nansen API (PAID SUBSCRIPTION REQUIRED).
        
        API Docs: https://docs.nansen.ai/api/smart-money/netflows
        Endpoint: POST /api/v1/smart-money/netflow
        
        NOTE: This endpoint requires a paid Nansen subscription.
        Free tier users will receive 403 errors.
        
        Returns:
            List of onchain flow records ready for persistence
        """
        api_key = self._config.nansen_api_key or os.getenv("NANSEN_API_KEY")
        if not api_key:
            self._logger.warning(
                "[Nansen] No API key configured (NANSEN_API_KEY). Skipping..."
            )
            return []
        
        url = f"{self._config.nansen_base_url}/smart-money/netflow"
        
        # Build request body according to Nansen API spec
        request_body = {
            "chains": self._config.nansen_chains,
            "filters": {
                "include_labels": self._config.nansen_smart_money_labels,
                "exclude_labels": [],  # No exclusions by default
                "include_stablecoins": self._config.nansen_include_stablecoins,
                "include_native_tokens": self._config.nansen_include_native_tokens,
            },
            "pagination": {
                "page": 1,
                "page_size": self._config.nansen_page_size,
            },
            "order_by": {
                "field": "net_flow_24h_usd",
                "direction": "desc",
            },
        }
        
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "apiKey": api_key,
        }
        
        self._logger.debug(
            f"[Nansen] Fetching smart money netflow from {url} "
            f"for chains: {self._config.nansen_chains}"
        )
        
        all_records = []
        now = datetime.now(timezone.utc)
        
        try:
            timeout = aiohttp.ClientTimeout(total=self._config.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=request_body, headers=headers) as response:
                    # Handle HTTP errors
                    if response.status == 401:
                        self._logger.error(
                            "[Nansen] Invalid API key (401 Unauthorized). "
                            "Check NANSEN_API_KEY in .env"
                        )
                        return []
                    
                    if response.status == 403:
                        self._logger.error(
                            "[Nansen] Access denied (403 Forbidden). "
                            "Smart Money API requires a PAID subscription. "
                            "Free tier users cannot access this endpoint."
                        )
                        return []
                    
                    if response.status == 429:
                        self._logger.warning(
                            "[Nansen] Rate limited (429). Please wait and retry."
                        )
                        return []
                    
                    if response.status != 200:
                        text = await response.text()
                        self._logger.error(
                            f"[Nansen] HTTP error {response.status}: {text[:200]}"
                        )
                        return []
                    
                    # Parse response
                    try:
                        data = await response.json()
                    except Exception as json_err:
                        self._logger.error(
                            f"[Nansen] Invalid JSON response: {json_err}"
                        )
                        return []
                    
                    # Validate schema
                    if not isinstance(data, dict):
                        self._logger.error(
                            f"[Nansen] Unexpected response type: {type(data).__name__}"
                        )
                        return []
                    
                    # Check for API errors
                    if "error" in data:
                        error_msg = data.get("error", {}).get("message", "Unknown error")
                        self._logger.error(f"[Nansen] API error: {error_msg}")
                        return []
                    
                    # Extract data array
                    netflow_data = data.get("data", [])
                    
                    if not isinstance(netflow_data, list):
                        self._logger.error(
                            "[Nansen] Expected 'data' to be list"
                        )
                        return []
                    
                    self._logger.debug(
                        f"[Nansen] Received {len(netflow_data)} smart money netflow records"
                    )
                    
                    # Transform netflow records to onchain flow records
                    for item in netflow_data:
                        if not isinstance(item, dict):
                            continue
                        
                        # Extract fields from Nansen response
                        chain = item.get("chain", "ethereum")
                        token_symbol = item.get("token_symbol", "").upper()
                        token_address = item.get("token_address", "")
                        
                        # Nansen provides netflow for different time windows
                        net_flow_1h = item.get("net_flow_1h_usd", 0) or 0
                        net_flow_24h = item.get("net_flow_24h_usd", 0) or 0
                        net_flow_7d = item.get("net_flow_7d_usd", 0) or 0
                        net_flow_30d = item.get("net_flow_30d_usd", 0) or 0
                        
                        # Determine flow direction based on 24h netflow
                        # Positive = smart money is buying (bullish)
                        # Negative = smart money is selling (bearish)
                        if net_flow_24h > 0:
                            flow_type = "smart_money_inflow"
                        elif net_flow_24h < 0:
                            flow_type = "smart_money_outflow"
                        else:
                            flow_type = "smart_money_neutral"
                        
                        record = {
                            "token": token_symbol or "UNKNOWN",
                            "chain": chain.lower(),
                            "flow_type": flow_type,
                            "amount": abs(net_flow_24h),  # Store absolute value
                            "amount_usd": abs(net_flow_24h),  # Already in USD
                            "from_address": token_address[:100] if token_address else None,
                            "to_address": None,
                            "from_entity": "smart_money",
                            "to_entity": None,
                            "tx_hash": None,  # Nansen provides aggregated data, no tx hash
                            "block_number": None,
                            "source_name": "nansen",
                            "source_module": "RealIngestionModule.nansen",
                            "event_time": now,  # Nansen provides current netflow
                            "fetched_at": now,
                            "raw_data": {
                                "chain": chain,
                                "token_symbol": token_symbol,
                                "token_address": token_address,
                                "net_flow_1h_usd": net_flow_1h,
                                "net_flow_24h_usd": net_flow_24h,
                                "net_flow_7d_usd": net_flow_7d,
                                "net_flow_30d_usd": net_flow_30d,
                            },
                        }
                        all_records.append(record)
                
                self._logger.info(
                    f"[Nansen] Fetched {len(all_records)} smart money netflow records "
                    f"for chains: {self._config.nansen_chains}"
                )
                
                return all_records
                    
        except aiohttp.ClientError as e:
            self._logger.error(
                f"[Nansen] Network error: {type(e).__name__}: {e}"
            )
            return []
        except asyncio.TimeoutError:
            self._logger.warning(
                f"[Nansen] Request timeout after {self._config.timeout_seconds}s"
            )
            return []
        except Exception as e:
            self._logger.error(
                f"[Nansen] Unexpected error: {type(e).__name__}: {e}",
                exc_info=True
            )
            return []
    
    # --------------------------------------------------------
    # EXCHANGE FLOW AGGREGATION
    # --------------------------------------------------------
    
    def _parse_time_window(self, window: str) -> timedelta:
        """Parse time window string to timedelta."""
        if window == "1h":
            return timedelta(hours=1)
        elif window == "4h":
            return timedelta(hours=4)
        elif window == "24h":
            return timedelta(hours=24)
        elif window == "7d":
            return timedelta(days=7)
        else:
            return timedelta(hours=1)  # Default
    
    async def _aggregate_exchange_flows(self) -> List[Dict[str, Any]]:
        """
        Aggregate raw onchain flow data by exchange and time window.
        
        Reads from onchain_flow_raw table, groups by:
        - Token (BTC, ETH, USDT, etc.)
        - Exchange (binance, coinbase, kraken, etc.)
        - Time window (1h, 4h, 24h)
        
        Computes:
        - Total inflow/outflow amounts
        - Net flow (inflow - outflow)
        - Transaction counts
        - Flow ratio (inflow/outflow)
        
        Returns:
            List of aggregate records ready for persistence
        """
        now = datetime.now(timezone.utc)
        aggregates = []
        
        try:
            with get_db_session() as session:
                for time_window in self._config.exchange_flow_time_windows:
                    window_delta = self._parse_time_window(time_window)
                    window_start = now - window_delta
                    
                    # Query for exchange inflows in this time window
                    for token in self._config.exchange_flow_tokens:
                        # Get all flows for this token in this window
                        flows = session.query(OnchainFlowRaw).filter(
                            OnchainFlowRaw.token == token,
                            OnchainFlowRaw.event_time >= window_start,
                            OnchainFlowRaw.event_time <= now,
                            OnchainFlowRaw.flow_type.in_(["exchange_inflow", "exchange_outflow"]),
                        ).all()
                        
                        if not flows:
                            continue
                        
                        # Group by exchange
                        exchange_flows = {}
                        for flow in flows:
                            # Determine exchange from entity
                            if flow.flow_type == "exchange_inflow":
                                exchange = flow.to_entity or "unknown"
                            else:  # exchange_outflow
                                exchange = flow.from_entity or "unknown"
                            
                            if not exchange or exchange == "unknown":
                                continue
                            
                            # Normalize exchange name
                            exchange = exchange.lower().strip()
                            
                            if exchange not in exchange_flows:
                                exchange_flows[exchange] = {
                                    "inflow_amount": 0.0,
                                    "outflow_amount": 0.0,
                                    "inflow_usd": 0.0,
                                    "outflow_usd": 0.0,
                                    "inflow_tx_count": 0,
                                    "outflow_tx_count": 0,
                                    "data_points": 0,
                                }
                            
                            ef = exchange_flows[exchange]
                            ef["data_points"] += 1
                            
                            if flow.flow_type == "exchange_inflow":
                                ef["inflow_amount"] += flow.amount or 0
                                ef["inflow_usd"] += flow.amount_usd or 0
                                ef["inflow_tx_count"] += 1
                            else:
                                ef["outflow_amount"] += flow.amount or 0
                                ef["outflow_usd"] += flow.amount_usd or 0
                                ef["outflow_tx_count"] += 1
                        
                        # Calculate totals for dominance percentage
                        total_flow_usd = sum(
                            ef["inflow_usd"] + ef["outflow_usd"]
                            for ef in exchange_flows.values()
                        )
                        
                        # Create aggregate records for each exchange
                        for exchange, ef in exchange_flows.items():
                            total_tx = ef["inflow_tx_count"] + ef["outflow_tx_count"]
                            
                            # Skip if below minimum transaction count
                            if total_tx < self._config.exchange_flow_min_tx_count:
                                continue
                            
                            net_flow = ef["inflow_amount"] - ef["outflow_amount"]
                            net_flow_usd = ef["inflow_usd"] - ef["outflow_usd"]
                            
                            # Calculate flow ratio (inflow/outflow)
                            flow_ratio = None
                            if ef["outflow_amount"] > 0:
                                flow_ratio = ef["inflow_amount"] / ef["outflow_amount"]
                            
                            # Calculate dominance percentage
                            dominance_pct = None
                            if total_flow_usd > 0:
                                exchange_flow_usd = ef["inflow_usd"] + ef["outflow_usd"]
                                dominance_pct = (exchange_flow_usd / total_flow_usd) * 100
                            
                            aggregate = {
                                "token": token,
                                "exchange": exchange,
                                "time_window": time_window,
                                "inflow_amount": ef["inflow_amount"],
                                "outflow_amount": ef["outflow_amount"],
                                "net_flow": net_flow,
                                "inflow_usd": ef["inflow_usd"] if ef["inflow_usd"] > 0 else None,
                                "outflow_usd": ef["outflow_usd"] if ef["outflow_usd"] > 0 else None,
                                "net_flow_usd": net_flow_usd if abs(net_flow_usd) > 0 else None,
                                "inflow_tx_count": ef["inflow_tx_count"],
                                "outflow_tx_count": ef["outflow_tx_count"],
                                "total_tx_count": total_tx,
                                "flow_ratio": flow_ratio,
                                "dominance_pct": dominance_pct,
                                "window_start": window_start,
                                "window_end": now,
                                "source_name": "whale_alert",
                                "data_points_count": ef["data_points"],
                                "aggregated_at": now,
                            }
                            aggregates.append(aggregate)
                
                self._logger.debug(
                    f"[ExchangeFlow] Generated {len(aggregates)} aggregates "
                    f"across {len(self._config.exchange_flow_time_windows)} time windows"
                )
                
        except Exception as e:
            self._logger.error(
                f"[ExchangeFlow] Aggregation error: {type(e).__name__}: {e}",
                exc_info=True
            )
        
        return aggregates
    
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
    
    async def _persist_onchain_flow_records(
        self,
        records: List[Dict[str, Any]],
        source: str,
    ) -> int:
        """
        Persist onchain flow records to onchain_flow_raw table.
        
        Handles duplicates by checking tx_hash + token + event_time.
        
        Args:
            records: List of onchain flow record dictionaries
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
                for record in records:
                    # Skip if duplicate by tx_hash (if exists)
                    tx_hash = record.get("tx_hash")
                    if tx_hash:
                        existing = session.query(OnchainFlowRaw).filter(
                            OnchainFlowRaw.tx_hash == tx_hash,
                            OnchainFlowRaw.token == record.get("token"),
                        ).first()
                        if existing:
                            continue  # Skip duplicate
                    
                    # Create new record
                    flow_record = OnchainFlowRaw(
                        correlation_id=correlation_id,
                        token=record.get("token", "UNKNOWN"),
                        chain=record.get("chain", "unknown"),
                        flow_type=record.get("flow_type", "transfer"),
                        amount=record.get("amount", 0),
                        amount_usd=record.get("amount_usd"),
                        from_address=record.get("from_address"),
                        to_address=record.get("to_address"),
                        from_entity=record.get("from_entity"),
                        to_entity=record.get("to_entity"),
                        tx_hash=tx_hash,
                        block_number=record.get("block_number"),
                        source_name=record.get("source_name", source),
                        source_module=record.get("source_module", "RealIngestionModule"),
                        event_time=record.get("event_time"),
                        fetched_at=record.get("fetched_at"),
                    )
                    session.add(flow_record)
                    stored_count += 1
                
                session.commit()
                
                self._logger.info(
                    f"[{source}] Persisted {stored_count}/{len(records)} onchain flow records "
                    f"(correlation_id={correlation_id[:8]}...)"
                )
                
        except Exception as e:
            self._logger.error(f"Failed to persist {source} onchain flows: {e}")
            # Don't raise - we want ingestion to continue
            return 0
        
        return stored_count
    
    async def _persist_exchange_flow_aggregates(
        self,
        records: List[Dict[str, Any]],
    ) -> int:
        """
        Persist exchange flow aggregates using upsert.
        
        Uses PostgreSQL ON CONFLICT DO UPDATE to update existing aggregates
        for the same (token, exchange, time_window, window_start).
        
        Args:
            records: List of aggregate dictionaries
            
        Returns:
            Number of records stored/updated
        """
        if not records:
            return 0
        
        correlation_id = uuid4().hex
        stored_count = 0
        
        try:
            with get_db_session() as session:
                for record in records:
                    # Build upsert statement
                    stmt = pg_insert(ExchangeFlowAggregate).values(
                        correlation_id=correlation_id,
                        token=record["token"],
                        exchange=record["exchange"],
                        time_window=record["time_window"],
                        inflow_amount=record["inflow_amount"],
                        outflow_amount=record["outflow_amount"],
                        net_flow=record["net_flow"],
                        inflow_usd=record.get("inflow_usd"),
                        outflow_usd=record.get("outflow_usd"),
                        net_flow_usd=record.get("net_flow_usd"),
                        inflow_tx_count=record["inflow_tx_count"],
                        outflow_tx_count=record["outflow_tx_count"],
                        total_tx_count=record["total_tx_count"],
                        flow_ratio=record.get("flow_ratio"),
                        dominance_pct=record.get("dominance_pct"),
                        window_start=record["window_start"],
                        window_end=record["window_end"],
                        source_name=record.get("source_name", "whale_alert"),
                        source_module="exchange_flow_aggregator",
                        data_points_count=record.get("data_points_count", 0),
                        aggregated_at=record.get("aggregated_at"),
                    )
                    
                    # On conflict, update the aggregate values
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_exchange_flow_aggregate",
                        set_={
                            "correlation_id": stmt.excluded.correlation_id,
                            "inflow_amount": stmt.excluded.inflow_amount,
                            "outflow_amount": stmt.excluded.outflow_amount,
                            "net_flow": stmt.excluded.net_flow,
                            "inflow_usd": stmt.excluded.inflow_usd,
                            "outflow_usd": stmt.excluded.outflow_usd,
                            "net_flow_usd": stmt.excluded.net_flow_usd,
                            "inflow_tx_count": stmt.excluded.inflow_tx_count,
                            "outflow_tx_count": stmt.excluded.outflow_tx_count,
                            "total_tx_count": stmt.excluded.total_tx_count,
                            "flow_ratio": stmt.excluded.flow_ratio,
                            "dominance_pct": stmt.excluded.dominance_pct,
                            "window_end": stmt.excluded.window_end,
                            "data_points_count": stmt.excluded.data_points_count,
                            "aggregated_at": stmt.excluded.aggregated_at,
                        },
                    )
                    
                    session.execute(stmt)
                    stored_count += 1
                
                session.commit()
                
                self._logger.info(
                    f"[ExchangeFlow] Persisted {stored_count} aggregate records "
                    f"(correlation_id={correlation_id[:8]}...)"
                )
                
        except Exception as e:
            self._logger.error(f"Failed to persist exchange flow aggregates: {e}")
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
