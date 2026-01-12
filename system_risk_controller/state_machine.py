"""
System Risk Controller - State Machine.

============================================================
PURPOSE
============================================================
Manages system state transitions with strict rules.

STATE TRANSITION RULES:
- RUNNING → DEGRADED: Auto on soft issues
- RUNNING → HALTED_SOFT: On SOFT halt trigger
- RUNNING → HALTED_HARD: On HARD halt trigger
- RUNNING → EMERGENCY_LOCKDOWN: On EMERGENCY halt trigger

- DEGRADED → RUNNING: Auto when issue resolved
- DEGRADED → HALTED_SOFT: On SOFT halt trigger
- DEGRADED → HALTED_HARD: On HARD halt trigger
- DEGRADED → EMERGENCY_LOCKDOWN: On EMERGENCY halt trigger

- HALTED_SOFT → RUNNING: Auto when issue resolved
- HALTED_SOFT → HALTED_HARD: On HARD halt trigger
- HALTED_SOFT → EMERGENCY_LOCKDOWN: On EMERGENCY halt trigger

- HALTED_HARD → RUNNING: MANUAL RESUME REQUIRED
- HALTED_HARD → EMERGENCY_LOCKDOWN: On EMERGENCY halt trigger

- EMERGENCY_LOCKDOWN → RUNNING: MANUAL RESUME REQUIRED + CONFIRMATION

CRITICAL CONSTRAINT:
- Higher severity state always takes precedence
- No automatic resume from HARD or EMERGENCY states
- All transitions logged for audit

============================================================
"""

from datetime import datetime
from typing import Optional, Set, Dict, Any, List, Tuple
from dataclasses import dataclass, field
import logging

from .types import (
    SystemState,
    HaltLevel,
    HaltTrigger,
    HaltEvent,
    StateTransition,
    ResumeRequest,
    InvalidStateTransitionError,
    ResumeNotAllowedError,
)
from .config import ResumeConfig


logger = logging.getLogger(__name__)


# ============================================================
# STATE TRANSITION RULES
# ============================================================

# Allowed transitions from each state
ALLOWED_TRANSITIONS: Dict[SystemState, Set[SystemState]] = {
    SystemState.RUNNING: {
        SystemState.DEGRADED,
        SystemState.HALTED_SOFT,
        SystemState.HALTED_HARD,
        SystemState.EMERGENCY_LOCKDOWN,
    },
    SystemState.DEGRADED: {
        SystemState.RUNNING,
        SystemState.HALTED_SOFT,
        SystemState.HALTED_HARD,
        SystemState.EMERGENCY_LOCKDOWN,
    },
    SystemState.HALTED_SOFT: {
        SystemState.RUNNING,
        SystemState.HALTED_HARD,
        SystemState.EMERGENCY_LOCKDOWN,
    },
    SystemState.HALTED_HARD: {
        SystemState.RUNNING,  # Manual only
        SystemState.EMERGENCY_LOCKDOWN,
    },
    SystemState.EMERGENCY_LOCKDOWN: {
        SystemState.RUNNING,  # Manual only with confirmation
    },
}

# States that require manual resume
MANUAL_RESUME_REQUIRED: Set[SystemState] = {
    SystemState.HALTED_HARD,
    SystemState.EMERGENCY_LOCKDOWN,
}

# Map halt levels to system states
HALT_LEVEL_TO_STATE: Dict[HaltLevel, SystemState] = {
    HaltLevel.NONE: SystemState.RUNNING,
    HaltLevel.SOFT: SystemState.HALTED_SOFT,
    HaltLevel.HARD: SystemState.HALTED_HARD,
    HaltLevel.EMERGENCY: SystemState.EMERGENCY_LOCKDOWN,
}

# State severity (higher = more severe)
STATE_SEVERITY: Dict[SystemState, int] = {
    SystemState.RUNNING: 0,
    SystemState.DEGRADED: 1,
    SystemState.HALTED_SOFT: 2,
    SystemState.HALTED_HARD: 3,
    SystemState.EMERGENCY_LOCKDOWN: 4,
}


# ============================================================
# STATE MACHINE
# ============================================================

@dataclass
class StateMachineState:
    """Internal state of the state machine."""
    
    current_state: SystemState = SystemState.RUNNING
    """Current system state."""
    
    entered_at: datetime = field(default_factory=datetime.utcnow)
    """When current state was entered."""
    
    active_triggers: Dict[HaltTrigger, HaltEvent] = field(default_factory=dict)
    """Active halt triggers."""
    
    transition_history: List[StateTransition] = field(default_factory=list)
    """Recent state transitions."""
    
    max_history_size: int = 1000
    """Maximum number of transitions to keep."""


class StateMachine:
    """
    System state machine.
    
    Manages state transitions with strict rules:
    1. Higher severity always takes precedence
    2. No automatic resume from HARD or EMERGENCY
    3. All transitions are logged
    """
    
    def __init__(
        self,
        resume_config: ResumeConfig,
        initial_state: SystemState = SystemState.RUNNING,
    ):
        """
        Initialize state machine.
        
        Args:
            resume_config: Resume configuration
            initial_state: Initial system state
        """
        self._resume_config = resume_config
        self._state = StateMachineState(
            current_state=initial_state,
            entered_at=datetime.utcnow(),
        )
    
    @property
    def current_state(self) -> SystemState:
        """Get current system state."""
        return self._state.current_state
    
    @property
    def entered_at(self) -> datetime:
        """Get when current state was entered."""
        return self._state.entered_at
    
    @property
    def active_triggers(self) -> Dict[HaltTrigger, HaltEvent]:
        """Get active halt triggers."""
        return dict(self._state.active_triggers)
    
    @property
    def transition_history(self) -> List[StateTransition]:
        """Get transition history."""
        return list(self._state.transition_history)
    
    def process_halt_event(self, event: HaltEvent) -> Optional[StateTransition]:
        """
        Process a halt event and potentially transition state.
        
        Args:
            event: Halt event to process
            
        Returns:
            StateTransition if state changed, None otherwise
        """
        # Add to active triggers
        self._state.active_triggers[event.trigger] = event
        
        # Determine target state
        target_state = HALT_LEVEL_TO_STATE.get(event.halt_level)
        if target_state is None:
            logger.warning(f"Unknown halt level: {event.halt_level}")
            return None
        
        # Only transition if target is more severe
        if not self._is_more_severe(target_state, self._state.current_state):
            logger.debug(
                f"Halt event {event.trigger} does not require state change: "
                f"current={self._state.current_state}, target={target_state}"
            )
            return None
        
        return self._transition_to(
            new_state=target_state,
            reason=f"Halt trigger: {event.trigger.value}",
            trigger=event.trigger,
            is_automatic=True,
        )
    
    def clear_trigger(self, trigger: HaltTrigger) -> Optional[StateTransition]:
        """
        Clear a halt trigger.
        
        If no active triggers remain at current severity, may auto-resume.
        
        Args:
            trigger: Trigger to clear
            
        Returns:
            StateTransition if state changed, None otherwise
        """
        if trigger not in self._state.active_triggers:
            return None
        
        del self._state.active_triggers[trigger]
        
        # Check if we can auto-resume
        return self._check_auto_resume()
    
    def request_resume(self, request: ResumeRequest) -> StateTransition:
        """
        Request manual resume from halted state.
        
        Args:
            request: Resume request details
            
        Returns:
            StateTransition on success
            
        Raises:
            ResumeNotAllowedError: If resume is not allowed
        """
        current = self._state.current_state
        
        # Validate current state allows resume
        if current not in MANUAL_RESUME_REQUIRED and current != SystemState.HALTED_SOFT:
            raise ResumeNotAllowedError(
                f"Cannot resume from state: {current}"
            )
        
        # Check if resume is allowed
        if current == SystemState.EMERGENCY_LOCKDOWN:
            if not request.confirmed:
                raise ResumeNotAllowedError(
                    "Resume from EMERGENCY_LOCKDOWN requires explicit confirmation"
                )
            if self._resume_config.require_confirmation_for_emergency:
                if not request.confirmation_code:
                    raise ResumeNotAllowedError(
                        "Resume from EMERGENCY_LOCKDOWN requires confirmation code"
                    )
        
        if current == SystemState.HALTED_HARD:
            if self._resume_config.require_acknowledgment_for_hard:
                if not request.acknowledged:
                    raise ResumeNotAllowedError(
                        "Resume from HALTED_HARD requires acknowledgment"
                    )
        
        # Check active triggers
        if self._state.active_triggers and not request.force:
            raise ResumeNotAllowedError(
                f"Cannot resume with active triggers: "
                f"{list(self._state.active_triggers.keys())}"
            )
        
        # Clear triggers if forced
        if request.force:
            self._state.active_triggers.clear()
        
        return self._transition_to(
            new_state=SystemState.RUNNING,
            reason=f"Manual resume by {request.operator}",
            trigger=None,
            is_automatic=False,
        )
    
    def force_state(
        self,
        new_state: SystemState,
        reason: str,
        operator: str,
    ) -> StateTransition:
        """
        Force a state change (emergency use only).
        
        Args:
            new_state: State to force
            reason: Reason for force
            operator: Operator performing force
            
        Returns:
            StateTransition
        """
        logger.warning(
            f"FORCE STATE CHANGE: {self._state.current_state} -> {new_state} "
            f"by {operator}: {reason}"
        )
        
        return self._transition_to(
            new_state=new_state,
            reason=f"FORCED by {operator}: {reason}",
            trigger=None,
            is_automatic=False,
        )
    
    def _transition_to(
        self,
        new_state: SystemState,
        reason: str,
        trigger: Optional[HaltTrigger],
        is_automatic: bool,
    ) -> StateTransition:
        """
        Perform state transition.
        
        Args:
            new_state: New state
            reason: Reason for transition
            trigger: Trigger that caused transition
            is_automatic: Whether transition is automatic
            
        Returns:
            StateTransition
        """
        old_state = self._state.current_state
        now = datetime.utcnow()
        
        transition = StateTransition(
            from_state=old_state,
            to_state=new_state,
            timestamp=now,
            trigger=trigger,
            reason=reason,
            is_automatic=is_automatic,
        )
        
        # Update state
        self._state.current_state = new_state
        self._state.entered_at = now
        
        # Add to history
        self._state.transition_history.append(transition)
        if len(self._state.transition_history) > self._state.max_history_size:
            self._state.transition_history = self._state.transition_history[-self._state.max_history_size:]
        
        logger.info(
            f"State transition: {old_state} -> {new_state} "
            f"(reason: {reason}, auto: {is_automatic})"
        )
        
        return transition
    
    def _check_auto_resume(self) -> Optional[StateTransition]:
        """
        Check if we can auto-resume to a lower severity state.
        
        Returns:
            StateTransition if resumed, None otherwise
        """
        current = self._state.current_state
        
        # Cannot auto-resume from manual states
        if current in MANUAL_RESUME_REQUIRED:
            return None
        
        # Check HALTED_SOFT
        if current == SystemState.HALTED_SOFT:
            if not self._resume_config.allow_soft_auto_resume:
                return None
            
            # Check if any SOFT triggers still active
            soft_triggers = [
                t for t, e in self._state.active_triggers.items()
                if e.halt_level >= HaltLevel.SOFT
            ]
            
            if soft_triggers:
                return None
            
            return self._transition_to(
                new_state=SystemState.RUNNING,
                reason="All soft halt triggers cleared",
                trigger=None,
                is_automatic=True,
            )
        
        return None
    
    def _is_more_severe(
        self,
        state1: SystemState,
        state2: SystemState,
    ) -> bool:
        """Check if state1 is more severe than state2."""
        return STATE_SEVERITY.get(state1, 0) > STATE_SEVERITY.get(state2, 0)
    
    def get_highest_severity_trigger(self) -> Optional[Tuple[HaltTrigger, HaltEvent]]:
        """Get the highest severity active trigger."""
        if not self._state.active_triggers:
            return None
        
        highest: Optional[Tuple[HaltTrigger, HaltEvent]] = None
        highest_level = HaltLevel.NONE
        
        for trigger, event in self._state.active_triggers.items():
            if event.halt_level > highest_level:
                highest = (trigger, event)
                highest_level = event.halt_level
        
        return highest


# ============================================================
# STATE GUARDS
# ============================================================

class StateGuard:
    """
    Guard that checks if operations are allowed in current state.
    
    Use this to protect critical operations:
    ```python
    guard = StateGuard(state_machine)
    
    if guard.can_open_new_positions():
        # OK to open position
    else:
        # Cannot open, system is halted
    ```
    """
    
    def __init__(self, state_machine: StateMachine):
        """
        Initialize guard.
        
        Args:
            state_machine: State machine to check
        """
        self._state_machine = state_machine
    
    @property
    def current_state(self) -> SystemState:
        """Get current state."""
        return self._state_machine.current_state
    
    def can_open_new_positions(self) -> bool:
        """Check if new positions can be opened."""
        return self.current_state in {
            SystemState.RUNNING,
            SystemState.DEGRADED,
        }
    
    def can_modify_positions(self) -> bool:
        """Check if existing positions can be modified."""
        return self.current_state in {
            SystemState.RUNNING,
            SystemState.DEGRADED,
            SystemState.HALTED_SOFT,
        }
    
    def can_close_positions(self) -> bool:
        """Check if positions can be closed."""
        # Always allow closing for risk reduction
        return True
    
    def can_send_orders(self) -> bool:
        """Check if orders can be sent to exchange."""
        return self.current_state in {
            SystemState.RUNNING,
            SystemState.DEGRADED,
            SystemState.HALTED_SOFT,
        }
    
    def can_run_strategies(self) -> bool:
        """Check if strategies can generate signals."""
        return self.current_state in {
            SystemState.RUNNING,
            SystemState.DEGRADED,
        }
    
    def is_system_halted(self) -> bool:
        """Check if system is in any halted state."""
        return self.current_state in {
            SystemState.HALTED_SOFT,
            SystemState.HALTED_HARD,
            SystemState.EMERGENCY_LOCKDOWN,
        }
    
    def is_emergency(self) -> bool:
        """Check if system is in emergency lockdown."""
        return self.current_state == SystemState.EMERGENCY_LOCKDOWN
    
    def require_running(self, operation: str) -> None:
        """
        Require system to be in RUNNING state.
        
        Args:
            operation: Name of operation
            
        Raises:
            InvalidStateTransitionError: If not RUNNING
        """
        if self.current_state != SystemState.RUNNING:
            raise InvalidStateTransitionError(
                f"Operation '{operation}' requires RUNNING state, "
                f"current state is {self.current_state}"
            )
    
    def require_not_halted(self, operation: str) -> None:
        """
        Require system to not be halted.
        
        Args:
            operation: Name of operation
            
        Raises:
            InvalidStateTransitionError: If halted
        """
        if self.is_system_halted():
            raise InvalidStateTransitionError(
                f"Operation '{operation}' not allowed in halted state, "
                f"current state is {self.current_state}"
            )
