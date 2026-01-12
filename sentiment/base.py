"""
Base Sentiment Source - Abstract interface for all sentiment adapters.

SAFETY: Sentiment data is CONTEXT ONLY - never a trade trigger.
All sources must follow non-blocking, cached, graceful degradation patterns.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Optional

from .exceptions import (
    CacheError,
    FetchError,
    RateLimitError,
    SentimentSourceError,
)
from .models import (
    SentimentData,
    SentimentRequest,
    SourceHealth,
    SourceMetadata,
    SourceStatus,
)


logger = logging.getLogger(__name__)


class BaseSentimentSource(ABC):
    """
    Abstract base class for sentiment data sources.
    
    DESIGN PRINCIPLES:
    1. NEVER block - return empty/cached on failure
    2. ALWAYS cache - respect TTL and stale fallback
    3. NEVER raise - log and return gracefully
    4. RATE LIMIT aware - track and respect limits
    5. CONTEXT ONLY - sentiment is not a trade trigger
    
    All subclasses must implement:
    - _fetch_raw() - Get raw data from source
    - _normalize() - Convert to SentimentData
    - metadata - Source metadata property
    """
    
    # Default configuration
    DEFAULT_CACHE_TTL = 300  # 5 minutes
    DEFAULT_STALE_TTL = 3600  # 1 hour stale fallback
    DEFAULT_TIMEOUT = 10  # 10 seconds
    MAX_RETRIES = 2
    RETRY_DELAY = 1.0
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.api_key = api_key
        self.cache_ttl = cache_ttl or self.DEFAULT_CACHE_TTL
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        
        # Cache storage
        self._cache: dict[str, tuple[list[SentimentData], datetime]] = {}
        self._stale_cache: dict[str, tuple[list[SentimentData], datetime]] = {}
        
        # Health tracking
        self._health = SourceHealth(
            status=SourceStatus.UNKNOWN,
            last_check=datetime.utcnow(),
        )
        
        # Rate limiting
        self._requests_this_minute: list[datetime] = []
        self._requests_today: int = 0
        self._day_start: datetime = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        # Statistics
        self._stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "rate_limits_hit": 0,
            "successful_fetches": 0,
        }
    
    @property
    @abstractmethod
    def metadata(self) -> SourceMetadata:
        """Return source metadata."""
        pass
    
    @abstractmethod
    async def _fetch_raw(
        self,
        request: SentimentRequest,
    ) -> list[dict[str, Any]]:
        """
        Fetch raw sentiment data from the source.
        
        Must be implemented by subclasses.
        Should return raw API response data as list of dicts.
        Should raise appropriate exceptions on failure.
        """
        pass
    
    @abstractmethod
    def _normalize(
        self,
        raw_data: dict[str, Any],
    ) -> Optional[SentimentData]:
        """
        Normalize raw data to SentimentData.
        
        Must be implemented by subclasses.
        Returns None if normalization fails.
        """
        pass
    
    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────
    
    async def fetch_sentiment(
        self,
        request: Optional[SentimentRequest] = None,
    ) -> list[SentimentData]:
        """
        Fetch normalized sentiment data.
        
        NEVER raises - returns empty list on failure.
        Uses cache with stale fallback.
        
        Args:
            request: Request parameters (uses defaults if None)
            
        Returns:
            List of normalized SentimentData objects
        """
        if request is None:
            request = SentimentRequest()
        
        try:
            request.validate()
        except ValueError as e:
            logger.warning(f"[{self.metadata.name}] Invalid request: {e}")
            return []
        
        self._stats["total_requests"] += 1
        cache_key = self._make_cache_key(request)
        
        # Check cache first
        if request.use_cache:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                self._stats["cache_hits"] += 1
                return cached
        
        self._stats["cache_misses"] += 1
        
        # Check rate limits
        if not self._check_rate_limit():
            logger.warning(f"[{self.metadata.name}] Rate limited")
            self._stats["rate_limits_hit"] += 1
            self._health.status = SourceStatus.RATE_LIMITED
            # Return stale cache if available
            return self._get_stale_cache(cache_key) or []
        
        # Fetch with retry
        result = await self._fetch_with_retry(request)
        
        if result:
            self._cache_result(cache_key, result)
            self._stats["successful_fetches"] += 1
            self._health.status = SourceStatus.HEALTHY
            return result
        else:
            # Return stale cache on failure
            stale = self._get_stale_cache(cache_key)
            if stale:
                logger.info(f"[{self.metadata.name}] Using stale cache")
                return stale
            return []
    
    async def get_health(self) -> SourceHealth:
        """Get current health status."""
        self._health.last_check = datetime.utcnow()
        self._health.requests_today = self._requests_today
        self._health.daily_limit = self.metadata.rate_limit_per_day
        return self._health
    
    def get_stats(self) -> dict[str, Any]:
        """Get source statistics."""
        total = self._stats["total_requests"]
        cache_rate = (
            self._stats["cache_hits"] / total * 100
            if total > 0 else 0
        )
        error_rate = (
            self._stats["errors"] / total * 100
            if total > 0 else 0
        )
        
        return {
            **self._stats,
            "cache_hit_rate_pct": round(cache_rate, 2),
            "error_rate_pct": round(error_rate, 2),
            "source_name": self.metadata.name,
        }
    
    async def check_connectivity(self) -> bool:
        """Check if source is reachable."""
        try:
            # Simple test request
            request = SentimentRequest(
                symbols=["BTC"],
                limit=1,
                time_range_hours=1,
                use_cache=False,
            )
            result = await self._fetch_raw(request)
            return bool(result)
        except Exception:
            return False
    
    # ─────────────────────────────────────────────────────────────
    # Internal methods
    # ─────────────────────────────────────────────────────────────
    
    async def _fetch_with_retry(
        self,
        request: SentimentRequest,
    ) -> list[SentimentData]:
        """Fetch with retry logic."""
        last_error: Optional[Exception] = None
        start_time = datetime.utcnow()
        
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # Track rate limit
                self._record_request()
                
                # Fetch raw data
                raw_data = await self._fetch_raw(request)
                
                if not raw_data:
                    return []
                
                # Normalize all items
                results: list[SentimentData] = []
                for item in raw_data:
                    normalized = self._normalize(item)
                    if normalized:
                        results.append(normalized)
                
                # Update health
                latency = (datetime.utcnow() - start_time).total_seconds() * 1000
                self._health.latency_ms = latency
                self._health.status = SourceStatus.HEALTHY
                self._health.consecutive_failures = 0
                
                return results
                
            except RateLimitError as e:
                logger.warning(f"[{self.metadata.name}] Rate limit hit: {e}")
                self._health.status = SourceStatus.RATE_LIMITED
                self._stats["rate_limits_hit"] += 1
                return []  # Don't retry rate limits
                
            except FetchError as e:
                last_error = e
                logger.warning(
                    f"[{self.metadata.name}] Fetch error (attempt {attempt + 1}): {e}"
                )
                
            except SentimentSourceError as e:
                last_error = e
                logger.warning(
                    f"[{self.metadata.name}] Source error (attempt {attempt + 1}): {e}"
                )
                
            except Exception as e:
                last_error = e
                logger.error(
                    f"[{self.metadata.name}] Unexpected error (attempt {attempt + 1}): {e}"
                )
            
            # Wait before retry
            if attempt < self.MAX_RETRIES:
                await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
        
        # All retries failed
        self._stats["errors"] += 1
        self._health.consecutive_failures += 1
        self._health.error_count += 1
        self._health.last_error = str(last_error)
        self._health.last_error_time = datetime.utcnow()
        
        if self._health.consecutive_failures >= 3:
            self._health.status = SourceStatus.UNAVAILABLE
        else:
            self._health.status = SourceStatus.DEGRADED
        
        return []
    
    def _make_cache_key(self, request: SentimentRequest) -> str:
        """Generate cache key from request."""
        symbols = ",".join(sorted(request.symbols))
        events = ""
        if request.filter_events:
            events = ",".join(sorted(e.value for e in request.filter_events))
        
        return (
            f"{self.metadata.name}:"
            f"{symbols}:"
            f"{request.time_range_hours}:"
            f"{request.limit}:"
            f"{events}:"
            f"{request.min_importance}"
        )
    
    def _get_from_cache(
        self,
        cache_key: str,
    ) -> Optional[list[SentimentData]]:
        """Get data from cache if valid."""
        if cache_key not in self._cache:
            return None
        
        data, timestamp = self._cache[cache_key]
        age = (datetime.utcnow() - timestamp).total_seconds()
        
        if age <= self.cache_ttl:
            # Mark as cached
            return [
                SentimentData(
                    sentiment_score=d.sentiment_score,
                    event_type=d.event_type,
                    source_reliability_weight=d.source_reliability_weight,
                    timestamp=d.timestamp,
                    source_name=d.source_name,
                    title=d.title,
                    summary=d.summary,
                    url=d.url,
                    symbols=d.symbols,
                    primary_symbol=d.primary_symbol,
                    raw_sentiment=d.raw_sentiment,
                    votes_positive=d.votes_positive,
                    votes_negative=d.votes_negative,
                    importance=d.importance,
                    is_verified=d.is_verified,
                    is_breaking=d.is_breaking,
                    requires_confirmation=d.requires_confirmation,
                    cached=True,
                    cache_age_seconds=age,
                )
                for d in data
            ]
        
        return None
    
    def _get_stale_cache(
        self,
        cache_key: str,
    ) -> Optional[list[SentimentData]]:
        """Get stale data as fallback."""
        if cache_key in self._stale_cache:
            data, timestamp = self._stale_cache[cache_key]
            age = (datetime.utcnow() - timestamp).total_seconds()
            if age <= self.DEFAULT_STALE_TTL:
                return [
                    SentimentData(
                        sentiment_score=d.sentiment_score,
                        event_type=d.event_type,
                        source_reliability_weight=d.source_reliability_weight,
                        timestamp=d.timestamp,
                        source_name=d.source_name,
                        title=d.title,
                        summary=d.summary,
                        url=d.url,
                        symbols=d.symbols,
                        primary_symbol=d.primary_symbol,
                        raw_sentiment=d.raw_sentiment,
                        votes_positive=d.votes_positive,
                        votes_negative=d.votes_negative,
                        importance=d.importance,
                        is_verified=d.is_verified,
                        is_breaking=d.is_breaking,
                        requires_confirmation=d.requires_confirmation,
                        cached=True,
                        cache_age_seconds=age,
                    )
                    for d in data
                ]
        return None
    
    def _cache_result(
        self,
        cache_key: str,
        data: list[SentimentData],
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
        
        # Clean main cache
        expired = [
            k for k, (_, ts) in self._cache.items()
            if (now - ts).total_seconds() > self.cache_ttl * 2
        ]
        for k in expired:
            del self._cache[k]
        
        # Clean stale cache
        expired = [
            k for k, (_, ts) in self._stale_cache.items()
            if (now - ts).total_seconds() > self.DEFAULT_STALE_TTL * 2
        ]
        for k in expired:
            del self._stale_cache[k]
    
    def _check_rate_limit(self) -> bool:
        """Check if request is within rate limits."""
        now = datetime.utcnow()
        
        # Reset daily counter if new day
        if now.date() > self._day_start.date():
            self._requests_today = 0
            self._day_start = now.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        
        # Check daily limit
        if self.metadata.rate_limit_per_day:
            if self._requests_today >= self.metadata.rate_limit_per_day:
                return False
        
        # Check per-minute limit
        if self.metadata.rate_limit_per_minute:
            # Clean old requests
            cutoff = now - timedelta(minutes=1)
            self._requests_this_minute = [
                t for t in self._requests_this_minute
                if t > cutoff
            ]
            
            if len(self._requests_this_minute) >= self.metadata.rate_limit_per_minute:
                return False
        
        return True
    
    def _record_request(self) -> None:
        """Record a request for rate limiting."""
        now = datetime.utcnow()
        self._requests_this_minute.append(now)
        self._requests_today += 1
    
    async def close(self) -> None:
        """Cleanup resources. Override if needed."""
        pass
