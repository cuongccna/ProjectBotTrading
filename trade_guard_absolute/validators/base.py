"""
Trade Guard Absolute - Base Validator.

============================================================
PURPOSE
============================================================
Abstract base class for all guard validators.

Each validator is responsible for one category of checks.
Validators are:
- Fast (< 20ms)
- Stateless (no side effects)
- Deterministic (same input = same output)
- Fail-safe (errors = BLOCK)

============================================================
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import time

from ..types import (
    GuardInput,
    ValidationResult,
    BlockReason,
    BlockSeverity,
    BlockCategory,
    ValidationError,
    TimeoutError,
)


# ============================================================
# VALIDATOR INTERFACE
# ============================================================

@dataclass
class ValidatorMeta:
    """
    Metadata about a validator.
    """
    name: str
    """Validator name."""
    
    category: BlockCategory
    """Primary category this validator covers."""
    
    description: str
    """What this validator checks."""
    
    is_critical: bool = True
    """
    Whether this validator is critical.
    Critical validators must pass for EXECUTE.
    Non-critical validators only warn.
    """


class BaseValidator(ABC):
    """
    Abstract base class for guard validators.
    
    Each validator:
    1. Receives GuardInput
    2. Performs category-specific checks
    3. Returns ValidationResult
    
    If ANY check fails, the validator returns is_valid=False.
    """
    
    @property
    @abstractmethod
    def meta(self) -> ValidatorMeta:
        """Get validator metadata."""
        pass
    
    @abstractmethod
    def _validate(self, guard_input: GuardInput) -> ValidationResult:
        """
        Internal validation logic.
        
        Subclasses implement this method.
        
        Args:
            guard_input: All input data for validation
            
        Returns:
            ValidationResult
        """
        pass
    
    def validate(
        self,
        guard_input: GuardInput,
        timeout_ms: float = 20.0,
    ) -> ValidationResult:
        """
        Execute validation with timeout protection.
        
        This is the main entry point. It wraps _validate with:
        - Timing measurement
        - Exception handling
        - Timeout protection
        
        Args:
            guard_input: Input data
            timeout_ms: Maximum time allowed
            
        Returns:
            ValidationResult (always returns, never throws)
        """
        start_time = time.perf_counter()
        
        try:
            # Run the actual validation
            result = self._validate(guard_input)
            
            # Check timing
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            result.validation_time_ms = elapsed_ms
            result.validator_name = self.meta.name
            
            # Timeout check (even if validation passed)
            if elapsed_ms > timeout_ms:
                return ValidationResult(
                    is_valid=False,
                    reason=BlockReason.IE_TIMEOUT,
                    severity=BlockSeverity.HIGH,
                    details={
                        "validator": self.meta.name,
                        "elapsed_ms": elapsed_ms,
                        "timeout_ms": timeout_ms,
                        "message": f"Validator exceeded timeout: {elapsed_ms:.2f}ms > {timeout_ms}ms",
                    },
                    validator_name=self.meta.name,
                    validation_time_ms=elapsed_ms,
                )
            
            return result
        
        except TimeoutError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ValidationResult(
                is_valid=False,
                reason=BlockReason.IE_TIMEOUT,
                severity=BlockSeverity.HIGH,
                details={
                    "validator": self.meta.name,
                    "error": str(e),
                    "message": "Validator timed out",
                },
                validator_name=self.meta.name,
                validation_time_ms=elapsed_ms,
            )
        
        except ValidationError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ValidationResult(
                is_valid=False,
                reason=BlockReason.IE_VALIDATOR_EXCEPTION,
                severity=BlockSeverity.CRITICAL,
                details={
                    "validator": self.meta.name,
                    "error_type": e.__class__.__name__,
                    "error": str(e),
                    "message": "Validation error occurred",
                },
                validator_name=self.meta.name,
                validation_time_ms=elapsed_ms,
            )
        
        except Exception as e:
            # Any unexpected exception = BLOCK
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ValidationResult(
                is_valid=False,
                reason=BlockReason.IE_GUARD_INTERNAL_ERROR,
                severity=BlockSeverity.CRITICAL,
                details={
                    "validator": self.meta.name,
                    "error_type": e.__class__.__name__,
                    "error": str(e),
                    "message": "Internal error in validator",
                },
                validator_name=self.meta.name,
                validation_time_ms=elapsed_ms,
            )


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def create_pass_result(
    validator_name: str,
    details: Optional[dict] = None,
) -> ValidationResult:
    """
    Create a passing validation result.
    
    Args:
        validator_name: Name of the validator
        details: Optional details
        
    Returns:
        ValidationResult with is_valid=True
    """
    return ValidationResult(
        is_valid=True,
        reason=None,
        severity=None,
        details=details or {"status": "OK"},
        validator_name=validator_name,
    )


def create_block_result(
    validator_name: str,
    reason: BlockReason,
    severity: Optional[BlockSeverity] = None,
    details: Optional[dict] = None,
) -> ValidationResult:
    """
    Create a blocking validation result.
    
    Args:
        validator_name: Name of the validator
        reason: Block reason code
        severity: Override severity (uses default if None)
        details: Additional details
        
    Returns:
        ValidationResult with is_valid=False
    """
    actual_severity = severity or reason.get_default_severity()
    
    return ValidationResult(
        is_valid=False,
        reason=reason,
        severity=actual_severity,
        details=details or {},
        validator_name=validator_name,
    )


def check_field_present(
    data: dict,
    field: str,
    validator_name: str,
) -> Optional[ValidationResult]:
    """
    Check if a required field is present.
    
    Args:
        data: Data dictionary
        field: Field name to check
        validator_name: Validator name for result
        
    Returns:
        ValidationResult if field missing, None if present
    """
    if field not in data or data[field] is None:
        return create_block_result(
            validator_name=validator_name,
            reason=BlockReason.IE_GUARD_INTERNAL_ERROR,
            severity=BlockSeverity.HIGH,
            details={
                "missing_field": field,
                "message": f"Required field '{field}' is missing",
            },
        )
    return None


def check_timestamp_valid(
    timestamp: datetime,
    max_age_seconds: float,
    validator_name: str,
    now: Optional[datetime] = None,
) -> Optional[ValidationResult]:
    """
    Check if a timestamp is recent enough.
    
    Args:
        timestamp: Timestamp to check
        max_age_seconds: Maximum allowed age
        validator_name: Validator name for result
        now: Current time (defaults to utcnow)
        
    Returns:
        ValidationResult if too old, None if valid
    """
    if now is None:
        now = datetime.utcnow()
    
    age_seconds = (now - timestamp).total_seconds()
    
    if age_seconds > max_age_seconds:
        return create_block_result(
            validator_name=validator_name,
            reason=BlockReason.SI_STALE_MARKET_DATA,
            severity=BlockSeverity.HIGH,
            details={
                "timestamp": timestamp.isoformat(),
                "age_seconds": age_seconds,
                "max_age_seconds": max_age_seconds,
                "message": f"Data is {age_seconds:.1f}s old, max allowed is {max_age_seconds}s",
            },
        )
    
    return None
