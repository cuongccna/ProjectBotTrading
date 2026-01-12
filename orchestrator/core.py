"""
Orchestrator - Core.

============================================================
RESPONSIBILITY
============================================================
Main orchestrator class - the nervous system of the platform.

- Single entrypoint for the entire application
- Controls startup, shutdown, and execution flow
- Enforces correct execution order
- Handles signals (SIGINT, SIGTERM)
- Ensures system-wide safety and observability

============================================================
ARCHITECTURAL POSITION
============================================================
- This orchestrator has NO business logic
- It does NOT modify decisions
- It does NOT bypass any authority
- It ONLY coordinates execution

============================================================
"""

import asyncio
import logging
import signal
import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional
import json

from .models import (
    RuntimeMode,
    ExecutionStage,
    ModuleStatus,
    OrchestratorConfig,
    SafetyContext,
    StageResult,
    CycleResult,
)
from .registry import ModuleRegistry, ModuleFactory
from .pipeline import (
    ExecutionPipeline,
    PipelineBuilder,
    CycleHistory,
    StageHandler,
)
from core.state_manager import StateManager, SystemState
from core.clock import ClockFactory, SystemClock, ReplayClock
from core.exceptions import (
    TradingException,
    EmergencyStopError,
    StartupError,
    ShutdownError,
    ConfigurationError,
    Severity,
)


# ============================================================
# LOGGING SETUP
# ============================================================

def setup_logging(
    level: str = "INFO",
    log_format: str = "json",
    correlation_id: Optional[str] = None,
) -> logging.Logger:
    """
    Set up structured logging.
    
    Args:
        level: Log level
        log_format: Output format (json or text)
        correlation_id: Correlation ID for tracing
        
    Returns:
        Configured logger
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    if log_format == "json":
        formatter = logging.Formatter(
            json.dumps({
                "timestamp": "%(asctime)s",
                "level": "%(levelname)s",
                "logger": "%(name)s",
                "message": "%(message)s",
                "correlation_id": correlation_id or "",
            })
        )
    else:
        formatter = logging.Formatter(
            f"%(asctime)s | %(levelname)-8s | %(name)s | {correlation_id or ''} | %(message)s"
        )
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = [handler]
    
    return logging.getLogger("orchestrator")


# ============================================================
# ORCHESTRATOR
# ============================================================

class Orchestrator:
    """
    Main system orchestrator.
    
    This is the single entrypoint of the entire application.
    It coordinates all modules and controls execution flow.
    """
    
    def __init__(
        self,
        config: OrchestratorConfig,
        alert_callback: Optional[Callable[[str, str, str], Awaitable[None]]] = None,
    ):
        """
        Initialize orchestrator.
        
        Args:
            config: Orchestrator configuration
            alert_callback: Async callback for alerts (severity, title, message)
        """
        self._config = config
        self._alert_callback = alert_callback
        
        # Validate configuration
        errors = config.validate()
        if errors:
            raise ConfigurationError(
                message=f"Invalid configuration: {', '.join(errors)}",
            )
        
        # Initialize components
        self._state_persistence_path = None
        if config.state_persistence_enabled and config.state_persistence_path:
            self._state_persistence_path = Path(config.state_persistence_path)
        
        self._state_manager = StateManager(
            persistence_path=self._state_persistence_path,
            initial_state=SystemState.INITIALIZING,
        )
        
        self._registry = ModuleRegistry()
        self._factory: Optional[ModuleFactory] = None
        self._pipeline: Optional[ExecutionPipeline] = None
        self._cycle_history = CycleHistory()
        
        # Stage handlers (to be registered)
        self._stage_handlers: Dict[ExecutionStage, StageHandler] = {}
        
        # Runtime state
        self._running = False
        self._shutdown_requested = False
        self._current_cycle: Optional[CycleResult] = None
        self._main_loop_task: Optional[asyncio.Task] = None
        
        # Signal handlers
        self._original_handlers: Dict[signal.Signals, Any] = {}
        
        # Clock setup
        if config.mode == RuntimeMode.BACKTEST:
            if config.backtest_start_date:
                start_time = datetime.fromisoformat(config.backtest_start_date)
                replay_clock = ReplayClock(
                    start_time=start_time,
                    speed_multiplier=config.backtest_speed_multiplier,
                )
                ClockFactory.set_clock(replay_clock)
        else:
            ClockFactory.set_clock(SystemClock())
        
        # Logging
        self._correlation_id = f"{config.correlation_id_prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self._logger = setup_logging(
            level=config.log_level,
            correlation_id=self._correlation_id,
        )
        
        self._logger.info(
            f"Orchestrator initialized | mode={config.mode.value} | "
            f"correlation_id={self._correlation_id}"
        )
    
    # --------------------------------------------------------
    # Properties
    # --------------------------------------------------------
    
    @property
    def config(self) -> OrchestratorConfig:
        """Get configuration."""
        return self._config
    
    @property
    def state(self) -> SystemState:
        """Get current system state."""
        return self._state_manager.state
    
    @property
    def is_running(self) -> bool:
        """Check if orchestrator is running."""
        return self._running
    
    @property
    def is_trading_allowed(self) -> bool:
        """Check if trading is allowed."""
        return (
            self._state_manager.is_trading_allowed and
            not self._shutdown_requested and
            self._config.mode.allows_trading
        )
    
    @property
    def registry(self) -> ModuleRegistry:
        """Get module registry."""
        return self._registry
    
    @property
    def cycle_history(self) -> CycleHistory:
        """Get cycle history."""
        return self._cycle_history
    
    # --------------------------------------------------------
    # Module Registration
    # --------------------------------------------------------
    
    def _is_placeholder_module(self, module_class: type) -> bool:
        """
        Check if a module class is a placeholder.
        
        Placeholder modules are identified by the _is_placeholder class attribute.
        """
        return getattr(module_class, '_is_placeholder', False) is True
    
    def _validate_module_registration(
        self,
        name: str,
        module_class: type,
    ) -> None:
        """
        Validate module registration against runtime mode restrictions.
        
        ============================================================
        CRITICAL ENFORCEMENT RULE
        ============================================================
        
        Placeholder modules are ONLY allowed in SCAFFOLD mode.
        In PAPER, FULL, or any other production mode, placeholder
        modules are FORBIDDEN and will cause a FATAL ERROR.
        
        This ensures the system REFUSES TO START if real implementations
        are not provided for production modes.
        """
        is_placeholder = self._is_placeholder_module(module_class)
        mode = self._config.mode
        allows_placeholders = mode.allows_placeholders
        
        # Get placeholder name if available
        placeholder_name = getattr(module_class, '_placeholder_name', module_class.__name__)
        
        # Log module registration type
        module_type = "PLACEHOLDER" if is_placeholder else "REAL"
        self._logger.info(
            f"Registering module [{name}]: {module_type} "
            f"(class={placeholder_name}, mode={mode.value})"
        )
        
        # CRITICAL CHECK: Placeholder in non-scaffold mode = FATAL ERROR
        if is_placeholder and not allows_placeholders:
            error_msg = (
                f"\n"
                f"{'=' * 70}\n"
                f"FATAL ERROR: PLACEHOLDER MODULE DETECTED IN {mode.value.upper()} MODE\n"
                f"{'=' * 70}\n"
                f"\n"
                f"Module:       {name}\n"
                f"Class:        {placeholder_name}\n"
                f"Runtime Mode: {mode.value}\n"
                f"\n"
                f"CRITICAL VIOLATION:\n"
                f"  Placeholder modules are ONLY allowed in 'scaffold' mode.\n"
                f"  In '{mode.value}' mode, ALL modules must have REAL implementations.\n"
                f"\n"
                f"REQUIRED ACTION:\n"
                f"  1. Replace placeholder with real module implementation, OR\n"
                f"  2. Switch to 'scaffold' mode for development/testing\n"
                f"\n"
                f"THE SYSTEM REFUSES TO START.\n"
                f"{'=' * 70}\n"
            )
            self._logger.critical(error_msg)
            raise StartupError(
                f"Placeholder module '{name}' is FORBIDDEN in {mode.value} mode. "
                f"Replace with real implementation or use scaffold mode."
            )
    
    def register_module(
        self,
        name: str,
        module_class: type,
        dependencies: List[str] = None,
        required_stages: List[ExecutionStage] = None,
        config_key: str = None,
        enabled: bool = True,
        critical: bool = False,
        timeout_seconds: float = 60.0,
    ) -> None:
        """Register a module with validation."""
        # CRITICAL: Validate before registration
        self._validate_module_registration(name, module_class)
        
        # If validation passes, proceed with registration
        self._registry.register(
            name=name,
            module_class=module_class,
            dependencies=dependencies,
            required_stages=required_stages,
            config_key=config_key,
            enabled=enabled,
            critical=critical,
            timeout_seconds=timeout_seconds,
        )
    
    def register_stage_handler(
        self,
        stage: ExecutionStage,
        handler: StageHandler,
    ) -> None:
        """Register a stage handler."""
        self._stage_handlers[stage] = handler
    
    def set_module_factory(self, factory: ModuleFactory) -> None:
        """Set the module factory."""
        self._factory = factory
    
    # --------------------------------------------------------
    # Safety Context
    # --------------------------------------------------------
    
    def get_safety_context(self) -> SafetyContext:
        """Get current safety context."""
        # Check system risk controller if available
        risk_controller = self._registry.get_instance("system_risk_controller")
        
        context = SafetyContext()
        
        if risk_controller:
            if hasattr(risk_controller, 'is_halted'):
                context.risk_controller_halted = risk_controller.is_halted()
            if hasattr(risk_controller, 'can_trade'):
                if not risk_controller.can_trade():
                    context.risk_state_high = True
        
        # Check trade guard if available
        trade_guard = self._registry.get_instance("trade_guard")
        if trade_guard:
            # Trade guard checks happen per-trade, not globally
            pass
        
        # Check system state
        if self._state_manager.is_halted:
            context.emergency_stop_active = True
        
        # Check module health
        unhealthy = self._registry.get_unhealthy_modules()
        if unhealthy:
            context.system_unhealthy = True
        
        return context
    
    # --------------------------------------------------------
    # Module Registration Summary
    # --------------------------------------------------------
    
    def log_module_registration_summary(self) -> None:
        """
        Log a summary of all registered modules showing REAL vs PLACEHOLDER status.
        
        This provides visibility into which modules are real implementations
        and which are placeholders, helping ensure production modes have
        all required real implementations.
        """
        mode = self._config.mode
        definitions = self._registry.get_all_definitions()
        
        # Categorize modules
        real_modules = []
        placeholder_modules = []
        
        for name, definition in definitions.items():
            module_class = definition.module_class
            is_placeholder = self._is_placeholder_module(module_class)
            
            if is_placeholder:
                placeholder_name = getattr(module_class, '_placeholder_name', module_class.__name__)
                placeholder_modules.append((name, placeholder_name))
            else:
                real_modules.append((name, module_class.__name__))
        
        # Build summary
        total = len(definitions)
        real_count = len(real_modules)
        placeholder_count = len(placeholder_modules)
        
        self._logger.info("")
        self._logger.info("=" * 70)
        self._logger.info("MODULE REGISTRATION SUMMARY")
        self._logger.info("=" * 70)
        self._logger.info(f"Runtime Mode:       {mode.value.upper()}")
        self._logger.info(f"Placeholders Allowed: {'YES' if mode.allows_placeholders else 'NO'}")
        self._logger.info("-" * 70)
        self._logger.info(f"Total Modules:      {total}")
        self._logger.info(f"REAL Modules:       {real_count}")
        self._logger.info(f"PLACEHOLDER Modules: {placeholder_count}")
        self._logger.info("-" * 70)
        
        if real_modules:
            self._logger.info("REAL IMPLEMENTATIONS:")
            for name, class_name in real_modules:
                self._logger.info(f"  [OK] {name:<30} ({class_name})")
        
        if placeholder_modules:
            self._logger.info("PLACEHOLDER MODULES:")
            for name, placeholder_name in placeholder_modules:
                self._logger.info(f"  [!!] {name:<30} (Placeholder[{placeholder_name}])")
        
        self._logger.info("=" * 70)
        
        # Additional warning for scaffold mode
        if mode.allows_placeholders and placeholder_count > 0:
            self._logger.warning(
                f"Running in {mode.value} mode with {placeholder_count} placeholder modules. "
                f"These modules return EMPTY/MOCK data. Switch to 'paper' or 'full' mode "
                f"for real data collection (requires real implementations)."
            )
        
        self._logger.info("")
    
    # --------------------------------------------------------
    # Lifecycle
    # --------------------------------------------------------
    
    async def start(self) -> None:
        """
        Start the orchestrator.
        
        This is the main startup sequence.
        """
        if self._running:
            self._logger.warning("Orchestrator already running")
            return
        
        self._logger.info("=== ORCHESTRATOR STARTUP SEQUENCE ===")
        
        try:
            # Install signal handlers
            self._install_signal_handlers()
            
            # Restore state if available
            await self._state_manager.restore_state()
            
            if self._state_manager.state == SystemState.EMERGENCY_STOP:
                self._logger.critical(
                    "System was in emergency stop state - cannot start automatically"
                )
                raise StartupError(
                    message="System requires manual intervention after emergency stop",
                    stage="state_recovery",
                )
            
            # Instantiate modules
            if self._factory:
                await self._registry.instantiate_all(self._factory.create)
            
            # Start modules
            started = await self._registry.start_all()
            self._logger.info(f"Started {len(started)} modules: {', '.join(started)}")
            
            # Build pipeline
            self._pipeline = PipelineBuilder(self._config.mode) \
                .with_handlers(self._stage_handlers) \
                .with_safety_checker(self.get_safety_context) \
                .with_stage_timeout(300.0) \
                .build()
            
            # Transition to running
            await self._state_manager.transition_to(
                SystemState.RUNNING,
                reason="Startup complete",
                triggered_by="orchestrator",
            )
            
            self._running = True
            
            self._logger.info("=== ORCHESTRATOR STARTUP COMPLETE ===")
            
            # Send startup notification
            await self._send_alert(
                "INFO",
                "System Started",
                f"Trading system started in {self._config.mode.value} mode",
            )
            
        except Exception as e:
            self._logger.error(f"Startup failed: {e}", exc_info=True)
            await self._state_manager.transition_to(
                SystemState.ERROR,
                reason=f"Startup failed: {e}",
                triggered_by="orchestrator",
            )
            raise
    
    async def stop(self) -> None:
        """
        Stop the orchestrator gracefully.
        """
        if not self._running:
            return
        
        self._logger.info("=== ORCHESTRATOR SHUTDOWN SEQUENCE ===")
        self._shutdown_requested = True
        
        try:
            # Cancel main loop if running
            if self._main_loop_task and not self._main_loop_task.done():
                self._main_loop_task.cancel()
                try:
                    await asyncio.wait_for(
                        self._main_loop_task,
                        timeout=self._config.drain_timeout_seconds,
                    )
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            # Stop modules in reverse order
            stopped = await self._registry.stop_all()
            self._logger.info(f"Stopped {len(stopped)} modules")
            
            # Transition to stopped
            await self._state_manager.transition_to(
                SystemState.STOPPED,
                reason="Graceful shutdown",
                triggered_by="orchestrator",
            )
            
            self._running = False
            
            # Restore signal handlers
            self._restore_signal_handlers()
            
            self._logger.info("=== ORCHESTRATOR SHUTDOWN COMPLETE ===")
            
            # Send shutdown notification
            await self._send_alert(
                "INFO",
                "System Stopped",
                "Trading system shutdown complete",
            )
            
        except Exception as e:
            self._logger.error(f"Shutdown error: {e}", exc_info=True)
            raise ShutdownError(
                message=f"Shutdown error: {e}",
                cause=e,
            )
    
    async def emergency_stop(self, reason: str, operator: str = "system") -> None:
        """
        Trigger emergency stop.
        
        Args:
            reason: Reason for emergency stop
            operator: Who triggered the stop
        """
        self._logger.critical(f"EMERGENCY STOP: {reason} (by {operator})")
        
        self._shutdown_requested = True
        
        # Transition to emergency stop
        await self._state_manager.emergency_stop(
            reason=reason,
            operator=operator,
        )
        
        # Cancel current cycle immediately
        if self._main_loop_task and not self._main_loop_task.done():
            self._main_loop_task.cancel()
        
        # Stop all modules
        await self._registry.stop_all()
        
        self._running = False
        
        # Send critical alert
        await self._send_alert(
            "CRITICAL",
            "EMERGENCY STOP",
            f"System halted: {reason}",
        )
    
    # --------------------------------------------------------
    # Main Loop
    # --------------------------------------------------------
    
    async def run_forever(self) -> None:
        """
        Run the main execution loop.
        
        This is a long-lived process that runs until shutdown.
        """
        if not self._running:
            await self.start()
        
        self._logger.info(
            f"Starting main loop | interval={self._config.tick_interval_seconds}s"
        )
        
        self._main_loop_task = asyncio.current_task()
        
        try:
            while not self._shutdown_requested:
                try:
                    # Execute a cycle
                    await self._execute_cycle()
                    
                    # Wait for next tick
                    if not self._shutdown_requested:
                        await self._wait_for_next_tick()
                        
                except asyncio.CancelledError:
                    self._logger.info("Main loop cancelled")
                    break
                except EmergencyStopError as e:
                    await self.emergency_stop(e.message, "exception")
                    break
                except Exception as e:
                    self._logger.error(f"Cycle error: {e}", exc_info=True)
                    
                    # Check if recoverable
                    if isinstance(e, TradingException) and not e.is_recoverable:
                        await self.emergency_stop(str(e), "exception")
                        break
                    
                    # Continue after recoverable error
                    await self._send_alert(
                        "HIGH",
                        "Cycle Error",
                        f"Error in execution cycle: {e}",
                    )
        finally:
            self._main_loop_task = None
    
    async def run_single_cycle(self) -> CycleResult:
        """
        Run a single execution cycle.
        
        Returns:
            CycleResult
        """
        if not self._running:
            await self.start()
        
        return await self._execute_cycle()
    
    async def _execute_cycle(self) -> CycleResult:
        """Execute one cycle of the pipeline."""
        if not self._pipeline:
            raise StartupError(
                message="Pipeline not initialized",
                stage="execute_cycle",
            )
        
        # Check if trading allowed
        safety = self.get_safety_context()
        if not safety.can_trade and self._config.mode.allows_trading:
            self._logger.warning(
                f"Trading blocked: {safety.block_reason}"
            )
        
        # Execute cycle
        result = await self._pipeline.execute_cycle()
        
        # Record in history
        await self._cycle_history.add(result)
        
        # Update current cycle
        self._current_cycle = result
        
        # Handle failure
        if not result.success:
            await self._handle_cycle_failure(result)
        
        return result
    
    async def _handle_cycle_failure(self, result: CycleResult) -> None:
        """Handle a failed cycle."""
        self._logger.error(
            f"Cycle failed: stage={result.failed_stage.stage_id if result.failed_stage else 'unknown'} "
            f"error={result.error}"
        )
        
        # Check if non-recoverable
        failed_result = next(
            (r for r in result.stage_results if not r.success),
            None
        )
        
        if failed_result and not failed_result.recoverable:
            await self.emergency_stop(
                f"Non-recoverable error in {failed_result.stage.stage_id}: {failed_result.error}",
                "pipeline",
            )
        else:
            # Send alert for recoverable errors
            await self._send_alert(
                "HIGH",
                "Cycle Failed",
                f"Stage {result.failed_stage.stage_id if result.failed_stage else 'unknown'} failed: {result.error}",
            )
    
    async def _wait_for_next_tick(self) -> None:
        """Wait until the next tick interval."""
        clock = ClockFactory.get_clock()
        now = clock.now()
        
        # Calculate next tick time (align to hour boundaries)
        interval = timedelta(seconds=self._config.tick_interval_seconds)
        
        if self._config.tick_interval_seconds == 3600:
            # Align to hour
            next_tick = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            next_tick = now + interval
        
        wait_seconds = (next_tick - now).total_seconds()
        
        if wait_seconds > 0:
            self._logger.debug(f"Waiting {wait_seconds:.1f}s until next tick")
            await asyncio.sleep(wait_seconds)
    
    # --------------------------------------------------------
    # Signal Handlers
    # --------------------------------------------------------
    
    def _install_signal_handlers(self) -> None:
        """Install signal handlers for graceful shutdown."""
        if sys.platform == "win32":
            # Windows doesn't support SIGTERM the same way
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGBREAK, self._signal_handler)
        else:
            loop = asyncio.get_running_loop()
            
            for sig in (signal.SIGTERM, signal.SIGINT):
                self._original_handlers[sig] = signal.getsignal(sig)
                loop.add_signal_handler(
                    sig,
                    lambda s=sig: asyncio.create_task(self._async_signal_handler(s)),
                )
    
    def _restore_signal_handlers(self) -> None:
        """Restore original signal handlers."""
        if sys.platform != "win32":
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.remove_signal_handler(sig)
                except Exception:
                    pass
    
    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Synchronous signal handler (Windows)."""
        self._logger.info(f"Received signal {signum}")
        self._shutdown_requested = True
    
    async def _async_signal_handler(self, sig: signal.Signals) -> None:
        """Async signal handler (Unix)."""
        self._logger.info(f"Received signal {sig.name}")
        await self.stop()
    
    # --------------------------------------------------------
    # Alerts
    # --------------------------------------------------------
    
    async def _send_alert(
        self,
        severity: str,
        title: str,
        message: str,
    ) -> None:
        """Send an alert notification."""
        if self._alert_callback:
            try:
                await self._alert_callback(severity, title, message)
            except Exception as e:
                self._logger.error(f"Failed to send alert: {e}")
    
    # --------------------------------------------------------
    # Health & Status
    # --------------------------------------------------------
    
    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status."""
        clock = ClockFactory.get_clock()
        
        return {
            "state": self._state_manager.state.value,
            "running": self._running,
            "shutdown_requested": self._shutdown_requested,
            "mode": self._config.mode.value,
            "correlation_id": self._correlation_id,
            "current_time": clock.now().isoformat(),
            "is_trading_allowed": self.is_trading_allowed,
            "modules": self._registry.get_status_summary(),
            "cycle_stats": self._cycle_history.get_statistics(),
            "last_cycle": self._current_cycle.to_dict() if self._current_cycle else None,
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform system health check."""
        module_health = await self._registry.check_all_health()
        unhealthy = self._registry.get_unhealthy_modules()
        
        overall_healthy = (
            self._running and
            not self._shutdown_requested and
            len(unhealthy) == 0 and
            self._state_manager.state == SystemState.RUNNING
        )
        
        return {
            "healthy": overall_healthy,
            "state": self._state_manager.state.value,
            "modules": module_health,
            "unhealthy_modules": unhealthy,
            "cycle_success_rate": self._cycle_history.get_success_rate(),
        }


# ============================================================
# ORCHESTRATOR FACTORY
# ============================================================

def create_orchestrator(
    mode: RuntimeMode = RuntimeMode.FULL,
    config: Optional[OrchestratorConfig] = None,
    alert_callback: Optional[Callable[[str, str, str], Awaitable[None]]] = None,
) -> Orchestrator:
    """
    Factory function to create an orchestrator.
    
    Args:
        mode: Runtime mode
        config: Configuration (or load from environment)
        alert_callback: Alert callback function
        
    Returns:
        Configured Orchestrator instance
    """
    if config is None:
        config = OrchestratorConfig.from_env()
        config.mode = mode
    
    return Orchestrator(config=config, alert_callback=alert_callback)


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "Orchestrator",
    "create_orchestrator",
    "setup_logging",
]
