"""
System Risk Controller - Infrastructure Monitor.

============================================================
PURPOSE
============================================================
Monitors infrastructure health.

HALT TRIGGERS:
- IF_VPS_UNSTABLE: VPS instability
- IF_NETWORK_LATENCY: Network latency spikes
- IF_SERVICE_CRASH: Service crash or deadlock
- IF_CLOCK_DESYNC: Clock desynchronization
- IF_MEMORY_EXHAUSTED: Memory exhaustion
- IF_DISK_EXHAUSTED: Disk space exhausted
- IF_DATABASE_ERROR: Database failures

============================================================
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import psutil
import os

from ..types import (
    HaltTrigger,
    HaltLevel,
    TriggerCategory,
    MonitorResult,
)
from ..config import InfrastructureConfig
from .base import (
    BaseMonitor,
    MonitorMeta,
    create_healthy_result,
    create_halt_result,
)


# ============================================================
# INFRASTRUCTURE STATE SNAPSHOT
# ============================================================

@dataclass
class InfrastructureStateSnapshot:
    """
    Snapshot of current infrastructure state.
    """
    
    # Network
    exchange_latency_ms: float = 0.0
    """Latency to exchange in ms."""
    
    latency_spikes_last_hour: int = 0
    """Number of latency spikes in last hour."""
    
    network_available: bool = True
    """Whether network is available."""
    
    # Clock
    clock_drift_ms: float = 0.0
    """Clock drift from NTP in ms."""
    
    ntp_synced: bool = True
    """Whether clock is synced with NTP."""
    
    last_ntp_check: Optional[datetime] = None
    """When NTP was last checked."""
    
    # Memory
    memory_usage_pct: float = 0.0
    """Memory usage percentage."""
    
    memory_available_mb: float = 0.0
    """Available memory in MB."""
    
    # Disk
    disk_usage_pct: float = 0.0
    """Disk usage percentage."""
    
    disk_available_mb: float = 0.0
    """Available disk space in MB."""
    
    # CPU
    cpu_usage_pct: float = 0.0
    """CPU usage percentage."""
    
    # Database
    database_connected: bool = True
    """Whether database is connected."""
    
    database_latency_ms: float = 0.0
    """Database query latency."""
    
    database_failures_last_hour: int = 0
    """Database failures in last hour."""
    
    # Services
    critical_services_running: bool = True
    """Whether all critical services are running."""
    
    service_errors: List[str] = field(default_factory=list)
    """Recent service errors."""
    
    # VPS
    system_uptime_seconds: float = 0.0
    """System uptime."""
    
    process_restarts_last_hour: int = 0
    """Process restarts in last hour."""


# ============================================================
# INFRASTRUCTURE MONITOR
# ============================================================

class InfrastructureMonitor(BaseMonitor):
    """
    Monitors infrastructure health.
    
    Checks:
    1. Network connectivity and latency
    2. Clock synchronization
    3. Memory usage
    4. Disk usage
    5. CPU usage
    6. Database health
    7. Service health
    """
    
    def __init__(
        self,
        config: InfrastructureConfig,
    ):
        """
        Initialize monitor.
        
        Args:
            config: Infrastructure configuration
        """
        self._config = config
        self._last_infra_state: Optional[InfrastructureStateSnapshot] = None
    
    @property
    def meta(self) -> MonitorMeta:
        return MonitorMeta(
            name="InfrastructureMonitor",
            category=TriggerCategory.INFRASTRUCTURE,
            description="Monitors infrastructure health",
            is_critical=True,
        )
    
    def update_state(self, state: InfrastructureStateSnapshot) -> None:
        """
        Update the infrastructure state for monitoring.
        
        Args:
            state: Current infrastructure state
        """
        self._last_infra_state = state
    
    def _check(self) -> MonitorResult:
        """
        Perform infrastructure health checks.
        """
        # If no state provided, gather basic metrics ourselves
        if self._last_infra_state is None:
            state = self._gather_basic_metrics()
        else:
            state = self._last_infra_state
        
        # Check 1: Database (critical for operation)
        result = self._check_database(state)
        if result is not None:
            return result
        
        # Check 2: Clock Sync
        result = self._check_clock_sync(state)
        if result is not None:
            return result
        
        # Check 3: Network
        result = self._check_network(state)
        if result is not None:
            return result
        
        # Check 4: Memory
        result = self._check_memory(state)
        if result is not None:
            return result
        
        # Check 5: Disk
        result = self._check_disk(state)
        if result is not None:
            return result
        
        # Check 6: CPU
        result = self._check_cpu(state)
        if result is not None:
            return result
        
        # Check 7: Services
        result = self._check_services(state)
        if result is not None:
            return result
        
        # All checks passed
        return create_healthy_result(
            monitor_name=self.meta.name,
            metrics={
                "exchange_latency_ms": state.exchange_latency_ms,
                "clock_drift_ms": state.clock_drift_ms,
                "memory_usage_pct": state.memory_usage_pct,
                "disk_usage_pct": state.disk_usage_pct,
                "cpu_usage_pct": state.cpu_usage_pct,
                "database_connected": state.database_connected,
            },
        )
    
    def _gather_basic_metrics(self) -> InfrastructureStateSnapshot:
        """Gather basic metrics from the system."""
        state = InfrastructureStateSnapshot()
        
        try:
            # Memory
            memory = psutil.virtual_memory()
            state.memory_usage_pct = memory.percent
            state.memory_available_mb = memory.available / (1024 * 1024)
            
            # Disk
            disk = psutil.disk_usage('/')
            state.disk_usage_pct = disk.percent
            state.disk_available_mb = disk.free / (1024 * 1024)
            
            # CPU
            state.cpu_usage_pct = psutil.cpu_percent(interval=0.1)
            
        except Exception:
            pass  # Use defaults if gathering fails
        
        return state
    
    def _check_database(
        self,
        state: InfrastructureStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check database health."""
        if not state.database_connected:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.IF_DATABASE_ERROR,
                halt_level=HaltLevel.HARD,
                message="Database is not connected",
                details={"database_connected": False},
            )
        
        # Check failure rate
        if state.database_failures_last_hour >= self._config.max_db_connection_failures:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.IF_DATABASE_ERROR,
                halt_level=HaltLevel.HARD,
                message=f"Too many database failures: {state.database_failures_last_hour}/hour",
                details={
                    "failures": state.database_failures_last_hour,
                    "threshold": self._config.max_db_connection_failures,
                },
            )
        
        return None
    
    def _check_clock_sync(
        self,
        state: InfrastructureStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check clock synchronization."""
        if self._config.ntp_sync_required and not state.ntp_synced:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.IF_CLOCK_DESYNC,
                halt_level=HaltLevel.HARD,
                message="Clock is not synchronized with NTP",
                details={"ntp_synced": False},
            )
        
        if abs(state.clock_drift_ms) > self._config.max_clock_drift_ms:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.IF_CLOCK_DESYNC,
                halt_level=HaltLevel.HARD,
                message=f"Clock drift too high: {state.clock_drift_ms:.0f}ms",
                details={
                    "clock_drift_ms": state.clock_drift_ms,
                    "max_drift_ms": self._config.max_clock_drift_ms,
                },
            )
        
        return None
    
    def _check_network(
        self,
        state: InfrastructureStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check network health."""
        if not state.network_available:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.IF_NETWORK_LATENCY,
                halt_level=HaltLevel.HARD,
                message="Network is not available",
                details={"network_available": False},
            )
        
        # Check latency
        if state.exchange_latency_ms > self._config.max_network_latency_ms:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.IF_NETWORK_LATENCY,
                halt_level=HaltLevel.SOFT,
                message=f"Network latency too high: {state.exchange_latency_ms:.0f}ms",
                details={
                    "latency_ms": state.exchange_latency_ms,
                    "max_latency_ms": self._config.max_network_latency_ms,
                },
            )
        
        # Check latency spikes
        if state.latency_spikes_last_hour >= self._config.max_latency_spikes_per_hour:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.IF_NETWORK_LATENCY,
                halt_level=HaltLevel.SOFT,
                message=f"Too many latency spikes: {state.latency_spikes_last_hour}/hour",
                details={
                    "spikes": state.latency_spikes_last_hour,
                    "threshold": self._config.max_latency_spikes_per_hour,
                },
            )
        
        return None
    
    def _check_memory(
        self,
        state: InfrastructureStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check memory usage."""
        if state.memory_usage_pct >= self._config.max_memory_usage_pct:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.IF_MEMORY_EXHAUSTED,
                halt_level=HaltLevel.HARD,
                message=f"Memory usage critical: {state.memory_usage_pct:.1f}%",
                details={
                    "usage_pct": state.memory_usage_pct,
                    "threshold_pct": self._config.max_memory_usage_pct,
                    "available_mb": state.memory_available_mb,
                },
            )
        
        # Warning threshold
        if state.memory_usage_pct >= self._config.memory_warning_pct:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.IF_MEMORY_EXHAUSTED,
                halt_level=HaltLevel.SOFT,
                message=f"Memory usage warning: {state.memory_usage_pct:.1f}%",
                details={
                    "usage_pct": state.memory_usage_pct,
                    "warning_pct": self._config.memory_warning_pct,
                },
            )
        
        return None
    
    def _check_disk(
        self,
        state: InfrastructureStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check disk usage."""
        if state.disk_available_mb < self._config.min_disk_space_mb:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.IF_DISK_EXHAUSTED,
                halt_level=HaltLevel.HARD,
                message=f"Disk space critical: {state.disk_available_mb:.0f}MB remaining",
                details={
                    "available_mb": state.disk_available_mb,
                    "min_required_mb": self._config.min_disk_space_mb,
                },
            )
        
        # Warning threshold
        if state.disk_available_mb < self._config.disk_warning_mb:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.IF_DISK_EXHAUSTED,
                halt_level=HaltLevel.SOFT,
                message=f"Disk space warning: {state.disk_available_mb:.0f}MB remaining",
                details={
                    "available_mb": state.disk_available_mb,
                    "warning_mb": self._config.disk_warning_mb,
                },
            )
        
        return None
    
    def _check_cpu(
        self,
        state: InfrastructureStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check CPU usage."""
        if state.cpu_usage_pct >= self._config.max_cpu_usage_pct:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.IF_VPS_UNSTABLE,
                halt_level=HaltLevel.SOFT,
                message=f"CPU usage critical: {state.cpu_usage_pct:.1f}%",
                details={
                    "usage_pct": state.cpu_usage_pct,
                    "threshold_pct": self._config.max_cpu_usage_pct,
                },
            )
        
        # Warning threshold
        if state.cpu_usage_pct >= self._config.cpu_warning_pct:
            # Just log, don't halt for CPU warning
            pass
        
        return None
    
    def _check_services(
        self,
        state: InfrastructureStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check critical services."""
        if not state.critical_services_running:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.IF_SERVICE_CRASH,
                halt_level=HaltLevel.EMERGENCY,
                message="Critical services are not running",
                details={
                    "service_errors": state.service_errors,
                },
            )
        
        return None
