"""
Orchestrator - Execution Pipeline.

============================================================
RESPONSIBILITY
============================================================
Manages stage execution with strict ordering and failure handling.

- Execute stages in correct order
- Short-circuit on failure
- Track execution timing
- Classify errors (recoverable vs non-recoverable)

============================================================
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from dataclasses import dataclass, field

from .models import (
    ExecutionStage,
    RuntimeMode,
    StageResult,
    CycleResult,
    SafetyContext,
)
from core.exceptions import (
    TradingException,
    PipelineError,
    EmergencyStopError,
    classify_exception,
    ErrorClassification,
)
from core.clock import ClockFactory


# ============================================================
# STAGE HANDLER TYPE
# ============================================================

StageHandler = Callable[[], Awaitable[Dict[str, Any]]]


# ============================================================
# STAGE EXECUTOR
# ============================================================

class StageExecutor:
    """
    Executes a single stage with timing and error handling.
    """
    
    def __init__(
        self,
        stage: ExecutionStage,
        handler: StageHandler,
        timeout_seconds: float = 300.0,
    ):
        """
        Initialize stage executor.
        
        Args:
            stage: The stage to execute
            handler: Async function to execute
            timeout_seconds: Execution timeout
        """
        self.stage = stage
        self.handler = handler
        self.timeout_seconds = timeout_seconds
        self._logger = logging.getLogger(__name__)
    
    async def execute(self) -> StageResult:
        """
        Execute the stage.
        
        Returns:
            StageResult with execution details
        """
        clock = ClockFactory.get_clock()
        started_at = clock.now()
        
        self._logger.info(
            f"Stage [{self.stage.order:02d}] START: {self.stage.description}"
        )
        
        try:
            # Execute with timeout
            context = await asyncio.wait_for(
                self.handler(),
                timeout=self.timeout_seconds,
            )
            
            completed_at = clock.now()
            duration = (completed_at - started_at).total_seconds()
            
            self._logger.info(
                f"Stage [{self.stage.order:02d}] COMPLETE: {self.stage.description} "
                f"({duration:.2f}s)"
            )
            
            return StageResult(
                stage=self.stage,
                success=True,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                context=context or {},
            )
            
        except asyncio.TimeoutError:
            completed_at = clock.now()
            duration = (completed_at - started_at).total_seconds()
            
            self._logger.error(
                f"Stage [{self.stage.order:02d}] TIMEOUT: {self.stage.description} "
                f"(>{self.timeout_seconds}s)"
            )
            
            return StageResult(
                stage=self.stage,
                success=False,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                error=f"Stage timeout after {self.timeout_seconds}s",
                error_type="TimeoutError",
                recoverable=True,
            )
            
        except EmergencyStopError as e:
            completed_at = clock.now()
            duration = (completed_at - started_at).total_seconds()
            
            self._logger.critical(
                f"Stage [{self.stage.order:02d}] EMERGENCY STOP: {self.stage.description} "
                f"- {e.message}"
            )
            
            return StageResult(
                stage=self.stage,
                success=False,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                error=e.message,
                error_type="EmergencyStopError",
                recoverable=False,
                context=e.context,
            )
            
        except TradingException as e:
            completed_at = clock.now()
            duration = (completed_at - started_at).total_seconds()
            
            self._logger.error(
                f"Stage [{self.stage.order:02d}] FAILED: {self.stage.description} "
                f"- {e.message}"
            )
            
            return StageResult(
                stage=self.stage,
                success=False,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                error=e.message,
                error_type=type(e).__name__,
                recoverable=e.is_recoverable,
                context=e.context,
            )
            
        except Exception as e:
            completed_at = clock.now()
            duration = (completed_at - started_at).total_seconds()
            
            classification = classify_exception(e)
            
            self._logger.error(
                f"Stage [{self.stage.order:02d}] ERROR: {self.stage.description} "
                f"- {type(e).__name__}: {e}",
                exc_info=True,
            )
            
            return StageResult(
                stage=self.stage,
                success=False,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                error=str(e),
                error_type=type(e).__name__,
                recoverable=classification != ErrorClassification.NON_RECOVERABLE,
            )


# ============================================================
# EXECUTION PIPELINE
# ============================================================

class ExecutionPipeline:
    """
    Orchestrates stage execution in strict order.
    
    Features:
    - Strict ordering enforcement
    - Failure short-circuit
    - Safety checks before trading stages
    - Cycle result tracking
    """
    
    def __init__(
        self,
        mode: RuntimeMode,
        handlers: Dict[ExecutionStage, StageHandler],
        safety_checker: Optional[Callable[[], SafetyContext]] = None,
        stage_timeout_seconds: float = 300.0,
    ):
        """
        Initialize pipeline.
        
        Args:
            mode: Runtime mode
            handlers: Stage handlers
            safety_checker: Function to check safety context
            stage_timeout_seconds: Default timeout per stage
        """
        self.mode = mode
        self._handlers = handlers
        self._safety_checker = safety_checker
        self._stage_timeout = stage_timeout_seconds
        self._logger = logging.getLogger(__name__)
        
        # Get stages for this mode
        self._stages = ExecutionStage.get_stages_for_mode(mode)
    
    @property
    def stages(self) -> List[ExecutionStage]:
        """Get stages to execute."""
        return self._stages
    
    def _generate_cycle_id(self) -> str:
        """Generate a unique cycle ID."""
        return f"cycle_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    async def execute_cycle(self) -> CycleResult:
        """
        Execute a complete cycle.
        
        Returns:
            CycleResult with all stage results
        """
        clock = ClockFactory.get_clock()
        cycle_id = self._generate_cycle_id()
        
        result = CycleResult(
            cycle_id=cycle_id,
            mode=self.mode,
            started_at=clock.now(),
        )
        
        self._logger.info(
            f"=== CYCLE START: {cycle_id} | mode={self.mode.value} | "
            f"stages={len(self._stages)} ==="
        )
        
        for stage in self._stages:
            # Check if we have a handler
            handler = self._handlers.get(stage)
            if not handler:
                self._logger.debug(f"No handler for stage: {stage.stage_id}")
                continue
            
            # Safety check before trading stages
            if stage in (
                ExecutionStage.RUN_STRATEGY,
                ExecutionStage.RUN_EXECUTION,
            ):
                if not await self._check_safety_for_trading(stage):
                    self._logger.warning(
                        f"Safety check failed for {stage.stage_id}, skipping"
                    )
                    continue
            
            # Execute stage
            executor = StageExecutor(
                stage=stage,
                handler=handler,
                timeout_seconds=self._stage_timeout,
            )
            
            stage_result = await executor.execute()
            result.add_stage_result(stage_result)
            
            # Short-circuit on failure
            if not stage_result.success:
                self._logger.error(
                    f"=== CYCLE ABORTED: {cycle_id} | "
                    f"failed_stage={stage.stage_id} ==="
                )
                result.completed_at = clock.now()
                result.success = False
                return result
        
        result.completed_at = clock.now()
        result.success = True
        
        self._logger.info(
            f"=== CYCLE COMPLETE: {cycle_id} | "
            f"duration={result.duration_seconds:.2f}s | "
            f"stages_completed={result.stages_completed} ==="
        )
        
        return result
    
    async def _check_safety_for_trading(self, stage: ExecutionStage) -> bool:
        """
        Check if it's safe to proceed with trading stages.
        
        Args:
            stage: The stage being checked
            
        Returns:
            True if safe to proceed
        """
        if not self._safety_checker:
            return True
        
        try:
            safety = self._safety_checker()
            
            if not safety.can_trade:
                self._logger.warning(
                    f"Trading blocked for {stage.stage_id}: {safety.block_reason}"
                )
                return False
            
            return True
            
        except Exception as e:
            self._logger.error(f"Safety check error: {e}")
            # Default to blocking on safety check failure
            return False
    
    async def execute_single_stage(
        self,
        stage: ExecutionStage,
    ) -> StageResult:
        """
        Execute a single stage (for testing/manual execution).
        
        Args:
            stage: Stage to execute
            
        Returns:
            StageResult
            
        Raises:
            PipelineError: If no handler for stage
        """
        handler = self._handlers.get(stage)
        if not handler:
            raise PipelineError(
                message=f"No handler for stage: {stage.stage_id}",
                stage=stage.stage_id,
            )
        
        executor = StageExecutor(
            stage=stage,
            handler=handler,
            timeout_seconds=self._stage_timeout,
        )
        
        return await executor.execute()


# ============================================================
# PIPELINE BUILDER
# ============================================================

class PipelineBuilder:
    """
    Builder for constructing execution pipelines.
    """
    
    def __init__(self, mode: RuntimeMode):
        """
        Initialize builder.
        
        Args:
            mode: Runtime mode
        """
        self._mode = mode
        self._handlers: Dict[ExecutionStage, StageHandler] = {}
        self._safety_checker: Optional[Callable[[], SafetyContext]] = None
        self._stage_timeout = 300.0
    
    def with_handler(
        self,
        stage: ExecutionStage,
        handler: StageHandler,
    ) -> "PipelineBuilder":
        """Add a stage handler."""
        self._handlers[stage] = handler
        return self
    
    def with_handlers(
        self,
        handlers: Dict[ExecutionStage, StageHandler],
    ) -> "PipelineBuilder":
        """Add multiple stage handlers."""
        self._handlers.update(handlers)
        return self
    
    def with_safety_checker(
        self,
        checker: Callable[[], SafetyContext],
    ) -> "PipelineBuilder":
        """Set safety checker."""
        self._safety_checker = checker
        return self
    
    def with_stage_timeout(self, timeout_seconds: float) -> "PipelineBuilder":
        """Set stage timeout."""
        self._stage_timeout = timeout_seconds
        return self
    
    def build(self) -> ExecutionPipeline:
        """Build the pipeline."""
        return ExecutionPipeline(
            mode=self._mode,
            handlers=self._handlers,
            safety_checker=self._safety_checker,
            stage_timeout_seconds=self._stage_timeout,
        )


# ============================================================
# CYCLE HISTORY
# ============================================================

class CycleHistory:
    """
    Tracks execution cycle history.
    """
    
    def __init__(self, max_size: int = 100):
        """
        Initialize history.
        
        Args:
            max_size: Maximum cycles to keep
        """
        self._max_size = max_size
        self._cycles: List[CycleResult] = []
        self._lock = asyncio.Lock()
    
    async def add(self, result: CycleResult) -> None:
        """Add a cycle result."""
        async with self._lock:
            self._cycles.append(result)
            if len(self._cycles) > self._max_size:
                self._cycles = self._cycles[-self._max_size:]
    
    def get_recent(self, limit: int = 10) -> List[CycleResult]:
        """Get recent cycles."""
        return self._cycles[-limit:]
    
    def get_last(self) -> Optional[CycleResult]:
        """Get last cycle."""
        return self._cycles[-1] if self._cycles else None
    
    def get_success_rate(self, last_n: int = 10) -> float:
        """Get success rate of last N cycles."""
        recent = self._cycles[-last_n:]
        if not recent:
            return 0.0
        successes = sum(1 for c in recent if c.success)
        return successes / len(recent)
    
    def get_average_duration(self, last_n: int = 10) -> float:
        """Get average duration of last N cycles."""
        recent = self._cycles[-last_n:]
        if not recent:
            return 0.0
        durations = [c.duration_seconds for c in recent if c.completed_at]
        return sum(durations) / len(durations) if durations else 0.0
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get cycle statistics."""
        if not self._cycles:
            return {
                "total_cycles": 0,
                "success_rate": 0.0,
                "average_duration_seconds": 0.0,
            }
        
        successes = sum(1 for c in self._cycles if c.success)
        durations = [c.duration_seconds for c in self._cycles if c.completed_at]
        
        return {
            "total_cycles": len(self._cycles),
            "successful_cycles": successes,
            "failed_cycles": len(self._cycles) - successes,
            "success_rate": successes / len(self._cycles),
            "average_duration_seconds": sum(durations) / len(durations) if durations else 0.0,
            "last_cycle_time": self._cycles[-1].started_at.isoformat() if self._cycles else None,
            "last_success": self._cycles[-1].success if self._cycles else None,
        }


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "StageHandler",
    "StageExecutor",
    "ExecutionPipeline",
    "PipelineBuilder",
    "CycleHistory",
]
