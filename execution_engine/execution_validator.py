"""
Execution Engine - Post-Execution Validator.

============================================================
PURPOSE
============================================================
Validates execution results against expectations.

VALIDATION CHECKS:
1. Fill price within expected range
2. Slippage within tolerance
3. Complete fill vs partial
4. Execution timing
5. Commission reasonableness

ANOMALY DETECTION:
- Unusual slippage
- Price deviation
- Execution delays
- Unexpected partial fills

============================================================
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal
from dataclasses import dataclass, field
from enum import Enum

from .types import (
    OrderRecord,
    OrderType,
    OrderSide,
    ExecutionResult,
    ExecutionResultCode,
)
from .config import ValidationConfig


logger = logging.getLogger(__name__)


# ============================================================
# VALIDATION TYPES
# ============================================================

class ValidationCheckType(Enum):
    """Types of validation checks."""
    
    FILL_PRICE = "FILL_PRICE"
    """Fill price check."""
    
    SLIPPAGE = "SLIPPAGE"
    """Slippage check."""
    
    QUANTITY = "QUANTITY"
    """Fill quantity check."""
    
    TIMING = "TIMING"
    """Execution timing check."""
    
    COMMISSION = "COMMISSION"
    """Commission check."""


@dataclass
class ValidationCheck:
    """Result of a single validation check."""
    
    check_type: ValidationCheckType
    """Type of check."""
    
    passed: bool
    """Whether check passed."""
    
    expected_value: Optional[str] = None
    """Expected value (as string for flexibility)."""
    
    actual_value: Optional[str] = None
    """Actual value."""
    
    deviation: Optional[Decimal] = None
    """Deviation from expected (percentage)."""
    
    message: str = ""
    """Human-readable message."""
    
    severity: str = "INFO"
    """Severity: INFO, WARNING, ERROR, CRITICAL"""


@dataclass
class PostExecutionValidationResult:
    """Result of post-execution validation."""
    
    order_id: str
    """Order ID validated."""
    
    is_valid: bool
    """Whether execution is valid overall."""
    
    checks: List[ValidationCheck] = field(default_factory=list)
    """Individual check results."""
    
    anomalies: List[str] = field(default_factory=list)
    """Detected anomalies."""
    
    warnings: List[str] = field(default_factory=list)
    """Non-critical warnings."""
    
    validated_at: datetime = field(default_factory=datetime.utcnow)
    """When validation was performed."""
    
    @property
    def failed_checks(self) -> List[ValidationCheck]:
        """Get failed checks."""
        return [c for c in self.checks if not c.passed]
    
    @property
    def has_critical(self) -> bool:
        """Check if there are critical issues."""
        return any(c.severity == "CRITICAL" for c in self.checks if not c.passed)


# ============================================================
# POST-EXECUTION VALIDATOR
# ============================================================

@dataclass
class PostExecutionValidatorConfig:
    """Configuration for post-execution validation."""
    
    # Slippage
    max_slippage_pct: Decimal = Decimal("0.5")
    """Maximum allowed slippage percentage."""
    
    critical_slippage_pct: Decimal = Decimal("2.0")
    """Slippage that triggers critical alert."""
    
    # Price
    max_price_deviation_pct: Decimal = Decimal("1.0")
    """Maximum price deviation from expected."""
    
    # Timing
    max_execution_time_seconds: float = 30.0
    """Maximum expected execution time."""
    
    # Quantity
    allow_partial_fills: bool = True
    """Whether to allow partial fills."""
    
    min_fill_ratio: Decimal = Decimal("0.5")
    """Minimum fill ratio for partial fills."""
    
    # Commission
    max_commission_pct: Decimal = Decimal("0.1")
    """Maximum commission as percentage of notional."""


class PostExecutionValidator:
    """
    Validates executions after completion.
    
    Checks for:
    - Abnormal slippage
    - Price deviations
    - Execution delays
    - Unexpected partial fills
    """
    
    def __init__(
        self,
        config: PostExecutionValidatorConfig = None,
    ):
        """
        Initialize validator.
        
        Args:
            config: Validation configuration
        """
        self._config = config or PostExecutionValidatorConfig()
    
    def validate(
        self,
        order: OrderRecord,
        result: ExecutionResult,
        expected_price: Optional[Decimal] = None,
    ) -> PostExecutionValidationResult:
        """
        Validate an execution result.
        
        Args:
            order: The order record
            result: Execution result
            expected_price: Expected fill price (optional)
            
        Returns:
            PostExecutionValidationResult
        """
        checks: List[ValidationCheck] = []
        anomalies: List[str] = []
        warnings: List[str] = []
        
        # 1. Validate fill price / slippage
        if expected_price and result.average_fill_price:
            slippage_check = self._validate_slippage(
                order, result, expected_price
            )
            checks.append(slippage_check)
            
            if not slippage_check.passed:
                if slippage_check.severity == "CRITICAL":
                    anomalies.append(f"Critical slippage: {slippage_check.message}")
                else:
                    warnings.append(slippage_check.message)
        
        # 2. Validate quantity
        quantity_check = self._validate_quantity(order, result)
        checks.append(quantity_check)
        
        if not quantity_check.passed:
            warnings.append(quantity_check.message)
        
        # 3. Validate timing
        if order.submitted_at and result.completed_at:
            timing_check = self._validate_timing(order, result)
            checks.append(timing_check)
            
            if not timing_check.passed:
                warnings.append(timing_check.message)
        
        # 4. Validate commission
        if result.commission > 0 and result.average_fill_price:
            commission_check = self._validate_commission(order, result)
            checks.append(commission_check)
            
            if not commission_check.passed:
                anomalies.append(f"Excessive commission: {commission_check.message}")
        
        # Determine overall validity
        is_valid = not any(
            (not c.passed and c.severity in {"ERROR", "CRITICAL"})
            for c in checks
        )
        
        return PostExecutionValidationResult(
            order_id=order.order_id,
            is_valid=is_valid,
            checks=checks,
            anomalies=anomalies,
            warnings=warnings,
        )
    
    def _validate_slippage(
        self,
        order: OrderRecord,
        result: ExecutionResult,
        expected_price: Decimal,
    ) -> ValidationCheck:
        """Validate slippage is within tolerance."""
        fill_price = result.average_fill_price
        
        if not fill_price or expected_price == 0:
            return ValidationCheck(
                check_type=ValidationCheckType.SLIPPAGE,
                passed=True,
                message="Slippage check skipped (no price data)",
            )
        
        # Calculate slippage
        price_diff = fill_price - expected_price
        slippage_pct = abs(price_diff / expected_price) * 100
        
        # Determine if slippage is in favorable direction
        if order.side == OrderSide.BUY:
            favorable = fill_price < expected_price
        else:
            favorable = fill_price > expected_price
        
        # Check against thresholds
        if slippage_pct >= self._config.critical_slippage_pct:
            return ValidationCheck(
                check_type=ValidationCheckType.SLIPPAGE,
                passed=False,
                expected_value=str(expected_price),
                actual_value=str(fill_price),
                deviation=slippage_pct,
                message=f"Critical slippage: {slippage_pct:.2f}%",
                severity="CRITICAL",
            )
        elif slippage_pct > self._config.max_slippage_pct and not favorable:
            return ValidationCheck(
                check_type=ValidationCheckType.SLIPPAGE,
                passed=False,
                expected_value=str(expected_price),
                actual_value=str(fill_price),
                deviation=slippage_pct,
                message=f"Unfavorable slippage: {slippage_pct:.2f}%",
                severity="WARNING",
            )
        else:
            return ValidationCheck(
                check_type=ValidationCheckType.SLIPPAGE,
                passed=True,
                expected_value=str(expected_price),
                actual_value=str(fill_price),
                deviation=slippage_pct,
                message=f"Slippage acceptable: {slippage_pct:.2f}%",
            )
    
    def _validate_quantity(
        self,
        order: OrderRecord,
        result: ExecutionResult,
    ) -> ValidationCheck:
        """Validate fill quantity."""
        requested = result.requested_quantity
        filled = result.filled_quantity
        
        if requested == 0:
            return ValidationCheck(
                check_type=ValidationCheckType.QUANTITY,
                passed=False,
                message="Zero quantity requested",
                severity="ERROR",
            )
        
        fill_ratio = filled / requested
        
        if fill_ratio >= Decimal("1"):
            return ValidationCheck(
                check_type=ValidationCheckType.QUANTITY,
                passed=True,
                expected_value=str(requested),
                actual_value=str(filled),
                deviation=Decimal("0"),
                message="Full fill",
            )
        elif fill_ratio == 0:
            return ValidationCheck(
                check_type=ValidationCheckType.QUANTITY,
                passed=False,
                expected_value=str(requested),
                actual_value=str(filled),
                deviation=Decimal("100"),
                message="No fill",
                severity="ERROR",
            )
        elif self._config.allow_partial_fills:
            if fill_ratio >= self._config.min_fill_ratio:
                return ValidationCheck(
                    check_type=ValidationCheckType.QUANTITY,
                    passed=True,
                    expected_value=str(requested),
                    actual_value=str(filled),
                    deviation=(1 - fill_ratio) * 100,
                    message=f"Partial fill: {fill_ratio * 100:.1f}%",
                    severity="INFO",
                )
            else:
                return ValidationCheck(
                    check_type=ValidationCheckType.QUANTITY,
                    passed=False,
                    expected_value=str(requested),
                    actual_value=str(filled),
                    deviation=(1 - fill_ratio) * 100,
                    message=f"Low fill ratio: {fill_ratio * 100:.1f}%",
                    severity="WARNING",
                )
        else:
            return ValidationCheck(
                check_type=ValidationCheckType.QUANTITY,
                passed=False,
                expected_value=str(requested),
                actual_value=str(filled),
                deviation=(1 - fill_ratio) * 100,
                message=f"Partial fill not allowed: {fill_ratio * 100:.1f}%",
                severity="ERROR",
            )
    
    def _validate_timing(
        self,
        order: OrderRecord,
        result: ExecutionResult,
    ) -> ValidationCheck:
        """Validate execution timing."""
        if not order.submitted_at or not result.completed_at:
            return ValidationCheck(
                check_type=ValidationCheckType.TIMING,
                passed=True,
                message="Timing check skipped (missing timestamps)",
            )
        
        duration = (result.completed_at - order.submitted_at).total_seconds()
        max_time = self._config.max_execution_time_seconds
        
        if duration <= max_time:
            return ValidationCheck(
                check_type=ValidationCheckType.TIMING,
                passed=True,
                expected_value=f"<{max_time}s",
                actual_value=f"{duration:.1f}s",
                message=f"Execution time: {duration:.1f}s",
            )
        else:
            return ValidationCheck(
                check_type=ValidationCheckType.TIMING,
                passed=False,
                expected_value=f"<{max_time}s",
                actual_value=f"{duration:.1f}s",
                deviation=Decimal(str((duration - max_time) / max_time * 100)),
                message=f"Slow execution: {duration:.1f}s (max: {max_time}s)",
                severity="WARNING",
            )
    
    def _validate_commission(
        self,
        order: OrderRecord,
        result: ExecutionResult,
    ) -> ValidationCheck:
        """Validate commission is reasonable."""
        if not result.average_fill_price or result.filled_quantity == 0:
            return ValidationCheck(
                check_type=ValidationCheckType.COMMISSION,
                passed=True,
                message="Commission check skipped",
            )
        
        notional = result.average_fill_price * result.filled_quantity
        commission_pct = (result.commission / notional) * 100
        max_pct = self._config.max_commission_pct
        
        if commission_pct <= max_pct:
            return ValidationCheck(
                check_type=ValidationCheckType.COMMISSION,
                passed=True,
                expected_value=f"<{max_pct}%",
                actual_value=f"{commission_pct:.4f}%",
                message=f"Commission: {commission_pct:.4f}%",
            )
        else:
            return ValidationCheck(
                check_type=ValidationCheckType.COMMISSION,
                passed=False,
                expected_value=f"<{max_pct}%",
                actual_value=f"{commission_pct:.4f}%",
                deviation=Decimal(str(commission_pct - float(max_pct))),
                message=f"High commission: {commission_pct:.4f}% (max: {max_pct}%)",
                severity="WARNING",
            )
