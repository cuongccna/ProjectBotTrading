"""
Trade Guard Absolute - Execution Safety Validator.

============================================================
PURPOSE
============================================================
Validates that the execution environment is healthy and
capable of processing orders.

CHECKS:
- ES_EXCHANGE_API_UNSTABLE: Exchange API status abnormal
- ES_EXCHANGE_UNREACHABLE: Cannot reach exchange
- ES_ORDER_FAILURE_THRESHOLD: Too many recent failures
- ES_RATE_LIMIT_EXHAUSTED: Rate limit depleted
- ES_UNCONFIRMED_ORDERS: Too many pending orders

============================================================
"""

from datetime import datetime
from typing import Optional

from ..types import (
    GuardInput,
    ValidationResult,
    BlockReason,
    BlockSeverity,
    BlockCategory,
)
from ..config import ExecutionSafetyConfig
from .base import (
    BaseValidator,
    ValidatorMeta,
    create_pass_result,
    create_block_result,
)


class ExecutionSafetyValidator(BaseValidator):
    """
    Validates execution environment safety.
    
    Ensures the exchange and network are healthy enough
    to reliably execute orders.
    """
    
    def __init__(
        self,
        config: ExecutionSafetyConfig,
    ):
        """
        Initialize validator.
        
        Args:
            config: Execution safety configuration
        """
        self._config = config
    
    @property
    def meta(self) -> ValidatorMeta:
        return ValidatorMeta(
            name="ExecutionSafetyValidator",
            category=BlockCategory.EXECUTION_SAFETY,
            description="Validates exchange and execution environment health",
            is_critical=True,
        )
    
    def _validate(self, guard_input: GuardInput) -> ValidationResult:
        """
        Validate execution safety.
        
        Checks performed:
        1. Exchange reachability
        2. Exchange API status
        3. Exchange latency
        4. Rate limits
        5. Order success rate
        6. Pending orders
        7. Unknown orders
        """
        health = guard_input.execution_health
        
        # Check 1: Exchange Reachability
        result = self._check_exchange_reachable(guard_input)
        if result is not None:
            return result
        
        # Check 2: Exchange API Status
        result = self._check_exchange_status(guard_input)
        if result is not None:
            return result
        
        # Check 3: Exchange Latency
        result = self._check_exchange_latency(guard_input)
        if result is not None:
            return result
        
        # Check 4: Rate Limits
        result = self._check_rate_limits(guard_input)
        if result is not None:
            return result
        
        # Check 5: Order Success Rate
        result = self._check_order_success_rate(guard_input)
        if result is not None:
            return result
        
        # Check 6: Pending Orders
        result = self._check_pending_orders(guard_input)
        if result is not None:
            return result
        
        # Check 7: Unknown Orders
        result = self._check_unknown_orders(guard_input)
        if result is not None:
            return result
        
        # All checks passed
        return create_pass_result(
            validator_name=self.meta.name,
            details={
                "exchange_reachable": health.exchange_reachable,
                "exchange_status": health.exchange_status,
                "latency_ms": health.exchange_latency_ms,
                "order_success_rate_1h": health.order_success_rate_1h,
                "pending_orders": health.pending_order_count,
            },
        )
    
    def _check_exchange_reachable(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check exchange is reachable."""
        if not self._config.require_exchange_reachable:
            return None
        
        health = guard_input.execution_health
        
        if not health.exchange_reachable:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.ES_EXCHANGE_UNREACHABLE,
                severity=BlockSeverity.CRITICAL,
                details={
                    "exchange_reachable": False,
                    "message": "Exchange is not reachable",
                },
            )
        
        return None
    
    def _check_exchange_status(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check exchange API status."""
        health = guard_input.execution_health
        
        if health.exchange_status is None:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.ES_EXCHANGE_API_UNSTABLE,
                severity=BlockSeverity.HIGH,
                details={
                    "exchange_status": None,
                    "message": "Exchange status unknown",
                },
            )
        
        status_upper = health.exchange_status.upper()
        allowed_upper = [s.upper() for s in self._config.allowed_exchange_statuses]
        
        if status_upper not in allowed_upper:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.ES_EXCHANGE_API_UNSTABLE,
                severity=BlockSeverity.HIGH,
                details={
                    "exchange_status": health.exchange_status,
                    "allowed_statuses": self._config.allowed_exchange_statuses,
                    "message": f"Exchange status '{health.exchange_status}' is not healthy",
                },
            )
        
        return None
    
    def _check_exchange_latency(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check exchange latency."""
        health = guard_input.execution_health
        
        if health.exchange_latency_ms is None:
            # Latency unknown - conservative block
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.ES_EXCHANGE_API_UNSTABLE,
                severity=BlockSeverity.MEDIUM,
                details={
                    "exchange_latency_ms": None,
                    "message": "Exchange latency unknown",
                },
            )
        
        if health.exchange_latency_ms > self._config.max_exchange_latency_ms:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.ES_EXCHANGE_API_UNSTABLE,
                severity=BlockSeverity.HIGH,
                details={
                    "exchange_latency_ms": health.exchange_latency_ms,
                    "max_latency_ms": self._config.max_exchange_latency_ms,
                    "message": f"Exchange latency too high: {health.exchange_latency_ms}ms",
                },
            )
        
        return None
    
    def _check_rate_limits(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check rate limit status."""
        health = guard_input.execution_health
        
        # Check remaining
        if health.rate_limit_remaining is not None:
            if health.rate_limit_remaining < self._config.min_rate_limit_remaining:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.ES_RATE_LIMIT_EXHAUSTED,
                    severity=BlockSeverity.HIGH,
                    details={
                        "rate_limit_remaining": health.rate_limit_remaining,
                        "min_required": self._config.min_rate_limit_remaining,
                        "message": f"Rate limit low: {health.rate_limit_remaining} remaining",
                    },
                )
        
        # Check utilization
        if health.rate_limit_utilization is not None:
            if health.rate_limit_utilization > self._config.max_rate_limit_utilization:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.ES_RATE_LIMIT_EXHAUSTED,
                    severity=BlockSeverity.MEDIUM,
                    details={
                        "rate_limit_utilization": health.rate_limit_utilization,
                        "max_utilization": self._config.max_rate_limit_utilization,
                        "message": f"Rate limit utilization: {health.rate_limit_utilization:.1%}",
                    },
                )
        
        return None
    
    def _check_order_success_rate(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check recent order success rate."""
        health = guard_input.execution_health
        
        # Check failure count
        if health.order_failures_1h is not None:
            if health.order_failures_1h > self._config.max_order_failures_1h:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.ES_ORDER_FAILURE_THRESHOLD,
                    severity=BlockSeverity.HIGH,
                    details={
                        "order_failures_1h": health.order_failures_1h,
                        "max_failures": self._config.max_order_failures_1h,
                        "message": f"Too many order failures: {health.order_failures_1h} in last hour",
                    },
                )
        
        # Check success rate
        if health.order_success_rate_1h is not None:
            if health.order_success_rate_1h < self._config.min_order_success_rate_1h:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.ES_ORDER_FAILURE_THRESHOLD,
                    severity=BlockSeverity.HIGH,
                    details={
                        "order_success_rate_1h": health.order_success_rate_1h,
                        "min_rate": self._config.min_order_success_rate_1h,
                        "message": f"Order success rate too low: {health.order_success_rate_1h:.1%}",
                    },
                )
        
        return None
    
    def _check_pending_orders(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check pending order count."""
        health = guard_input.execution_health
        
        # Check pending orders
        if health.pending_order_count is not None:
            if health.pending_order_count > self._config.max_pending_orders:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.ES_UNCONFIRMED_ORDERS,
                    severity=BlockSeverity.MEDIUM,
                    details={
                        "pending_order_count": health.pending_order_count,
                        "max_pending": self._config.max_pending_orders,
                        "message": f"Too many pending orders: {health.pending_order_count}",
                    },
                )
        
        # Check pending cancellations
        if health.pending_cancellation_count is not None:
            if health.pending_cancellation_count > self._config.max_pending_cancellations:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.ES_UNCONFIRMED_ORDERS,
                    severity=BlockSeverity.MEDIUM,
                    details={
                        "pending_cancellation_count": health.pending_cancellation_count,
                        "max_pending": self._config.max_pending_cancellations,
                        "message": f"Pending cancellations: {health.pending_cancellation_count}",
                    },
                )
        
        return None
    
    def _check_unknown_orders(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check for unknown orders on exchange."""
        health = guard_input.execution_health
        
        if health.unknown_order_count is not None:
            if health.unknown_order_count > self._config.max_unknown_open_orders:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.SC_UNKNOWN_OPEN_ORDERS,
                    severity=BlockSeverity.CRITICAL,
                    details={
                        "unknown_order_count": health.unknown_order_count,
                        "max_allowed": self._config.max_unknown_open_orders,
                        "message": f"Unknown orders on exchange: {health.unknown_order_count}",
                    },
                )
        
        return None
