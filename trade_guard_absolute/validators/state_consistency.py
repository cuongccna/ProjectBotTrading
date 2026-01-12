"""
Trade Guard Absolute - State Consistency Validator.

============================================================
PURPOSE
============================================================
Validates that system state matches exchange state.

Detects mismatches that could lead to:
- Duplicate positions
- Unknown exposure
- Incorrect risk calculations

CHECKS:
- SC_POSITION_STATE_MISMATCH: Position counts don't match
- SC_UNKNOWN_OPEN_ORDERS: Orders on exchange not in system
- SC_BALANCE_INCONSISTENCY: Balance values don't match
- SC_MARGIN_STATE_UNDEFINED: Margin mode unknown

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
from ..config import StateConsistencyConfig
from .base import (
    BaseValidator,
    ValidatorMeta,
    create_pass_result,
    create_block_result,
)


class StateConsistencyValidator(BaseValidator):
    """
    Validates state consistency.
    
    Ensures system view matches exchange reality.
    """
    
    def __init__(
        self,
        config: StateConsistencyConfig,
    ):
        """
        Initialize validator.
        
        Args:
            config: State consistency configuration
        """
        self._config = config
    
    @property
    def meta(self) -> ValidatorMeta:
        return ValidatorMeta(
            name="StateConsistencyValidator",
            category=BlockCategory.STATE_CONSISTENCY,
            description="Validates system state matches exchange state",
            is_critical=True,
        )
    
    def _validate(self, guard_input: GuardInput) -> ValidationResult:
        """
        Validate state consistency.
        
        Checks performed:
        1. Position sync age
        2. Position count match
        3. Equity consistency
        4. Balance availability
        5. Margin state
        """
        now = datetime.utcnow()
        account = guard_input.account_state
        
        # Check 1: Position Sync Age
        result = self._check_position_sync_age(guard_input, now)
        if result is not None:
            return result
        
        # Check 2: Position Count Match
        result = self._check_position_match(guard_input)
        if result is not None:
            return result
        
        # Check 3: Equity Consistency
        result = self._check_equity_consistency(guard_input)
        if result is not None:
            return result
        
        # Check 4: Balance Availability
        result = self._check_balance_available(guard_input)
        if result is not None:
            return result
        
        # Check 5: Margin State
        result = self._check_margin_state(guard_input)
        if result is not None:
            return result
        
        # All checks passed
        return create_pass_result(
            validator_name=self.meta.name,
            details={
                "position_sync_age_seconds": (
                    (now - account.last_sync_timestamp).total_seconds()
                    if account.last_sync_timestamp else None
                ),
                "positions_match": account.system_position_count == account.exchange_position_count,
                "equity_match": self._equity_matches(
                    account.system_equity,
                    account.exchange_equity,
                ),
                "margin_mode": account.margin_mode,
            },
        )
    
    def _check_position_sync_age(
        self,
        guard_input: GuardInput,
        now: datetime,
    ) -> Optional[ValidationResult]:
        """Check position sync is recent."""
        if not self._config.require_position_sync:
            return None
        
        account = guard_input.account_state
        
        if account.last_sync_timestamp is None:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SC_POSITION_STATE_MISMATCH,
                severity=BlockSeverity.HIGH,
                details={
                    "last_sync_timestamp": None,
                    "message": "Position state never synced",
                },
            )
        
        sync_age = (now - account.last_sync_timestamp).total_seconds()
        
        if sync_age > self._config.max_position_sync_age_seconds:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SC_POSITION_STATE_MISMATCH,
                severity=BlockSeverity.HIGH,
                details={
                    "sync_age_seconds": sync_age,
                    "max_age_seconds": self._config.max_position_sync_age_seconds,
                    "last_sync": account.last_sync_timestamp.isoformat(),
                    "message": f"Position sync is {sync_age:.1f}s old",
                },
            )
        
        return None
    
    def _check_position_match(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check position counts match."""
        if self._config.allow_position_mismatch:
            return None
        
        account = guard_input.account_state
        
        # Skip if either count is unknown
        if (account.system_position_count is None or 
            account.exchange_position_count is None):
            return None
        
        if account.system_position_count != account.exchange_position_count:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SC_POSITION_STATE_MISMATCH,
                severity=BlockSeverity.CRITICAL,
                details={
                    "system_position_count": account.system_position_count,
                    "exchange_position_count": account.exchange_position_count,
                    "difference": account.exchange_position_count - account.system_position_count,
                    "message": (
                        f"Position count mismatch: system={account.system_position_count}, "
                        f"exchange={account.exchange_position_count}"
                    ),
                },
            )
        
        return None
    
    def _check_equity_consistency(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check equity values match within tolerance."""
        if not self._config.require_equity_match:
            return None
        
        account = guard_input.account_state
        
        # Skip if either value is unknown
        if account.system_equity is None or account.exchange_equity is None:
            return None
        
        if not self._equity_matches(account.system_equity, account.exchange_equity):
            diff_pct = abs(account.system_equity - account.exchange_equity) / max(account.exchange_equity, 1.0) * 100
            
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SC_BALANCE_INCONSISTENCY,
                severity=BlockSeverity.HIGH,
                details={
                    "system_equity": account.system_equity,
                    "exchange_equity": account.exchange_equity,
                    "difference_pct": diff_pct,
                    "tolerance_pct": self._config.equity_mismatch_tolerance_pct,
                    "message": f"Equity mismatch: {diff_pct:.2f}% difference",
                },
            )
        
        return None
    
    def _equity_matches(
        self,
        system_equity: Optional[float],
        exchange_equity: Optional[float],
    ) -> bool:
        """Check if equity values match within tolerance."""
        if system_equity is None or exchange_equity is None:
            return True  # Skip check if unknown
        
        if exchange_equity == 0:
            return system_equity == 0
        
        diff_pct = abs(system_equity - exchange_equity) / exchange_equity * 100
        return diff_pct <= self._config.equity_mismatch_tolerance_pct
    
    def _check_balance_available(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check minimum balance is available."""
        account = guard_input.account_state
        
        if account.available_balance is None:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SC_BALANCE_INCONSISTENCY,
                severity=BlockSeverity.HIGH,
                details={
                    "available_balance": None,
                    "message": "Available balance unknown",
                },
            )
        
        if account.available_balance < self._config.min_available_balance:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SC_BALANCE_INCONSISTENCY,
                severity=BlockSeverity.HIGH,
                details={
                    "available_balance": account.available_balance,
                    "min_required": self._config.min_available_balance,
                    "message": f"Insufficient balance: ${account.available_balance:.2f}",
                },
            )
        
        return None
    
    def _check_margin_state(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check margin state is defined and acceptable."""
        if not self._config.require_margin_state_defined:
            return None
        
        account = guard_input.account_state
        
        # Check margin mode defined
        if account.margin_mode is None:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SC_MARGIN_STATE_UNDEFINED,
                severity=BlockSeverity.MEDIUM,
                details={
                    "margin_mode": None,
                    "message": "Margin mode undefined",
                },
            )
        
        # Check margin mode allowed
        mode_upper = account.margin_mode.upper()
        allowed_upper = [m.upper() for m in self._config.allowed_margin_modes]
        
        if mode_upper not in allowed_upper:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SC_MARGIN_STATE_UNDEFINED,
                severity=BlockSeverity.HIGH,
                details={
                    "margin_mode": account.margin_mode,
                    "allowed_modes": self._config.allowed_margin_modes,
                    "message": f"Invalid margin mode: {account.margin_mode}",
                },
            )
        
        # Check margin ratio
        if account.margin_ratio is not None:
            if account.margin_ratio > self._config.max_margin_ratio:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.SC_BALANCE_INCONSISTENCY,
                    severity=BlockSeverity.HIGH,
                    details={
                        "margin_ratio": account.margin_ratio,
                        "max_ratio": self._config.max_margin_ratio,
                        "message": f"Margin utilization too high: {account.margin_ratio:.1%}",
                    },
                )
        
        return None
