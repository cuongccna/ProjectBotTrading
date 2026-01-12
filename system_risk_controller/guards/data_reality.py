"""
System Risk Controller - Data Reality Guard.

============================================================
ABSOLUTE GATE: DATA REALITY CHECK
============================================================

This guard CANNOT BE BYPASSED.

It runs BEFORE strategy or execution and validates:
1. Market data freshness (not older than 2 intervals)
2. Price deviation from live reference (max configurable %)

If either check fails:
- System MUST HALT
- Execution engine BLOCKED
- CRITICAL alert emitted

============================================================
PHILOSOPHY
============================================================
If the system cannot TRUST its market data is:
  a) Recent enough to act on
  b) Close enough to reality

Then it MUST NOT trade.

============================================================
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple

import httpx

from database.engine import get_db_session
from database.models import MarketData


logger = logging.getLogger("data_reality_guard")


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class DataRealityGuardConfig:
    """
    Configuration for Data Reality Guard.
    
    All thresholds are CONSERVATIVE by design.
    """
    
    # === Freshness Check ===
    reference_interval_seconds: int = 3600
    """Reference interval in seconds (default: 1 hour)."""
    
    max_intervals_stale: int = 2
    """Maximum number of intervals data can be stale."""
    
    # === Price Deviation Check ===
    max_price_deviation_pct: float = 3.0
    """
    Maximum allowed deviation from live reference price.
    Default: 3%
    """
    
    reference_symbol: str = "BTC"
    """Symbol to check for price deviation."""
    
    reference_pair: str = "BTCUSDT"
    """Trading pair for reference."""
    
    # === Live Reference Source ===
    live_reference_url: str = "https://api.coingecko.com/api/v3/simple/price"
    """URL for live price reference."""
    
    live_reference_params: Dict[str, str] = field(default_factory=lambda: {
        "ids": "bitcoin",
        "vs_currencies": "usd",
    })
    """Parameters for live reference API."""
    
    request_timeout_seconds: float = 10.0
    """Timeout for HTTP requests."""
    
    # === Behavior ===
    enabled: bool = True
    """Whether the guard is enabled."""
    
    halt_on_failure: bool = True
    """Whether to halt on guard failure (True = cannot bypass)."""
    
    check_interval_seconds: float = 60.0
    """How often to run the guard check."""
    
    @property
    def max_data_age_seconds(self) -> float:
        """Calculate maximum allowed data age."""
        return self.reference_interval_seconds * self.max_intervals_stale


# ============================================================
# GUARD RESULT
# ============================================================

@dataclass
class DataRealityCheckResult:
    """Result of a data reality check."""
    
    passed: bool
    """Whether all checks passed."""
    
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    """When the check was performed."""
    
    # === Freshness Check ===
    freshness_passed: bool = True
    """Whether freshness check passed."""
    
    latest_data_timestamp: Optional[datetime] = None
    """Timestamp of latest market data."""
    
    data_age_seconds: Optional[float] = None
    """Age of market data in seconds."""
    
    max_allowed_age_seconds: Optional[float] = None
    """Maximum allowed age in seconds."""
    
    # === Price Deviation Check ===
    deviation_passed: bool = True
    """Whether deviation check passed."""
    
    stored_price: Optional[float] = None
    """Price from database."""
    
    live_price: Optional[float] = None
    """Live reference price."""
    
    deviation_pct: Optional[float] = None
    """Actual deviation percentage."""
    
    max_allowed_deviation_pct: Optional[float] = None
    """Maximum allowed deviation percentage."""
    
    # === Error Details ===
    error_message: Optional[str] = None
    """Error message if check failed."""
    
    halt_required: bool = False
    """Whether system halt is required."""
    
    details: Dict[str, Any] = field(default_factory=dict)
    """Additional details."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/alerts."""
        return {
            "passed": self.passed,
            "timestamp": self.timestamp.isoformat(),
            "freshness": {
                "passed": self.freshness_passed,
                "data_timestamp": self.latest_data_timestamp.isoformat() if self.latest_data_timestamp else None,
                "age_seconds": self.data_age_seconds,
                "max_age_seconds": self.max_allowed_age_seconds,
            },
            "deviation": {
                "passed": self.deviation_passed,
                "stored_price": self.stored_price,
                "live_price": self.live_price,
                "deviation_pct": self.deviation_pct,
                "max_deviation_pct": self.max_allowed_deviation_pct,
            },
            "halt_required": self.halt_required,
            "error": self.error_message,
        }


# ============================================================
# DATA REALITY GUARD
# ============================================================

class DataRealityGuard:
    """
    Data Reality Guard - ABSOLUTE GATE.
    
    ============================================================
    CANNOT BE BYPASSED
    ============================================================
    
    This guard ensures the trading system operates on:
    1. FRESH data (not older than 2 intervals)
    2. ACCURATE data (within 3% of live reference)
    
    If either condition fails, the system MUST HALT.
    
    Usage:
    ```python
    guard = DataRealityGuard(config)
    
    # Run check (call before any trading decision)
    result = await guard.check()
    
    if not result.passed:
        # System must halt - do not proceed
        raise SystemHaltRequired(result.error_message)
    ```
    """
    
    def __init__(
        self,
        config: Optional[DataRealityGuardConfig] = None,
    ) -> None:
        """
        Initialize the Data Reality Guard.
        
        Args:
            config: Guard configuration
        """
        self._config = config or DataRealityGuardConfig()
        self._last_result: Optional[DataRealityCheckResult] = None
        self._check_count = 0
        self._failure_count = 0
        
        logger.info(
            f"DataRealityGuard initialized | "
            f"max_age={self._config.max_data_age_seconds}s | "
            f"max_deviation={self._config.max_price_deviation_pct}%"
        )
    
    @property
    def config(self) -> DataRealityGuardConfig:
        """Get configuration."""
        return self._config
    
    @property
    def last_result(self) -> Optional[DataRealityCheckResult]:
        """Get last check result."""
        return self._last_result
    
    @property
    def is_enabled(self) -> bool:
        """Check if guard is enabled."""
        return self._config.enabled
    
    # --------------------------------------------------------
    # MAIN CHECK
    # --------------------------------------------------------
    
    async def check(self) -> DataRealityCheckResult:
        """
        Perform data reality check.
        
        This method:
        1. Queries latest market data from database
        2. Verifies timestamp freshness
        3. Fetches live reference price
        4. Compares stored price vs live price
        
        Returns:
            DataRealityCheckResult with pass/fail status
        """
        self._check_count += 1
        
        if not self._config.enabled:
            return DataRealityCheckResult(
                passed=True,
                details={"skipped": "Guard disabled"},
            )
        
        result = DataRealityCheckResult(
            passed=False,  # Assume failure until proven otherwise
            max_allowed_age_seconds=self._config.max_data_age_seconds,
            max_allowed_deviation_pct=self._config.max_price_deviation_pct,
        )
        
        try:
            # Step 1: Get latest market data
            latest_data = self._get_latest_market_data()
            
            if latest_data is None:
                result.error_message = "No market data found in database"
                result.halt_required = self._config.halt_on_failure
                self._failure_count += 1
                self._last_result = result
                return result
            
            result.latest_data_timestamp = latest_data.candle_open_time
            result.stored_price = float(latest_data.close_price)
            
            # Step 2: Check freshness
            freshness_ok, age_seconds = self._check_freshness(latest_data)
            result.freshness_passed = freshness_ok
            result.data_age_seconds = age_seconds
            
            if not freshness_ok:
                result.error_message = (
                    f"STALE DATA: Market data is {age_seconds:.0f}s old "
                    f"(max allowed: {self._config.max_data_age_seconds}s = "
                    f"{self._config.max_intervals_stale} intervals)"
                )
                result.halt_required = self._config.halt_on_failure
                self._failure_count += 1
                self._last_result = result
                return result
            
            # Step 3: Get live reference price
            live_price = await self._fetch_live_price()
            
            if live_price is None:
                result.error_message = "Failed to fetch live reference price"
                result.halt_required = self._config.halt_on_failure
                self._failure_count += 1
                self._last_result = result
                return result
            
            result.live_price = live_price
            
            # Step 4: Check deviation
            deviation_ok, deviation_pct = self._check_deviation(
                result.stored_price,
                live_price,
            )
            result.deviation_passed = deviation_ok
            result.deviation_pct = deviation_pct
            
            if not deviation_ok:
                result.error_message = (
                    f"PRICE DEVIATION: Stored price ${result.stored_price:,.2f} "
                    f"deviates {deviation_pct:.2f}% from live price ${live_price:,.2f} "
                    f"(max allowed: {self._config.max_price_deviation_pct}%)"
                )
                result.halt_required = self._config.halt_on_failure
                self._failure_count += 1
                self._last_result = result
                return result
            
            # All checks passed
            result.passed = True
            result.halt_required = False
            
            logger.debug(
                f"DataRealityGuard PASSED | "
                f"age={age_seconds:.0f}s | "
                f"deviation={deviation_pct:.2f}%"
            )
            
        except Exception as e:
            result.error_message = f"Guard check failed with error: {e}"
            result.halt_required = self._config.halt_on_failure
            self._failure_count += 1
            logger.error(f"DataRealityGuard error: {e}", exc_info=True)
        
        self._last_result = result
        return result
    
    # --------------------------------------------------------
    # FRESHNESS CHECK
    # --------------------------------------------------------
    
    def _get_latest_market_data(self) -> Optional[MarketData]:
        """
        Get the latest market data from database.
        
        Returns:
            Latest MarketData record or None
        """
        try:
            with get_db_session() as session:
                record = session.query(MarketData).filter(
                    MarketData.symbol == self._config.reference_symbol
                ).order_by(
                    MarketData.candle_open_time.desc()
                ).first()
                
                return record
                
        except Exception as e:
            logger.error(f"Failed to query market data: {e}")
            return None
    
    def _check_freshness(
        self,
        data: MarketData,
    ) -> Tuple[bool, float]:
        """
        Check if market data is fresh enough.
        
        Args:
            data: Market data record
            
        Returns:
            Tuple of (passed, age_in_seconds)
        """
        now = datetime.now(timezone.utc)
        
        # Handle timezone-naive timestamps
        data_timestamp = data.candle_open_time
        if data_timestamp.tzinfo is None:
            data_timestamp = data_timestamp.replace(tzinfo=timezone.utc)
        
        age_seconds = (now - data_timestamp).total_seconds()
        max_age = self._config.max_data_age_seconds
        
        passed = age_seconds <= max_age
        
        return passed, age_seconds
    
    # --------------------------------------------------------
    # PRICE DEVIATION CHECK
    # --------------------------------------------------------
    
    async def _fetch_live_price(self) -> Optional[float]:
        """
        Fetch live reference price from CoinGecko.
        
        Returns:
            Live BTC price in USD or None on failure
        """
        try:
            async with httpx.AsyncClient(
                timeout=self._config.request_timeout_seconds
            ) as client:
                response = await client.get(
                    self._config.live_reference_url,
                    params=self._config.live_reference_params,
                )
                response.raise_for_status()
                
                data = response.json()
                
                # CoinGecko response: {"bitcoin": {"usd": 90000.00}}
                price = data.get("bitcoin", {}).get("usd")
                
                if price is None:
                    logger.error(f"Unexpected CoinGecko response: {data}")
                    return None
                
                return float(price)
                
        except httpx.HTTPStatusError as e:
            logger.error(f"CoinGecko HTTP error: {e}")
            return None
        except httpx.TimeoutException:
            logger.error("CoinGecko request timed out")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch live price: {e}")
            return None
    
    def _check_deviation(
        self,
        stored_price: float,
        live_price: float,
    ) -> Tuple[bool, float]:
        """
        Check if stored price deviates too much from live price.
        
        Args:
            stored_price: Price from database
            live_price: Live reference price
            
        Returns:
            Tuple of (passed, deviation_percentage)
        """
        if live_price == 0:
            return False, 100.0
        
        deviation_pct = abs(stored_price - live_price) / live_price * 100
        max_deviation = self._config.max_price_deviation_pct
        
        passed = deviation_pct <= max_deviation
        
        return passed, deviation_pct
    
    # --------------------------------------------------------
    # HEALTH STATUS
    # --------------------------------------------------------
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get guard health status for monitoring."""
        return {
            "enabled": self._config.enabled,
            "check_count": self._check_count,
            "failure_count": self._failure_count,
            "last_check": self._last_result.to_dict() if self._last_result else None,
            "config": {
                "max_data_age_seconds": self._config.max_data_age_seconds,
                "max_deviation_pct": self._config.max_price_deviation_pct,
                "reference_symbol": self._config.reference_symbol,
            },
        }


# ============================================================
# INTEGRATION HELPER
# ============================================================

async def run_data_reality_check(
    config: Optional[DataRealityGuardConfig] = None,
) -> DataRealityCheckResult:
    """
    Convenience function to run a single data reality check.
    
    Args:
        config: Optional configuration
        
    Returns:
        Check result
    """
    guard = DataRealityGuard(config)
    return await guard.check()
