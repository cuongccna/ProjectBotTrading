"""
System Risk Controller - Engine.

============================================================
PURPOSE
============================================================
This is the MAIN CONTROLLER of the System Risk Controller.

It orchestrates all monitors, manages state transitions, and
has ABSOLUTE AUTHORITY to halt the entire trading system.

CRITICAL PRINCIPLE:
    "If the system cannot TRUST its own data, state, or 
     execution, IT MUST STOP."

============================================================
ARCHITECTURE
============================================================

                    ┌─────────────────────┐
                    │ SystemRiskController│  <-- ABSOLUTE AUTHORITY
                    │       Engine        │
                    └─────────┬───────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
   ┌─────────┐          ┌─────────┐          ┌─────────┐
   │ Monitors│          │  State  │          │ Alerting│
   │         │          │ Machine │          │         │
   └─────────┘          └─────────┘          └─────────┘

============================================================
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable, Awaitable, Tuple
from dataclasses import dataclass, field

from .types import (
    SystemState,
    HaltLevel,
    HaltTrigger,
    HaltEvent,
    StateTransition,
    MonitorResult,
    SystemHealthSnapshot,
    ResumeRequest,
    SystemRiskControllerError,
)
from .config import SystemRiskControllerConfig
from .state_machine import StateMachine, StateGuard
from .monitors import (
    BaseMonitor,
    DataIntegrityMonitor,
    DataStateSnapshot,
    ProcessingMonitor,
    ProcessingStateSnapshot,
    ExecutionMonitor,
    ExecutionStateSnapshot,
    ControlMonitor,
    ControlStateSnapshot,
    InfrastructureMonitor,
    InfrastructureStateSnapshot,
)
from .guards.data_reality import (
    DataRealityGuard,
    DataRealityGuardConfig,
    DataRealityCheckResult,
)


logger = logging.getLogger(__name__)


# ============================================================
# CALLBACK TYPES
# ============================================================

OnStateChangeCallback = Callable[[StateTransition], Awaitable[None]]
OnHaltEventCallback = Callable[[HaltEvent], Awaitable[None]]


# ============================================================
# SYSTEM RISK CONTROLLER ENGINE
# ============================================================

class SystemRiskController:
    """
    System Risk Controller - ABSOLUTE AUTHORITY.
    
    This is the highest authority in the trading system.
    It has the power to:
    
    1. HALT the entire system immediately
    2. OVERRIDE all other components
    3. PREVENT any trading activity
    4. FORCE position closure in emergency
    
    NOTHING can bypass this controller.
    
    Usage:
    ```python
    controller = SystemRiskController(config)
    await controller.start()
    
    # Check before any trading operation
    if controller.can_trade():
        # OK to trade
    else:
        # System is halted, do not trade
        
    # Update state from various sources
    controller.update_data_state(data_snapshot)
    controller.update_execution_state(exec_snapshot)
    
    await controller.stop()
    ```
    """
    
    # Class marker: This is NOT a placeholder
    _is_placeholder: bool = False
    
    def __init__(
        self,
        config: Optional[SystemRiskControllerConfig] = None,
        on_state_change: Optional[OnStateChangeCallback] = None,
        on_halt_event: Optional[OnHaltEventCallback] = None,
        **kwargs,  # For orchestrator compatibility
    ):
        """
        Initialize System Risk Controller.
        
        Args:
            config: Controller configuration (if dict, uses defaults)
            on_state_change: Callback for state changes
            on_halt_event: Callback for halt events
            **kwargs: Additional arguments (for orchestrator compatibility)
        """
        # Handle dict or missing config
        if config is None or isinstance(config, dict):
            config = SystemRiskControllerConfig()
        
        self._config = config
        self._on_state_change = on_state_change
        self._on_halt_event = on_halt_event
        
        # State machine
        self._state_machine = StateMachine(
            resume_config=config.resume,
            initial_state=SystemState.RUNNING,
        )
        self._guard = StateGuard(self._state_machine)
        
        # ============================================================
        # DATA REALITY GUARD - CANNOT BE BYPASSED
        # ============================================================
        # This guard runs BEFORE any strategy or execution and validates
        # that market data is fresh and accurate.
        self._data_reality_guard = DataRealityGuard(
            config=DataRealityGuardConfig(
                reference_interval_seconds=config.data_reality_guard.reference_interval_seconds,
                max_intervals_stale=config.data_reality_guard.max_intervals_stale,
                max_price_deviation_pct=config.data_reality_guard.max_price_deviation_pct,
                reference_symbol=config.data_reality_guard.reference_symbol,
                enabled=config.data_reality_guard.enabled,
                halt_on_failure=config.data_reality_guard.halt_on_failure,
            )
        )
        self._data_reality_guard_result: Optional[DataRealityCheckResult] = None
        
        # Monitors
        self._data_monitor = DataIntegrityMonitor(config.data_integrity)
        self._processing_monitor = ProcessingMonitor(config.processing)
        self._execution_monitor = ExecutionMonitor(config.execution)
        self._control_monitor = ControlMonitor(config.control)
        self._infrastructure_monitor = InfrastructureMonitor(config.infrastructure)
        
        self._monitors: List[BaseMonitor] = [
            self._data_monitor,
            self._processing_monitor,
            self._execution_monitor,
            self._control_monitor,
            self._infrastructure_monitor,
        ]
        
        # Last results from each monitor
        self._last_results: Dict[str, MonitorResult] = {}
        
        # Background task
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Lock for state updates
        self._lock = asyncio.Lock()
        
        logger.info(
            f"SystemRiskController initialized with ABSOLUTE AUTHORITY | "
            f"DataRealityGuard enabled={config.data_reality_guard.enabled}"
        )
    
    # --------------------------------------------------------
    # PROPERTIES
    # --------------------------------------------------------
    
    @property
    def state(self) -> SystemState:
        """Get current system state."""
        return self._state_machine.current_state
    
    @property
    def guard(self) -> StateGuard:
        """Get state guard for operation checks."""
        return self._guard
    
    @property
    def is_running(self) -> bool:
        """Check if controller is running."""
        return self._running
    
    # --------------------------------------------------------
    # STATE CHECKS (USE THESE BEFORE ANY OPERATION)
    # --------------------------------------------------------
    
    def can_trade(self) -> bool:
        """
        Check if trading is allowed.
        
        USE THIS BEFORE EVERY TRADING OPERATION.
        """
        return self._guard.can_open_new_positions()
    
    def can_modify_positions(self) -> bool:
        """Check if position modifications are allowed."""
        return self._guard.can_modify_positions()
    
    def can_send_orders(self) -> bool:
        """Check if orders can be sent."""
        return self._guard.can_send_orders()
    
    def is_halted(self) -> bool:
        """Check if system is halted."""
        return self._guard.is_system_halted()
    
    def is_emergency(self) -> bool:
        """Check if system is in emergency lockdown."""
        return self._guard.is_emergency()
    
    # --------------------------------------------------------
    # DATA REALITY GUARD (CANNOT BE BYPASSED)
    # --------------------------------------------------------
    
    async def run_data_reality_check(self) -> DataRealityCheckResult:
        """
        Run Data Reality Guard check.
        
        This method validates that market data is:
        1. Fresh enough (not older than 2 intervals)
        2. Accurate (within 3% of live reference)
        
        If either check fails and halt_on_failure=True, this will
        trigger a system HALT.
        
        Returns:
            DataRealityCheckResult with pass/fail status
        """
        result = await self._data_reality_guard.check()
        self._data_reality_guard_result = result
        
        if not result.passed and result.halt_required:
            # Determine trigger based on failure type
            if not result.freshness_passed:
                trigger = HaltTrigger.DI_STALE_DATA
            elif not result.deviation_passed:
                trigger = HaltTrigger.DI_PRICE_DEVIATION
            else:
                trigger = HaltTrigger.DI_DATA_REALITY_FAILURE
            
            # Create halt event
            event = HaltEvent(
                event_id=f"drg_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{id(result) % 10000:04d}",
                trigger=trigger,
                halt_level=HaltLevel.HARD,
                timestamp=datetime.utcnow(),
                source_monitor="DataRealityGuard",
                message=result.error_message or "Data reality check failed",
                details=result.to_dict(),
            )
            
            logger.critical(
                f"DATA REALITY GUARD TRIGGERED HALT: {result.error_message}"
            )
            
            # Process halt event
            await self._process_halt_event(event)
        
        return result
    
    @property
    def data_reality_guard(self) -> DataRealityGuard:
        """Get the Data Reality Guard instance."""
        return self._data_reality_guard
    
    @property
    def data_reality_result(self) -> Optional[DataRealityCheckResult]:
        """Get the last Data Reality Guard result."""
        return self._data_reality_guard_result
    
    async def validate_before_execution(self) -> Tuple[bool, str]:
        """
        Validate system state before any trade execution.
        
        ============================================================
        EXECUTION ENGINE MUST CALL THIS BEFORE EVERY TRADE
        ============================================================
        
        This method:
        1. Checks if system is halted
        2. Runs Data Reality Guard if configured
        3. Returns (allowed, reason) tuple
        
        Returns:
            Tuple[bool, str]: (execution_allowed, reason)
            
        Example:
            allowed, reason = await controller.validate_before_execution()
            if not allowed:
                logger.error(f"Execution blocked: {reason}")
                return
        """
        # Check if already halted
        if self.is_halted():
            return False, f"System is halted: {self.state.value}"
        
        if self.is_emergency():
            return False, "System is in EMERGENCY LOCKDOWN"
        
        # Run Data Reality Guard if configured
        if self._config.data_reality_guard.check_before_execution:
            result = await self.run_data_reality_check()
            
            if not result.passed:
                return False, f"Data Reality Guard failed: {result.error_message}"
        
        # Final state check (guard might have triggered halt)
        if not self.can_trade():
            return False, f"Trading not allowed: {self.state.value}"
        
        return True, "OK"
    
    # --------------------------------------------------------
    # STATE UPDATES (CALL THESE REGULARLY)
    # --------------------------------------------------------
    
    def update_data_state(self, snapshot: DataStateSnapshot) -> None:
        """Update data integrity state."""
        self._data_monitor.update_state(snapshot)
    
    def update_processing_state(self, snapshot: ProcessingStateSnapshot) -> None:
        """Update processing pipeline state."""
        self._processing_monitor.update_state(snapshot)
    
    def update_execution_state(self, snapshot: ExecutionStateSnapshot) -> None:
        """Update execution state."""
        self._execution_monitor.update_state(snapshot)
    
    def update_control_state(self, snapshot: ControlStateSnapshot) -> None:
        """Update risk control state."""
        self._control_monitor.update_state(snapshot)
    
    def update_infrastructure_state(self, snapshot: InfrastructureStateSnapshot) -> None:
        """Update infrastructure state."""
        self._infrastructure_monitor.update_state(snapshot)
    
    # --------------------------------------------------------
    # LIFECYCLE
    # --------------------------------------------------------
    
    async def start(self) -> None:
        """
        Start the controller.
        
        This will run the Data Reality Guard check on startup
        if configured to do so.
        """
        if self._running:
            return
        
        # ============================================================
        # DATA REALITY CHECK ON STARTUP - CANNOT BE BYPASSED
        # ============================================================
        if self._config.data_reality_guard.check_on_startup:
            logger.info("Running Data Reality Guard check on startup...")
            result = await self.run_data_reality_check()
            
            if not result.passed:
                logger.critical(
                    f"STARTUP BLOCKED: Data Reality Guard failed - {result.error_message}"
                )
                # System will be in HALTED state from the check
                # Do not proceed with normal startup
                self._running = True  # Set running so stop() works
                return
            else:
                logger.info(
                    f"Data Reality Guard PASSED | "
                    f"data_age={result.data_age_seconds:.0f}s | "
                    f"deviation={result.deviation_pct:.2f}%"
                )
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("SystemRiskController STARTED - ABSOLUTE AUTHORITY ACTIVE")
    
    async def stop(self) -> None:
        """Stop the controller."""
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        
        logger.info("SystemRiskController STOPPED")
    
    # --------------------------------------------------------
    # MANUAL CONTROLS
    # --------------------------------------------------------
    
    async def request_halt(
        self,
        trigger: HaltTrigger,
        level: HaltLevel,
        reason: str,
        operator: str,
    ) -> StateTransition:
        """
        Manually request a halt.
        
        Args:
            trigger: Halt trigger (use MN_* triggers for manual)
            level: Halt level
            reason: Reason for halt
            operator: Operator name
            
        Returns:
            StateTransition
        """
        async with self._lock:
            event = HaltEvent(
                event_id=f"manual_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{id(operator) % 10000:04d}",
                trigger=trigger,
                halt_level=level,
                timestamp=datetime.utcnow(),
                source_monitor="MANUAL",
                message=f"Manual halt by {operator}: {reason}",
                details={"operator": operator},
            )
            
            transition = self._state_machine.process_halt_event(event)
            
            if transition and self._on_state_change:
                await self._on_state_change(transition)
            
            if self._on_halt_event:
                await self._on_halt_event(event)
            
            logger.warning(
                f"MANUAL HALT by {operator}: {trigger.value} -> {level.name}"
            )
            
            return transition
    
    async def request_resume(self, request: ResumeRequest) -> StateTransition:
        """
        Request manual resume.
        
        Args:
            request: Resume request
            
        Returns:
            StateTransition
        """
        async with self._lock:
            transition = self._state_machine.request_resume(request)
            
            if self._on_state_change:
                await self._on_state_change(transition)
            
            logger.info(f"MANUAL RESUME by {request.operator}")
            
            return transition
    
    async def emergency_stop(self, operator: str, reason: str) -> StateTransition:
        """
        Emergency stop - immediate lockdown.
        
        Args:
            operator: Operator name
            reason: Reason for emergency stop
            
        Returns:
            StateTransition
        """
        return await self.request_halt(
            trigger=HaltTrigger.MN_EMERGENCY_STOP,
            level=HaltLevel.EMERGENCY,
            reason=reason,
            operator=operator,
        )
    
    # --------------------------------------------------------
    # HEALTH SNAPSHOT
    # --------------------------------------------------------
    
    def get_health_snapshot(self) -> SystemHealthSnapshot:
        """Get complete system health snapshot."""
        return SystemHealthSnapshot(
            timestamp=datetime.utcnow(),
            system_state=self.state,
            active_triggers=list(self._state_machine.active_triggers.keys()),
            monitor_results={
                name: result
                for name, result in self._last_results.items()
            },
            state_entered_at=self._state_machine.entered_at,
        )
    
    # --------------------------------------------------------
    # INTERNAL - MONITORING LOOP
    # --------------------------------------------------------
    
    async def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        interval = self._config.timing.check_interval_seconds
        
        while self._running:
            try:
                await self._run_all_monitors()
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                # On internal error, trigger SOFT halt
                await self._handle_internal_error(e)
            
            await asyncio.sleep(interval)
    
    async def _run_all_monitors(self) -> None:
        """Run all monitors and process results."""
        async with self._lock:
            for monitor in self._monitors:
                try:
                    result = monitor.check()
                    self._last_results[monitor.meta.name] = result
                    
                    if result.halt_event:
                        await self._process_halt_event(result.halt_event)
                    else:
                        # Monitor is healthy, try to clear any previous triggers
                        self._try_clear_monitor_triggers(monitor)
                        
                except Exception as e:
                    logger.error(f"Monitor {monitor.meta.name} error: {e}")
                    # Treat monitor failure as SOFT halt
                    event = HaltEvent(
                        event_id=f"mon_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{id(e) % 10000:04d}",
                        trigger=HaltTrigger.IN_CONTROLLER_ERROR,
                        halt_level=HaltLevel.SOFT,
                        timestamp=datetime.utcnow(),
                        source_monitor=monitor.meta.name,
                        message=f"Monitor failed: {e}",
                        details={"error": str(e)},
                    )
                    await self._process_halt_event(event)
    
    async def _process_halt_event(self, event: HaltEvent) -> None:
        """Process a halt event."""
        transition = self._state_machine.process_halt_event(event)
        
        if transition and self._on_state_change:
            await self._on_state_change(transition)
        
        if self._on_halt_event:
            await self._on_halt_event(event)
        
        logger.warning(
            f"HALT EVENT: {event.trigger.value} (level={event.halt_level.name}) "
            f"from {event.source_monitor}: {event.message}"
        )
    
    def _try_clear_monitor_triggers(self, monitor: BaseMonitor) -> None:
        """Try to clear triggers from a healthy monitor."""
        # Get triggers that belong to this monitor's category
        category = monitor.meta.category
        
        for trigger in list(self._state_machine.active_triggers.keys()):
            if trigger.get_category() == category:
                self._state_machine.clear_trigger(trigger)
    
    async def _handle_internal_error(self, error: Exception) -> None:
        """Handle internal controller error."""
        async with self._lock:
            event = HaltEvent(
                event_id=f"int_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{id(error) % 10000:04d}",
                trigger=HaltTrigger.IN_CONTROLLER_ERROR,
                halt_level=HaltLevel.SOFT,
                timestamp=datetime.utcnow(),
                source_monitor="SystemRiskController",
                message=f"Internal error: {error}",
                details={"error": str(error)},
            )
            await self._process_halt_event(event)


# ============================================================
# SINGLETON ACCESS
# ============================================================

_controller: Optional[SystemRiskController] = None


def get_controller() -> SystemRiskController:
    """
    Get the global SystemRiskController instance.
    
    Raises:
        SystemRiskControllerError: If not initialized
    """
    if _controller is None:
        raise SystemRiskControllerError("SystemRiskController not initialized")
    return _controller


def init_controller(
    config: SystemRiskControllerConfig,
    on_state_change: Optional[OnStateChangeCallback] = None,
    on_halt_event: Optional[OnHaltEventCallback] = None,
) -> SystemRiskController:
    """
    Initialize the global SystemRiskController instance.
    
    Args:
        config: Controller configuration
        on_state_change: Callback for state changes
        on_halt_event: Callback for halt events
        
    Returns:
        SystemRiskController instance
    """
    global _controller
    
    if _controller is not None:
        logger.warning("SystemRiskController already initialized, replacing")
    
    _controller = SystemRiskController(
        config=config,
        on_state_change=on_state_change,
        on_halt_event=on_halt_event,
    )
    
    return _controller


# ============================================================
# DECORATOR FOR PROTECTED OPERATIONS
# ============================================================

def require_trading_allowed(func):
    """
    Decorator that requires trading to be allowed.
    
    Usage:
    ```python
    @require_trading_allowed
    async def open_position(...):
        ...
    ```
    """
    async def wrapper(*args, **kwargs):
        controller = get_controller()
        if not controller.can_trade():
            raise SystemRiskControllerError(
                f"Trading not allowed: system state is {controller.state}"
            )
        return await func(*args, **kwargs)
    return wrapper


def require_not_halted(func):
    """
    Decorator that requires system not to be halted.
    
    Usage:
    ```python
    @require_not_halted
    async def some_critical_operation(...):
        ...
    ```
    """
    async def wrapper(*args, **kwargs):
        controller = get_controller()
        if controller.is_halted():
            raise SystemRiskControllerError(
                f"Operation not allowed: system is halted ({controller.state})"
            )
        return await func(*args, **kwargs)
    return wrapper
