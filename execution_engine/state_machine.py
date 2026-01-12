"""
Execution Engine - Order State Machine.

============================================================
PURPOSE
============================================================
Manages order lifecycle with strict state transitions.

STATE MACHINE:
                                                    
    PENDING_VALIDATION                              
           │                                        
           ▼                                        
    PENDING_SUBMISSION ──────► REJECTED             
           │                      ▲                 
           ▼                      │                 
       SUBMITTED ─────────────────┤                 
           │                      │                 
           ├──► PARTIALLY_FILLED ─┤                 
           │         │            │                 
           │         ▼            │                 
           └──────► FILLED        │                 
                      │           │                 
                      ▼           │                 
                  COMPLETED ◄─────┘                 
                                                    
    Any state can transition to:                    
    - CANCELED (by user/system)                     
    - EXPIRED (by exchange)                         
    - FAILED (internal error)                       

INVARIANTS:
- Terminal states are final
- Each transition has a guard
- All transitions are logged

============================================================
"""

import logging
from datetime import datetime
from typing import Optional, Set, Dict, Callable, List, Any
from dataclasses import dataclass, field
from enum import Enum

from .types import OrderState, OrderRecord


logger = logging.getLogger(__name__)


# ============================================================
# STATE TRANSITION RULES
# ============================================================

# Valid transitions from each state
VALID_TRANSITIONS: Dict[OrderState, Set[OrderState]] = {
    OrderState.PENDING_VALIDATION: {
        OrderState.PENDING_SUBMISSION,
        OrderState.REJECTED,
        OrderState.FAILED,
    },
    OrderState.PENDING_SUBMISSION: {
        OrderState.SUBMITTED,
        OrderState.REJECTED,
        OrderState.CANCELED,
        OrderState.FAILED,
    },
    OrderState.SUBMITTED: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
        OrderState.FAILED,
    },
    OrderState.PARTIALLY_FILLED: {
        OrderState.FILLED,
        OrderState.CANCELED,
        OrderState.EXPIRED,
        OrderState.FAILED,
    },
    OrderState.FILLED: {
        OrderState.COMPLETED,
    },
    # Terminal states - no transitions out
    OrderState.COMPLETED: set(),
    OrderState.CANCELED: set(),
    OrderState.REJECTED: set(),
    OrderState.EXPIRED: set(),
    OrderState.FAILED: set(),
}


# ============================================================
# STATE TRANSITION EVENT
# ============================================================

@dataclass
class StateTransitionEvent:
    """Event representing a state transition."""
    
    order_id: str
    """Order ID."""
    
    from_state: OrderState
    """Previous state."""
    
    to_state: OrderState
    """New state."""
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """When transition occurred."""
    
    reason: str = ""
    """Reason for transition."""
    
    exchange_update: bool = False
    """Whether this came from exchange update."""
    
    details: Dict[str, Any] = field(default_factory=dict)
    """Additional details."""


# ============================================================
# STATE TRANSITION GUARD
# ============================================================

class TransitionGuard:
    """
    Guard for state transitions.
    
    Ensures transitions are valid and provides reason for denial.
    """
    
    @staticmethod
    def can_transition(
        from_state: OrderState,
        to_state: OrderState,
    ) -> tuple[bool, str]:
        """
        Check if transition is allowed.
        
        Args:
            from_state: Current state
            to_state: Target state
            
        Returns:
            Tuple of (allowed, reason)
        """
        # Same state is always valid (idempotent)
        if from_state == to_state:
            return True, "Same state"
        
        # Check if transition is valid
        valid_targets = VALID_TRANSITIONS.get(from_state, set())
        
        if to_state in valid_targets:
            return True, "Valid transition"
        
        # Check if current state is terminal
        if from_state.is_terminal():
            return False, f"Cannot transition from terminal state {from_state.value}"
        
        return False, f"Invalid transition: {from_state.value} -> {to_state.value}"
    
    @staticmethod
    def validate_order_for_state(
        order: OrderRecord,
        target_state: OrderState,
    ) -> tuple[bool, str]:
        """
        Validate order data for target state.
        
        Args:
            order: Order record
            target_state: Target state
            
        Returns:
            Tuple of (valid, reason)
        """
        if target_state == OrderState.SUBMITTED:
            if not order.exchange_order_id:
                return False, "Missing exchange_order_id for SUBMITTED state"
            if not order.submitted_at:
                return False, "Missing submitted_at for SUBMITTED state"
        
        if target_state == OrderState.FILLED:
            if order.filled_quantity <= 0:
                return False, "filled_quantity must be positive for FILLED state"
            if order.filled_quantity < order.quantity:
                return False, "filled_quantity must equal quantity for FILLED state"
        
        if target_state == OrderState.PARTIALLY_FILLED:
            if order.filled_quantity <= 0:
                return False, "filled_quantity must be positive for PARTIALLY_FILLED"
            if order.filled_quantity >= order.quantity:
                return False, "filled_quantity must be less than quantity for PARTIALLY_FILLED"
        
        if target_state == OrderState.COMPLETED:
            if not order.filled_at:
                return False, "Missing filled_at for COMPLETED state"
        
        return True, "Order valid for state"


# ============================================================
# ORDER STATE MACHINE
# ============================================================

class OrderStateMachine:
    """
    State machine for order lifecycle.
    
    Manages state transitions with:
    - Validation
    - Guard checks
    - Event emission
    - History tracking
    """
    
    def __init__(self, order: OrderRecord):
        """
        Initialize state machine.
        
        Args:
            order: Order record to manage
        """
        self._order = order
        self._history: List[StateTransitionEvent] = []
        self._listeners: List[Callable[[StateTransitionEvent], None]] = []
    
    @property
    def current_state(self) -> OrderState:
        """Get current order state."""
        return self._order.state
    
    @property
    def order(self) -> OrderRecord:
        """Get the managed order."""
        return self._order
    
    @property
    def history(self) -> List[StateTransitionEvent]:
        """Get transition history."""
        return list(self._history)
    
    def add_listener(
        self,
        listener: Callable[[StateTransitionEvent], None],
    ) -> None:
        """Add a transition listener."""
        self._listeners.append(listener)
    
    def can_transition_to(self, target_state: OrderState) -> tuple[bool, str]:
        """
        Check if transition to target state is allowed.
        
        Args:
            target_state: Target state
            
        Returns:
            Tuple of (allowed, reason)
        """
        # Check basic transition validity
        allowed, reason = TransitionGuard.can_transition(
            self.current_state,
            target_state,
        )
        
        if not allowed:
            return False, reason
        
        # Check order data validity
        return TransitionGuard.validate_order_for_state(
            self._order,
            target_state,
        )
    
    def transition_to(
        self,
        target_state: OrderState,
        reason: str = "",
        exchange_update: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> StateTransitionEvent:
        """
        Transition to a new state.
        
        Args:
            target_state: Target state
            reason: Reason for transition
            exchange_update: Whether from exchange update
            details: Additional details
            
        Returns:
            StateTransitionEvent
            
        Raises:
            ValueError: If transition is not allowed
        """
        # Validate transition
        allowed, validation_reason = self.can_transition_to(target_state)
        
        if not allowed:
            raise ValueError(
                f"Cannot transition {self._order.order_id} from "
                f"{self.current_state.value} to {target_state.value}: "
                f"{validation_reason}"
            )
        
        # Same state - no-op
        if self.current_state == target_state:
            return StateTransitionEvent(
                order_id=self._order.order_id,
                from_state=self.current_state,
                to_state=target_state,
                reason="No change",
            )
        
        # Create event
        event = StateTransitionEvent(
            order_id=self._order.order_id,
            from_state=self.current_state,
            to_state=target_state,
            reason=reason,
            exchange_update=exchange_update,
            details=details or {},
        )
        
        # Update order
        self._order.previous_state = self._order.state
        self._order.state = target_state
        self._order.last_update_at = event.timestamp
        
        # Update timestamps based on state
        if target_state == OrderState.SUBMITTED:
            self._order.submitted_at = event.timestamp
        elif target_state == OrderState.FILLED:
            self._order.filled_at = event.timestamp
        elif target_state == OrderState.COMPLETED:
            self._order.completed_at = event.timestamp
        
        # Add to history
        self._history.append(event)
        
        # Notify listeners
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"State listener error: {e}")
        
        logger.info(
            f"Order {self._order.order_id}: "
            f"{event.from_state.value} -> {event.to_state.value} "
            f"({reason})"
        )
        
        return event
    
    # --------------------------------------------------------
    # CONVENIENCE METHODS
    # --------------------------------------------------------
    
    def mark_pending_submission(self, reason: str = "Validation passed") -> StateTransitionEvent:
        """Mark order as pending submission."""
        return self.transition_to(OrderState.PENDING_SUBMISSION, reason)
    
    def mark_submitted(
        self,
        exchange_order_id: str,
        reason: str = "Order submitted",
    ) -> StateTransitionEvent:
        """Mark order as submitted."""
        self._order.exchange_order_id = exchange_order_id
        self._order.submitted_at = datetime.utcnow()
        return self.transition_to(OrderState.SUBMITTED, reason, exchange_update=True)
    
    def mark_partially_filled(
        self,
        filled_quantity,
        average_price,
        reason: str = "Partial fill",
    ) -> StateTransitionEvent:
        """Mark order as partially filled."""
        self._order.filled_quantity = filled_quantity
        self._order.average_fill_price = average_price
        self._order.update_remaining()
        return self.transition_to(
            OrderState.PARTIALLY_FILLED,
            reason,
            exchange_update=True,
            details={"filled_quantity": str(filled_quantity)},
        )
    
    def mark_filled(
        self,
        filled_quantity,
        average_price,
        reason: str = "Order filled",
    ) -> StateTransitionEvent:
        """Mark order as fully filled."""
        self._order.filled_quantity = filled_quantity
        self._order.average_fill_price = average_price
        self._order.remaining_quantity = 0
        self._order.filled_at = datetime.utcnow()
        return self.transition_to(
            OrderState.FILLED,
            reason,
            exchange_update=True,
            details={"filled_quantity": str(filled_quantity)},
        )
    
    def mark_completed(self, reason: str = "Execution complete") -> StateTransitionEvent:
        """Mark order as completed."""
        self._order.completed_at = datetime.utcnow()
        return self.transition_to(OrderState.COMPLETED, reason)
    
    def mark_canceled(
        self,
        reason: str = "Order canceled",
        exchange_update: bool = False,
    ) -> StateTransitionEvent:
        """Mark order as canceled."""
        return self.transition_to(OrderState.CANCELED, reason, exchange_update)
    
    def mark_rejected(
        self,
        reason: str = "Order rejected",
        error_code: Optional[str] = None,
    ) -> StateTransitionEvent:
        """Mark order as rejected."""
        if error_code:
            self._order.exchange_error_code = error_code
            self._order.last_error = reason
        return self.transition_to(
            OrderState.REJECTED,
            reason,
            exchange_update=True,
            details={"error_code": error_code} if error_code else {},
        )
    
    def mark_expired(self, reason: str = "Order expired") -> StateTransitionEvent:
        """Mark order as expired."""
        return self.transition_to(OrderState.EXPIRED, reason, exchange_update=True)
    
    def mark_failed(
        self,
        reason: str = "Execution failed",
        error: Optional[str] = None,
    ) -> StateTransitionEvent:
        """Mark order as failed."""
        if error:
            self._order.last_error = error
        return self.transition_to(
            OrderState.FAILED,
            reason,
            details={"error": error} if error else {},
        )
    
    # --------------------------------------------------------
    # STATE QUERIES
    # --------------------------------------------------------
    
    def is_terminal(self) -> bool:
        """Check if order is in terminal state."""
        return self.current_state.is_terminal()
    
    def is_active(self) -> bool:
        """Check if order is still active."""
        return self.current_state.is_active()
    
    def can_cancel(self) -> bool:
        """Check if order can be canceled."""
        return self.current_state.allows_cancel()
    
    def time_in_current_state(self) -> float:
        """Get time in current state in seconds."""
        return (datetime.utcnow() - self._order.last_update_at).total_seconds()
