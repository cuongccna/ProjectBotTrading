"""
System Risk Controller - Execution Monitor.

============================================================
PURPOSE
============================================================
Monitors order execution health and anomalies.

HALT TRIGGERS:
- EX_REPEATED_REJECTIONS: Orders rejected repeatedly
- EX_SLIPPAGE_EXCEEDED: Slippage beyond limits
- EX_POSITION_MISMATCH: Position mismatch with exchange
- EX_UNCONFIRMED_EXECUTION: Unconfirmed orders
- EX_EXCHANGE_ERROR: Exchange API errors
- EX_ORDER_STUCK: Stuck pending orders

============================================================
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from ..types import (
    HaltTrigger,
    HaltLevel,
    TriggerCategory,
    MonitorResult,
)
from ..config import ExecutionConfig
from .base import (
    BaseMonitor,
    MonitorMeta,
    create_healthy_result,
    create_halt_result,
)


# ============================================================
# EXECUTION STATE SNAPSHOT
# ============================================================

@dataclass
class ExecutionStateSnapshot:
    """
    Snapshot of current execution state.
    """
    
    # Order Rejections
    rejections_last_hour: int = 0
    """Order rejections in the last hour."""
    
    consecutive_rejections: int = 0
    """Consecutive order rejections."""
    
    last_rejection_reason: Optional[str] = None
    """Reason for last rejection."""
    
    # Slippage
    slippage_violations_count: int = 0
    """Number of slippage violations."""
    
    last_slippage_pct: Optional[float] = None
    """Last recorded slippage percentage."""
    
    max_slippage_last_hour: float = 0.0
    """Maximum slippage in last hour."""
    
    # Position State
    system_position_count: int = 0
    """Positions tracked by system."""
    
    exchange_position_count: int = 0
    """Positions on exchange."""
    
    position_value_mismatch_pct: float = 0.0
    """Percentage mismatch in position values."""
    
    positions_synced: bool = True
    """Whether positions are synced."""
    
    last_position_sync: Optional[datetime] = None
    """When positions were last synced."""
    
    # Unconfirmed Orders
    unconfirmed_order_count: int = 0
    """Number of unconfirmed orders."""
    
    oldest_unconfirmed_age_seconds: float = 0.0
    """Age of oldest unconfirmed order."""
    
    # Pending Orders
    pending_order_count: int = 0
    """Number of pending orders."""
    
    oldest_pending_age_seconds: float = 0.0
    """Age of oldest pending order."""
    
    # Exchange Errors
    exchange_errors_last_hour: int = 0
    """Exchange errors in the last hour."""
    
    exchange_reachable: bool = True
    """Whether exchange is reachable."""
    
    exchange_status: Optional[str] = None
    """Current exchange status."""


# ============================================================
# EXECUTION MONITOR
# ============================================================

class ExecutionMonitor(BaseMonitor):
    """
    Monitors execution health.
    
    Checks:
    1. Order rejection rate
    2. Slippage violations
    3. Position synchronization
    4. Unconfirmed orders
    5. Stuck pending orders
    6. Exchange errors
    """
    
    def __init__(
        self,
        config: ExecutionConfig,
    ):
        """
        Initialize monitor.
        
        Args:
            config: Execution configuration
        """
        self._config = config
        self._last_execution_state: Optional[ExecutionStateSnapshot] = None
    
    @property
    def meta(self) -> MonitorMeta:
        return MonitorMeta(
            name="ExecutionMonitor",
            category=TriggerCategory.EXECUTION,
            description="Monitors order execution health",
            is_critical=True,
        )
    
    def update_state(self, state: ExecutionStateSnapshot) -> None:
        """
        Update the execution state for monitoring.
        
        Args:
            state: Current execution state
        """
        self._last_execution_state = state
    
    def _check(self) -> MonitorResult:
        """
        Perform execution health checks.
        """
        if self._last_execution_state is None:
            return create_healthy_result(
                monitor_name=self.meta.name,
                metrics={"warning": "No execution state provided"},
            )
        
        state = self._last_execution_state
        
        # Check 1: Position Mismatch (HIGHEST PRIORITY - EMERGENCY)
        result = self._check_position_mismatch(state)
        if result is not None:
            return result
        
        # Check 2: Order Rejections
        result = self._check_order_rejections(state)
        if result is not None:
            return result
        
        # Check 3: Slippage
        result = self._check_slippage(state)
        if result is not None:
            return result
        
        # Check 4: Unconfirmed Orders
        result = self._check_unconfirmed_orders(state)
        if result is not None:
            return result
        
        # Check 5: Stuck Orders
        result = self._check_stuck_orders(state)
        if result is not None:
            return result
        
        # Check 6: Exchange Errors
        result = self._check_exchange_errors(state)
        if result is not None:
            return result
        
        # All checks passed
        return create_healthy_result(
            monitor_name=self.meta.name,
            metrics={
                "rejections_last_hour": state.rejections_last_hour,
                "max_slippage_last_hour": state.max_slippage_last_hour,
                "positions_synced": state.positions_synced,
                "unconfirmed_orders": state.unconfirmed_order_count,
                "pending_orders": state.pending_order_count,
                "exchange_reachable": state.exchange_reachable,
            },
        )
    
    def _check_position_mismatch(
        self,
        state: ExecutionStateSnapshot,
    ) -> Optional[MonitorResult]:
        """
        Check position synchronization.
        
        THIS IS CRITICAL - position mismatch = EMERGENCY HALT.
        """
        # Check if positions are synced
        if not state.positions_synced:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.EX_POSITION_MISMATCH,
                halt_level=HaltLevel.EMERGENCY,
                message="Position state is not synchronized with exchange",
                details={
                    "positions_synced": False,
                    "last_sync": (
                        state.last_position_sync.isoformat()
                        if state.last_position_sync else None
                    ),
                },
            )
        
        # Check position count mismatch
        if state.system_position_count != state.exchange_position_count:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.EX_POSITION_MISMATCH,
                halt_level=HaltLevel.EMERGENCY,
                message=f"Position count mismatch: system={state.system_position_count}, exchange={state.exchange_position_count}",
                details={
                    "system_positions": state.system_position_count,
                    "exchange_positions": state.exchange_position_count,
                },
            )
        
        # Check position value mismatch
        if state.position_value_mismatch_pct > self._config.position_mismatch_tolerance_pct:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.EX_POSITION_MISMATCH,
                halt_level=HaltLevel.EMERGENCY,
                message=f"Position value mismatch: {state.position_value_mismatch_pct:.2f}%",
                details={
                    "mismatch_pct": state.position_value_mismatch_pct,
                    "tolerance_pct": self._config.position_mismatch_tolerance_pct,
                },
            )
        
        return None
    
    def _check_order_rejections(
        self,
        state: ExecutionStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check order rejection rate."""
        # Consecutive rejections
        if state.consecutive_rejections >= self._config.max_consecutive_rejections:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.EX_REPEATED_REJECTIONS,
                halt_level=HaltLevel.HARD,
                message=f"Too many consecutive order rejections: {state.consecutive_rejections}",
                details={
                    "consecutive_rejections": state.consecutive_rejections,
                    "threshold": self._config.max_consecutive_rejections,
                    "last_reason": state.last_rejection_reason,
                },
            )
        
        # Hourly rejections
        if state.rejections_last_hour >= self._config.max_rejections_per_hour:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.EX_REPEATED_REJECTIONS,
                halt_level=HaltLevel.SOFT,
                message=f"Too many order rejections in last hour: {state.rejections_last_hour}",
                details={
                    "rejections_last_hour": state.rejections_last_hour,
                    "threshold": self._config.max_rejections_per_hour,
                },
            )
        
        return None
    
    def _check_slippage(
        self,
        state: ExecutionStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check slippage violations."""
        # Check max slippage
        if state.max_slippage_last_hour > self._config.max_slippage_pct:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.EX_SLIPPAGE_EXCEEDED,
                halt_level=HaltLevel.HARD,
                message=f"Slippage exceeded hard limit: {state.max_slippage_last_hour:.2f}%",
                details={
                    "max_slippage": state.max_slippage_last_hour,
                    "limit": self._config.max_slippage_pct,
                },
            )
        
        # Check violation count
        if state.slippage_violations_count >= self._config.slippage_halt_threshold:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.EX_SLIPPAGE_EXCEEDED,
                halt_level=HaltLevel.SOFT,
                message=f"Too many slippage violations: {state.slippage_violations_count}",
                details={
                    "violations": state.slippage_violations_count,
                    "threshold": self._config.slippage_halt_threshold,
                },
            )
        
        return None
    
    def _check_unconfirmed_orders(
        self,
        state: ExecutionStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check unconfirmed orders."""
        # Check count
        if state.unconfirmed_order_count > self._config.max_unconfirmed_orders:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.EX_UNCONFIRMED_EXECUTION,
                halt_level=HaltLevel.HARD,
                message=f"Too many unconfirmed orders: {state.unconfirmed_order_count}",
                details={
                    "unconfirmed_count": state.unconfirmed_order_count,
                    "max_allowed": self._config.max_unconfirmed_orders,
                },
            )
        
        # Check age
        if state.oldest_unconfirmed_age_seconds > self._config.max_unconfirmed_seconds:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.EX_UNCONFIRMED_EXECUTION,
                halt_level=HaltLevel.HARD,
                message=f"Unconfirmed order too old: {state.oldest_unconfirmed_age_seconds:.0f}s",
                details={
                    "oldest_age_seconds": state.oldest_unconfirmed_age_seconds,
                    "max_seconds": self._config.max_unconfirmed_seconds,
                },
            )
        
        return None
    
    def _check_stuck_orders(
        self,
        state: ExecutionStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check for stuck pending orders."""
        if state.oldest_pending_age_seconds > self._config.max_pending_order_age_seconds:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.EX_ORDER_STUCK,
                halt_level=HaltLevel.SOFT,
                message=f"Pending order stuck: {state.oldest_pending_age_seconds:.0f}s old",
                details={
                    "oldest_pending_seconds": state.oldest_pending_age_seconds,
                    "max_seconds": self._config.max_pending_order_age_seconds,
                    "pending_count": state.pending_order_count,
                },
            )
        
        return None
    
    def _check_exchange_errors(
        self,
        state: ExecutionStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check exchange errors."""
        # Check reachability
        if not state.exchange_reachable:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.EX_EXCHANGE_ERROR,
                halt_level=HaltLevel.HARD,
                message="Exchange is not reachable",
                details={"exchange_reachable": False},
            )
        
        # Check error rate
        if state.exchange_errors_last_hour >= self._config.max_exchange_errors_per_hour:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.EX_EXCHANGE_ERROR,
                halt_level=HaltLevel.SOFT,
                message=f"Too many exchange errors: {state.exchange_errors_last_hour}/hour",
                details={
                    "errors_last_hour": state.exchange_errors_last_hour,
                    "threshold": self._config.max_exchange_errors_per_hour,
                },
            )
        
        return None
