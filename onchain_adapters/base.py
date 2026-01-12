"""
Base On-chain Data Adapter - Abstract interface for all on-chain data providers.

All adapters MUST:
- Handle API limits gracefully
- Cache aggressively
- Never block system execution
- Only provide signal context (NOT execution decisions)
"""

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Optional

import aiohttp

from onchain_adapters.exceptions import (
    CacheError,
    FetchError,
    NormalizationError,
    OnchainAdapterError,
    RateLimitError,
)
from onchain_adapters.models import (
    AdapterHealth,
    AdapterIncident,
    AdapterMetadata,
    AdapterStatus,
    CacheEntry,
    Chain,
    MetricsRequest,
    OnchainMetrics,
)


logger = logging.getLogger(__name__)


class BaseOnchainAdapter(ABC):
    """
    Abstract base class for all on-chain data adapters.
    
    Each adapter must:
    1. Implement fetch_raw() - Get raw data from provider
    2. Implement normalize() - Convert to OnchainMetrics
    3. Implement health_check() - Verify connectivity
    4. Implement metadata() - Return adapter metadata
    
    Features:
    - Aggressive caching with configurable TTL
    - Rate limiting with backoff
    - Non-blocking async operations
    - Graceful degradation
    """
    
    # Configuration defaults
    DEFAULT_TIMEOUT = 30.0
    DEFAULT_CACHE_TTL = 300  # 5 minutes
    MAX_RETRIES = 2  # Fewer retries - don't block
    RETRY_BACKOFF_BASE = 1.5  # Faster backoff
    DEGRADED_THRESHOLD = 3
    UNAVAILABLE_THRESHOLD = 5
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._cache_ttl = cache_ttl
        self._session = session
        self._owns_session = session is None
        
        # Cache storage
        self._cache: dict[str, CacheEntry] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        
        # Rate limiting
        self._request_timestamps: list[float] = []
        self._requests_today = 0
        self._last_request_date: Optional[datetime] = None
        
        # Health tracking
        self._health = AdapterHealth(
            status=AdapterStatus.UNKNOWN,
            last_check=datetime.utcnow(),
        )
        self._last_successful_request: Optional[datetime] = None
        
        # Incident log
        self._incidents: list[AdapterIncident] = []
        self._max_incidents = 100
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this adapter."""
        pass
    
    @abstractmethod
    async def fetch_raw(
        self,
        request: MetricsRequest,
    ) -> dict[str, Any]:
        """
        Fetch raw data from the provider API.
        
        Args:
            request: Metrics request parameters
            
        Returns:
            Raw data dictionary from provider
            
        Raises:
            FetchError: If fetch fails
        """
        pass
    
    @abstractmethod
    def normalize(
        self,
        raw_data: dict[str, Any],
        request: MetricsRequest,
    ) -> OnchainMetrics:
        """
        Normalize raw provider data to standard format.
        
        Args:
            raw_data: Raw data from fetch_raw()
            request: Original request
            
        Returns:
            OnchainMetrics object
            
        Raises:
            NormalizationError: If normalization fails
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> AdapterHealth:
        """
        Check provider connectivity and health.
        
        Returns:
            AdapterHealth object with current status
        """
        pass
    
    @abstractmethod
    def metadata(self) -> AdapterMetadata:
        """
        Return adapter metadata.
        
        Returns:
            AdapterMetadata with provider information
        """
        pass
    
    async def fetch(
        self,
        request: MetricsRequest,
        force_refresh: bool = False,
    ) -> Optional[OnchainMetrics]:
        """
        Fetch on-chain metrics (main entry point).
        
        This method:
        1. Checks cache first (if enabled)
        2. Fetches from provider if cache miss
        3. Normalizes and caches result
        4. NEVER blocks or raises - returns None on failure
        
        Args:
            request: Metrics request
            force_refresh: Bypass cache
            
        Returns:
            OnchainMetrics or None if unavailable
        """
        try:
            request.validate()
            
            # Check cache first
            if request.use_cache and not force_refresh:
                cached = self._get_from_cache(request)
                if cached:
                    self._cache_hits += 1
                    logger.debug(f"[{self.name}] Cache hit for {request.chain.value}")
                    return cached
                self._cache_misses += 1
            
            # Check rate limits
            if not self._check_rate_limit():
                logger.warning(f"[{self.name}] Rate limited, using stale cache")
                return self._get_stale_from_cache(request)
            
            # Fetch with timeout
            try:
                raw_data = await asyncio.wait_for(
                    self._fetch_with_retry(request),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(f"[{self.name}] Fetch timeout for {request.chain.value}")
                self._on_error(
                    FetchError("Timeout", self.name, request.chain.value),
                    request,
                )
                return self._get_stale_from_cache(request)
            
            if not raw_data:
                logger.warning(f"[{self.name}] Empty response for {request.chain.value}")
                return self._get_stale_from_cache(request)
            
            # Normalize
            metrics = self.normalize(raw_data, request)
            
            # Cache result
            self._put_in_cache(request, metrics)
            
            # Track success
            self._on_success()
            
            return metrics
            
        except OnchainAdapterError as e:
            self._on_error(e, request)
            return self._get_stale_from_cache(request)
        except Exception as e:
            error = OnchainAdapterError(
                message=f"Unexpected error: {e}",
                adapter_name=self.name,
                original_error=e,
            )
            self._on_error(error, request)
            return self._get_stale_from_cache(request)
    
    async def _fetch_with_retry(
        self,
        request: MetricsRequest,
    ) -> dict[str, Any]:
        """Fetch with limited retries."""
        last_error: Optional[Exception] = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                self._record_request()
                return await self.fetch_raw(request)
                
            except RateLimitError as e:
                # Don't retry on rate limit - return immediately
                self._health.status = AdapterStatus.RATE_LIMITED
                self._health.rate_limit_remaining = 0
                if e.retry_after_seconds:
                    self._health.rate_limit_reset = datetime.utcnow() + timedelta(
                        seconds=e.retry_after_seconds
                    )
                raise
                
            except FetchError as e:
                if e.status_code and 400 <= e.status_code < 500:
                    # Don't retry client errors
                    raise
                
                wait_time = self.RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    f"[{self.name}] Retry {attempt + 1}/{self.MAX_RETRIES} "
                    f"in {wait_time:.1f}s: {e}"
                )
                await asyncio.sleep(wait_time)
                last_error = e
                
            except Exception as e:
                wait_time = self.RETRY_BACKOFF_BASE ** attempt
                await asyncio.sleep(wait_time)
                last_error = e
        
        raise FetchError(
            message=f"Failed after {self.MAX_RETRIES} retries",
            adapter_name=self.name,
            original_error=last_error,
        )
    
    # ─────────────────────────────────────────────────────────────
    # Cache Management
    # ─────────────────────────────────────────────────────────────
    
    def _cache_key(self, request: MetricsRequest) -> str:
        """Generate cache key from request."""
        key_parts = [
            self.name,
            request.chain.value,
            str(request.token_address or ""),
            str(request.time_range_hours),
            ",".join(sorted(m.value for m in request.metrics)),
        ]
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_from_cache(self, request: MetricsRequest) -> Optional[OnchainMetrics]:
        """Get from cache if valid."""
        key = self._cache_key(request)
        entry = self._cache.get(key)
        
        if entry is None:
            return None
        
        if entry.is_expired():
            # Check max age preference
            age = entry.age_seconds()
            if age > request.max_cache_age_seconds:
                return None
        
        entry.hits += 1
        
        # Return with cache metadata
        return OnchainMetrics(
            chain=entry.data.chain,
            timestamp=entry.data.timestamp,
            tx_count=entry.data.tx_count,
            active_addresses=entry.data.active_addresses,
            gas_used=entry.data.gas_used,
            net_flow=entry.data.net_flow,
            whale_activity_score=entry.data.whale_activity_score,
            avg_gas_price_gwei=entry.data.avg_gas_price_gwei,
            pending_tx_count=entry.data.pending_tx_count,
            block_number=entry.data.block_number,
            avg_block_time=entry.data.avg_block_time,
            token_address=entry.data.token_address,
            token_symbol=entry.data.token_symbol,
            token_transfers=entry.data.token_transfers,
            unique_holders=entry.data.unique_holders,
            source_name=entry.data.source_name,
            cached=True,
            cache_age_seconds=entry.age_seconds(),
        )
    
    def _get_stale_from_cache(self, request: MetricsRequest) -> Optional[OnchainMetrics]:
        """Get stale data from cache as fallback."""
        key = self._cache_key(request)
        entry = self._cache.get(key)
        
        if entry is None:
            return None
        
        # Return stale data with warning
        logger.warning(
            f"[{self.name}] Using stale cache data "
            f"(age={entry.age_seconds():.1f}s)"
        )
        
        return OnchainMetrics(
            chain=entry.data.chain,
            timestamp=entry.data.timestamp,
            tx_count=entry.data.tx_count,
            active_addresses=entry.data.active_addresses,
            gas_used=entry.data.gas_used,
            net_flow=entry.data.net_flow,
            whale_activity_score=entry.data.whale_activity_score,
            avg_gas_price_gwei=entry.data.avg_gas_price_gwei,
            pending_tx_count=entry.data.pending_tx_count,
            block_number=entry.data.block_number,
            avg_block_time=entry.data.avg_block_time,
            token_address=entry.data.token_address,
            token_symbol=entry.data.token_symbol,
            token_transfers=entry.data.token_transfers,
            unique_holders=entry.data.unique_holders,
            source_name=entry.data.source_name,
            cached=True,
            cache_age_seconds=entry.age_seconds(),
        )
    
    def _put_in_cache(self, request: MetricsRequest, data: OnchainMetrics) -> None:
        """Store in cache."""
        key = self._cache_key(request)
        now = datetime.utcnow()
        
        self._cache[key] = CacheEntry(
            data=data,
            created_at=now,
            expires_at=now + timedelta(seconds=self._cache_ttl),
        )
        
        # Clean old entries periodically
        if len(self._cache) > 1000:
            self._clean_cache()
    
    def _clean_cache(self) -> None:
        """Remove expired cache entries."""
        now = datetime.utcnow()
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired() and entry.age_seconds() > 3600  # Keep for 1 hour
        ]
        for key in expired_keys:
            del self._cache[key]
        
        logger.debug(f"[{self.name}] Cleaned {len(expired_keys)} expired cache entries")
    
    def clear_cache(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        logger.info(f"[{self.name}] Cache cleared")
    
    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "entries": len(self._cache),
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate_percent": round(hit_rate, 2),
        }
    
    # ─────────────────────────────────────────────────────────────
    # Rate Limiting
    # ─────────────────────────────────────────────────────────────
    
    def _check_rate_limit(self) -> bool:
        """Check if we can make a request."""
        meta = self.metadata()
        now = time.time()
        
        # Check per-second limit
        if meta.rate_limit_per_second:
            recent = [t for t in self._request_timestamps if now - t < 1.0]
            if len(recent) >= meta.rate_limit_per_second:
                return False
        
        # Check daily limit
        if meta.rate_limit_per_day:
            today = datetime.utcnow().date()
            if self._last_request_date != today:
                self._requests_today = 0
                self._last_request_date = today
            
            if self._requests_today >= meta.rate_limit_per_day:
                return False
        
        return True
    
    def _record_request(self) -> None:
        """Record a request for rate limiting."""
        now = time.time()
        self._request_timestamps.append(now)
        
        # Keep only last 100 timestamps
        if len(self._request_timestamps) > 100:
            self._request_timestamps = self._request_timestamps[-100:]
        
        # Increment daily counter
        self._requests_today += 1
        self._health.requests_today = self._requests_today
    
    # ─────────────────────────────────────────────────────────────
    # HTTP Helpers
    # ─────────────────────────────────────────────────────────────
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout),
                headers=self._get_default_headers(),
            )
            self._owns_session = True
        return self._session
    
    def _get_default_headers(self) -> dict[str, str]:
        """Get default HTTP headers."""
        return {
            "Accept": "application/json",
            "User-Agent": "InstitutionalTradingSystem/1.0",
        }
    
    async def _make_request(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Make HTTP request with error handling."""
        session = await self._get_session()
        
        start_time = time.time()
        try:
            async with session.request(
                method,
                url,
                params=params,
                headers=headers,
            ) as response:
                latency_ms = (time.time() - start_time) * 1000
                self._health.latency_ms = latency_ms
                
                # Check rate limit headers
                self._parse_rate_limit_headers(response.headers)
                
                if response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    raise RateLimitError(
                        message="Rate limit exceeded",
                        adapter_name=self.name,
                        retry_after_seconds=int(retry_after) if retry_after else 60,
                    )
                
                if response.status >= 400:
                    body = await response.text()
                    raise FetchError(
                        message=f"HTTP {response.status}",
                        adapter_name=self.name,
                        status_code=response.status,
                        response_body=body[:500],
                        request_url=url,
                    )
                
                return await response.json()
                
        except aiohttp.ClientError as e:
            raise FetchError(
                message=f"Connection error: {e}",
                adapter_name=self.name,
                request_url=url,
                original_error=e,
            )
    
    def _parse_rate_limit_headers(self, headers: dict) -> None:
        """Parse rate limit info from response headers."""
        # Common header names
        remaining = headers.get("X-RateLimit-Remaining") or headers.get("X-Rate-Limit-Remaining")
        if remaining:
            try:
                self._health.rate_limit_remaining = int(remaining)
            except ValueError:
                pass
    
    # ─────────────────────────────────────────────────────────────
    # Health & Error Tracking
    # ─────────────────────────────────────────────────────────────
    
    def _on_success(self) -> None:
        """Handle successful request."""
        self._last_successful_request = datetime.utcnow()
        self._health.consecutive_failures = 0
        
        if self._health.status != AdapterStatus.HEALTHY:
            self._health.status = AdapterStatus.HEALTHY
            logger.info(f"[{self.name}] Recovered to HEALTHY status")
    
    def _on_error(
        self,
        error: OnchainAdapterError,
        request: Optional[MetricsRequest] = None,
    ) -> None:
        """Handle request error."""
        self._health.error_count += 1
        self._health.consecutive_failures += 1
        self._health.last_error = str(error)
        self._health.last_error_time = datetime.utcnow()
        
        # Update status based on failures
        if isinstance(error, RateLimitError):
            self._health.status = AdapterStatus.RATE_LIMITED
        elif self._health.consecutive_failures >= self.UNAVAILABLE_THRESHOLD:
            if self._health.status != AdapterStatus.UNAVAILABLE:
                self._health.status = AdapterStatus.UNAVAILABLE
                logger.error(f"[{self.name}] Marked UNAVAILABLE")
        elif self._health.consecutive_failures >= self.DEGRADED_THRESHOLD:
            if self._health.status != AdapterStatus.DEGRADED:
                self._health.status = AdapterStatus.DEGRADED
                logger.warning(f"[{self.name}] Marked DEGRADED")
        
        # Log incident
        self._log_incident(error, request)
    
    def _log_incident(
        self,
        error: OnchainAdapterError,
        request: Optional[MetricsRequest] = None,
    ) -> None:
        """Log an incident."""
        incident = AdapterIncident(
            adapter_name=self.name,
            incident_type=error.__class__.__name__,
            timestamp=datetime.utcnow(),
            error_message=str(error),
            chain=request.chain.value if request else None,
            request_params={
                "token_address": request.token_address,
                "time_range_hours": request.time_range_hours,
            } if request else None,
        )
        
        self._incidents.append(incident)
        
        if len(self._incidents) > self._max_incidents:
            self._incidents = self._incidents[-self._max_incidents:]
        
        logger.warning(f"[{self.name}] Incident: {error}")
    
    def get_health(self) -> AdapterHealth:
        """Get current health status."""
        meta = self.metadata()
        self._health.daily_limit = meta.rate_limit_per_day
        return self._health
    
    def get_incidents(self, limit: int = 10) -> list[AdapterIncident]:
        """Get recent incidents."""
        return self._incidents[-limit:]
    
    def is_healthy(self) -> bool:
        """Check if adapter is healthy."""
        return self._health.status == AdapterStatus.HEALTHY
    
    def is_usable(self) -> bool:
        """Check if adapter can be used."""
        return self._health.status in (
            AdapterStatus.HEALTHY,
            AdapterStatus.DEGRADED,
        )
    
    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────
    
    async def close(self) -> None:
        """Close resources."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
    
    async def __aenter__(self) -> "BaseOnchainAdapter":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, status={self._health.status.value})>"
