"""
Process Fault Injectors.

============================================================
PURPOSE
============================================================
Inject faults in process/module behavior:
- Module crashes
- Infinite loops
- High latency
- Memory exhaustion
- Deadlocks

============================================================
"""

import asyncio
import logging
import random
import sys
import time
from typing import Dict, Any, Callable

from ..models import (
    FaultCategory,
    ProcessFaultType,
    FaultDefinition,
    ActiveFault,
)
from .base import (
    BaseFaultInjector,
    InjectedFaultException,
)


logger = logging.getLogger(__name__)


# ============================================================
# PROCESS FAULT INJECTOR
# ============================================================

class ProcessFaultInjector(BaseFaultInjector):
    """
    Injects process/module faults.
    """
    
    def __init__(self):
        """Initialize process fault injector."""
        super().__init__(FaultCategory.PROCESS)
    
    async def inject(self, fault_def: FaultDefinition) -> ActiveFault:
        """Inject a process fault."""
        if fault_def.category != FaultCategory.PROCESS:
            raise ValueError(f"Invalid fault category: {fault_def.category}")
        
        active = await self.create_active_fault(fault_def)
        
        logger.warning(
            f"CHAOS: Injected process fault {fault_def.fault_type} "
            f"at {fault_def.injection_point}"
        )
        
        return active
    
    async def remove(self, injection_id: str) -> bool:
        """Remove a process fault."""
        fault = await self.registry.unregister(injection_id)
        return fault is not None


# ============================================================
# FAULT EXECUTION FUNCTIONS
# ============================================================

async def execute_module_crash(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute module crash fault."""
    logger.warning("CHAOS: Injecting MODULE_CRASH fault")
    
    crash_type = params.get("crash_type", "exception")
    
    if crash_type == "exception":
        raise InjectedFaultException(
            "MODULE_CRASH",
            "Module crashed unexpectedly (injected)"
        )
    elif crash_type == "runtime_error":
        raise RuntimeError("CHAOS: Simulated runtime error")
    elif crash_type == "assertion":
        assert False, "CHAOS: Simulated assertion failure"
    else:
        raise SystemError("CHAOS: Simulated system error")


async def execute_infinite_loop(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """
    Execute infinite loop fault.
    
    NOTE: This is bounded to prevent actual infinite loops.
    The loop runs for max_seconds before raising an exception.
    """
    max_seconds = params.get("max_seconds", 60)
    logger.warning(f"CHAOS: Injecting INFINITE_LOOP fault (max {max_seconds}s)")
    
    start = time.time()
    iteration = 0
    
    while True:
        iteration += 1
        await asyncio.sleep(0.1)  # Yield to event loop
        
        elapsed = time.time() - start
        if elapsed >= max_seconds:
            raise InjectedFaultException(
                "INFINITE_LOOP",
                f"Simulated infinite loop ran for {elapsed:.1f}s ({iteration} iterations)"
            )


async def execute_high_latency(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute high latency fault."""
    min_latency = params.get("min_latency_ms", 1000)
    max_latency = params.get("max_latency_ms", 10000)
    
    latency_ms = random.randint(min_latency, max_latency)
    latency_s = latency_ms / 1000.0
    
    logger.warning(f"CHAOS: Injecting HIGH_LATENCY fault ({latency_ms}ms)")
    
    await asyncio.sleep(latency_s)
    
    # Continue with original function after latency
    return await original_func(*args, **kwargs)


async def execute_memory_exhaustion(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """
    Execute memory exhaustion fault.
    
    NOTE: This simulates memory pressure, not actual exhaustion.
    It allocates a bounded amount of memory then releases it.
    """
    logger.warning("CHAOS: Injecting MEMORY_EXHAUSTION fault")
    
    # Simulate by raising MemoryError
    # We don't actually exhaust memory as that would crash the system
    raise MemoryError("CHAOS: Simulated memory exhaustion")


async def execute_deadlock(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """
    Execute deadlock fault.
    
    Simulates a deadlock by hanging until timeout.
    """
    timeout = params.get("timeout_seconds", 30)
    logger.warning(f"CHAOS: Injecting DEADLOCK fault (timeout {timeout}s)")
    
    await asyncio.sleep(timeout)
    
    raise InjectedFaultException(
        "DEADLOCK",
        f"Simulated deadlock (hung for {timeout}s)"
    )


async def execute_unhandled_exception(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute unhandled exception fault."""
    logger.warning("CHAOS: Injecting UNHANDLED_EXCEPTION fault")
    
    exception_type = params.get("exception_type", "generic")
    
    exceptions = {
        "generic": Exception("CHAOS: Unhandled exception"),
        "value": ValueError("CHAOS: Invalid value"),
        "type": TypeError("CHAOS: Type mismatch"),
        "key": KeyError("CHAOS: Missing key"),
        "index": IndexError("CHAOS: Index out of range"),
        "attribute": AttributeError("CHAOS: Attribute not found"),
        "zero_division": ZeroDivisionError("CHAOS: Division by zero"),
    }
    
    raise exceptions.get(exception_type, Exception("CHAOS: Unknown exception"))


async def execute_queue_overflow(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute queue overflow fault."""
    logger.warning("CHAOS: Injecting QUEUE_OVERFLOW fault")
    
    raise InjectedFaultException(
        "QUEUE_OVERFLOW",
        "Queue is full, cannot accept more items (injected)"
    )


async def execute_heartbeat_miss(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute heartbeat miss fault."""
    logger.warning("CHAOS: Injecting HEARTBEAT_MISS fault")
    
    # Simulate missing heartbeat by delaying response
    delay = params.get("delay_seconds", 60)
    await asyncio.sleep(delay)
    
    raise InjectedFaultException(
        "HEARTBEAT_MISS",
        f"Heartbeat not received for {delay}s (injected)"
    )
