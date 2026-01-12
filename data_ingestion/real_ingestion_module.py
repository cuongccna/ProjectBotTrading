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
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database.engine import get_session, get_db_session
from database.models import MarketData


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
    
    # Timeouts and retries
    timeout_seconds: float = 30.0
    max_retries: int = 3
    
    # Failure mode: if True, any fetch failure stops ingestion
    fail_fast: bool = True


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
            
            # Calculate totals
            result.total_fetched = result.coingecko_fetched + result.binance_fetched
            result.total_stored = result.coingecko_stored + result.binance_stored
            
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
        if self._config.coingecko_api_key:
            headers["x-cg-pro-api-key"] = self._config.coingecko_api_key
        
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
            raise RuntimeError(
                f"CoinGecko HTTP error {e.response.status_code}: {e.response.text[:200]}"
            ) from e
        except httpx.TimeoutException as e:
            raise RuntimeError(f"CoinGecko timeout: {e}") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"CoinGecko request error: {e}") from e
    
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
            raise RuntimeError(
                f"Binance HTTP error {e.response.status_code}: {e.response.text[:200]}"
            ) from e
        except httpx.TimeoutException as e:
            raise RuntimeError(f"Binance timeout: {e}") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"Binance request error: {e}") from e
    
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
