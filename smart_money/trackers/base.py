"""
Base On-Chain Tracker - Abstract interface for blockchain trackers.

Designed for extensibility - can swap public APIs for premium (Arkham, Nansen)
without changing the interface or downstream consumers.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Optional

from ..config import ChainConfig, SmartMoneyConfig, get_config
from ..models import Chain, TrackerHealth, WalletActivity, WalletInfo


logger = logging.getLogger(__name__)


class BaseOnChainTracker(ABC):
    """
    Abstract base class for on-chain activity trackers.
    
    DESIGN PRINCIPLES:
    1. NEVER block - return empty/cached on failure
    2. RATE LIMIT aware - respect API limits
    3. CACHE aggressively - minimize API calls
    4. PREMIUM READY - interface supports swap to paid APIs
    
    All subclasses must implement:
    - _fetch_transactions() - Get raw transactions
    - _fetch_token_transfers() - Get token transfers
    - chain - Property returning the chain
    """
    
    # Default settings
    DEFAULT_CACHE_TTL = 300  # 5 minutes
    DEFAULT_TIMEOUT = 15  # seconds
    MAX_RETRIES = 2
    
    def __init__(
        self,
        config: Optional[SmartMoneyConfig] = None,
        chain_config: Optional[ChainConfig] = None,
    ) -> None:
        self.config = config or get_config()
        self.chain_config = chain_config
        
        # Rate limiting
        self._requests_this_minute: list[datetime] = []
        self._requests_today: int = 0
        self._day_start: datetime = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        # Cache
        self._cache: dict[str, tuple[list[WalletActivity], datetime]] = {}
        self._stale_cache: dict[str, tuple[list[WalletActivity], datetime]] = {}
        
        # Health tracking
        self._health = TrackerHealth(
            chain=self.chain,
            is_healthy=True,
            last_check=datetime.utcnow(),
        )
        
        # Statistics
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "cache_hits": 0,
            "rate_limits_hit": 0,
            "errors": 0,
        }
    
    @property
    @abstractmethod
    def chain(self) -> Chain:
        """Return the chain this tracker handles."""
        pass
    
    @abstractmethod
    async def _fetch_transactions(
        self,
        address: str,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch raw transactions for an address.
        
        Must be implemented by subclasses.
        Returns raw API response data.
        """
        pass
    
    @abstractmethod
    async def _fetch_token_transfers(
        self,
        address: str,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch token transfers for an address.
        
        Must be implemented by subclasses.
        Returns raw API response data.
        """
        pass
    
    @abstractmethod
    def _parse_transaction(
        self,
        raw: dict[str, Any],
        wallet_address: str,
    ) -> Optional[WalletActivity]:
        """
        Parse raw transaction data into WalletActivity.
        
        Returns None if parsing fails.
        """
        pass
    
    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────
    
    async def get_activity(
        self,
        wallet: WalletInfo,
        hours: int = 24,
        use_cache: bool = True,
    ) -> list[WalletActivity]:
        """
        Get recent activity for a wallet.
        
        NEVER raises - returns empty list on failure.
        Uses cache with stale fallback.
        
        Args:
            wallet: Wallet to track
            hours: Lookback period in hours
            use_cache: Whether to use cache
            
        Returns:
            List of WalletActivity records
        """
        if wallet.chain != self.chain:
            logger.warning(f"Chain mismatch: {wallet.chain} != {self.chain}")
            return []
        
        self._stats["total_requests"] += 1
        cache_key = self._make_cache_key(wallet.address, hours)
        
        # Check cache
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                self._stats["cache_hits"] += 1
                return cached
        
        # Check rate limit
        if not self._check_rate_limit():
            logger.warning(f"[{self.chain.value}] Rate limited")
            self._stats["rate_limits_hit"] += 1
            self._health.is_healthy = False
            return self._get_stale_cache(cache_key) or []
        
        # Fetch with retry
        activities = await self._fetch_with_retry(wallet.address, hours)
        
        if activities:
            self._cache_result(cache_key, activities)
            self._stats["successful_requests"] += 1
            self._health.is_healthy = True
        
        return activities
    
    async def get_large_transfers(
        self,
        wallet: WalletInfo,
        hours: int = 24,
        threshold_usd: float = 100_000,
    ) -> list[WalletActivity]:
        """Get large transfers above threshold."""
        activities = await self.get_activity(wallet, hours)
        return [a for a in activities if a.value_usd >= threshold_usd]
    
    async def check_health(self) -> TrackerHealth:
        """Check tracker health."""
        self._health.last_check = datetime.utcnow()
        return self._health
    
    def get_stats(self) -> dict[str, Any]:
        """Get tracker statistics."""
        return {
            **self._stats,
            "chain": self.chain.value,
            "requests_today": self._requests_today,
            "cache_size": len(self._cache),
        }
    
    # ─────────────────────────────────────────────────────────────
    # Internal methods
    # ─────────────────────────────────────────────────────────────
    
    async def _fetch_with_retry(
        self,
        address: str,
        hours: int,
    ) -> list[WalletActivity]:
        """Fetch with retry logic."""
        activities: list[WalletActivity] = []
        
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                self._record_request()
                
                # Fetch transactions
                raw_txs = await self._fetch_transactions(address, limit=100)
                
                # Fetch token transfers
                raw_transfers = await self._fetch_token_transfers(address, limit=100)
                
                # Parse all
                cutoff = datetime.utcnow() - timedelta(hours=hours)
                
                for raw in raw_txs:
                    activity = self._parse_transaction(raw, address)
                    if activity and activity.timestamp >= cutoff:
                        activities.append(activity)
                
                for raw in raw_transfers:
                    activity = self._parse_transaction(raw, address)
                    if activity and activity.timestamp >= cutoff:
                        activities.append(activity)
                
                # Update health
                self._health.is_healthy = True
                self._health.error_count = 0
                
                return activities
                
            except Exception as e:
                logger.warning(
                    f"[{self.chain.value}] Fetch error (attempt {attempt + 1}): {e}"
                )
                self._stats["errors"] += 1
                
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(1 * (attempt + 1))
        
        # All retries failed
        self._health.is_healthy = False
        self._health.error_count += 1
        self._health.last_error = "Fetch failed after retries"
        
        return []
    
    def _make_cache_key(self, address: str, hours: int) -> str:
        """Generate cache key."""
        return f"{self.chain.value}:{address.lower()}:{hours}"
    
    def _get_from_cache(
        self,
        cache_key: str,
    ) -> Optional[list[WalletActivity]]:
        """Get from cache if valid."""
        if cache_key not in self._cache:
            return None
        
        data, timestamp = self._cache[cache_key]
        age = (datetime.utcnow() - timestamp).total_seconds()
        
        if age <= self.DEFAULT_CACHE_TTL:
            return data
        
        return None
    
    def _get_stale_cache(
        self,
        cache_key: str,
    ) -> Optional[list[WalletActivity]]:
        """Get stale cache as fallback."""
        if cache_key in self._stale_cache:
            data, timestamp = self._stale_cache[cache_key]
            age = (datetime.utcnow() - timestamp).total_seconds()
            if age <= 3600:  # 1 hour stale limit
                return data
        return None
    
    def _cache_result(
        self,
        cache_key: str,
        data: list[WalletActivity],
    ) -> None:
        """Cache the result."""
        now = datetime.utcnow()
        self._cache[cache_key] = (data, now)
        self._stale_cache[cache_key] = (data, now)
        
        # Cleanup old entries
        self._cleanup_cache()
    
    def _cleanup_cache(self) -> None:
        """Remove expired cache entries."""
        now = datetime.utcnow()
        
        expired = [
            k for k, (_, ts) in self._cache.items()
            if (now - ts).total_seconds() > self.DEFAULT_CACHE_TTL * 2
        ]
        for k in expired:
            del self._cache[k]
    
    def _check_rate_limit(self) -> bool:
        """Check if request is within rate limits."""
        if not self.chain_config:
            return True
        
        now = datetime.utcnow()
        
        # Reset daily counter
        if now.date() > self._day_start.date():
            self._requests_today = 0
            self._day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Check daily limit
        if self._requests_today >= self.chain_config.requests_per_day:
            return False
        
        # Check per-second limit
        cutoff = now - timedelta(seconds=1)
        recent = [t for t in self._requests_this_minute if t > cutoff]
        
        if len(recent) >= self.chain_config.requests_per_second:
            return False
        
        return True
    
    def _record_request(self) -> None:
        """Record a request for rate limiting."""
        now = datetime.utcnow()
        self._requests_this_minute.append(now)
        self._requests_today += 1
        
        # Cleanup old entries
        cutoff = now - timedelta(minutes=1)
        self._requests_this_minute = [
            t for t in self._requests_this_minute if t > cutoff
        ]
    
    async def close(self) -> None:
        """Cleanup resources. Override if needed."""
        pass
