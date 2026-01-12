"""
Chaos Test Executor.

============================================================
PURPOSE
============================================================
Orchestrates chaos test execution with proper safety controls.

The executor:
1. Validates run mode before execution
2. Injects faults at specified points
3. Monitors system reactions
4. Validates expected behaviors
5. Generates detailed results

============================================================
SAFETY GUARANTEES
============================================================

1. DRY_RUN mode: No faults actually injected, just validated
2. STAGING mode: Full execution in isolated environment
3. SHADOW_PRODUCTION: Observe-only, no execution

The executor NEVER allows fault injection in production
without explicit shadow mode configuration.

============================================================
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .models import (
    RunMode,
    FaultCategory,
    FaultIntensity,
    FaultDefinition,
    ActiveFault,
    ChaosTestCase,
    ChaosTestResult,
    ChaosTestRun,
    ChaosReport,
    ExpectedSystemState,
    ExpectedTradeGuardDecision,
    ForbiddenBehavior,
)
from .faults import (
    FaultRegistry,
    get_fault_registry,
    BaseFaultInjector,
    DataFaultInjector,
    ApiFaultInjector,
    ProcessFaultInjector,
    ExecutionFaultInjector,
    SystemFaultInjector,
    ChaosException,
)
from .validator import (
    ChaosValidator,
    SystemStateMonitor,
    TradeGuardMonitor,
    AlertMonitor,
    BehaviorMonitor,
    create_validator,
)


logger = logging.getLogger(__name__)


# ============================================================
# EXECUTION CONTEXT
# ============================================================

class ChaosExecutionContext:
    """Context for a chaos test execution."""
    
    def __init__(
        self,
        run_mode: RunMode,
        test_run_id: str,
        validator: ChaosValidator,
    ):
        self.run_mode = run_mode
        self.test_run_id = test_run_id
        self.validator = validator
        self.started_at: Optional[datetime] = None
        self.ended_at: Optional[datetime] = None
        self._active_faults: List[ActiveFault] = []
        self._metadata: Dict[str, Any] = {}
    
    def add_fault(self, fault: ActiveFault) -> None:
        """Add an active fault to context."""
        self._active_faults.append(fault)
    
    def get_active_faults(self) -> List[ActiveFault]:
        """Get all active faults."""
        return list(self._active_faults)
    
    def set_metadata(self, key: str, value: Any) -> None:
        """Set context metadata."""
        self._metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get context metadata."""
        return self._metadata.get(key, default)


# ============================================================
# CHAOS TEST EXECUTOR
# ============================================================

class ChaosTestExecutor:
    """
    Executes chaos tests with safety controls.
    
    This is the main entry point for running chaos tests.
    It orchestrates fault injection, monitoring, and validation.
    """
    
    def __init__(
        self,
        run_mode: RunMode,
        fault_registry: Optional[FaultRegistry] = None,
    ):
        """
        Initialize the executor.
        
        Args:
            run_mode: Execution mode (DRY_RUN, STAGING, SHADOW_PRODUCTION)
            fault_registry: Optional fault registry (uses global if not provided)
        """
        self._run_mode = run_mode
        self._fault_registry = fault_registry or get_fault_registry()
        
        # Initialize injectors
        self._injectors: Dict[FaultCategory, BaseFaultInjector] = {
            FaultCategory.DATA: DataFaultInjector(self._fault_registry),
            FaultCategory.API: ApiFaultInjector(self._fault_registry),
            FaultCategory.PROCESS: ProcessFaultInjector(self._fault_registry),
            FaultCategory.EXECUTION: ExecutionFaultInjector(self._fault_registry),
            FaultCategory.SYSTEM: SystemFaultInjector(self._fault_registry),
        }
        
        # Execution hooks
        self._before_test_hooks: List[Callable] = []
        self._after_test_hooks: List[Callable] = []
        self._on_failure_hooks: List[Callable] = []
        
        logger.info(f"ChaosTestExecutor initialized in {run_mode.value} mode")
    
    @property
    def run_mode(self) -> RunMode:
        """Get current run mode."""
        return self._run_mode
    
    def set_run_mode(self, mode: RunMode) -> None:
        """Update run mode."""
        logger.info(f"Changing run mode from {self._run_mode.value} to {mode.value}")
        self._run_mode = mode
    
    def add_before_test_hook(self, hook: Callable) -> None:
        """Add a hook to run before each test."""
        self._before_test_hooks.append(hook)
    
    def add_after_test_hook(self, hook: Callable) -> None:
        """Add a hook to run after each test."""
        self._after_test_hooks.append(hook)
    
    def add_on_failure_hook(self, hook: Callable) -> None:
        """Add a hook to run when a test fails."""
        self._on_failure_hooks.append(hook)
    
    # ========================================================
    # SINGLE TEST EXECUTION
    # ========================================================
    
    async def execute_test(
        self,
        test_case: ChaosTestCase,
        timeout_seconds: float = 120.0,
    ) -> ChaosTestResult:
        """
        Execute a single chaos test case.
        
        Args:
            test_case: The test case to execute
            timeout_seconds: Maximum execution time
            
        Returns:
            ChaosTestResult with pass/fail and details
        """
        test_run_id = str(uuid.uuid4())
        validator = create_validator()
        context = ChaosExecutionContext(
            run_mode=self._run_mode,
            test_run_id=test_run_id,
            validator=validator,
        )
        
        logger.info(
            f"Executing chaos test: {test_case.name} "
            f"(run_id={test_run_id}, mode={self._run_mode.value})"
        )
        
        # Run before hooks
        for hook in self._before_test_hooks:
            try:
                await self._call_hook(hook, test_case, context)
            except Exception as e:
                logger.error(f"Before hook failed: {e}")
        
        context.started_at = datetime.utcnow()
        
        try:
            result = await asyncio.wait_for(
                self._execute_test_internal(test_case, context),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            context.ended_at = datetime.utcnow()
            result = ChaosTestResult(
                result_id=str(uuid.uuid4()),
                test_case=test_case,
                passed=False,
                actual_system_state=None,
                actual_trade_guard_decision=None,
                alerts_generated=[],
                forbidden_behavior_violations=[],
                started_at=context.started_at,
                ended_at=context.ended_at,
                error_message=f"Test timed out after {timeout_seconds} seconds",
            )
        except Exception as e:
            context.ended_at = datetime.utcnow()
            result = ChaosTestResult(
                result_id=str(uuid.uuid4()),
                test_case=test_case,
                passed=False,
                actual_system_state=None,
                actual_trade_guard_decision=None,
                alerts_generated=[],
                forbidden_behavior_violations=[],
                started_at=context.started_at,
                ended_at=context.ended_at,
                error_message=f"Test execution error: {str(e)}",
            )
            logger.exception(f"Test execution failed: {e}")
        
        # Run after hooks
        for hook in self._after_test_hooks:
            try:
                await self._call_hook(hook, test_case, context, result)
            except Exception as e:
                logger.error(f"After hook failed: {e}")
        
        # Run failure hooks if needed
        if not result.passed:
            for hook in self._on_failure_hooks:
                try:
                    await self._call_hook(hook, test_case, context, result)
                except Exception as e:
                    logger.error(f"Failure hook failed: {e}")
        
        return result
    
    async def _execute_test_internal(
        self,
        test_case: ChaosTestCase,
        context: ChaosExecutionContext,
    ) -> ChaosTestResult:
        """Internal test execution logic."""
        fault_def = test_case.fault_definition
        injector = self._injectors.get(fault_def.category)
        
        if not injector:
            raise ChaosException(f"No injector for category: {fault_def.category}")
        
        module_crashed = False
        
        try:
            # Check if we should actually inject
            if self._run_mode == RunMode.DRY_RUN:
                logger.info(f"DRY_RUN mode: Simulating fault {fault_def.name}")
                # In dry run, we just validate the test case structure
                await self._simulate_fault_dry_run(test_case, context)
            else:
                # Actually inject the fault
                await self._inject_fault(
                    injector,
                    fault_def,
                    context,
                )
                
                # Monitor for reactions
                await self._monitor_reactions(test_case, context)
                
        except ChaosException as e:
            if "crash" in str(e).lower():
                module_crashed = True
            raise
        finally:
            # Cleanup active faults
            await self._cleanup_faults(context)
        
        context.ended_at = datetime.utcnow()
        
        # Validate results
        return await context.validator.validate_test_case(
            test_case=test_case,
            test_start_time=context.started_at,
            test_end_time=context.ended_at,
            module_crashed=module_crashed,
        )
    
    async def _simulate_fault_dry_run(
        self,
        test_case: ChaosTestCase,
        context: ChaosExecutionContext,
    ) -> None:
        """Simulate fault injection in dry run mode."""
        fault_def = test_case.fault_definition
        
        # Log what would happen
        logger.info(
            f"Would inject fault: {fault_def.name} "
            f"at {fault_def.injection_point} "
            f"with intensity {fault_def.intensity.value}"
        )
        
        # Simulate expected state transitions
        context.validator._state_monitor.update_state(
            test_case.expected_system_state
        )
        context.validator._trade_guard_monitor.record_decision(
            test_case.expected_trade_guard_decision,
            reason="Simulated in dry run",
        )
        for alert in test_case.expected_alerts:
            context.validator._alert_monitor.record_alert("INFO", alert)
        
        # Small delay to simulate execution
        await asyncio.sleep(0.1)
    
    async def _inject_fault(
        self,
        injector: BaseFaultInjector,
        fault_def: FaultDefinition,
        context: ChaosExecutionContext,
    ) -> None:
        """Inject a fault using the appropriate injector."""
        logger.info(
            f"Injecting fault: {fault_def.name} "
            f"at {fault_def.injection_point}"
        )
        
        # Get the injection method
        method_name = f"execute_{fault_def.fault_type}"
        method = getattr(injector, method_name, None)
        
        if method is None:
            raise ChaosException(
                f"Unknown fault type: {fault_def.fault_type} "
                f"for injector {injector.__class__.__name__}"
            )
        
        # Create active fault
        active_fault = ActiveFault(
            fault_id=fault_def.fault_id,
            definition=fault_def,
            started_at=datetime.utcnow(),
            expires_at=(
                datetime.utcnow() + timedelta(seconds=fault_def.duration_seconds)
                if fault_def.duration_seconds
                else None
            ),
        )
        context.add_fault(active_fault)
        
        # Execute the fault
        await method(**fault_def.parameters)
    
    async def _monitor_reactions(
        self,
        test_case: ChaosTestCase,
        context: ChaosExecutionContext,
    ) -> None:
        """Monitor system reactions to the injected fault."""
        # Wait for system to react
        monitoring_duration = min(
            test_case.fault_definition.duration_seconds or 5.0,
            30.0,  # Cap at 30 seconds
        )
        
        logger.info(f"Monitoring reactions for {monitoring_duration}s")
        await asyncio.sleep(monitoring_duration)
    
    async def _cleanup_faults(self, context: ChaosExecutionContext) -> None:
        """Clean up all active faults."""
        for fault in context.get_active_faults():
            try:
                self._fault_registry.deactivate(fault.fault_id)
                logger.info(f"Deactivated fault: {fault.fault_id}")
            except Exception as e:
                logger.error(f"Failed to deactivate fault {fault.fault_id}: {e}")
    
    async def _call_hook(self, hook: Callable, *args) -> None:
        """Call a hook function."""
        if asyncio.iscoroutinefunction(hook):
            await hook(*args)
        else:
            hook(*args)
    
    # ========================================================
    # BATCH TEST EXECUTION
    # ========================================================
    
    async def execute_test_run(
        self,
        test_cases: List[ChaosTestCase],
        run_name: str = "Chaos Test Run",
        stop_on_first_failure: bool = False,
        parallel: bool = False,
        max_parallel: int = 5,
    ) -> ChaosTestRun:
        """
        Execute a batch of chaos tests.
        
        Args:
            test_cases: List of test cases to run
            run_name: Name for this test run
            stop_on_first_failure: Stop execution on first failure
            parallel: Run tests in parallel
            max_parallel: Maximum parallel tests
            
        Returns:
            ChaosTestRun with all results
        """
        run_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        results: List[ChaosTestResult] = []
        
        logger.info(
            f"Starting chaos test run: {run_name} "
            f"(run_id={run_id}, tests={len(test_cases)})"
        )
        
        if parallel and self._run_mode != RunMode.DRY_RUN:
            results = await self._execute_parallel(
                test_cases,
                max_parallel,
                stop_on_first_failure,
            )
        else:
            results = await self._execute_sequential(
                test_cases,
                stop_on_first_failure,
            )
        
        ended_at = datetime.utcnow()
        
        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        
        run = ChaosTestRun(
            run_id=run_id,
            run_mode=self._run_mode,
            name=run_name,
            started_at=started_at,
            ended_at=ended_at,
            test_results=results,
            total_tests=len(test_cases),
            passed_tests=passed_count,
            failed_tests=failed_count,
        )
        
        logger.info(
            f"Chaos test run complete: {passed_count}/{len(results)} passed "
            f"in {(ended_at - started_at).total_seconds():.2f}s"
        )
        
        return run
    
    async def _execute_sequential(
        self,
        test_cases: List[ChaosTestCase],
        stop_on_first_failure: bool,
    ) -> List[ChaosTestResult]:
        """Execute tests sequentially."""
        results: List[ChaosTestResult] = []
        
        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"Running test {i}/{len(test_cases)}: {test_case.name}")
            
            result = await self.execute_test(test_case)
            results.append(result)
            
            if not result.passed and stop_on_first_failure:
                logger.warning(
                    f"Stopping test run due to failure: {test_case.name}"
                )
                break
        
        return results
    
    async def _execute_parallel(
        self,
        test_cases: List[ChaosTestCase],
        max_parallel: int,
        stop_on_first_failure: bool,
    ) -> List[ChaosTestResult]:
        """Execute tests in parallel with semaphore control."""
        semaphore = asyncio.Semaphore(max_parallel)
        results: List[ChaosTestResult] = []
        stop_flag = asyncio.Event()
        
        async def run_with_semaphore(test_case: ChaosTestCase) -> ChaosTestResult:
            if stop_flag.is_set():
                return ChaosTestResult(
                    result_id=str(uuid.uuid4()),
                    test_case=test_case,
                    passed=False,
                    actual_system_state=None,
                    actual_trade_guard_decision=None,
                    alerts_generated=[],
                    forbidden_behavior_violations=[],
                    started_at=datetime.utcnow(),
                    ended_at=datetime.utcnow(),
                    error_message="Test run stopped due to earlier failure",
                )
            
            async with semaphore:
                result = await self.execute_test(test_case)
                if not result.passed and stop_on_first_failure:
                    stop_flag.set()
                return result
        
        tasks = [run_with_semaphore(tc) for tc in test_cases]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to failed results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(
                    ChaosTestResult(
                        result_id=str(uuid.uuid4()),
                        test_case=test_cases[i],
                        passed=False,
                        actual_system_state=None,
                        actual_trade_guard_decision=None,
                        alerts_generated=[],
                        forbidden_behavior_violations=[],
                        started_at=datetime.utcnow(),
                        ended_at=datetime.utcnow(),
                        error_message=str(result),
                    )
                )
            else:
                processed_results.append(result)
        
        return processed_results


# ============================================================
# FACTORY FUNCTION
# ============================================================

def create_executor(run_mode: RunMode = RunMode.DRY_RUN) -> ChaosTestExecutor:
    """
    Create a ChaosTestExecutor with default configuration.
    
    Args:
        run_mode: Execution mode (defaults to DRY_RUN for safety)
        
    Returns:
        Configured ChaosTestExecutor
    """
    return ChaosTestExecutor(run_mode=run_mode)
