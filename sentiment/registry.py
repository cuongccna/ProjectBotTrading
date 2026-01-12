"""
Sentiment Registry - Central manager for all sentiment sources.

SAFETY: All sentiment data is CONTEXT ONLY - never a standalone trade trigger.

The registry:
1. Manages multiple sentiment sources
2. Aggregates data with proper weighting
3. Handles failures gracefully (non-blocking)
4. Provides unified access point
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from .base import BaseSentimentSource
from .models import (
    AggregatedSentiment,
    SentimentData,
    SentimentRequest,
    SourceHealth,
    SourceIncident,
    SourceStatus,
)
from .pipeline import SentimentPipeline


logger = logging.getLogger(__name__)


class SentimentRegistry:
    """
    Central registry for sentiment data sources.
    
    DESIGN PRINCIPLES:
    1. NON-BLOCKING - Never wait indefinitely for any source
    2. GRACEFUL - Partial data is better than no data
    3. WEIGHTED - Sources weighted by reliability
    4. TRANSPARENT - Health and stats available
    5. SAFE - Sentiment is CONTEXT ONLY
    
    Usage:
        registry = SentimentRegistry()
        registry.register(CryptoPanicSource())
        registry.register(TwitterScraperSource())
        
        sentiment = await registry.get_sentiment(
            symbols=["BTC", "ETH"],
            time_range_hours=24,
        )
    """
    
    # Timeout for individual source fetch
    SOURCE_TIMEOUT = 15  # seconds
    
    def __init__(
        self,
        pipeline: Optional[SentimentPipeline] = None,
    ) -> None:
        self._sources: dict[str, BaseSentimentSource] = {}
        self._pipeline = pipeline or SentimentPipeline()
        self._incidents: list[SourceIncident] = []
        self._last_fetch: dict[str, datetime] = {}
        
        # Statistics
        self._stats = {
            "total_requests": 0,
            "successful_aggregations": 0,
            "partial_aggregations": 0,
            "failed_aggregations": 0,
        }
    
    def register(self, source: BaseSentimentSource) -> None:
        """Register a sentiment source."""
        name = source.metadata.name
        if name in self._sources:
            logger.warning(f"Overwriting existing source: {name}")
        
        self._sources[name] = source
        logger.info(f"Registered sentiment source: {name}")
    
    def unregister(self, name: str) -> bool:
        """Unregister a sentiment source."""
        if name in self._sources:
            del self._sources[name]
            logger.info(f"Unregistered sentiment source: {name}")
            return True
        return False
    
    async def get_sentiment(
        self,
        symbols: Optional[list[str]] = None,
        time_range_hours: int = 24,
        limit: int = 50,
        primary_symbol: Optional[str] = None,
    ) -> AggregatedSentiment:
        """
        Get aggregated sentiment from all sources.
        
        NEVER blocks indefinitely - returns partial data on timeout.
        
        Args:
            symbols: List of symbols to get sentiment for
            time_range_hours: How far back to look
            limit: Max items per source
            primary_symbol: Symbol to focus aggregation on
            
        Returns:
            AggregatedSentiment with weighted score and confidence
        """
        self._stats["total_requests"] += 1
        
        if not self._sources:
            logger.warning("No sentiment sources registered")
            return self._pipeline.aggregate([], primary_symbol, time_range_hours)
        
        # Build request
        request = SentimentRequest(
            symbols=symbols or ["BTC", "ETH"],
            time_range_hours=time_range_hours,
            limit=limit,
        )
        
        # Fetch from all sources concurrently with timeout
        all_sentiments: list[SentimentData] = []
        sources_succeeded: list[str] = []
        sources_failed: list[str] = []
        
        # Create tasks for each source
        tasks = {}
        for name, source in self._sources.items():
            task = asyncio.create_task(
                self._fetch_with_timeout(source, request),
                name=name,
            )
            tasks[name] = task
        
        # Wait for all tasks
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        # Process results
        for name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                sources_failed.append(name)
                self._record_incident(
                    name, "fetch_error",
                    str(result), request,
                )
            elif result:
                all_sentiments.extend(result)
                sources_succeeded.append(name)
                self._last_fetch[name] = datetime.utcnow()
            else:
                sources_failed.append(name)
        
        # Update stats
        if sources_succeeded and not sources_failed:
            self._stats["successful_aggregations"] += 1
        elif sources_succeeded:
            self._stats["partial_aggregations"] += 1
        else:
            self._stats["failed_aggregations"] += 1
        
        # Aggregate
        return self._pipeline.aggregate(
            all_sentiments,
            symbol=primary_symbol,
            time_range_hours=time_range_hours,
        )
    
    async def get_sentiment_raw(
        self,
        symbols: Optional[list[str]] = None,
        time_range_hours: int = 24,
        limit: int = 50,
    ) -> list[SentimentData]:
        """
        Get raw sentiment data without aggregation.
        
        Returns list of individual SentimentData items.
        """
        if not self._sources:
            return []
        
        request = SentimentRequest(
            symbols=symbols or ["BTC", "ETH"],
            time_range_hours=time_range_hours,
            limit=limit,
        )
        
        all_sentiments: list[SentimentData] = []
        
        tasks = [
            asyncio.create_task(self._fetch_with_timeout(source, request))
            for source in self._sources.values()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                all_sentiments.extend(result)
        
        return all_sentiments
    
    async def get_alerts(
        self,
        symbols: Optional[list[str]] = None,
        time_range_hours: int = 4,
    ) -> list[SentimentData]:
        """Get high-priority sentiment alerts."""
        raw = await self.get_sentiment_raw(
            symbols=symbols,
            time_range_hours=time_range_hours,
            limit=100,
        )
        return self._pipeline.get_alerts(raw)
    
    async def _fetch_with_timeout(
        self,
        source: BaseSentimentSource,
        request: SentimentRequest,
    ) -> list[SentimentData]:
        """Fetch from source with timeout."""
        try:
            return await asyncio.wait_for(
                source.fetch_sentiment(request),
                timeout=self.SOURCE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Source {source.metadata.name} timed out")
            return []
        except Exception as e:
            logger.error(f"Source {source.metadata.name} error: {e}")
            return []
    
    def _record_incident(
        self,
        source_name: str,
        incident_type: str,
        error_message: str,
        request: Optional[SentimentRequest] = None,
    ) -> None:
        """Record an incident for debugging."""
        incident = SourceIncident(
            source_name=source_name,
            incident_type=incident_type,
            timestamp=datetime.utcnow(),
            error_message=error_message,
            request_params={"symbols": request.symbols} if request else None,
        )
        self._incidents.append(incident)
        
        # Keep only last 100 incidents
        if len(self._incidents) > 100:
            self._incidents = self._incidents[-100:]
    
    async def get_health(self) -> dict[str, SourceHealth]:
        """Get health status of all sources."""
        health = {}
        for name, source in self._sources.items():
            health[name] = await source.get_health()
        return health
    
    async def get_health_summary(self) -> dict[str, Any]:
        """Get summary health information."""
        health = await self.get_health()
        
        total = len(health)
        healthy = sum(1 for h in health.values() if h.status == SourceStatus.HEALTHY)
        degraded = sum(1 for h in health.values() if h.status == SourceStatus.DEGRADED)
        unavailable = sum(1 for h in health.values() if h.status == SourceStatus.UNAVAILABLE)
        
        return {
            "total_sources": total,
            "healthy": healthy,
            "degraded": degraded,
            "unavailable": unavailable,
            "health_pct": round(healthy / total * 100, 1) if total > 0 else 0,
            "sources": {name: h.status.value for name, h in health.items()},
        }
    
    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        source_stats = {}
        for name, source in self._sources.items():
            source_stats[name] = source.get_stats()
        
        return {
            **self._stats,
            "registered_sources": len(self._sources),
            "source_names": list(self._sources.keys()),
            "source_stats": source_stats,
            "recent_incidents": len(self._incidents),
        }
    
    def get_incidents(
        self,
        limit: int = 20,
        source_name: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get recent incidents."""
        incidents = self._incidents
        
        if source_name:
            incidents = [i for i in incidents if i.source_name == source_name]
        
        return [i.to_dict() for i in incidents[-limit:]]
    
    async def check_connectivity(self) -> dict[str, bool]:
        """Check connectivity for all sources."""
        results = {}
        
        tasks = {
            name: asyncio.create_task(source.check_connectivity())
            for name, source in self._sources.items()
        }
        
        done = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        for name, result in zip(tasks.keys(), done):
            if isinstance(result, Exception):
                results[name] = False
            else:
                results[name] = bool(result)
        
        return results
    
    async def close(self) -> None:
        """Close all sources."""
        for source in self._sources.values():
            await source.close()
        self._sources.clear()


# Singleton instance for convenience
_default_registry: Optional[SentimentRegistry] = None


def get_registry() -> SentimentRegistry:
    """Get the default sentiment registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = SentimentRegistry()
    return _default_registry


async def get_sentiment(
    symbols: Optional[list[str]] = None,
    time_range_hours: int = 24,
) -> AggregatedSentiment:
    """Convenience function to get sentiment from default registry."""
    registry = get_registry()
    return await registry.get_sentiment(
        symbols=symbols,
        time_range_hours=time_range_hours,
    )
