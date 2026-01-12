"""
Base Market Data Source - Abstract interface for all data providers.

All providers MUST implement this interface to ensure:
- Isolation
- Replaceability  
- Fail-safety
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional, TypeVar

import aiohttp

from data_sources.exceptions import (
    DataSourceError,
    FetchError,
    HealthCheckError,
    NormalizationError,
    RateLimitError,
)
from data_sources.models import (
    DataType,
    FetchRequest,
    Interval,
    NormalizedMarketData,
    SourceHealth,
    SourceIncident,
    SourceMetadata,
    SourceStatus,
)


logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseMarketDataSource(ABC):
    """
    Abstract base class for all market data sources.
    
    Each data source implementation must:
    1. Implement fetch_raw() - Get raw data from provider
    2. Implement normalize() - Convert to NormalizedMarketData
    3. Implement health_check() - Verify provider connectivity
    4. Implement metadata() - Return provider metadata
    
    Features:
    - Automatic retry with exponential backoff
    - Rate limiting protection
    - Health tracking
    - Incident logging
    """
    
    # Configuration defaults (can be overridden by subclasses)
    DEFAULT_TIMEOUT = 30.0
    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 2.0
    HEALTH_CHECK_INTERVAL = 60  # seconds
    DEGRADED_THRESHOLD = 3  # consecutive failures before degraded
    UNAVAILABLE_THRESHOLD = 5  # consecutive failures before unavailable
    
    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._session = session
        self._owns_session = session is None
        
        # Health tracking
        self._health = SourceHealth(
            status=SourceStatus.UNKNOWN,
            last_check=datetime.utcnow(),
        )
        self._last_successful_request: Optional[datetime] = None
        self._request_count = 0
        self._success_count = 0
        self._error_count = 0
        
        # Incident log
        self._incidents: list[SourceIncident] = []
        self._max_incidents = 100
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this data source."""
        pass
    
    @abstractmethod
    async def fetch_raw(
        self,
        request: FetchRequest,
    ) -> list[dict[str, Any]]:
        """
        Fetch raw data from the provider API.
        
        Args:
            request: Fetch request parameters
            
        Returns:
            List of raw data dictionaries from provider
            
        Raises:
            FetchError: If fetch fails after retries
        """
        pass
    
    @abstractmethod
    def normalize(
        self,
        raw_data: list[dict[str, Any]],
        request: FetchRequest,
    ) -> list[NormalizedMarketData]:
        """
        Normalize raw provider data to standard format.
        
        Args:
            raw_data: Raw data from fetch_raw()
            request: Original fetch request
            
        Returns:
            List of NormalizedMarketData objects
            
        Raises:
            NormalizationError: If normalization fails
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> SourceHealth:
        """
        Check provider connectivity and health.
        
        Returns:
            SourceHealth object with current status
        """
        pass
    
    @abstractmethod
    def metadata(self) -> SourceMetadata:
        """
        Return provider metadata.
        
        Returns:
            SourceMetadata with provider information
        """
        pass
    
    async def fetch(
        self,
        request: FetchRequest,
    ) -> list[NormalizedMarketData]:
        """
        Fetch and normalize market data (main entry point).
        
        This method combines fetch_raw() and normalize() with
        proper error handling and health tracking.
        
        Args:
            request: Fetch request parameters
            
        Returns:
            List of normalized market data
            
        Note:
            Never raises unhandled exceptions - returns empty list on failure
        """
        try:
            request.validate()
            
            # Fetch raw data with retries
            raw_data = await self._fetch_with_retry(request)
            
            if not raw_data:
                logger.warning(f"[{self.name}] Empty response for {request.symbol}")
                return []
            
            # Normalize data
            normalized = self.normalize(raw_data, request)
            
            # Track success
            self._on_success()
            
            return normalized
            
        except DataSourceError as e:
            self._on_error(e, request)
            return []
        except Exception as e:
            error = DataSourceError(
                message=f"Unexpected error: {e}",
                source_name=self.name,
                original_error=e,
            )
            self._on_error(error, request)
            return []
    
    async def _fetch_with_retry(
        self,
        request: FetchRequest,
    ) -> list[dict[str, Any]]:
        """Fetch with exponential backoff retry."""
        last_error: Optional[Exception] = None
        
        for attempt in range(self._max_retries):
            try:
                return await self.fetch_raw(request)
                
            except RateLimitError as e:
                # Wait for rate limit to reset
                wait_time = e.retry_after_seconds or (self.RETRY_BACKOFF_BASE ** attempt * 10)
                logger.warning(
                    f"[{self.name}] Rate limited, waiting {wait_time}s "
                    f"(attempt {attempt + 1}/{self._max_retries})"
                )
                await asyncio.sleep(wait_time)
                last_error = e
                
            except FetchError as e:
                if e.is_server_error():
                    # Retry on server errors
                    wait_time = self.RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        f"[{self.name}] Server error {e.status_code}, "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/{self._max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                    last_error = e
                else:
                    # Don't retry client errors
                    raise
                    
            except Exception as e:
                wait_time = self.RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    f"[{self.name}] Error: {e}, "
                    f"retrying in {wait_time}s (attempt {attempt + 1}/{self._max_retries})"
                )
                await asyncio.sleep(wait_time)
                last_error = e
        
        # All retries exhausted
        raise FetchError(
            message=f"Failed after {self._max_retries} retries",
            source_name=self.name,
            original_error=last_error,
        )
    
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
                
                if response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    raise RateLimitError(
                        message="Rate limit exceeded",
                        source_name=self.name,
                        retry_after_seconds=int(retry_after) if retry_after else None,
                    )
                
                if response.status >= 400:
                    body = await response.text()
                    raise FetchError(
                        message=f"HTTP {response.status}",
                        source_name=self.name,
                        status_code=response.status,
                        response_body=body[:1000],
                        request_url=url,
                    )
                
                data = await response.json()
                logger.debug(f"[{self.name}] Request completed in {latency_ms:.1f}ms")
                return data
                
        except aiohttp.ClientError as e:
            raise FetchError(
                message=f"Connection error: {e}",
                source_name=self.name,
                request_url=url,
                original_error=e,
            )
    
    def _on_success(self) -> None:
        """Handle successful request."""
        self._request_count += 1
        self._success_count += 1
        self._last_successful_request = datetime.utcnow()
        
        # Reset consecutive failures
        self._health.consecutive_failures = 0
        
        # Update health status
        if self._health.status != SourceStatus.HEALTHY:
            self._health.status = SourceStatus.HEALTHY
            logger.info(f"[{self.name}] Recovered to HEALTHY status")
    
    def _on_error(
        self,
        error: DataSourceError,
        request: Optional[FetchRequest] = None,
    ) -> None:
        """Handle request error."""
        self._request_count += 1
        self._error_count += 1
        self._health.error_count += 1
        self._health.consecutive_failures += 1
        self._health.last_error = str(error)
        self._health.last_error_time = datetime.utcnow()
        
        # Update health status based on consecutive failures
        if self._health.consecutive_failures >= self.UNAVAILABLE_THRESHOLD:
            if self._health.status != SourceStatus.UNAVAILABLE:
                self._health.status = SourceStatus.UNAVAILABLE
                logger.error(f"[{self.name}] Marked UNAVAILABLE after {self._health.consecutive_failures} failures")
        elif self._health.consecutive_failures >= self.DEGRADED_THRESHOLD:
            if self._health.status != SourceStatus.DEGRADED:
                self._health.status = SourceStatus.DEGRADED
                logger.warning(f"[{self.name}] Marked DEGRADED after {self._health.consecutive_failures} failures")
        
        # Log incident
        self._log_incident(error, request)
    
    def _log_incident(
        self,
        error: DataSourceError,
        request: Optional[FetchRequest] = None,
    ) -> None:
        """Log an incident."""
        incident = SourceIncident(
            source_name=self.name,
            incident_type=error.__class__.__name__,
            timestamp=datetime.utcnow(),
            error_message=str(error),
            request_params={
                "symbol": request.symbol,
                "interval": request.interval.value,
                "data_type": request.data_type.value,
            } if request else None,
        )
        
        self._incidents.append(incident)
        
        # Trim incidents to max size
        if len(self._incidents) > self._max_incidents:
            self._incidents = self._incidents[-self._max_incidents:]
        
        logger.warning(f"[{self.name}] Incident logged: {error}")
    
    def get_health(self) -> SourceHealth:
        """Get current health status."""
        # Update uptime percentage
        if self._request_count > 0:
            self._health.uptime_percentage = (
                self._success_count / self._request_count * 100
            )
        return self._health
    
    def get_incidents(self, limit: int = 10) -> list[SourceIncident]:
        """Get recent incidents."""
        return self._incidents[-limit:]
    
    def is_healthy(self) -> bool:
        """Check if source is healthy."""
        return self._health.status == SourceStatus.HEALTHY
    
    def is_usable(self) -> bool:
        """Check if source can be used (healthy or degraded)."""
        return self._health.status in (SourceStatus.HEALTHY, SourceStatus.DEGRADED)
    
    async def close(self) -> None:
        """Close resources."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
    
    async def __aenter__(self) -> "BaseMarketDataSource":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, status={self._health.status.value})>"
