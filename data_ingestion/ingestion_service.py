"""
Data Ingestion - Ingestion Service.

============================================================
RESPONSIBILITY
============================================================
Orchestrates all data ingestion activities.

- Manages all collectors and normalizers
- Coordinates collection schedules
- Handles storage of raw and normalized data
- Reports ingestion health and metrics

============================================================
DESIGN PRINCIPLES
============================================================
- Single entry point for data ingestion
- No business logic - coordination only
- All data flows to storage
- Failure isolation between sources

============================================================
WORKFLOW
============================================================
1. Initialize all configured collectors
2. Start collection schedules
3. For each collected item:
   a. Store raw data immediately
   b. Normalize data (future phase)
   c. Store normalized data (future phase)
   d. Publish to downstream consumers (future phase)
4. Report metrics and health

============================================================
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from data_ingestion.types import (
    CollectorConfig,
    NewsApiConfig,
    CoinGeckoConfig,
    OnChainConfig,
    WebSocketConfig,
    IngestionResult,
    IngestionStatus,
    IngestionMetrics,
    IngestionSource,
    IngestionError,
)
from data_ingestion.collectors.base import BaseCollector
from data_ingestion.collectors.crypto_news_api import CryptoNewsApiCollector
from data_ingestion.collectors.coingecko import CoinGeckoCollector
from data_ingestion.collectors.onchain_free_sources import OnChainCollector
from data_ingestion.collectors.market_data_ws import MarketDataWebSocketCollector


# ============================================================
# CONFIGURATION
# ============================================================


@dataclass
class IngestionServiceConfig:
    """Configuration for the ingestion service."""
    
    # Enabled collectors
    enabled_collectors: List[str] = field(default_factory=lambda: [
        "crypto_news_api",
        "coingecko",
        "onchain",
    ])
    
    # Parallel collection
    parallel_collection: bool = True
    
    # Health check interval
    health_check_interval_seconds: int = 60
    
    # Collector-specific configs
    news_api_config: Optional[NewsApiConfig] = None
    coingecko_config: Optional[CoinGeckoConfig] = None
    onchain_config: Optional[OnChainConfig] = None
    websocket_config: Optional[WebSocketConfig] = None


# ============================================================
# COLLECTOR REGISTRY
# ============================================================


@dataclass
class CollectorRegistration:
    """Registration entry for a collector."""
    
    name: str
    collector_class: Type
    config_type: Type[CollectorConfig]
    enabled: bool = True


COLLECTOR_REGISTRY: Dict[str, CollectorRegistration] = {
    "crypto_news_api": CollectorRegistration(
        name="crypto_news_api",
        collector_class=CryptoNewsApiCollector,
        config_type=NewsApiConfig,
    ),
    "coingecko": CollectorRegistration(
        name="coingecko",
        collector_class=CoinGeckoCollector,
        config_type=CoinGeckoConfig,
    ),
    "onchain": CollectorRegistration(
        name="onchain",
        collector_class=OnChainCollector,
        config_type=OnChainConfig,
    ),
}


# ============================================================
# INGESTION SERVICE
# ============================================================


class IngestionService:
    """
    Orchestrates all data ingestion activities.
    
    ============================================================
    DESIGN
    ============================================================
    This service:
    - Manages lifecycle of all collectors
    - Coordinates collection schedules
    - Aggregates health and metrics
    - Isolates failures between sources
    
    ============================================================
    USAGE
    ============================================================
    ```python
    # Create service
    config = IngestionServiceConfig(...)
    service = IngestionService(config, session_factory)
    
    # Run single cycle
    results = await service.run_collection_cycle()
    
    # Or run continuously
    await service.start()
    ```
    
    ============================================================
    """
    
    def __init__(
        self,
        config: IngestionServiceConfig,
        session_factory: Callable[[], Session],
    ) -> None:
        """
        Initialize the ingestion service.
        
        Args:
            config: Service configuration
            session_factory: Factory to create database sessions
        """
        self._config = config
        self._session_factory = session_factory
        self._logger = logging.getLogger("ingestion_service")
        
        # Collector instances
        self._collectors: Dict[str, BaseCollector] = {}
        self._ws_collector: Optional[MarketDataWebSocketCollector] = None
        
        # Service state
        self._running = False
        self._run_count = 0
        
        # Metrics
        self._results: List[IngestionResult] = []
        self._last_run_at: Optional[datetime] = None
        self._total_records_stored = 0
        self._total_errors = 0
        
        # Initialize collectors
        self._initialize_collectors()
    
    def _initialize_collectors(self) -> None:
        """Initialize enabled collectors."""
        for collector_name in self._config.enabled_collectors:
            if collector_name not in COLLECTOR_REGISTRY:
                self._logger.warning(f"Unknown collector: {collector_name}")
                continue
            
            registration = COLLECTOR_REGISTRY[collector_name]
            config = self._get_collector_config(collector_name)
            
            if config is None:
                self._logger.warning(f"No config for collector: {collector_name}")
                continue
            
            try:
                # Create a session for this collector
                session = self._session_factory()
                collector = registration.collector_class(config, session)
                self._collectors[collector_name] = collector
                self._logger.info(f"Initialized collector: {collector_name}")
                
            except Exception as e:
                self._logger.error(f"Failed to initialize {collector_name}: {e}")
        
        # Initialize WebSocket collector separately (uses session factory)
        if self._config.websocket_config:
            try:
                self._ws_collector = MarketDataWebSocketCollector(
                    self._config.websocket_config,
                    self._session_factory,
                )
                self._logger.info("Initialized WebSocket collector")
            except Exception as e:
                self._logger.error(f"Failed to initialize WebSocket collector: {e}")
    
    def _get_collector_config(self, collector_name: str) -> Optional[CollectorConfig]:
        """Get configuration for a collector."""
        if collector_name == "crypto_news_api":
            return self._config.news_api_config
        elif collector_name == "coingecko":
            return self._config.coingecko_config
        elif collector_name == "onchain":
            return self._config.onchain_config
        return None
    
    # =========================================================
    # COLLECTION EXECUTION
    # =========================================================
    
    async def run_collection_cycle(self) -> List[IngestionResult]:
        """
        Run a single collection cycle for all REST collectors.
        
        Returns:
            List of ingestion results from all collectors
        """
        cycle_id = uuid4()
        self._run_count += 1
        started_at = datetime.utcnow()
        
        self._logger.info(f"Starting collection cycle {cycle_id}")
        
        results: List[IngestionResult] = []
        
        if self._config.parallel_collection:
            # Run collectors in parallel
            tasks = [
                self._run_collector(name, collector)
                for name, collector in self._collectors.items()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter exceptions to IngestionResults
            results = [
                r if isinstance(r, IngestionResult) 
                else self._error_to_result(r, "unknown")
                for r in results
            ]
        else:
            # Run collectors sequentially
            for name, collector in self._collectors.items():
                try:
                    result = await self._run_collector(name, collector)
                    results.append(result)
                except Exception as e:
                    results.append(self._error_to_result(e, name))
        
        # Record metrics
        self._last_run_at = datetime.utcnow()
        self._results.extend(results)
        
        for result in results:
            self._total_records_stored += result.records_stored
            self._total_errors += result.records_failed
        
        duration = (self._last_run_at - started_at).total_seconds()
        self._logger.info(
            f"Collection cycle {cycle_id} completed in {duration:.2f}s. "
            f"Stored: {sum(r.records_stored for r in results)}, "
            f"Failed: {sum(r.records_failed for r in results)}"
        )
        
        return results
    
    async def _run_collector(
        self,
        name: str,
        collector: BaseCollector,
    ) -> IngestionResult:
        """Run a single collector with error isolation."""
        try:
            self._logger.debug(f"Running collector: {name}")
            return await collector.collect()
            
        except Exception as e:
            self._logger.error(f"Collector {name} failed: {e}")
            return self._error_to_result(e, name)
    
    def _error_to_result(self, error: Exception, source: str) -> IngestionResult:
        """Convert exception to IngestionResult."""
        from data_ingestion.types import DataType
        
        return IngestionResult(
            batch_id=uuid4(),
            source=source,
            data_type=DataType.UNKNOWN,
            status=IngestionStatus.FAILED,
            records_fetched=0,
            records_stored=0,
            records_failed=0,
            errors=[str(error)],
        )
    
    # =========================================================
    # CONTINUOUS OPERATION
    # =========================================================
    
    async def start(self) -> None:
        """
        Start continuous ingestion.
        
        This runs collection cycles on a schedule and manages
        the WebSocket collector for real-time data.
        """
        self._running = True
        self._logger.info("Ingestion service started")
        
        # Start WebSocket collector in background
        ws_task = None
        if self._ws_collector:
            ws_task = asyncio.create_task(self._ws_collector.start())
        
        # Run REST collection cycles
        try:
            while self._running:
                await self.run_collection_cycle()
                
                # Wait for next cycle
                await asyncio.sleep(
                    self._config.health_check_interval_seconds
                )
        except asyncio.CancelledError:
            self._logger.info("Ingestion service cancelled")
        finally:
            # Stop WebSocket collector
            if self._ws_collector:
                await self._ws_collector.stop()
            if ws_task:
                ws_task.cancel()
    
    async def stop(self) -> None:
        """Stop ingestion service."""
        self._running = False
        
        if self._ws_collector:
            await self._ws_collector.stop()
        
        self._logger.info("Ingestion service stopped")
    
    # =========================================================
    # HEALTH & METRICS
    # =========================================================
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get aggregated health status.
        
        Returns:
            Health status dictionary
        """
        collector_health = {}
        
        for name, collector in self._collectors.items():
            collector_health[name] = {
                "source": collector.source_name,
                "healthy": True,  # TODO: Track per-collector health
            }
        
        if self._ws_collector:
            collector_health["websocket"] = self._ws_collector.get_health_status()
        
        return {
            "running": self._running,
            "run_count": self._run_count,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "collectors": collector_health,
        }
    
    def get_metrics(self) -> IngestionMetrics:
        """
        Get aggregated metrics.
        
        Returns:
            Aggregated ingestion metrics
        """
        # Aggregate from recent results
        recent_results = self._results[-100:]  # Last 100 results
        
        return IngestionMetrics(
            total_runs=self._run_count,
            total_records_fetched=sum(r.records_fetched for r in recent_results),
            total_records_stored=self._total_records_stored,
            total_records_failed=self._total_errors,
            successful_runs=len([r for r in recent_results if r.status == IngestionStatus.SUCCESS]),
            failed_runs=len([r for r in recent_results if r.status == IngestionStatus.FAILED]),
            average_duration_seconds=sum(
                r.duration_seconds for r in recent_results if r.duration_seconds
            ) / max(len(recent_results), 1),
            last_run_at=self._last_run_at,
        )
    
    def get_recent_results(self, limit: int = 10) -> List[IngestionResult]:
        """
        Get recent ingestion results.
        
        Args:
            limit: Maximum number of results to return
            
        Returns:
            List of recent IngestionResult objects
        """
        return self._results[-limit:]
    
    # =========================================================
    # COLLECTOR MANAGEMENT
    # =========================================================
    
    def register_collector(
        self,
        name: str,
        collector: BaseCollector,
    ) -> None:
        """
        Register a new collector.
        
        Args:
            name: Unique collector name
            collector: Collector instance
        """
        if name in self._collectors:
            self._logger.warning(f"Overwriting existing collector: {name}")
        
        self._collectors[name] = collector
        self._logger.info(f"Registered collector: {name}")
    
    def unregister_collector(self, name: str) -> None:
        """
        Unregister a collector.
        
        Args:
            name: Collector name to remove
        """
        if name in self._collectors:
            del self._collectors[name]
            self._logger.info(f"Unregistered collector: {name}")
    
    def get_collector_names(self) -> List[str]:
        """Get list of registered collector names."""
        return list(self._collectors.keys())
    
    def get_collector(self, name: str) -> Optional[BaseCollector]:
        """Get collector by name."""
        return self._collectors.get(name)
