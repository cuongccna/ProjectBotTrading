"""
Monitoring Collectors - Base and System State.

============================================================
PURPOSE
============================================================
Read-only data collectors for monitoring subsystem.

PRINCIPLES:
- All collectors are READ-ONLY
- No state mutation
- No derived assumptions
- Display UNKNOWN when data unavailable

============================================================
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from decimal import Decimal

from ..models import (
    SystemMode,
    ModuleStatus,
    DataFreshness,
    SystemStateSnapshot,
    DataSourceStatus,
    ModuleHealth,
    FRESHNESS_THRESHOLDS,
    HEARTBEAT_THRESHOLDS,
)


logger = logging.getLogger(__name__)


# ============================================================
# BASE COLLECTOR
# ============================================================

class BaseCollector(ABC):
    """
    Base class for all monitoring collectors.
    
    All collectors MUST be read-only.
    """
    
    def __init__(self, name: str):
        """Initialize collector."""
        self._name = name
        self._last_collection_time: Optional[datetime] = None
        self._collection_count = 0
        self._error_count = 0
    
    @property
    def name(self) -> str:
        """Collector name."""
        return self._name
    
    @abstractmethod
    async def collect(self) -> Any:
        """
        Collect data.
        
        MUST be read-only.
        MUST return UNKNOWN/None for missing data.
        MUST NOT make assumptions.
        """
        pass
    
    async def safe_collect(self) -> Any:
        """
        Safely collect data with error handling.
        
        Never throws, returns None on error.
        """
        try:
            self._last_collection_time = datetime.utcnow()
            self._collection_count += 1
            return await self.collect()
        except Exception as e:
            self._error_count += 1
            logger.error(f"Collector {self._name} error: {e}")
            return None


# ============================================================
# SYSTEM STATE COLLECTOR
# ============================================================

class SystemStateCollector(BaseCollector):
    """
    Collects system-wide state information.
    
    READ-ONLY: Only reads from shared state stores.
    """
    
    def __init__(
        self,
        state_store: Any = None,  # Injected read-only state store
    ):
        """Initialize system state collector."""
        super().__init__("system_state")
        self._state_store = state_store
        self._start_time = datetime.utcnow()
    
    async def collect(self) -> SystemStateSnapshot:
        """Collect current system state."""
        
        # Get current mode
        mode = await self._get_current_mode()
        mode_info = await self._get_mode_change_info()
        
        # Get module health counts
        health_counts = await self._get_module_health_counts()
        
        # Get trading state
        trading_state = await self._get_trading_state()
        
        uptime = (datetime.utcnow() - self._start_time).total_seconds()
        
        return SystemStateSnapshot(
            mode=mode,
            mode_changed_at=mode_info.get("changed_at", datetime.utcnow()),
            mode_changed_by=mode_info.get("changed_by", "UNKNOWN"),
            mode_reason=mode_info.get("reason", "UNKNOWN"),
            snapshot_time=datetime.utcnow(),
            system_uptime_seconds=uptime,
            healthy_modules=health_counts.get("healthy", 0),
            degraded_modules=health_counts.get("degraded", 0),
            unhealthy_modules=health_counts.get("unhealthy", 0),
            trading_enabled=trading_state.get("enabled", False),
            active_orders_count=trading_state.get("active_orders", 0),
            open_positions_count=trading_state.get("open_positions", 0),
        )
    
    async def _get_current_mode(self) -> SystemMode:
        """Get current system mode."""
        if self._state_store is None:
            return SystemMode.INITIALIZING
        
        try:
            mode_str = await self._state_store.get("system.mode")
            if mode_str:
                return SystemMode(mode_str)
        except Exception:
            pass
        
        return SystemMode.INITIALIZING
    
    async def _get_mode_change_info(self) -> Dict[str, Any]:
        """Get mode change information."""
        if self._state_store is None:
            return {}
        
        try:
            return {
                "changed_at": await self._state_store.get("system.mode_changed_at"),
                "changed_by": await self._state_store.get("system.mode_changed_by"),
                "reason": await self._state_store.get("system.mode_reason"),
            }
        except Exception:
            return {}
    
    async def _get_module_health_counts(self) -> Dict[str, int]:
        """Get module health counts."""
        if self._state_store is None:
            return {"healthy": 0, "degraded": 0, "unhealthy": 0}
        
        try:
            modules = await self._state_store.get("modules.health") or {}
            counts = {"healthy": 0, "degraded": 0, "unhealthy": 0}
            
            for module_name, health in modules.items():
                status = health.get("status", "UNKNOWN")
                if status == "HEALTHY":
                    counts["healthy"] += 1
                elif status == "DEGRADED":
                    counts["degraded"] += 1
                else:
                    counts["unhealthy"] += 1
            
            return counts
        except Exception:
            return {"healthy": 0, "degraded": 0, "unhealthy": 0}
    
    async def _get_trading_state(self) -> Dict[str, Any]:
        """Get trading state."""
        if self._state_store is None:
            return {"enabled": False, "active_orders": 0, "open_positions": 0}
        
        try:
            return {
                "enabled": await self._state_store.get("trading.enabled") or False,
                "active_orders": await self._state_store.get("trading.active_orders") or 0,
                "open_positions": await self._state_store.get("trading.open_positions") or 0,
            }
        except Exception:
            return {"enabled": False, "active_orders": 0, "open_positions": 0}


# ============================================================
# DATA PIPELINE COLLECTOR
# ============================================================

class DataPipelineCollector(BaseCollector):
    """
    Collects data pipeline status.
    
    READ-ONLY: Only reads from data source registries.
    """
    
    def __init__(
        self,
        data_source_registry: Any = None,
    ):
        """Initialize data pipeline collector."""
        super().__init__("data_pipeline")
        self._registry = data_source_registry
        
        # Track error counts per source
        self._error_counts: Dict[str, List[datetime]] = {}
    
    async def collect(self) -> List[DataSourceStatus]:
        """Collect all data source statuses."""
        sources = []
        
        if self._registry is None:
            return sources
        
        try:
            source_names = await self._get_registered_sources()
            
            for name in source_names:
                status = await self._collect_source_status(name)
                if status:
                    sources.append(status)
        except Exception as e:
            logger.error(f"Error collecting data pipeline status: {e}")
        
        return sources
    
    async def _get_registered_sources(self) -> List[str]:
        """Get list of registered data sources."""
        try:
            if hasattr(self._registry, "list_sources"):
                return await self._registry.list_sources()
            return []
        except Exception:
            return []
    
    async def _collect_source_status(self, source_name: str) -> Optional[DataSourceStatus]:
        """Collect status for a single source."""
        try:
            info = await self._registry.get_source_info(source_name)
            if not info:
                return None
            
            last_fetch = info.get("last_fetch_time")
            freshness = self._calculate_freshness(source_name, last_fetch)
            
            # Get error counts from rolling windows
            error_counts = self._get_error_counts(source_name)
            
            return DataSourceStatus(
                source_name=source_name,
                source_type=info.get("type", "unknown"),
                last_successful_fetch=last_fetch,
                last_fetch_latency_ms=info.get("latency_ms"),
                freshness=freshness,
                error_count_1m=error_counts.get("1m", 0),
                error_count_5m=error_counts.get("5m", 0),
                error_count_1h=error_counts.get("1h", 0),
                is_stale=freshness == DataFreshness.STALE,
                has_missing_fields=info.get("missing_fields", False),
                has_abnormal_volume=info.get("abnormal_volume", False),
                last_error=info.get("last_error"),
                last_error_time=info.get("last_error_time"),
            )
        except Exception as e:
            logger.error(f"Error collecting source {source_name}: {e}")
            return None
    
    def _calculate_freshness(
        self,
        source_name: str,
        last_fetch: Optional[datetime],
    ) -> DataFreshness:
        """Calculate data freshness."""
        if last_fetch is None:
            return DataFreshness.MISSING
        
        # Get threshold for this source type
        threshold_seconds = FRESHNESS_THRESHOLDS.get(source_name, 60)
        
        age = (datetime.utcnow() - last_fetch).total_seconds()
        
        if age <= threshold_seconds:
            return DataFreshness.FRESH
        elif age <= threshold_seconds * 3:
            return DataFreshness.STALE
        else:
            return DataFreshness.MISSING
    
    def _get_error_counts(self, source_name: str) -> Dict[str, int]:
        """Get error counts for rolling windows."""
        now = datetime.utcnow()
        
        if source_name not in self._error_counts:
            return {"1m": 0, "5m": 0, "1h": 0}
        
        errors = self._error_counts[source_name]
        
        # Clean old errors (older than 1 hour)
        cutoff = now - timedelta(hours=1)
        errors = [e for e in errors if e > cutoff]
        self._error_counts[source_name] = errors
        
        # Count by window
        return {
            "1m": sum(1 for e in errors if e > now - timedelta(minutes=1)),
            "5m": sum(1 for e in errors if e > now - timedelta(minutes=5)),
            "1h": len(errors),
        }
    
    def record_error(self, source_name: str) -> None:
        """Record an error for a source (called by data pipeline)."""
        if source_name not in self._error_counts:
            self._error_counts[source_name] = []
        self._error_counts[source_name].append(datetime.utcnow())


# ============================================================
# MODULE HEALTH COLLECTOR
# ============================================================

class ModuleHealthCollector(BaseCollector):
    """
    Collects health status of all modules.
    
    READ-ONLY: Only reads from module registries.
    """
    
    def __init__(
        self,
        module_registry: Any = None,
    ):
        """Initialize module health collector."""
        super().__init__("module_health")
        self._registry = module_registry
        self._heartbeats: Dict[str, datetime] = {}
    
    async def collect(self) -> Dict[str, ModuleHealth]:
        """Collect health for all modules."""
        health_map = {}
        
        modules = await self._get_registered_modules()
        
        for module_name in modules:
            health = await self._collect_module_health(module_name)
            if health:
                health_map[module_name] = health
        
        return health_map
    
    async def _get_registered_modules(self) -> List[str]:
        """Get list of registered modules."""
        # Core modules that should always exist
        core_modules = [
            "execution_engine",
            "risk_controller",
            "trade_guard",
            "data_pipeline",
            "signal_generator",
            "reconciliation",
            "alerting",
        ]
        
        if self._registry:
            try:
                registered = await self._registry.list_modules()
                return list(set(core_modules + registered))
            except Exception:
                pass
        
        return core_modules
    
    async def _collect_module_health(self, module_name: str) -> Optional[ModuleHealth]:
        """Collect health for a single module."""
        try:
            # Get module info
            info = {}
            if self._registry:
                info = await self._registry.get_module_info(module_name) or {}
            
            # Check heartbeat
            last_heartbeat = self._heartbeats.get(module_name)
            heartbeat_interval = HEARTBEAT_THRESHOLDS.get(module_name, 30)
            
            heartbeat_missed = False
            if last_heartbeat:
                age = (datetime.utcnow() - last_heartbeat).total_seconds()
                heartbeat_missed = age > heartbeat_interval * 2
            
            # Determine status
            status = self._determine_status(info, heartbeat_missed)
            
            return ModuleHealth(
                module_name=module_name,
                module_type=info.get("type", "unknown"),
                status=status,
                status_reason=info.get("status_reason"),
                last_heartbeat=last_heartbeat,
                heartbeat_interval_seconds=heartbeat_interval,
                heartbeat_missed=heartbeat_missed,
                cpu_usage_pct=info.get("cpu_usage"),
                memory_usage_mb=info.get("memory_usage"),
                memory_limit_mb=info.get("memory_limit"),
                queue_backlog=info.get("queue_backlog"),
                queue_max_size=info.get("queue_max_size"),
                requests_per_minute=info.get("requests_per_minute"),
                errors_per_minute=info.get("errors_per_minute"),
            )
        except Exception as e:
            logger.error(f"Error collecting module health {module_name}: {e}")
            return ModuleHealth(
                module_name=module_name,
                module_type="unknown",
                status=ModuleStatus.UNKNOWN,
                status_reason=f"Collection error: {str(e)}",
                last_heartbeat=None,
                heartbeat_interval_seconds=30,
                heartbeat_missed=True,
            )
    
    def _determine_status(
        self,
        info: Dict[str, Any],
        heartbeat_missed: bool,
    ) -> ModuleStatus:
        """Determine module status."""
        if heartbeat_missed:
            return ModuleStatus.UNHEALTHY
        
        # Check explicit status
        explicit_status = info.get("status")
        if explicit_status:
            try:
                return ModuleStatus(explicit_status)
            except ValueError:
                pass
        
        # Check error rate
        errors_per_minute = info.get("errors_per_minute", 0)
        if errors_per_minute > 10:
            return ModuleStatus.UNHEALTHY
        elif errors_per_minute > 5:
            return ModuleStatus.DEGRADED
        
        # Check queue backlog
        backlog = info.get("queue_backlog", 0)
        max_size = info.get("queue_max_size", 1000)
        if max_size > 0 and backlog / max_size > 0.9:
            return ModuleStatus.DEGRADED
        
        return ModuleStatus.HEALTHY
    
    def record_heartbeat(self, module_name: str) -> None:
        """Record a heartbeat (called by modules)."""
        self._heartbeats[module_name] = datetime.utcnow()
