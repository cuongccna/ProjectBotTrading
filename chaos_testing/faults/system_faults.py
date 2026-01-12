"""
System/Infrastructure Fault Injectors.

============================================================
PURPOSE
============================================================
Inject infrastructure-level faults:
- Clock drift
- Disk full
- CPU spike
- Database unavailable
- Network partition

============================================================
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Callable

from ..models import (
    FaultCategory,
    SystemFaultType,
    FaultDefinition,
    ActiveFault,
)
from .base import (
    BaseFaultInjector,
    InjectedFaultException,
    ConnectionFaultException,
)


logger = logging.getLogger(__name__)


# ============================================================
# SYSTEM FAULT INJECTOR
# ============================================================

class SystemFaultInjector(BaseFaultInjector):
    """
    Injects system/infrastructure faults.
    """
    
    def __init__(self):
        """Initialize system fault injector."""
        super().__init__(FaultCategory.SYSTEM)
    
    async def inject(self, fault_def: FaultDefinition) -> ActiveFault:
        """Inject a system fault."""
        if fault_def.category != FaultCategory.SYSTEM:
            raise ValueError(f"Invalid fault category: {fault_def.category}")
        
        active = await self.create_active_fault(fault_def)
        
        logger.warning(
            f"CHAOS: Injected system fault {fault_def.fault_type} "
            f"at {fault_def.injection_point}"
        )
        
        return active
    
    async def remove(self, injection_id: str) -> bool:
        """Remove a system fault."""
        fault = await self.registry.unregister(injection_id)
        return fault is not None


# ============================================================
# CLOCK DRIFT SIMULATOR
# ============================================================

class ClockDriftSimulator:
    """
    Simulates clock drift for testing time-sensitive operations.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._drift_seconds = 0.0
            cls._instance._enabled = False
        return cls._instance
    
    def set_drift(self, seconds: float):
        """Set clock drift in seconds."""
        self._drift_seconds = seconds
        self._enabled = True
        logger.warning(f"CHAOS: Clock drift set to {seconds}s")
    
    def clear(self):
        """Clear clock drift."""
        self._drift_seconds = 0.0
        self._enabled = False
    
    def now(self) -> datetime:
        """Get current time with drift applied."""
        if self._enabled:
            return datetime.utcnow() + timedelta(seconds=self._drift_seconds)
        return datetime.utcnow()
    
    def timestamp(self) -> float:
        """Get timestamp with drift applied."""
        if self._enabled:
            return time.time() + self._drift_seconds
        return time.time()
    
    @property
    def drift_seconds(self) -> float:
        return self._drift_seconds
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled


# Global instance
clock_drift = ClockDriftSimulator()


# ============================================================
# FAULT EXECUTION FUNCTIONS
# ============================================================

async def execute_clock_drift(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute clock drift fault."""
    drift_seconds = params.get("drift_seconds", 300)  # 5 minutes default
    drift_direction = params.get("direction", "forward")  # forward or backward
    
    if drift_direction == "backward":
        drift_seconds = -drift_seconds
    
    logger.warning(f"CHAOS: Injecting CLOCK_DRIFT fault ({drift_seconds}s)")
    
    # Set the clock drift
    clock_drift.set_drift(drift_seconds)
    
    try:
        # Execute with drifted clock
        return await original_func(*args, **kwargs)
    finally:
        # Note: drift remains active until explicitly cleared
        pass


async def execute_disk_full(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute disk full fault."""
    logger.warning("CHAOS: Injecting DISK_FULL fault")
    
    raise IOError("CHAOS: No space left on device (injected)")


async def execute_cpu_spike(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """
    Execute CPU spike fault.
    
    Simulates high CPU by introducing processing delays.
    """
    duration_seconds = params.get("duration_seconds", 5)
    intensity = params.get("intensity", 0.8)  # 0-1, how much to slow down
    
    logger.warning(f"CHAOS: Injecting CPU_SPIKE fault ({duration_seconds}s)")
    
    # Simulate CPU spike with delays
    start = time.time()
    result = None
    
    while time.time() - start < duration_seconds:
        # Busy wait to simulate CPU load
        await asyncio.sleep(0.01)  # Small sleeps to not block event loop
        
        # Try to execute the function
        if result is None:
            result = await original_func(*args, **kwargs)
    
    return result


async def execute_process_killed(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute process killed fault."""
    logger.warning("CHAOS: Injecting PROCESS_KILLED fault")
    
    raise InjectedFaultException(
        "PROCESS_KILLED",
        "Process was killed unexpectedly (injected)"
    )


async def execute_database_unavailable(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute database unavailable fault."""
    logger.warning("CHAOS: Injecting DATABASE_UNAVAILABLE fault")
    
    error_type = params.get("error_type", "connection_refused")
    
    messages = {
        "connection_refused": "Cannot connect to database: Connection refused",
        "timeout": "Database connection timed out",
        "too_many_connections": "Too many database connections",
        "read_only": "Database is in read-only mode",
        "corrupted": "Database corruption detected",
    }
    
    raise ConnectionFaultException(
        messages.get(error_type, "Database unavailable") + " (injected)"
    )


async def execute_redis_unavailable(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute Redis unavailable fault."""
    logger.warning("CHAOS: Injecting REDIS_UNAVAILABLE fault")
    
    raise ConnectionFaultException(
        "Cannot connect to Redis: Connection refused (injected)"
    )


async def execute_network_partition(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute network partition fault."""
    logger.warning("CHAOS: Injecting NETWORK_PARTITION fault")
    
    partition_type = params.get("partition_type", "complete")
    
    if partition_type == "complete":
        raise ConnectionFaultException(
            "Network partition: Cannot reach any external services (injected)"
        )
    elif partition_type == "partial":
        # Simulate partial connectivity - random failures
        if random.random() < 0.7:
            raise ConnectionFaultException(
                "Network partition: Intermittent connectivity (injected)"
            )
        return await original_func(*args, **kwargs)
    else:
        raise ConnectionFaultException(
            "Network partition (injected)"
        )


async def execute_config_corruption(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute configuration corruption fault."""
    logger.warning("CHAOS: Injecting CONFIG_CORRUPTION fault")
    
    raise InjectedFaultException(
        "CONFIG_CORRUPTION",
        "Configuration file is corrupted or invalid (injected)"
    )
