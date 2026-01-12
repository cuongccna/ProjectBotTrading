"""
Trade Guard Absolute - Main Engine.

============================================================
PURPOSE
============================================================
The TradeGuardAbsolute class is the FINAL, NON-BYPASSABLE
execution gate before any trade reaches the Execution Engine.

This is the highest authority in the trading pipeline.

============================================================
CRITICAL BEHAVIOR
============================================================
1. BINARY OUTPUT ONLY
   - EXECUTE: Trade may proceed to Execution Engine
   - BLOCK: Trade is rejected, no further action

2. NO MODIFICATIONS
   - Cannot adjust position size
   - Cannot defer decision
   - Cannot retry

3. FAIL-SAFE DEFAULT
   - Any error = BLOCK
   - Any timeout = BLOCK
   - Any missing data = BLOCK

4. ALL DECISIONS LOGGED
   - Every decision goes to database
   - BLOCK decisions trigger Telegram alert

5. DETERMINISTIC
   - Same input = Same output (given same state)
   - No randomness
   - No machine learning

============================================================
"""

import time
from datetime import datetime
from typing import List, Optional
import logging

from .types import (
    GuardInput,
    GuardDecision,
    GuardDecisionOutput,
    ValidationResult,
    BlockReason,
    BlockSeverity,
    BlockCategory,
    TradeGuardError,
)
from .config import TradeGuardConfig
from .validators import (
    BaseValidator,
    SystemIntegrityValidator,
    ExecutionSafetyValidator,
    StateConsistencyValidator,
    RuleValidator,
    EnvironmentValidator,
    create_block_result,
)


logger = logging.getLogger(__name__)


class TradeGuardAbsolute:
    """
    The Final Execution Gate.
    
    This class is the highest authority before trade execution.
    NO OTHER MODULE MAY OVERRIDE ITS DECISIONS.
    
    Usage:
        guard = TradeGuardAbsolute(config)
        result = guard.evaluate(guard_input)
        
        if result.decision == GuardDecision.EXECUTE:
            # Proceed to Execution Engine
            pass
        else:
            # Trade blocked - log and alert
            pass
    """
    
    def __init__(
        self,
        config: Optional[TradeGuardConfig] = None,
    ):
        """
        Initialize Trade Guard Absolute.
        
        Args:
            config: Guard configuration (uses defaults if None)
        """
        self._config = config or TradeGuardConfig()
        self._validators: List[BaseValidator] = []
        
        # Initialize validators
        self._init_validators()
        
        logger.info("TradeGuardAbsolute initialized")
    
    def _init_validators(self) -> None:
        """Initialize all validators in priority order."""
        # Order matters - most critical first
        # RuleValidator checks halt state first
        self._validators = [
            RuleValidator(self._config.rules),
            SystemIntegrityValidator(self._config.system_integrity),
            ExecutionSafetyValidator(self._config.execution_safety),
            StateConsistencyValidator(self._config.state_consistency),
            EnvironmentValidator(self._config.environmental),
        ]
    
    @property
    def config(self) -> TradeGuardConfig:
        """Get current configuration."""
        return self._config
    
    def evaluate(
        self,
        guard_input: GuardInput,
    ) -> GuardDecisionOutput:
        """
        Evaluate a trade intent.
        
        This is the main entry point.
        
        CRITICAL: This method NEVER throws exceptions.
        Any exception results in BLOCK.
        
        Args:
            guard_input: All input data for evaluation
            
        Returns:
            GuardDecisionOutput with decision and details
        """
        start_time = time.perf_counter()
        evaluation_id = self._generate_evaluation_id(guard_input)
        
        try:
            return self._evaluate_internal(
                guard_input=guard_input,
                evaluation_id=evaluation_id,
                start_time=start_time,
            )
        
        except Exception as e:
            # CRITICAL: Any exception = BLOCK
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            logger.error(
                f"TradeGuardAbsolute internal error: {e}",
                exc_info=True,
            )
            
            return self._create_internal_error_block(
                guard_input=guard_input,
                evaluation_id=evaluation_id,
                error=e,
                elapsed_ms=elapsed_ms,
            )
    
    def _evaluate_internal(
        self,
        guard_input: GuardInput,
        evaluation_id: str,
        start_time: float,
    ) -> GuardDecisionOutput:
        """
        Internal evaluation logic.
        
        Runs all validators and aggregates results.
        """
        validation_results: List[ValidationResult] = []
        first_failure: Optional[ValidationResult] = None
        
        # Validate input
        input_result = self._validate_input(guard_input)
        if input_result is not None:
            validation_results.append(input_result)
            first_failure = input_result
        
        # Run validators (stop on first failure for efficiency)
        if first_failure is None:
            for validator in self._validators:
                # Check timeout
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                if elapsed_ms > self._config.timing.max_evaluation_time_ms:
                    timeout_result = create_block_result(
                        validator_name="TradeGuardAbsolute",
                        reason=BlockReason.IE_TIMEOUT,
                        severity=BlockSeverity.HIGH,
                        details={
                            "elapsed_ms": elapsed_ms,
                            "timeout_ms": self._config.timing.max_evaluation_time_ms,
                            "message": "Evaluation timeout exceeded",
                        },
                    )
                    validation_results.append(timeout_result)
                    first_failure = timeout_result
                    break
                
                # Run validator
                result = validator.validate(
                    guard_input=guard_input,
                    timeout_ms=self._config.timing.validator_timeout_ms,
                )
                validation_results.append(result)
                
                if not result.is_valid:
                    first_failure = result
                    break  # Stop on first failure
        
        # Calculate timing
        total_elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        # Determine decision
        if first_failure is None:
            # All validators passed
            return GuardDecisionOutput(
                decision=GuardDecision.EXECUTE,
                evaluation_id=evaluation_id,
                trade_intent=guard_input.trade_intent,
                timestamp=datetime.utcnow(),
                reason=None,
                severity=None,
                category=None,
                details={"status": "All validators passed"},
                validation_results=validation_results,
                evaluation_time_ms=total_elapsed_ms,
            )
        else:
            # At least one validator failed
            return GuardDecisionOutput(
                decision=GuardDecision.BLOCK,
                evaluation_id=evaluation_id,
                trade_intent=guard_input.trade_intent,
                timestamp=datetime.utcnow(),
                reason=first_failure.reason,
                severity=first_failure.severity,
                category=first_failure.reason.get_category() if first_failure.reason else None,
                details=first_failure.details,
                validation_results=validation_results,
                evaluation_time_ms=total_elapsed_ms,
            )
    
    def _validate_input(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """
        Validate input data is present.
        
        Missing input = BLOCK.
        """
        if not self._config.block_on_missing_input:
            return None
        
        errors = []
        
        # Check trade intent
        if guard_input.trade_intent is None:
            errors.append("trade_intent is missing")
        
        # Check system state
        if guard_input.system_state is None:
            errors.append("system_state is missing")
        
        # Check execution health
        if guard_input.execution_health is None:
            errors.append("execution_health is missing")
        
        # Check halt state
        if guard_input.halt_state is None:
            errors.append("halt_state is missing")
        
        # Check account state
        if guard_input.account_state is None:
            errors.append("account_state is missing")
        
        # Check environmental context
        if guard_input.environmental_context is None:
            errors.append("environmental_context is missing")
        
        if errors:
            return ValidationResult(
                is_valid=False,
                reason=BlockReason.IE_GUARD_INTERNAL_ERROR,
                severity=BlockSeverity.CRITICAL,
                details={
                    "missing_inputs": errors,
                    "message": "Required input data is missing",
                },
                validator_name="TradeGuardAbsolute.InputValidator",
            )
        
        return None
    
    def _create_internal_error_block(
        self,
        guard_input: GuardInput,
        evaluation_id: str,
        error: Exception,
        elapsed_ms: float,
    ) -> GuardDecisionOutput:
        """
        Create BLOCK result for internal error.
        
        This is the fail-safe path.
        """
        return GuardDecisionOutput(
            decision=GuardDecision.BLOCK,
            evaluation_id=evaluation_id,
            trade_intent=guard_input.trade_intent if guard_input else None,
            timestamp=datetime.utcnow(),
            reason=BlockReason.IE_GUARD_INTERNAL_ERROR,
            severity=BlockSeverity.CRITICAL,
            category=BlockCategory.INTERNAL_ERROR,
            details={
                "error_type": error.__class__.__name__,
                "error_message": str(error),
                "message": "Internal error in Trade Guard - defaulting to BLOCK",
            },
            validation_results=[],
            evaluation_time_ms=elapsed_ms,
        )
    
    def _generate_evaluation_id(
        self,
        guard_input: GuardInput,
    ) -> str:
        """Generate unique evaluation ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        request_id = (
            guard_input.trade_intent.request_id[:8]
            if guard_input.trade_intent and guard_input.trade_intent.request_id
            else "UNKNOWN"
        )
        return f"GUARD-{timestamp}-{request_id}"
    
    def get_validator_info(self) -> List[dict]:
        """
        Get information about registered validators.
        
        Useful for diagnostics and monitoring.
        """
        return [
            {
                "name": v.meta.name,
                "category": v.meta.category.value,
                "description": v.meta.description,
                "is_critical": v.meta.is_critical,
            }
            for v in self._validators
        ]
    
    def health_check(self) -> dict:
        """
        Perform health check on the guard.
        
        Returns status of all components.
        """
        return {
            "status": "OK",
            "timestamp": datetime.utcnow().isoformat(),
            "validator_count": len(self._validators),
            "validators": [v.meta.name for v in self._validators],
            "config": {
                "block_on_internal_error": self._config.block_on_internal_error,
                "block_on_missing_input": self._config.block_on_missing_input,
                "max_evaluation_time_ms": self._config.timing.max_evaluation_time_ms,
            },
        }


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def create_guard(
    config: Optional[TradeGuardConfig] = None,
) -> TradeGuardAbsolute:
    """
    Create a new Trade Guard Absolute instance.
    
    Args:
        config: Optional configuration
        
    Returns:
        Configured TradeGuardAbsolute instance
    """
    return TradeGuardAbsolute(config=config)


def evaluate_trade(
    guard: TradeGuardAbsolute,
    guard_input: GuardInput,
) -> GuardDecisionOutput:
    """
    Evaluate a trade using the guard.
    
    This is the primary interface for trade evaluation.
    
    Args:
        guard: The guard instance
        guard_input: Input data for evaluation
        
    Returns:
        GuardDecisionOutput with decision
    """
    return guard.evaluate(guard_input)


def is_trade_allowed(
    guard: TradeGuardAbsolute,
    guard_input: GuardInput,
) -> bool:
    """
    Quick check if trade is allowed.
    
    Returns True if EXECUTE, False if BLOCK.
    
    Args:
        guard: The guard instance
        guard_input: Input data for evaluation
        
    Returns:
        True if trade is allowed, False otherwise
    """
    result = guard.evaluate(guard_input)
    return result.decision == GuardDecision.EXECUTE
