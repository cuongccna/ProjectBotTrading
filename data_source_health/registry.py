"""
Data Source Health - Health Registry.

============================================================
CENTRAL HEALTH STATE REGISTRY
============================================================

Maintains health state for all registered data sources:
- Auto-registration of new sources
- Health record storage
- State transition tracking
- Query interface for Risk Controller

============================================================
EXTENSIBILITY
============================================================

Per requirements:
- New data sources must be auto-registered
- No code changes required in Strategy/Execution/Risk

============================================================
"""

import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set
import logging

from .config import HealthConfig, get_config
from .models import (
    HealthScore,
    HealthState,
    HealthTransition,
    SourceHealthRecord,
    SourceType,
)
from .exceptions import SourceNotFoundError


logger = logging.getLogger(__name__)


# =============================================================
# CALLBACK TYPES
# =============================================================

TransitionCallback = Callable[[HealthTransition], None]
CriticalCallback = Callable[[str, HealthScore], None]


# =============================================================
# HEALTH REGISTRY
# =============================================================


class HealthRegistry:
    """
    Central registry for all data source health states.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    
    - Stores health records for all sources
    - Auto-registers new sources
    - Tracks state transitions
    - Provides query interface
    - Notifies callbacks on state changes
    
    ============================================================
    THREAD SAFETY
    ============================================================
    
    All operations are thread-safe for concurrent access.
    
    ============================================================
    USAGE
    ============================================================
    
    ```python
    registry = HealthRegistry()
    
    # Register source
    registry.register_source("binance", SourceType.MARKET_DATA)
    
    # Update health
    registry.update_health("binance", health_score)
    
    # Query health
    health = registry.get_health("binance")
    state = registry.get_state("binance")
    
    # Get all critical sources
    critical = registry.get_sources_by_state(HealthState.CRITICAL)
    ```
    
    ============================================================
    """
    
    def __init__(self, config: Optional[HealthConfig] = None) -> None:
        """
        Initialize health registry.
        
        Args:
            config: Health configuration
        """
        self._config = config or get_config()
        self._records: Dict[str, SourceHealthRecord] = {}
        self._lock = threading.RLock()
        
        # Callbacks
        self._transition_callbacks: List[TransitionCallback] = []
        self._critical_callbacks: List[CriticalCallback] = []
        
        # Statistics
        self._total_updates = 0
        self._total_transitions = 0
        
        logger.info("HealthRegistry initialized")
    
    # =========================================================
    # REGISTRATION
    # =========================================================
    
    def register_source(
        self,
        source_name: str,
        source_type: SourceType = SourceType.UNKNOWN,
    ) -> SourceHealthRecord:
        """
        Register a new data source.
        
        If source already exists, returns existing record.
        
        Args:
            source_name: Unique name for the source
            source_type: Type of data source
            
        Returns:
            Source health record
        """
        with self._lock:
            if source_name in self._records:
                logger.debug(f"Source already registered: {source_name}")
                return self._records[source_name]
            
            record = SourceHealthRecord(
                source_name=source_name,
                source_type=source_type,
            )
            self._records[source_name] = record
            
            logger.info(
                f"Registered source: {source_name} (type={source_type.value})"
            )
            
            return record
    
    def unregister_source(self, source_name: str) -> bool:
        """
        Unregister a data source.
        
        Args:
            source_name: Name of source to remove
            
        Returns:
            True if source was removed
        """
        with self._lock:
            if source_name in self._records:
                del self._records[source_name]
                logger.info(f"Unregistered source: {source_name}")
                return True
            return False
    
    def is_registered(self, source_name: str) -> bool:
        """Check if source is registered."""
        with self._lock:
            return source_name in self._records
    
    def get_or_register(
        self,
        source_name: str,
        source_type: SourceType = SourceType.UNKNOWN,
    ) -> SourceHealthRecord:
        """
        Get existing record or register new source.
        
        This enables auto-registration of new sources.
        """
        with self._lock:
            if source_name not in self._records:
                return self.register_source(source_name, source_type)
            return self._records[source_name]
    
    # =========================================================
    # HEALTH UPDATES
    # =========================================================
    
    def update_health(
        self,
        source_name: str,
        health: HealthScore,
    ) -> Optional[HealthTransition]:
        """
        Update health for a source.
        
        Args:
            source_name: Name of the source
            health: New health score
            
        Returns:
            HealthTransition if state changed, None otherwise
        """
        with self._lock:
            # Auto-register if needed
            record = self.get_or_register(source_name, health.source_type)
            
            # Update record
            transition = record.update_health(health)
            
            # Update statistics
            self._total_updates += 1
            
            # Handle transition
            if transition:
                self._total_transitions += 1
                self._handle_transition(transition, health)
            
            return transition
    
    def _handle_transition(
        self,
        transition: HealthTransition,
        health: HealthScore,
    ) -> None:
        """Handle a state transition."""
        # Log transition
        if transition.is_degradation:
            logger.warning(
                f"[{transition.source_name}] State degraded: "
                f"{transition.from_state.value} -> {transition.to_state.value} "
                f"(score: {transition.from_score:.1f} -> {transition.to_score:.1f})"
            )
        else:
            logger.info(
                f"[{transition.source_name}] State improved: "
                f"{transition.from_state.value} -> {transition.to_state.value} "
                f"(score: {transition.from_score:.1f} -> {transition.to_score:.1f})"
            )
        
        # Notify transition callbacks
        for callback in self._transition_callbacks:
            try:
                callback(transition)
            except Exception as e:
                logger.error(f"Transition callback failed: {e}")
        
        # Handle CRITICAL transitions
        if transition.to_state == HealthState.CRITICAL:
            self._handle_critical(transition.source_name, health)
    
    def _handle_critical(
        self,
        source_name: str,
        health: HealthScore,
    ) -> None:
        """Handle source going CRITICAL."""
        logger.error(
            f"[{source_name}] SOURCE CRITICAL - "
            f"Score: {health.final_score:.1f}, "
            f"Weakest: {health.get_weakest_dimension()}"
        )
        
        # Notify critical callbacks
        for callback in self._critical_callbacks:
            try:
                callback(source_name, health)
            except Exception as e:
                logger.error(f"Critical callback failed: {e}")
        
        # Auto-disable if configured
        if self._config.auto_disable_on_critical:
            record = self._records.get(source_name)
            if record:
                # Count consecutive critical
                critical_count = sum(
                    1 for h in record.health_history[-self._config.critical_count_before_disable:]
                    if h.state == HealthState.CRITICAL
                )
                
                if critical_count >= self._config.critical_count_before_disable:
                    record.disable(f"Auto-disabled after {critical_count} consecutive CRITICAL states")
                    logger.error(f"[{source_name}] AUTO-DISABLED")
    
    # =========================================================
    # QUERIES
    # =========================================================
    
    def get_record(self, source_name: str) -> Optional[SourceHealthRecord]:
        """Get health record for a source."""
        with self._lock:
            return self._records.get(source_name)
    
    def get_health(self, source_name: str) -> Optional[HealthScore]:
        """Get current health score for a source."""
        record = self.get_record(source_name)
        if record:
            return record.current_health
        return None
    
    def get_state(self, source_name: str) -> HealthState:
        """Get current state for a source."""
        record = self.get_record(source_name)
        if record:
            return record.state
        return HealthState.UNKNOWN
    
    def get_score(self, source_name: str) -> float:
        """Get current score for a source."""
        record = self.get_record(source_name)
        if record:
            return record.score
        return 0.0
    
    def get_all_records(self) -> Dict[str, SourceHealthRecord]:
        """Get all health records."""
        with self._lock:
            return dict(self._records)
    
    def get_all_sources(self) -> List[str]:
        """Get list of all registered sources."""
        with self._lock:
            return list(self._records.keys())
    
    def get_sources_by_state(self, state: HealthState) -> List[str]:
        """Get sources with a specific state."""
        with self._lock:
            return [
                name for name, record in self._records.items()
                if record.state == state
            ]
    
    def get_sources_by_type(self, source_type: SourceType) -> List[str]:
        """Get sources of a specific type."""
        with self._lock:
            return [
                name for name, record in self._records.items()
                if record.source_type == source_type
            ]
    
    def get_healthy_sources(self) -> List[str]:
        """Get all healthy sources."""
        return self.get_sources_by_state(HealthState.HEALTHY)
    
    def get_degraded_sources(self) -> List[str]:
        """Get all degraded sources."""
        return self.get_sources_by_state(HealthState.DEGRADED)
    
    def get_critical_sources(self) -> List[str]:
        """Get all critical sources."""
        return self.get_sources_by_state(HealthState.CRITICAL)
    
    def get_usable_sources(self) -> List[str]:
        """Get all sources that are usable (HEALTHY or DEGRADED)."""
        with self._lock:
            return [
                name for name, record in self._records.items()
                if record.state.is_usable() and not record.is_disabled
            ]
    
    def get_disabled_sources(self) -> List[str]:
        """Get all manually disabled sources."""
        with self._lock:
            return [
                name for name, record in self._records.items()
                if record.is_disabled
            ]
    
    # =========================================================
    # SOURCE HEALTH CHECKS
    # =========================================================
    
    def is_source_healthy(self, source_name: str) -> bool:
        """Check if source is healthy."""
        return self.get_state(source_name) == HealthState.HEALTHY
    
    def is_source_degraded(self, source_name: str) -> bool:
        """Check if source is degraded."""
        return self.get_state(source_name) == HealthState.DEGRADED
    
    def is_source_critical(self, source_name: str) -> bool:
        """Check if source is critical."""
        return self.get_state(source_name) == HealthState.CRITICAL
    
    def is_source_usable(self, source_name: str) -> bool:
        """Check if source is usable for trading."""
        record = self.get_record(source_name)
        if record:
            return record.state.is_usable() and not record.is_disabled
        return False
    
    def should_reduce_risk(self, source_name: str) -> bool:
        """Check if risk should be reduced for this source."""
        return self.get_state(source_name).should_reduce_risk()
    
    # =========================================================
    # MANUAL CONTROLS
    # =========================================================
    
    def disable_source(self, source_name: str, reason: str) -> bool:
        """Manually disable a source."""
        with self._lock:
            record = self._records.get(source_name)
            if record:
                record.disable(reason)
                logger.warning(f"[{source_name}] Manually disabled: {reason}")
                return True
            return False
    
    def enable_source(self, source_name: str) -> bool:
        """Re-enable a manually disabled source."""
        with self._lock:
            record = self._records.get(source_name)
            if record:
                record.enable()
                logger.info(f"[{source_name}] Re-enabled")
                return True
            return False
    
    # =========================================================
    # CALLBACKS
    # =========================================================
    
    def on_transition(self, callback: TransitionCallback) -> None:
        """Register callback for state transitions."""
        self._transition_callbacks.append(callback)
    
    def on_critical(self, callback: CriticalCallback) -> None:
        """Register callback for CRITICAL state."""
        self._critical_callbacks.append(callback)
    
    # =========================================================
    # STATISTICS
    # =========================================================
    
    def get_statistics(self) -> Dict:
        """Get registry statistics."""
        with self._lock:
            states = {state: 0 for state in HealthState}
            for record in self._records.values():
                states[record.state] += 1
            
            return {
                "total_sources": len(self._records),
                "total_updates": self._total_updates,
                "total_transitions": self._total_transitions,
                "states": {
                    state.value: count
                    for state, count in states.items()
                },
                "disabled_count": len(self.get_disabled_sources()),
            }
    
    def get_summary(self) -> Dict:
        """Get summary of all source health."""
        with self._lock:
            return {
                name: {
                    "state": record.state.value,
                    "score": round(record.score, 1),
                    "disabled": record.is_disabled,
                }
                for name, record in self._records.items()
            }
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return {
            "statistics": self.get_statistics(),
            "sources": self.get_summary(),
        }
