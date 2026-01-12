"""
Base Fault Injector.

============================================================
PURPOSE
============================================================
Base class and infrastructure for fault injection.

SAFETY:
- Fault injection NEVER modifies real capital
- All injections are tracked and auditable
- Injections can be disabled instantly

============================================================
"""

import asyncio
import functools
import logging
import random
import time
import uuid
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable, TypeVar, Set

from ..models import (
    FaultCategory,
    FaultIntensity,
    FaultDefinition,
    ActiveFault,
)


logger = logging.getLogger(__name__)


# ============================================================
# TYPE DEFINITIONS
# ============================================================

T = TypeVar('T')
FaultHandler = Callable[[ActiveFault], Any]


# ============================================================
# FAULT REGISTRY
# ============================================================

class FaultRegistry:
    """
    Global registry of active faults.
    
    Thread-safe singleton for tracking injected faults.
    """
    
    _instance: Optional["FaultRegistry"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize the registry."""
        self._active_faults: Dict[str, ActiveFault] = {}
        self._fault_history: List[ActiveFault] = []
        self._enabled = True
        self._injection_points: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()
    
    @property
    def is_enabled(self) -> bool:
        """Check if fault injection is enabled."""
        return self._enabled
    
    def enable(self) -> None:
        """Enable fault injection globally."""
        self._enabled = True
        logger.warning("CHAOS: Fault injection ENABLED")
    
    def disable(self) -> None:
        """Disable fault injection globally."""
        self._enabled = False
        self.clear_all()
        logger.warning("CHAOS: Fault injection DISABLED")
    
    async def register(self, fault: ActiveFault) -> None:
        """Register an active fault."""
        async with self._lock:
            self._active_faults[fault.injection_id] = fault
            
            # Track by injection point
            point = fault.fault_definition.injection_point
            if point not in self._injection_points:
                self._injection_points[point] = set()
            self._injection_points[point].add(fault.injection_id)
            
            logger.info(
                f"CHAOS: Registered fault {fault.injection_id} "
                f"at {point} ({fault.fault_definition.fault_type})"
            )
    
    async def unregister(self, injection_id: str) -> Optional[ActiveFault]:
        """Unregister an active fault."""
        async with self._lock:
            fault = self._active_faults.pop(injection_id, None)
            if fault:
                fault.is_active = False
                self._fault_history.append(fault)
                
                # Remove from injection points
                point = fault.fault_definition.injection_point
                if point in self._injection_points:
                    self._injection_points[point].discard(injection_id)
                
                logger.info(f"CHAOS: Unregistered fault {injection_id}")
            return fault
    
    def get_faults_at(self, injection_point: str) -> List[ActiveFault]:
        """Get all active faults at an injection point."""
        if not self._enabled:
            return []
        
        fault_ids = self._injection_points.get(injection_point, set())
        return [
            self._active_faults[fid]
            for fid in fault_ids
            if fid in self._active_faults
        ]
    
    def get_all_active(self) -> List[ActiveFault]:
        """Get all active faults."""
        return list(self._active_faults.values())
    
    def clear_all(self) -> int:
        """Clear all active faults. Returns count cleared."""
        count = len(self._active_faults)
        for fault in self._active_faults.values():
            fault.is_active = False
            self._fault_history.append(fault)
        self._active_faults.clear()
        self._injection_points.clear()
        logger.warning(f"CHAOS: Cleared {count} active faults")
        return count
    
    def get_history(self, limit: int = 100) -> List[ActiveFault]:
        """Get fault injection history."""
        return self._fault_history[-limit:]


# Global registry instance
_registry = FaultRegistry()


def get_fault_registry() -> FaultRegistry:
    """Get the global fault registry."""
    return _registry


# ============================================================
# BASE FAULT INJECTOR
# ============================================================

class BaseFaultInjector(ABC):
    """
    Base class for fault injectors.
    
    Each injector handles a specific category of faults.
    """
    
    def __init__(self, category: FaultCategory):
        """Initialize injector."""
        self.category = category
        self.registry = get_fault_registry()
        self._handlers: Dict[str, FaultHandler] = {}
    
    @abstractmethod
    async def inject(self, fault_def: FaultDefinition) -> ActiveFault:
        """
        Inject a fault based on definition.
        
        Returns the active fault instance.
        """
        pass
    
    @abstractmethod
    async def remove(self, injection_id: str) -> bool:
        """
        Remove an injected fault.
        
        Returns True if removed successfully.
        """
        pass
    
    def register_handler(self, fault_type: str, handler: FaultHandler) -> None:
        """Register a handler for a fault type."""
        self._handlers[fault_type] = handler
    
    def get_handler(self, fault_type: str) -> Optional[FaultHandler]:
        """Get handler for a fault type."""
        return self._handlers.get(fault_type)
    
    async def create_active_fault(
        self,
        fault_def: FaultDefinition,
    ) -> ActiveFault:
        """Create an active fault from definition."""
        now = datetime.utcnow()
        expires_at = None
        
        if fault_def.duration_seconds:
            expires_at = now + timedelta(seconds=fault_def.duration_seconds)
        
        active = ActiveFault(
            injection_id=str(uuid.uuid4()),
            fault_definition=fault_def,
            injected_at=now,
            expires_at=expires_at,
        )
        
        await self.registry.register(active)
        return active


# ============================================================
# INJECTION POINT DECORATOR
# ============================================================

def injection_point(point_name: str):
    """
    Decorator to mark a function as a fault injection point.
    
    Usage:
        @injection_point("data_pipeline.fetch_price")
        async def fetch_price(symbol: str) -> Price:
            ...
    
    When a fault is registered at this point, it will be triggered
    when the decorated function is called.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            registry = get_fault_registry()
            
            if not registry.is_enabled:
                return await func(*args, **kwargs)
            
            # Check for faults at this point
            faults = registry.get_faults_at(point_name)
            
            for fault in faults:
                if not fault.is_active:
                    continue
                
                # Check if fault should trigger based on intensity
                if not fault.should_trigger(fault.fault_definition.intensity):
                    continue
                
                # Update fault stats
                fault.injection_count += 1
                fault.last_triggered = datetime.utcnow()
                
                # Get fault type and execute fault behavior
                fault_type = fault.fault_definition.fault_type
                params = fault.fault_definition.parameters
                
                # Execute fault
                result = await _execute_fault(fault_type, params, func, args, kwargs)
                if result is not None:
                    return result
            
            # No fault triggered, execute normally
            return await func(*args, **kwargs)
        
        # Store point name for introspection
        wrapper._injection_point = point_name
        return wrapper
    
    return decorator


async def _execute_fault(
    fault_type: str,
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute a fault behavior."""
    # Import fault behaviors (lazy to avoid circular imports)
    from . import data_faults, api_faults, process_faults, execution_faults, system_faults
    
    # Find and execute the fault
    fault_modules = [data_faults, api_faults, process_faults, execution_faults, system_faults]
    
    for module in fault_modules:
        if hasattr(module, f"execute_{fault_type.lower()}"):
            handler = getattr(module, f"execute_{fault_type.lower()}")
            return await handler(params, original_func, args, kwargs)
    
    # Unknown fault type - log and continue
    logger.warning(f"CHAOS: Unknown fault type {fault_type}")
    return None


# ============================================================
# CONTEXT MANAGER FOR FAULT INJECTION
# ============================================================

@asynccontextmanager
async def fault_injection_scope(
    fault_def: FaultDefinition,
    injector: BaseFaultInjector,
):
    """
    Context manager for scoped fault injection.
    
    Fault is automatically removed when scope exits.
    
    Usage:
        async with fault_injection_scope(fault_def, injector) as active:
            # Fault is active here
            await run_test()
        # Fault is removed
    """
    active = await injector.inject(fault_def)
    try:
        yield active
    finally:
        await injector.remove(active.injection_id)


# ============================================================
# FAULT INJECTION EXCEPTIONS
# ============================================================

class ChaosException(Exception):
    """Base exception for chaos testing."""
    pass


class InjectedFaultException(ChaosException):
    """Exception raised by injected faults."""
    
    def __init__(
        self,
        fault_type: str,
        message: str,
        injection_id: Optional[str] = None,
    ):
        self.fault_type = fault_type
        self.injection_id = injection_id
        super().__init__(f"[CHAOS:{fault_type}] {message}")


class TimeoutFaultException(InjectedFaultException):
    """Timeout fault exception."""
    
    def __init__(self, message: str = "Operation timed out"):
        super().__init__("TIMEOUT", message)


class ConnectionFaultException(InjectedFaultException):
    """Connection fault exception."""
    
    def __init__(self, message: str = "Connection failed"):
        super().__init__("CONNECTION", message)


class DataFaultException(InjectedFaultException):
    """Data fault exception."""
    
    def __init__(self, message: str = "Data error"):
        super().__init__("DATA", message)


class ExecutionFaultException(InjectedFaultException):
    """Execution fault exception."""
    
    def __init__(self, message: str = "Execution error"):
        super().__init__("EXECUTION", message)


# ============================================================
# FAULT PROBABILITY HELPERS
# ============================================================

def should_inject(intensity: FaultIntensity) -> bool:
    """Determine if fault should be injected based on intensity."""
    probability = {
        FaultIntensity.LOW: 0.1,
        FaultIntensity.MEDIUM: 0.5,
        FaultIntensity.HIGH: 0.9,
        FaultIntensity.ALWAYS: 1.0,
    }
    return random.random() < probability.get(intensity, 1.0)


def random_delay(min_ms: int = 100, max_ms: int = 5000) -> float:
    """Generate random delay in seconds."""
    return random.randint(min_ms, max_ms) / 1000.0
