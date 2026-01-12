"""
Core Module - State Manager.

============================================================
RESPONSIBILITY
============================================================
Manages the global state of the trading system.

- Tracks system state (running, paused, stopped, error)
- Manages state transitions with validation
- Persists state for recovery
- Provides state queries for all modules

============================================================
STATE MACHINE
============================================================
Valid states:
- INITIALIZING: System is starting up
- RUNNING: Normal operation
- PAUSED: Trading paused, monitoring active
- STOPPED: Graceful shutdown
- ERROR: Error state, requires intervention
- EMERGENCY_STOP: Permanent stop, manual restart required

============================================================
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set
import asyncio
import json
import logging
from pathlib import Path

from .exceptions import StateTransitionError


# ============================================================
# SYSTEM STATE
# ============================================================

class SystemState(Enum):
    """System state enumeration."""
    
    INITIALIZING = "initializing"
    """System is starting up."""
    
    RUNNING = "running"
    """Normal operation - all systems active."""
    
    PAUSED = "paused"
    """Trading paused, monitoring active."""
    
    STOPPED = "stopped"
    """Graceful shutdown complete."""
    
    ERROR = "error"
    """Error state, requires intervention."""
    
    EMERGENCY_STOP = "emergency_stop"
    """Permanent stop, manual restart required."""
    
    @property
    def is_trading_allowed(self) -> bool:
        """Check if trading is allowed in this state."""
        return self == SystemState.RUNNING
    
    @property
    def is_operational(self) -> bool:
        """Check if system is operational."""
        return self in (SystemState.RUNNING, SystemState.PAUSED)
    
    @property
    def is_terminal(self) -> bool:
        """Check if state is terminal (requires restart)."""
        return self in (SystemState.STOPPED, SystemState.EMERGENCY_STOP)


# ============================================================
# STATE TRANSITIONS
# ============================================================

# Valid state transitions mapping
VALID_TRANSITIONS: Dict[SystemState, Set[SystemState]] = {
    SystemState.INITIALIZING: {
        SystemState.RUNNING,
        SystemState.ERROR,
        SystemState.STOPPED,
    },
    SystemState.RUNNING: {
        SystemState.PAUSED,
        SystemState.STOPPED,
        SystemState.ERROR,
        SystemState.EMERGENCY_STOP,
    },
    SystemState.PAUSED: {
        SystemState.RUNNING,
        SystemState.STOPPED,
        SystemState.ERROR,
        SystemState.EMERGENCY_STOP,
    },
    SystemState.ERROR: {
        SystemState.RUNNING,  # After resolution
        SystemState.STOPPED,
        SystemState.EMERGENCY_STOP,
    },
    SystemState.STOPPED: set(),  # Terminal - no transitions
    SystemState.EMERGENCY_STOP: set(),  # Terminal - no transitions
}


@dataclass
class StateTransition:
    """Record of a state transition."""
    
    transition_id: str
    from_state: SystemState
    to_state: SystemState
    reason: str
    triggered_by: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "transition_id": self.transition_id,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateTransition":
        """Deserialize from dictionary."""
        return cls(
            transition_id=data["transition_id"],
            from_state=SystemState(data["from_state"]),
            to_state=SystemState(data["to_state"]),
            reason=data["reason"],
            triggered_by=data["triggered_by"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            context=data.get("context", {}),
        )


@dataclass
class StateSnapshot:
    """Snapshot of system state for persistence."""
    
    state: SystemState
    reason: str
    triggered_by: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    transition_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "state": self.state.value,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
            "timestamp": self.timestamp.isoformat(),
            "transition_count": self.transition_count,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateSnapshot":
        """Deserialize from dictionary."""
        return cls(
            state=SystemState(data["state"]),
            reason=data["reason"],
            triggered_by=data["triggered_by"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            transition_count=data.get("transition_count", 0),
        )


# ============================================================
# STATE LISTENER TYPES
# ============================================================

StateListener = Callable[[StateTransition], Awaitable[None]]


# ============================================================
# STATE MANAGER
# ============================================================

class StateManager:
    """
    Manages system state with persistence and notifications.
    
    Thread-safe state management with:
    - Valid transition enforcement
    - Persistence for crash recovery
    - Listener notifications on state change
    """
    
    def __init__(
        self,
        persistence_path: Optional[Path] = None,
        initial_state: SystemState = SystemState.INITIALIZING,
    ):
        """
        Initialize state manager.
        
        Args:
            persistence_path: Path for state persistence file
            initial_state: Initial system state
        """
        self._state = initial_state
        self._reason = "System initialization"
        self._triggered_by = "system"
        self._transition_count = 0
        self._last_transition: Optional[StateTransition] = None
        self._history: List[StateTransition] = []
        self._max_history = 100
        
        self._persistence_path = persistence_path
        self._listeners: List[StateListener] = []
        
        self._lock = asyncio.Lock()
        self._logger = logging.getLogger(__name__)
    
    @property
    def state(self) -> SystemState:
        """Get current system state."""
        return self._state
    
    @property
    def reason(self) -> str:
        """Get reason for current state."""
        return self._reason
    
    @property
    def is_trading_allowed(self) -> bool:
        """Check if trading is allowed."""
        return self._state.is_trading_allowed
    
    @property
    def is_operational(self) -> bool:
        """Check if system is operational."""
        return self._state.is_operational
    
    @property
    def is_halted(self) -> bool:
        """Check if system is halted."""
        return self._state in (SystemState.ERROR, SystemState.EMERGENCY_STOP)
    
    @property
    def last_transition(self) -> Optional[StateTransition]:
        """Get last transition."""
        return self._last_transition
    
    def get_snapshot(self) -> StateSnapshot:
        """Get current state snapshot."""
        return StateSnapshot(
            state=self._state,
            reason=self._reason,
            triggered_by=self._triggered_by,
            transition_count=self._transition_count,
        )
    
    def get_history(self, limit: int = 10) -> List[StateTransition]:
        """Get transition history."""
        return self._history[-limit:]
    
    def can_transition_to(self, target_state: SystemState) -> bool:
        """Check if transition to target state is valid."""
        valid_targets = VALID_TRANSITIONS.get(self._state, set())
        return target_state in valid_targets
    
    async def transition_to(
        self,
        target_state: SystemState,
        reason: str,
        triggered_by: str = "system",
        context: Optional[Dict[str, Any]] = None,
    ) -> StateTransition:
        """
        Transition to a new state.
        
        Args:
            target_state: Target state
            reason: Reason for transition
            triggered_by: Who/what triggered the transition
            context: Additional context
            
        Returns:
            StateTransition record
            
        Raises:
            StateTransitionError: If transition is invalid
        """
        async with self._lock:
            # Validate transition
            if not self.can_transition_to(target_state):
                raise StateTransitionError(
                    message=f"Invalid state transition: {self._state.value} -> {target_state.value}",
                    from_state=self._state.value,
                    to_state=target_state.value,
                    reason=reason,
                )
            
            # Create transition record
            self._transition_count += 1
            transition = StateTransition(
                transition_id=f"transition_{self._transition_count}",
                from_state=self._state,
                to_state=target_state,
                reason=reason,
                triggered_by=triggered_by,
                context=context or {},
            )
            
            # Apply transition
            old_state = self._state
            self._state = target_state
            self._reason = reason
            self._triggered_by = triggered_by
            self._last_transition = transition
            
            # Add to history
            self._history.append(transition)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            
            # Log transition
            self._logger.info(
                f"State transition: {old_state.value} -> {target_state.value} "
                f"| reason={reason} | triggered_by={triggered_by}"
            )
            
            # Persist state
            if self._persistence_path:
                await self._persist_state()
            
            # Notify listeners
            await self._notify_listeners(transition)
            
            return transition
    
    async def emergency_stop(
        self,
        reason: str,
        operator: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> StateTransition:
        """
        Trigger emergency stop from any state.
        
        This bypasses normal transition rules for emergencies.
        """
        async with self._lock:
            self._transition_count += 1
            transition = StateTransition(
                transition_id=f"transition_{self._transition_count}",
                from_state=self._state,
                to_state=SystemState.EMERGENCY_STOP,
                reason=f"EMERGENCY STOP: {reason}",
                triggered_by=operator,
                context=context or {},
            )
            
            old_state = self._state
            self._state = SystemState.EMERGENCY_STOP
            self._reason = reason
            self._triggered_by = operator
            self._last_transition = transition
            self._history.append(transition)
            
            self._logger.critical(
                f"EMERGENCY STOP: {old_state.value} -> emergency_stop "
                f"| reason={reason} | operator={operator}"
            )
            
            if self._persistence_path:
                await self._persist_state()
            
            await self._notify_listeners(transition)
            
            return transition
    
    def register_listener(self, listener: StateListener) -> None:
        """Register a state change listener."""
        self._listeners.append(listener)
    
    def unregister_listener(self, listener: StateListener) -> None:
        """Unregister a state change listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)
    
    async def _notify_listeners(self, transition: StateTransition) -> None:
        """Notify all listeners of state change."""
        for listener in self._listeners:
            try:
                await listener(transition)
            except Exception as e:
                self._logger.error(
                    f"State listener error: {e}",
                    exc_info=True,
                )
    
    async def _persist_state(self) -> None:
        """Persist current state to file."""
        if not self._persistence_path:
            return
        
        try:
            snapshot = self.get_snapshot()
            self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
            
            async with asyncio.Lock():
                with open(self._persistence_path, "w") as f:
                    json.dump(snapshot.to_dict(), f, indent=2)
        except Exception as e:
            self._logger.error(f"Failed to persist state: {e}")
    
    async def restore_state(self) -> Optional[StateSnapshot]:
        """
        Restore state from persistence.
        
        Returns:
            Restored snapshot or None if not found
        """
        if not self._persistence_path or not self._persistence_path.exists():
            return None
        
        try:
            with open(self._persistence_path, "r") as f:
                data = json.load(f)
            
            snapshot = StateSnapshot.from_dict(data)
            
            # Determine recovery state
            if snapshot.state == SystemState.EMERGENCY_STOP:
                # Preserve emergency stop
                self._state = SystemState.EMERGENCY_STOP
                self._reason = f"Recovered: {snapshot.reason}"
            elif snapshot.state in (SystemState.RUNNING, SystemState.PAUSED):
                # Reset to initializing for recovery
                self._state = SystemState.INITIALIZING
                self._reason = f"Recovered from: {snapshot.state.value}"
            else:
                self._state = SystemState.INITIALIZING
                self._reason = "System restart"
            
            self._triggered_by = "recovery"
            self._transition_count = snapshot.transition_count
            
            self._logger.info(
                f"State restored: previous={snapshot.state.value}, current={self._state.value}"
            )
            
            return snapshot
        except Exception as e:
            self._logger.error(f"Failed to restore state: {e}")
            return None


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "SystemState",
    "StateTransition",
    "StateSnapshot",
    "StateListener",
    "StateManager",
    "VALID_TRANSITIONS",
]
