"""
Data Source Health - Health Manager.

============================================================
MAIN ORCHESTRATOR
============================================================

The HealthManager is the main entry point for the health
scoring system:
- Registers data sources
- Records metrics
- Triggers evaluations
- Exposes health signals

============================================================
PUBLIC INTERFACE
============================================================

For Risk Scoring Engine, Risk Budget Manager, System Risk Controller:

```python
manager = get_manager()

# Check if source is healthy
if manager.is_source_healthy("binance"):
    # Normal operation
    pass

# Get health score (0-100)
score = manager.get_score("binance")

# Get health state
state = manager.get_state("binance")  # HEALTHY, DEGRADED, CRITICAL

# Get all critical sources (for global halt decision)
critical = manager.get_critical_sources()

# Get risk multiplier (1.0 for healthy, 0.5-0.8 for degraded, 0 for critical)
multiplier = manager.get_risk_multiplier("binance")
```

============================================================
"""

import asyncio
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any
import logging

from .config import HealthConfig, get_config
from .models import (
    HealthScore,
    HealthState,
    HealthTransition,
    SourceHealthRecord,
    SourceType,
)
from .metrics import MetricsCollector, SourceMetrics
from .base import HealthScorerFactory, BaseHealthScorer
from .registry import HealthRegistry
from .exceptions import SourceNotFoundError, MetricRecordError


logger = logging.getLogger(__name__)


class HealthManager:
    """
    Main orchestrator for data source health scoring.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    
    - Central entry point for health scoring
    - Manages metrics collection
    - Coordinates health evaluation
    - Exposes health signals to Risk components
    
    ============================================================
    USAGE
    ============================================================
    
    ```python
    # Initialize
    manager = HealthManager()
    
    # Register source
    manager.register_source("binance", SourceType.MARKET_DATA)
    
    # Record metrics (call from data collectors)
    manager.record_request("binance", latency_ms=150, success=True)
    manager.record_data("binance", timestamp=now, fields=10)
    
    # Evaluate health
    health = manager.evaluate("binance")
    
    # Query health (for Risk components)
    if manager.is_source_healthy("binance"):
        # Normal trading
        pass
    elif manager.is_source_degraded("binance"):
        # Reduce position size
        size *= manager.get_risk_multiplier("binance")
    else:
        # Source critical - use fallback
        pass
    ```
    
    ============================================================
    """
    
    def __init__(
        self,
        config: Optional[HealthConfig] = None,
    ) -> None:
        """
        Initialize health manager.
        
        Args:
            config: Health configuration
        """
        self._config = config or get_config()
        
        # Core components
        self._metrics = MetricsCollector(
            max_samples=1000,
            window_seconds=self._config.metrics_window_seconds,
        )
        self._registry = HealthRegistry(self._config)
        
        # Health scorers (one per source)
        self._scorers: Dict[str, BaseHealthScorer] = {}
        self._scorers_lock = threading.RLock()
        
        # Background evaluation
        self._evaluation_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info("HealthManager initialized")
    
    # =========================================================
    # SOURCE REGISTRATION
    # =========================================================
    
    def register_source(
        self,
        source_name: str,
        source_type: SourceType = SourceType.UNKNOWN,
    ) -> None:
        """
        Register a data source for health monitoring.
        
        Args:
            source_name: Unique name for the source
            source_type: Type of data source
        """
        # Register in registry
        self._registry.register_source(source_name, source_type)
        
        # Create metrics container
        self._metrics.get_or_create_source(source_name)
        
        # Create scorer
        with self._scorers_lock:
            if source_name not in self._scorers:
                self._scorers[source_name] = HealthScorerFactory.create(
                    source_name, source_type, self._config
                )
        
        logger.debug(f"Registered source for health monitoring: {source_name}")
    
    def unregister_source(self, source_name: str) -> bool:
        """Unregister a data source."""
        with self._scorers_lock:
            if source_name in self._scorers:
                del self._scorers[source_name]
        
        self._metrics.clear_source(source_name)
        return self._registry.unregister_source(source_name)
    
    # =========================================================
    # METRIC RECORDING
    # =========================================================
    
    def record_request(
        self,
        source_name: str,
        latency_ms: float,
        success: bool,
        error_type: Optional[str] = None,
        is_timeout: bool = False,
        is_retry: bool = False,
        retry_count: int = 0,
        http_status: Optional[int] = None,
    ) -> None:
        """
        Record a request metric.
        
        Call this after each API request to a data source.
        
        Args:
            source_name: Name of the data source
            latency_ms: Request latency in milliseconds
            success: Whether request succeeded
            error_type: Type of error if failed
            is_timeout: Whether request timed out
            is_retry: Whether this was a retry
            retry_count: Number of retries attempted
            http_status: HTTP status code
        """
        try:
            # Auto-register if needed
            if not self._registry.is_registered(source_name):
                self.register_source(source_name)
            
            self._metrics.record_request(
                source_name=source_name,
                latency_ms=latency_ms,
                success=success,
                error_type=error_type,
                is_timeout=is_timeout,
                is_retry=is_retry,
                retry_count=retry_count,
                http_status=http_status,
            )
            
        except Exception as e:
            logger.warning(f"Failed to record request metric for {source_name}: {e}")
    
    def record_data(
        self,
        source_name: str,
        data_timestamp: datetime,
        fields_expected: int,
        fields_received: int,
        is_empty: bool = False,
        is_partial: bool = False,
        data_size_bytes: int = 0,
    ) -> None:
        """
        Record a data metric.
        
        Call this after receiving data from a source.
        
        Args:
            source_name: Name of the data source
            data_timestamp: When the data was generated
            fields_expected: Expected number of fields
            fields_received: Actual fields received
            is_empty: Whether response was empty
            is_partial: Whether data is partial
            data_size_bytes: Size of data in bytes
        """
        try:
            if not self._registry.is_registered(source_name):
                self.register_source(source_name)
            
            self._metrics.record_data(
                source_name=source_name,
                data_timestamp=data_timestamp,
                fields_expected=fields_expected,
                fields_received=fields_received,
                is_empty=is_empty,
                is_partial=is_partial,
                data_size_bytes=data_size_bytes,
            )
            
        except Exception as e:
            logger.warning(f"Failed to record data metric for {source_name}: {e}")
    
    def record_value(
        self,
        source_name: str,
        field_name: str,
        value: float,
    ) -> None:
        """
        Record a value for consistency tracking.
        
        Args:
            source_name: Name of the data source
            field_name: Name of the field
            value: Current value
        """
        try:
            if not self._registry.is_registered(source_name):
                self.register_source(source_name)
            
            self._metrics.record_value(source_name, field_name, value)
            
        except Exception as e:
            logger.warning(f"Failed to record value for {source_name}: {e}")
    
    def record_error(
        self,
        source_name: str,
        error_type: str,
        error_message: str,
        is_recoverable: bool = True,
    ) -> None:
        """
        Record an error.
        
        Args:
            source_name: Name of the data source
            error_type: Type of error
            error_message: Error message
            is_recoverable: Whether error is recoverable
        """
        try:
            if not self._registry.is_registered(source_name):
                self.register_source(source_name)
            
            self._metrics.record_error(
                source_name, error_type, error_message, is_recoverable
            )
            
        except Exception as e:
            logger.warning(f"Failed to record error for {source_name}: {e}")
    
    # =========================================================
    # HEALTH EVALUATION
    # =========================================================
    
    def evaluate(
        self,
        source_name: str,
        window_seconds: Optional[int] = None,
    ) -> HealthScore:
        """
        Evaluate health for a specific source.
        
        Args:
            source_name: Name of the source
            window_seconds: Time window for evaluation
            
        Returns:
            HealthScore with final score and state
        """
        # Get or create scorer
        with self._scorers_lock:
            if source_name not in self._scorers:
                # Auto-register
                self.register_source(source_name)
            
            scorer = self._scorers[source_name]
        
        # Get metrics
        metrics = self._metrics.get_or_create_source(source_name)
        
        # Evaluate
        health = scorer.evaluate(metrics, window_seconds)
        
        # Update registry
        self._registry.update_health(source_name, health)
        
        return health
    
    def evaluate_all(
        self,
        window_seconds: Optional[int] = None,
    ) -> Dict[str, HealthScore]:
        """
        Evaluate health for all registered sources.
        
        Returns:
            Dict of source name to HealthScore
        """
        results = {}
        
        for source_name in self._registry.get_all_sources():
            try:
                results[source_name] = self.evaluate(source_name, window_seconds)
            except Exception as e:
                logger.error(f"Failed to evaluate {source_name}: {e}")
        
        return results
    
    # =========================================================
    # HEALTH QUERIES (for Risk components)
    # =========================================================
    
    def get_health(self, source_name: str) -> Optional[HealthScore]:
        """Get current health score for a source."""
        return self._registry.get_health(source_name)
    
    def get_state(self, source_name: str) -> HealthState:
        """Get current health state for a source."""
        return self._registry.get_state(source_name)
    
    def get_score(self, source_name: str) -> float:
        """Get current health score (0-100) for a source."""
        return self._registry.get_score(source_name)
    
    def is_source_healthy(self, source_name: str) -> bool:
        """Check if source is HEALTHY."""
        return self._registry.is_source_healthy(source_name)
    
    def is_source_degraded(self, source_name: str) -> bool:
        """Check if source is DEGRADED."""
        return self._registry.is_source_degraded(source_name)
    
    def is_source_critical(self, source_name: str) -> bool:
        """Check if source is CRITICAL."""
        return self._registry.is_source_critical(source_name)
    
    def is_source_usable(self, source_name: str) -> bool:
        """Check if source is usable for trading."""
        return self._registry.is_source_usable(source_name)
    
    def should_reduce_risk(self, source_name: str) -> bool:
        """Check if risk should be reduced for this source."""
        return self._registry.should_reduce_risk(source_name)
    
    # =========================================================
    # RISK MULTIPLIERS (for Risk Budget Manager)
    # =========================================================
    
    def get_risk_multiplier(self, source_name: str) -> float:
        """
        Get risk multiplier based on health state.
        
        - HEALTHY:  1.0 (full risk)
        - DEGRADED: 0.5-0.8 (reduced risk, scaled by score)
        - CRITICAL: 0.0 (no risk)
        
        Returns:
            Float from 0.0 to 1.0
        """
        state = self.get_state(source_name)
        score = self.get_score(source_name)
        
        if state == HealthState.HEALTHY:
            return 1.0
        elif state == HealthState.DEGRADED:
            # Scale between 0.5 and 0.8 based on score within degraded range
            # Score 65-85 maps to 0.5-0.8
            degraded_range = self._config.thresholds.healthy_threshold - self._config.thresholds.degraded_threshold
            score_in_range = score - self._config.thresholds.degraded_threshold
            ratio = score_in_range / degraded_range if degraded_range > 0 else 0.5
            return 0.5 + (ratio * 0.3)  # 0.5 to 0.8
        else:
            # CRITICAL or UNKNOWN
            return 0.0
    
    def get_aggregate_risk_multiplier(self) -> float:
        """
        Get aggregate risk multiplier across all sources.
        
        Uses minimum multiplier (most conservative).
        
        Returns:
            Float from 0.0 to 1.0
        """
        sources = self._registry.get_all_sources()
        if not sources:
            return 1.0
        
        multipliers = [self.get_risk_multiplier(s) for s in sources]
        return min(multipliers)
    
    # =========================================================
    # BATCH QUERIES
    # =========================================================
    
    def get_healthy_sources(self) -> List[str]:
        """Get all healthy sources."""
        return self._registry.get_healthy_sources()
    
    def get_degraded_sources(self) -> List[str]:
        """Get all degraded sources."""
        return self._registry.get_degraded_sources()
    
    def get_critical_sources(self) -> List[str]:
        """Get all critical sources."""
        return self._registry.get_critical_sources()
    
    def get_usable_sources(self) -> List[str]:
        """Get all usable sources (HEALTHY or DEGRADED)."""
        return self._registry.get_usable_sources()
    
    def get_all_sources(self) -> List[str]:
        """Get all registered sources."""
        return self._registry.get_all_sources()
    
    # =========================================================
    # MANUAL CONTROLS
    # =========================================================
    
    def disable_source(self, source_name: str, reason: str) -> bool:
        """Manually disable a source."""
        return self._registry.disable_source(source_name, reason)
    
    def enable_source(self, source_name: str) -> bool:
        """Re-enable a disabled source."""
        return self._registry.enable_source(source_name)
    
    # =========================================================
    # CALLBACKS
    # =========================================================
    
    def on_transition(self, callback: Callable[[HealthTransition], None]) -> None:
        """Register callback for state transitions."""
        self._registry.on_transition(callback)
    
    def on_critical(self, callback: Callable[[str, HealthScore], None]) -> None:
        """Register callback for CRITICAL state (for Risk Controller)."""
        self._registry.on_critical(callback)
    
    # =========================================================
    # BACKGROUND EVALUATION
    # =========================================================
    
    async def start_background_evaluation(self) -> None:
        """Start background health evaluation loop."""
        if self._running:
            return
        
        self._running = True
        self._evaluation_task = asyncio.create_task(self._evaluation_loop())
        logger.info("Started background health evaluation")
    
    async def stop_background_evaluation(self) -> None:
        """Stop background health evaluation."""
        self._running = False
        if self._evaluation_task:
            self._evaluation_task.cancel()
            try:
                await self._evaluation_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped background health evaluation")
    
    async def _evaluation_loop(self) -> None:
        """Background evaluation loop."""
        while self._running:
            try:
                # Evaluate all sources
                self.evaluate_all()
                
                # Wait for next interval
                await asyncio.sleep(self._config.evaluation_interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Background evaluation error: {e}")
                await asyncio.sleep(5)  # Brief pause on error
    
    # =========================================================
    # DIAGNOSTICS
    # =========================================================
    
    def get_statistics(self) -> Dict:
        """Get health system statistics."""
        return {
            "registry": self._registry.get_statistics(),
            "metrics": self._metrics.to_dict(),
            "scorers": len(self._scorers),
            "running": self._running,
        }
    
    def get_summary(self) -> Dict:
        """Get summary of all source health."""
        return self._registry.get_summary()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return {
            "statistics": self.get_statistics(),
            "summary": self.get_summary(),
        }


# =============================================================
# GLOBAL MANAGER SINGLETON
# =============================================================


_default_manager: Optional[HealthManager] = None
_manager_lock = threading.Lock()


def get_manager() -> HealthManager:
    """
    Get the global health manager.
    
    Creates one if it doesn't exist.
    """
    global _default_manager
    
    with _manager_lock:
        if _default_manager is None:
            _default_manager = HealthManager()
        return _default_manager


def set_manager(manager: HealthManager) -> None:
    """Set the global health manager."""
    global _default_manager
    
    with _manager_lock:
        _default_manager = manager
