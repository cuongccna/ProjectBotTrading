"""
On-chain Adapter Registry - Central registry with caching and fallback.

Features:
- Adapter registration and discovery
- Aggressive caching to minimize API calls
- Graceful rate limit handling
- Non-blocking fetch with fallback
- Never blocks system execution
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from onchain_adapters.base import BaseOnchainAdapter
from onchain_adapters.exceptions import (
    NoAvailableAdapterError,
    OnchainAdapterError,
)
from onchain_adapters.models import (
    AdapterHealth,
    AdapterIncident,
    AdapterMetadata,
    AdapterStatus,
    Chain,
    MetricsRequest,
    OnchainMetrics,
)


logger = logging.getLogger(__name__)


class AdapterRegistry:
    """
    Central registry for on-chain data adapters.
    
    Features:
    - Register multiple adapters
    - Automatic fallback on failure
    - Shared caching across adapters
    - Non-blocking operations
    - Never raises to caller - returns None on failure
    
    Usage:
        registry = AdapterRegistry()
        registry.register(EtherscanAdapter())
        registry.register(FlipsideAdapter())
        
        # Fetch with automatic fallback
        metrics = await registry.fetch(request)
        
        # Returns None if all adapters fail - NEVER blocks
    """
    
    def __init__(
        self,
        health_check_interval: int = 120,  # 2 minutes
        max_incidents: int = 500,
    ) -> None:
        self._adapters: dict[str, BaseOnchainAdapter] = {}
        self._adapter_order: list[str] = []
        self._health_check_interval = health_check_interval
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Incident tracking
        self._incidents: list[AdapterIncident] = []
        self._max_incidents = max_incidents
        
        # Event callbacks
        self._on_incident_callbacks: list[Callable[[AdapterIncident], None]] = []
        self._on_fallback_callbacks: list[Callable[[str, str], None]] = []
    
    def register(
        self,
        adapter: BaseOnchainAdapter,
        priority: Optional[int] = None,
    ) -> None:
        """
        Register an on-chain adapter.
        
        Args:
            adapter: Adapter instance
            priority: Lower = higher priority
        """
        name = adapter.name
        
        if name in self._adapters:
            logger.warning(f"Adapter '{name}' already registered, replacing")
        
        self._adapters[name] = adapter
        
        if priority is None:
            priority = adapter.metadata().priority
        
        # Insert in priority order
        insert_idx = len(self._adapter_order)
        for i, existing_name in enumerate(self._adapter_order):
            if existing_name in self._adapters:
                existing_priority = self._adapters[existing_name].metadata().priority
                if priority < existing_priority:
                    insert_idx = i
                    break
        
        if name not in self._adapter_order:
            self._adapter_order.insert(insert_idx, name)
        
        logger.info(f"Registered on-chain adapter '{name}' with priority {priority}")
    
    def unregister(self, name: str) -> Optional[BaseOnchainAdapter]:
        """Unregister an adapter."""
        if name in self._adapters:
            adapter = self._adapters.pop(name)
            if name in self._adapter_order:
                self._adapter_order.remove(name)
            logger.info(f"Unregistered adapter '{name}'")
            return adapter
        return None
    
    def get_adapter(self, name: str) -> Optional[BaseOnchainAdapter]:
        """Get a specific adapter by name."""
        return self._adapters.get(name)
    
    def list_adapters(self) -> list[str]:
        """List all registered adapter names in priority order."""
        return self._adapter_order.copy()
    
    def get_adapters_for_chain(self, chain: Chain) -> list[str]:
        """Get adapters that support a specific chain."""
        result = []
        for name in self._adapter_order:
            adapter = self._adapters.get(name)
            if adapter and adapter.metadata().supports_chain(chain):
                result.append(name)
        return result
    
    async def fetch(
        self,
        request: MetricsRequest,
        preferred_adapter: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Optional[OnchainMetrics]:
        """
        Fetch on-chain metrics with automatic fallback.
        
        This method:
        1. Tries preferred adapter first (if specified)
        2. Falls back to other adapters on failure
        3. Returns cached data if available
        4. NEVER blocks or raises - returns None on failure
        
        Args:
            request: Metrics request
            preferred_adapter: Preferred adapter name
            timeout: Maximum time to wait
            
        Returns:
            OnchainMetrics or None if unavailable
        """
        try:
            # Get adapters that support this chain
            adapters_for_chain = self.get_adapters_for_chain(request.chain)
            
            if not adapters_for_chain:
                logger.warning(
                    f"No adapters support chain {request.chain.value}"
                )
                return None
            
            # Determine fetch order
            if preferred_adapter and preferred_adapter in adapters_for_chain:
                adapters_to_try = [preferred_adapter]
                adapters_to_try.extend(
                    [a for a in adapters_for_chain if a != preferred_adapter]
                )
            else:
                adapters_to_try = adapters_for_chain
            
            # Filter to usable adapters
            usable = [
                name for name in adapters_to_try
                if name in self._adapters and self._adapters[name].is_usable()
            ]
            
            if not usable:
                # Try all as last resort
                usable = adapters_to_try
                logger.warning("No healthy adapters, trying all")
            
            # Try each adapter with timeout
            for adapter_name in usable:
                adapter = self._adapters.get(adapter_name)
                if not adapter:
                    continue
                
                try:
                    result = await asyncio.wait_for(
                        adapter.fetch(request),
                        timeout=timeout,
                    )
                    
                    if result:
                        return result
                    
                except asyncio.TimeoutError:
                    logger.warning(f"[{adapter_name}] Fetch timeout")
                    self._log_incident(
                        adapter_name,
                        "timeout",
                        f"Fetch timeout after {timeout}s",
                        request,
                    )
                    
                except Exception as e:
                    logger.warning(f"[{adapter_name}] Fetch error: {e}")
                    self._log_incident(
                        adapter_name,
                        "fetch_error",
                        str(e),
                        request,
                    )
            
            # All adapters failed
            logger.warning(
                f"All adapters failed for chain {request.chain.value}"
            )
            
            return None
            
        except Exception as e:
            logger.error(f"Registry fetch error: {e}")
            return None
    
    async def fetch_from_all(
        self,
        request: MetricsRequest,
        timeout: float = 30.0,
    ) -> dict[str, Optional[OnchainMetrics]]:
        """
        Fetch from all adapters concurrently.
        
        Useful for data validation and comparison.
        """
        adapters_for_chain = self.get_adapters_for_chain(request.chain)
        
        tasks = {}
        for name in adapters_for_chain:
            adapter = self._adapters.get(name)
            if adapter and adapter.is_usable():
                tasks[name] = asyncio.create_task(adapter.fetch(request))
        
        results = {}
        for name, task in tasks.items():
            try:
                results[name] = await asyncio.wait_for(task, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"[{name}] Fetch timeout")
                results[name] = None
            except Exception as e:
                logger.warning(f"[{name}] Fetch error: {e}")
                results[name] = None
        
        return results
    
    async def health_check_all(self) -> dict[str, AdapterHealth]:
        """Run health check on all adapters."""
        tasks = {
            name: asyncio.create_task(adapter.health_check())
            for name, adapter in self._adapters.items()
        }
        
        results = {}
        for name, task in tasks.items():
            try:
                results[name] = await asyncio.wait_for(task, timeout=30.0)
            except Exception as e:
                logger.warning(f"[{name}] Health check failed: {e}")
                results[name] = AdapterHealth(
                    status=AdapterStatus.UNAVAILABLE,
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
        logger.info(
            f"Started on-chain health monitoring "
            f"(interval={self._health_check_interval}s)"
        )
    
    async def stop_health_monitoring(self) -> None:
        """Stop health monitoring."""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped on-chain health monitoring")
    
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
    
    def _log_incident(
        self,
        adapter_name: str,
        incident_type: str,
        message: str,
        request: Optional[MetricsRequest] = None,
    ) -> None:
        """Log an incident."""
        incident = AdapterIncident(
            adapter_name=adapter_name,
            incident_type=incident_type,
            timestamp=datetime.utcnow(),
            error_message=message,
            chain=request.chain.value if request else None,
            request_params={
                "token_address": request.token_address,
                "time_range_hours": request.time_range_hours,
            } if request else None,
        )
        
        self._incidents.append(incident)
        
        if len(self._incidents) > self._max_incidents:
            self._incidents = self._incidents[-self._max_incidents:]
        
        for callback in self._on_incident_callbacks:
            try:
                callback(incident)
            except Exception as e:
                logger.error(f"Incident callback error: {e}")
    
    def on_incident(self, callback: Callable[[AdapterIncident], None]) -> None:
        """Register callback for incidents."""
        self._on_incident_callbacks.append(callback)
    
    def on_fallback(self, callback: Callable[[str, str], None]) -> None:
        """Register callback for adapter fallback."""
        self._on_fallback_callbacks.append(callback)
    
    def get_incidents(self, limit: int = 50) -> list[AdapterIncident]:
        """Get recent incidents."""
        return self._incidents[-limit:]
    
    def get_all_metadata(self) -> dict[str, AdapterMetadata]:
        """Get metadata for all adapters."""
        return {name: adapter.metadata() for name, adapter in self._adapters.items()}
    
    def get_all_health(self) -> dict[str, AdapterHealth]:
        """Get health for all adapters."""
        return {name: adapter.get_health() for name, adapter in self._adapters.items()}
    
    def get_cache_stats(self) -> dict[str, dict[str, Any]]:
        """Get cache statistics for all adapters."""
        return {
            name: adapter.get_cache_stats()
            for name, adapter in self._adapters.items()
        }
    
    def clear_all_caches(self) -> None:
        """Clear caches for all adapters."""
        for adapter in self._adapters.values():
            adapter.clear_cache()
        logger.info("Cleared all adapter caches")
    
    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        health_summary = {}
        for status in AdapterStatus:
            health_summary[status.value] = sum(
                1 for a in self._adapters.values()
                if a.get_health().status == status
            )
        
        # Cache stats
        total_cache_entries = sum(
            stats.get("entries", 0)
            for stats in self.get_cache_stats().values()
        )
        total_cache_hits = sum(
            stats.get("hits", 0)
            for stats in self.get_cache_stats().values()
        )
        
        return {
            "total_adapters": len(self._adapters),
            "adapter_order": self._adapter_order,
            "health_summary": health_summary,
            "total_incidents": len(self._incidents),
            "total_cache_entries": total_cache_entries,
            "total_cache_hits": total_cache_hits,
            "adapters": {
                name: {
                    "status": adapter.get_health().status.value,
                    "is_usable": adapter.is_usable(),
                    "supported_chains": [
                        c.value for c in adapter.metadata().supported_chains
                    ],
                }
                for name, adapter in self._adapters.items()
            },
        }
    
    async def close(self) -> None:
        """Close all resources."""
        await self.stop_health_monitoring()
        
        for adapter in self._adapters.values():
            try:
                await adapter.close()
            except Exception as e:
                logger.error(f"Error closing adapter {adapter.name}: {e}")
        
        self._adapters.clear()
        self._adapter_order.clear()
        logger.info("On-chain registry closed")
    
    async def __aenter__(self) -> "AdapterRegistry":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


# Singleton instance
_default_registry: Optional[AdapterRegistry] = None


def get_default_registry() -> AdapterRegistry:
    """Get or create the default registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = AdapterRegistry()
    return _default_registry


async def setup_default_adapters() -> AdapterRegistry:
    """
    Set up the default registry with standard adapters.
    
    Returns configured registry with Etherscan and Flipside.
    """
    from onchain_adapters.providers.etherscan import EtherscanAdapter
    from onchain_adapters.providers.flipside import FlipsideAdapter
    
    registry = get_default_registry()
    
    # Register Etherscan as primary
    registry.register(EtherscanAdapter(), priority=1)
    
    # Register Flipside as secondary
    registry.register(FlipsideAdapter(), priority=2)
    
    # Run initial health check
    await registry.health_check_all()
    
    return registry
