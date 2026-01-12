"""
System Risk Controller - Base Monitor.

============================================================
PURPOSE
============================================================
Abstract base class for all health monitors.

Each monitor is responsible for one category of health checks.
Monitors are:
- Fast (< 10 seconds)
- Stateless (no side effects)
- Deterministic (same input = same output)
- Fail-safe (errors = HALT)

============================================================
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
import time
import uuid
import logging

from ..types import (
    HaltEvent,
    HaltLevel,
    HaltTrigger,
    TriggerCategory,
    MonitorResult,
    MonitorError,
)


logger = logging.getLogger(__name__)


# ============================================================
# MONITOR METADATA
# ============================================================

@dataclass
class MonitorMeta:
    """
    Metadata about a monitor.
    """
    
    name: str
    """Monitor name."""
    
    category: TriggerCategory
    """Primary category this monitor covers."""
    
    description: str
    """What this monitor checks."""
    
    is_critical: bool = True
    """
    Whether this monitor is critical.
    Critical monitor failures cause HALT.
    """


# ============================================================
# BASE MONITOR
# ============================================================

class BaseMonitor(ABC):
    """
    Abstract base class for health monitors.
    
    Each monitor:
    1. Checks system health for its category
    2. Returns MonitorResult
    3. Creates HaltEvent if unhealthy
    
    If ANY check fails, the monitor returns is_healthy=False
    with a corresponding HaltEvent.
    """
    
    @property
    @abstractmethod
    def meta(self) -> MonitorMeta:
        """Get monitor metadata."""
        pass
    
    @abstractmethod
    def _check(self) -> MonitorResult:
        """
        Internal health check logic.
        
        Subclasses implement this method.
        
        Returns:
            MonitorResult
        """
        pass
    
    def check(
        self,
        timeout_seconds: float = 10.0,
    ) -> MonitorResult:
        """
        Execute health check with timeout protection.
        
        This is the main entry point. It wraps _check with:
        - Timing measurement
        - Exception handling
        - Timeout protection
        
        Args:
            timeout_seconds: Maximum time allowed
            
        Returns:
            MonitorResult (always returns, never throws)
        """
        start_time = time.perf_counter()
        
        try:
            # Run the actual check
            result = self._check()
            
            # Update timing
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            result.check_time_ms = elapsed_ms
            result.timestamp = datetime.utcnow()
            
            # Check for timeout (even if check passed)
            if elapsed_ms > timeout_seconds * 1000:
                return self._create_error_result(
                    trigger=HaltTrigger.PR_PROCESSING_TIMEOUT,
                    halt_level=HaltLevel.SOFT,
                    message=f"Monitor check exceeded timeout: {elapsed_ms:.0f}ms > {timeout_seconds * 1000}ms",
                    elapsed_ms=elapsed_ms,
                )
            
            return result
        
        except MonitorError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Monitor error in {self.meta.name}: {e}")
            return self._create_error_result(
                trigger=HaltTrigger.IN_CONTROLLER_ERROR,
                halt_level=HaltLevel.HARD,
                message=f"Monitor error: {e}",
                elapsed_ms=elapsed_ms,
            )
        
        except Exception as e:
            # Any unexpected exception = HALT
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Unexpected error in {self.meta.name}: {e}", exc_info=True)
            return self._create_error_result(
                trigger=HaltTrigger.IN_UNKNOWN_ERROR,
                halt_level=HaltLevel.HARD,
                message=f"Unexpected monitor error: {e}",
                elapsed_ms=elapsed_ms,
            )
    
    def _create_error_result(
        self,
        trigger: HaltTrigger,
        halt_level: HaltLevel,
        message: str,
        elapsed_ms: float,
    ) -> MonitorResult:
        """Create an error result with halt event."""
        event = HaltEvent(
            event_id=self._generate_event_id(),
            trigger=trigger,
            halt_level=halt_level,
            timestamp=datetime.utcnow(),
            source_monitor=self.meta.name,
            message=message,
            details={"error": True},
        )
        
        return MonitorResult(
            monitor_name=self.meta.name,
            is_healthy=False,
            halt_event=event,
            check_time_ms=elapsed_ms,
            timestamp=datetime.utcnow(),
        )
    
    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        short_uuid = uuid.uuid4().hex[:8]
        return f"HALT-{timestamp}-{short_uuid}"


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def create_healthy_result(
    monitor_name: str,
    metrics: Optional[Dict[str, Any]] = None,
) -> MonitorResult:
    """
    Create a healthy monitor result.
    
    Args:
        monitor_name: Name of the monitor
        metrics: Optional metrics
        
    Returns:
        MonitorResult with is_healthy=True
    """
    return MonitorResult(
        monitor_name=monitor_name,
        is_healthy=True,
        halt_event=None,
        metrics=metrics or {},
        timestamp=datetime.utcnow(),
    )


def create_halt_result(
    monitor_name: str,
    trigger: HaltTrigger,
    halt_level: Optional[HaltLevel] = None,
    message: str = "",
    details: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None,
) -> MonitorResult:
    """
    Create a halt monitor result.
    
    Args:
        monitor_name: Name of the monitor
        trigger: The halt trigger
        halt_level: Override halt level (uses default if None)
        message: Human-readable message
        details: Additional details
        metrics: Monitored metrics
        
    Returns:
        MonitorResult with is_healthy=False
    """
    actual_level = halt_level or trigger.get_default_halt_level()
    timestamp = datetime.utcnow()
    
    event = HaltEvent(
        event_id=f"HALT-{timestamp.strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:8]}",
        trigger=trigger,
        halt_level=actual_level,
        timestamp=timestamp,
        source_monitor=monitor_name,
        message=message,
        details=details or {},
    )
    
    return MonitorResult(
        monitor_name=monitor_name,
        is_healthy=False,
        halt_event=event,
        metrics=metrics or {},
        timestamp=timestamp,
    )
