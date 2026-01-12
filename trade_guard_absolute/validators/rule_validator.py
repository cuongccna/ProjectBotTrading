"""
Trade Guard Absolute - Rule Validator.

============================================================
PURPOSE
============================================================
Validates that trading rules and operational constraints
are satisfied.

These are policy-based rules, not technical safety checks.

CHECKS:
- RV_OUTSIDE_TRADING_HOURS: Trade outside allowed hours
- RV_COOLDOWN_ACTIVE: Cooldown period active
- RV_SYSTEM_HALT_STATE: System is halted
- RV_MANUAL_INTERVENTION_LOCK: Manual lock active

============================================================
"""

from datetime import datetime
from typing import Optional, List, Dict

from ..types import (
    GuardInput,
    ValidationResult,
    BlockReason,
    BlockSeverity,
    BlockCategory,
)
from ..config import RuleConfig
from .base import (
    BaseValidator,
    ValidatorMeta,
    create_pass_result,
    create_block_result,
)


class RuleValidator(BaseValidator):
    """
    Validates trading rules.
    
    Enforces operational policies and restrictions.
    """
    
    def __init__(
        self,
        config: RuleConfig,
    ):
        """
        Initialize validator.
        
        Args:
            config: Rule configuration
        """
        self._config = config
    
    @property
    def meta(self) -> ValidatorMeta:
        return ValidatorMeta(
            name="RuleValidator",
            category=BlockCategory.RULE_VIOLATION,
            description="Validates trading rules and operational constraints",
            is_critical=True,
        )
    
    def _validate(self, guard_input: GuardInput) -> ValidationResult:
        """
        Validate trading rules.
        
        Checks performed:
        1. System halt state
        2. Manual intervention lock
        3. Trading hours
        4. Cooldown period
        5. Symbol tradeable
        6. Direction allowed
        7. Maintenance window
        """
        now = datetime.utcnow()
        halt = guard_input.halt_state
        intent = guard_input.trade_intent
        
        # Check 1: System Halt (HIGHEST PRIORITY)
        result = self._check_system_halt(guard_input)
        if result is not None:
            return result
        
        # Check 2: Manual Lock
        result = self._check_manual_lock(guard_input)
        if result is not None:
            return result
        
        # Check 3: Maintenance Window
        result = self._check_maintenance(guard_input)
        if result is not None:
            return result
        
        # Check 4: Trading Hours
        result = self._check_trading_hours(guard_input, now)
        if result is not None:
            return result
        
        # Check 5: Cooldown
        result = self._check_cooldown(guard_input)
        if result is not None:
            return result
        
        # Check 6: Symbol Tradeable
        result = self._check_symbol_tradeable(guard_input)
        if result is not None:
            return result
        
        # Check 7: Direction Allowed
        result = self._check_direction_allowed(guard_input)
        if result is not None:
            return result
        
        # All checks passed
        return create_pass_result(
            validator_name=self.meta.name,
            details={
                "system_halted": halt.is_halted,
                "manual_lock_active": halt.manual_intervention_active,
                "symbol": intent.symbol,
                "direction": intent.direction,
            },
        )
    
    def _check_system_halt(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check system halt state."""
        if not self._config.respect_system_halt:
            return None
        
        halt = guard_input.halt_state
        
        if halt.is_halted:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.RV_SYSTEM_HALT_STATE,
                severity=BlockSeverity.EMERGENCY,
                details={
                    "is_halted": True,
                    "halt_reason": halt.halt_reason,
                    "halt_timestamp": (
                        halt.halt_timestamp.isoformat() 
                        if halt.halt_timestamp else None
                    ),
                    "message": f"System is halted: {halt.halt_reason}",
                },
            )
        
        return None
    
    def _check_manual_lock(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check manual intervention lock."""
        if not self._config.respect_manual_lock:
            return None
        
        halt = guard_input.halt_state
        
        if halt.manual_intervention_active:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.RV_MANUAL_INTERVENTION_LOCK,
                severity=BlockSeverity.HIGH,
                details={
                    "manual_intervention_active": True,
                    "lock_reason": halt.intervention_reason,
                    "lock_timestamp": (
                        halt.intervention_timestamp.isoformat()
                        if halt.intervention_timestamp else None
                    ),
                    "message": f"Manual lock active: {halt.intervention_reason}",
                },
            )
        
        return None
    
    def _check_maintenance(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check maintenance window."""
        if not self._config.block_during_maintenance:
            return None
        
        halt = guard_input.halt_state
        
        if halt.maintenance_active:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.RV_SYSTEM_HALT_STATE,
                severity=BlockSeverity.MEDIUM,
                details={
                    "maintenance_active": True,
                    "maintenance_end": (
                        halt.maintenance_end.isoformat()
                        if halt.maintenance_end else None
                    ),
                    "message": "Maintenance window active",
                },
            )
        
        return None
    
    def _check_trading_hours(
        self,
        guard_input: GuardInput,
        now: datetime,
    ) -> Optional[ValidationResult]:
        """Check trading hours."""
        if not self._config.enforce_trading_hours:
            return None
        
        # If no hours configured, allow all
        if not self._config.allowed_trading_hours_utc:
            return None
        
        current_hour = now.hour
        
        in_allowed_window = False
        for window in self._config.allowed_trading_hours_utc:
            start_hour = window.get("start_hour", 0)
            end_hour = window.get("end_hour", 24)
            
            if start_hour <= current_hour < end_hour:
                in_allowed_window = True
                break
        
        if not in_allowed_window:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.RV_OUTSIDE_TRADING_HOURS,
                severity=BlockSeverity.LOW,
                details={
                    "current_hour_utc": current_hour,
                    "allowed_windows": self._config.allowed_trading_hours_utc,
                    "message": f"Outside trading hours (current: {current_hour:02d}:00 UTC)",
                },
            )
        
        return None
    
    def _check_cooldown(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check cooldown period."""
        if not self._config.respect_cooldown:
            return None
        
        halt = guard_input.halt_state
        
        if halt.cooldown_active:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.RV_COOLDOWN_ACTIVE,
                severity=BlockSeverity.LOW,
                details={
                    "cooldown_active": True,
                    "cooldown_end": (
                        halt.cooldown_end.isoformat()
                        if halt.cooldown_end else None
                    ),
                    "cooldown_reason": halt.cooldown_reason,
                    "message": f"Cooldown active: {halt.cooldown_reason}",
                },
            )
        
        return None
    
    def _check_symbol_tradeable(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check if symbol is tradeable."""
        if not self._config.check_symbol_tradeable:
            return None
        
        intent = guard_input.trade_intent
        symbol = intent.symbol
        
        # Check restricted list
        if symbol in self._config.restricted_symbols:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.RV_SYSTEM_HALT_STATE,
                severity=BlockSeverity.MEDIUM,
                details={
                    "symbol": symbol,
                    "reason": "restricted",
                    "message": f"Symbol {symbol} is restricted from trading",
                },
            )
        
        return None
    
    def _check_direction_allowed(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check if trade direction is allowed."""
        intent = guard_input.trade_intent
        direction = intent.direction.upper() if intent.direction else ""
        
        if direction == "LONG" and not self._config.allow_long:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.RV_SYSTEM_HALT_STATE,
                severity=BlockSeverity.MEDIUM,
                details={
                    "direction": direction,
                    "allow_long": False,
                    "message": "LONG trades are currently disabled",
                },
            )
        
        if direction == "SHORT" and not self._config.allow_short:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.RV_SYSTEM_HALT_STATE,
                severity=BlockSeverity.MEDIUM,
                details={
                    "direction": direction,
                    "allow_short": False,
                    "message": "SHORT trades are currently disabled",
                },
            )
        
        return None
