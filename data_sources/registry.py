"""
Source Registry - Central registry for market data sources with fallback logic.

Provides:
- Source registration and discovery
- Automatic health monitoring
- Fallback to secondary sources on failure
- No downstream dependency on specific providers
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from data_sources.base import BaseMarketDataSource
from data_sources.exceptions import (
    DataSourceError,
    NoAvailableSourceError,
    SourceUnavailableError,
)
from data_sources.models import (
    FetchRequest,
    NormalizedMarketData,
    SourceHealth,
    SourceIncident,
    SourceMetadata,
    SourceStatus,
)


logger = logging.getLogger(__name__)


class SourceRegistry:
    """
    Central registry for market data sources.
    
    Features:
    - Register multiple data sources
    - Automatic fallback on source failure
    - Periodic health monitoring
    - Event callbacks for incidents
    - No downstream code depends on specific providers
    
    Usage:
        registry = SourceRegistry()
        registry.register(BinanceMarketSource())
        registry.register(OKXMarketSource())
        
        # Fetch with automatic fallback
        data = await registry.fetch(request)
    """
    
    def __init__(
        self,
        health_check_interval: int = 60,
        max_incidents: int = 1000,
    ) -> None:
        self._sources: dict[str, BaseMarketDataSource] = {}
        self._source_order: list[str] = []  # Priority order
        self._health_check_interval = health_check_interval
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Incident tracking
        self._incidents: list[SourceIncident] = []
        self._max_incidents = max_incidents
        
        # Event callbacks
        self._on_incident_callbacks: list[Callable[[SourceIncident], None]] = []
        self._on_fallback_callbacks: list[Callable[[str, str], None]] = []
        self._on_recovery_callbacks: list[Callable[[str], None]] = []
    
    def register(
        self,
        source: BaseMarketDataSource,
        priority: Optional[int] = None,
    ) -> None:
        """
        Register a data source.
        
        Args:
            source: Data source instance
            priority: Lower = higher priority (optional, uses metadata priority)
        """
        name = source.name
        
        if name in self._sources:
            logger.warning(f"Source '{name}' already registered, replacing")
        
        self._sources[name] = source
        
        # Insert in priority order
        if priority is None:
            priority = source.metadata().priority
        
        # Find insertion point
        insert_idx = len(self._source_order)
        for i, existing_name in enumerate(self._source_order):
            if existing_name in self._sources:
                existing_priority = self._sources[existing_name].metadata().priority
                if priority < existing_priority:
                    insert_idx = i
                    break
        
        if name not in self._source_order:
            self._source_order.insert(insert_idx, name)
        
        logger.info(f"Registered source '{name}' with priority {priority}")
    
    def unregister(self, name: str) -> Optional[BaseMarketDataSource]:
        """Unregister a data source."""
        if name in self._sources:
            source = self._sources.pop(name)
            if name in self._source_order:
                self._source_order.remove(name)
            logger.info(f"Unregistered source '{name}'")
            return source
        return None
    
    def get_source(self, name: str) -> Optional[BaseMarketDataSource]:
        """Get a specific source by name."""
        return self._sources.get(name)
    
    def list_sources(self) -> list[str]:
        """List all registered source names in priority order."""
        return self._source_order.copy()
    
    def get_all_metadata(self) -> dict[str, SourceMetadata]:
        """Get metadata for all registered sources."""
        return {name: source.metadata() for name, source in self._sources.items()}
    
    def get_all_health(self) -> dict[str, SourceHealth]:
        """Get health status for all registered sources."""
        return {name: source.get_health() for name, source in self._sources.items()}
    
    async def fetch(
        self,
        request: FetchRequest,
        preferred_source: Optional[str] = None,
        allow_fallback: bool = True,
    ) -> list[NormalizedMarketData]:
        """
        Fetch market data with automatic fallback.
        
        Args:
            request: Fetch request parameters
            preferred_source: Preferred source name (optional)
            allow_fallback: Whether to try other sources on failure
            
        Returns:
            List of normalized market data
            
        Note:
            Never raises exceptions - returns empty list on complete failure
        """
        # Determine source order
        if preferred_source and preferred_source in self._sources:
            sources_to_try = [preferred_source]
            if allow_fallback:
                sources_to_try.extend([s for s in self._source_order if s != preferred_source])
        else:
            sources_to_try = self._source_order.copy()
        
        # Filter to usable sources
        usable_sources = [
            name for name in sources_to_try
            if name in self._sources and self._sources[name].is_usable()
        ]
        
        if not usable_sources:
            # Try all sources anyway as last resort
            usable_sources = sources_to_try
            logger.warning("No healthy sources available, trying all sources")
        
        attempted_sources: list[str] = []
        last_source: Optional[str] = None
        
        for source_name in usable_sources:
            if source_name not in self._sources:
                continue
            
            source = self._sources[source_name]
            attempted_sources.append(source_name)
            
            try:
                data = await source.fetch(request)
                
                if data:
                    # Log fallback if not primary source
                    if last_source and last_source != source_name:
                        self._on_fallback(last_source, source_name)
                    
                    return data
                
                # Empty response, try next source
                logger.warning(f"[{source_name}] Empty response for {request.symbol}")
                last_source = source_name
                
            except Exception as e:
                logger.warning(f"[{source_name}] Failed: {e}")
                self._log_incident(source_name, "fetch_error", str(e), request)
                last_source = source_name
                
                if not allow_fallback:
                    break
        
        # All sources failed
        logger.error(
            f"All sources failed for {request.symbol}: {attempted_sources}"
        )
        
        self._log_incident(
            "registry",
            "all_sources_failed",
            f"Attempted sources: {attempted_sources}",
            request,
        )
        
        return []
    
    async def fetch_from_all(
        self,
        request: FetchRequest,
    ) -> dict[str, list[NormalizedMarketData]]:
        """
        Fetch from all sources concurrently.
        
        Useful for data validation and comparison.
        """
        tasks = {}
        for name, source in self._sources.items():
            if source.is_usable():
                tasks[name] = asyncio.create_task(source.fetch(request))
        
        results = {}
        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception as e:
                logger.warning(f"[{name}] Failed: {e}")
                results[name] = []
        
        return results
    
    async def health_check_all(self) -> dict[str, SourceHealth]:
        """Run health check on all sources."""
        tasks = {
            name: asyncio.create_task(source.health_check())
            for name, source in self._sources.items()
        }
        
        results = {}
        for name, task in tasks.items():
            try:
                health = await task
                results[name] = health
                
                # Check for recovery
                if health.status == SourceStatus.HEALTHY:
                    prev_health = self._sources[name].get_health()
                    if prev_health.status in (SourceStatus.DEGRADED, SourceStatus.UNAVAILABLE):
                        self._on_recovery(name)
                        
            except Exception as e:
                logger.warning(f"[{name}] Health check failed: {e}")
                results[name] = SourceHealth(
                    status=SourceStatus.UNAVAILABLE,
                    last_check=datetime.utcnow(),
                    last_error=str(e),
                )
        
        return results
    
    async def start_health_monitoring(self) -> None:
        """Start periodic health monitoring."""
        if self._running:
            return
        
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_monitor_loop())
        logger.info(f"Started health monitoring (interval={self._health_check_interval}s)")
    
    async def stop_health_monitoring(self) -> None:
        """Stop health monitoring."""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped health monitoring")
    
    async def _health_monitor_loop(self) -> None:
        """Health monitoring loop."""
        while self._running:
            try:
                await self.health_check_all()
                await asyncio.sleep(self._health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(self._health_check_interval)
    
    def on_incident(self, callback: Callable[[SourceIncident], None]) -> None:
        """Register callback for incidents."""
        self._on_incident_callbacks.append(callback)
    
    def on_fallback(self, callback: Callable[[str, str], None]) -> None:
        """Register callback for source fallback (from_source, to_source)."""
        self._on_fallback_callbacks.append(callback)
    
    def on_recovery(self, callback: Callable[[str], None]) -> None:
        """Register callback for source recovery."""
        self._on_recovery_callbacks.append(callback)
    
    def _log_incident(
        self,
        source_name: str,
        incident_type: str,
        message: str,
        request: Optional[FetchRequest] = None,
    ) -> None:
        """Log an incident."""
        incident = SourceIncident(
            source_name=source_name,
            incident_type=incident_type,
            timestamp=datetime.utcnow(),
            error_message=message,
            request_params={
                "symbol": request.symbol,
                "interval": request.interval.value,
                "data_type": request.data_type.value,
            } if request else None,
        )
        
        self._incidents.append(incident)
        
        # Trim to max size
        if len(self._incidents) > self._max_incidents:
            self._incidents = self._incidents[-self._max_incidents:]
        
        # Notify callbacks
        for callback in self._on_incident_callbacks:
            try:
                callback(incident)
            except Exception as e:
                logger.error(f"Incident callback error: {e}")
    
    def _on_fallback(self, from_source: str, to_source: str) -> None:
        """Handle source fallback."""
        logger.warning(f"Fallback: {from_source} -> {to_source}")
        
        self._log_incident(
            from_source,
            "fallback",
            f"Switched to {to_source}",
        )
        
        for callback in self._on_fallback_callbacks:
            try:
                callback(from_source, to_source)
            except Exception as e:
                logger.error(f"Fallback callback error: {e}")
    
    def _on_recovery(self, source_name: str) -> None:
        """Handle source recovery."""
        logger.info(f"Source recovered: {source_name}")
        
        self._log_incident(
            source_name,
            "recovery",
            "Source recovered to healthy status",
        )
        
        for callback in self._on_recovery_callbacks:
            try:
                callback(source_name)
            except Exception as e:
                logger.error(f"Recovery callback error: {e}")
    
    def get_incidents(self, limit: int = 100) -> list[SourceIncident]:
        """Get recent incidents."""
        return self._incidents[-limit:]
    
    def get_source_incidents(self, source_name: str, limit: int = 50) -> list[SourceIncident]:
        """Get incidents for a specific source."""
        source_incidents = [i for i in self._incidents if i.source_name == source_name]
        return source_incidents[-limit:]
    
    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        health_summary = {}
        for status in SourceStatus:
            health_summary[status.value] = sum(
                1 for s in self._sources.values()
                if s.get_health().status == status
            )
        
        return {
            "total_sources": len(self._sources),
            "source_order": self._source_order,
            "health_summary": health_summary,
            "total_incidents": len(self._incidents),
            "sources": {
                name: {
                    "status": source.get_health().status.value,
                    "is_usable": source.is_usable(),
                    "priority": source.metadata().priority,
                }
                for name, source in self._sources.items()
            },
        }
    
    async def close(self) -> None:
        """Close all resources."""
        await self.stop_health_monitoring()
        
        for source in self._sources.values():
            try:
                await source.close()
            except Exception as e:
                logger.error(f"Error closing source {source.name}: {e}")
        
        self._sources.clear()
        self._source_order.clear()
        logger.info("Registry closed")
    
    async def __aenter__(self) -> "SourceRegistry":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


# Singleton instance for convenience
_default_registry: Optional[SourceRegistry] = None


def get_default_registry() -> SourceRegistry:
    """Get or create the default registry instance."""
    global _default_registry
    if _default_registry is None:
        _default_registry = SourceRegistry()
    return _default_registry


async def setup_default_sources() -> SourceRegistry:
    """
    Set up the default registry with standard sources.
    
    Returns configured registry with Binance and OKX sources.
    """
    from data_sources.providers.binance import BinanceMarketSource
    from data_sources.providers.okx import OKXMarketSource
    
    registry = get_default_registry()
    
    # Register Binance as primary (priority 1)
    registry.register(BinanceMarketSource(use_futures=True), priority=1)
    
    # Register OKX as secondary (priority 2)
    registry.register(OKXMarketSource(inst_type="SWAP"), priority=2)
    
    # Run initial health check
    await registry.health_check_all()
    
    return registry
