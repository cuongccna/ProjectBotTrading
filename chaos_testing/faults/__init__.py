"""
Faults Package.

Fault injectors for chaos testing.
"""

from .base import (
    FaultRegistry,
    get_fault_registry,
    BaseFaultInjector,
    injection_point,
    fault_injection_scope,
    ChaosException,
    InjectedFaultException,
    TimeoutFaultException,
    ConnectionFaultException,
    DataFaultException,
    ExecutionFaultException,
    should_inject,
    random_delay,
)

from .data_faults import DataFaultInjector
from .api_faults import ApiFaultInjector
from .process_faults import ProcessFaultInjector
from .execution_faults import ExecutionFaultInjector
from .system_faults import SystemFaultInjector, ClockDriftSimulator, clock_drift


__all__ = [
    # Registry
    "FaultRegistry",
    "get_fault_registry",
    
    # Base
    "BaseFaultInjector",
    "injection_point",
    "fault_injection_scope",
    
    # Exceptions
    "ChaosException",
    "InjectedFaultException",
    "TimeoutFaultException",
    "ConnectionFaultException",
    "DataFaultException",
    "ExecutionFaultException",
    
    # Helpers
    "should_inject",
    "random_delay",
    
    # Injectors
    "DataFaultInjector",
    "ApiFaultInjector",
    "ProcessFaultInjector",
    "ExecutionFaultInjector",
    "SystemFaultInjector",
    
    # Clock drift
    "ClockDriftSimulator",
    "clock_drift",
]
