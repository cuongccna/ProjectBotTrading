"""
Trade Guard Absolute - Environment Validator.

============================================================
PURPOSE
============================================================
Validates environmental conditions that affect trading
safety.

These are external factors beyond system control.

CHECKS:
- EE_RISK_LEVEL_CRITICAL: Risk level at critical
- EE_SYSTEM_ESCALATION_ACTIVE: System escalation in progress
- EE_CIRCUIT_BREAKER_TRIGGERED: Exchange circuit breaker hit

============================================================
"""

from datetime import datetime
from typing import Optional, List

from ..types import (
    GuardInput,
    ValidationResult,
    BlockReason,
    BlockSeverity,
    BlockCategory,
)
from ..config import EnvironmentalConfig
from .base import (
    BaseValidator,
    ValidatorMeta,
    create_pass_result,
    create_block_result,
)


class EnvironmentValidator(BaseValidator):
    """
    Validates environmental conditions.
    
    Checks market conditions and system-level alerts
    that should block trading.
    """
    
    def __init__(
        self,
        config: EnvironmentalConfig,
    ):
        """
        Initialize validator.
        
        Args:
            config: Environmental configuration
        """
        self._config = config
    
    @property
    def meta(self) -> ValidatorMeta:
        return ValidatorMeta(
            name="EnvironmentValidator",
            category=BlockCategory.ENVIRONMENTAL,
            description="Validates market conditions and environmental factors",
            is_critical=True,
        )
    
    def _validate(self, guard_input: GuardInput) -> ValidationResult:
        """
        Validate environmental conditions.
        
        Checks performed:
        1. Risk level
        2. Escalation state
        3. Circuit breaker
        4. Volatility regime
        5. Liquidity
        6. Spread
        """
        env = guard_input.environmental_context
        
        # Check 1: Risk Level (CRITICAL)
        result = self._check_risk_level(guard_input)
        if result is not None:
            return result
        
        # Check 2: System Escalation
        result = self._check_escalation(guard_input)
        if result is not None:
            return result
        
        # Check 3: Circuit Breaker
        result = self._check_circuit_breaker(guard_input)
        if result is not None:
            return result
        
        # Check 4: Volatility Regime
        result = self._check_volatility(guard_input)
        if result is not None:
            return result
        
        # Check 5: Liquidity
        result = self._check_liquidity(guard_input)
        if result is not None:
            return result
        
        # Check 6: Spread
        result = self._check_spread(guard_input)
        if result is not None:
            return result
        
        # All checks passed
        return create_pass_result(
            validator_name=self.meta.name,
            details={
                "risk_level": env.current_risk_level,
                "volatility_regime": env.volatility_regime,
                "liquidity_score": env.liquidity_score,
                "circuit_breaker_active": env.circuit_breaker_active,
            },
        )
    
    def _check_risk_level(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check risk level."""
        if not self._config.block_on_critical_risk:
            return None
        
        env = guard_input.environmental_context
        
        # Check named risk levels
        if env.current_risk_level:
            level_upper = env.current_risk_level.upper()
            blocked_levels = [l.upper() for l in self._config.critical_risk_levels]
            
            if level_upper in blocked_levels:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.EE_RISK_LEVEL_CRITICAL,
                    severity=BlockSeverity.EMERGENCY,
                    details={
                        "risk_level": env.current_risk_level,
                        "blocked_levels": self._config.critical_risk_levels,
                        "message": f"Risk level is {env.current_risk_level}",
                    },
                )
        
        # Check numeric risk score
        if env.risk_score is not None:
            if env.risk_score > self._config.max_risk_score:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.EE_RISK_LEVEL_CRITICAL,
                    severity=BlockSeverity.HIGH,
                    details={
                        "risk_score": env.risk_score,
                        "max_score": self._config.max_risk_score,
                        "message": f"Risk score {env.risk_score:.2f} exceeds threshold {self._config.max_risk_score}",
                    },
                )
        
        return None
    
    def _check_escalation(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check system escalation state."""
        if not self._config.block_on_escalation:
            return None
        
        env = guard_input.environmental_context
        
        if env.escalation_level is not None:
            if env.escalation_level >= self._config.min_escalation_level_to_block:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.EE_SYSTEM_ESCALATION_ACTIVE,
                    severity=BlockSeverity.HIGH,
                    details={
                        "escalation_level": env.escalation_level,
                        "min_blocking_level": self._config.min_escalation_level_to_block,
                        "escalation_reason": env.escalation_reason,
                        "message": f"System escalation level {env.escalation_level} active",
                    },
                )
        
        return None
    
    def _check_circuit_breaker(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check circuit breaker status."""
        if not self._config.respect_circuit_breaker:
            return None
        
        env = guard_input.environmental_context
        
        if env.circuit_breaker_active:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.EE_CIRCUIT_BREAKER_TRIGGERED,
                severity=BlockSeverity.CRITICAL,
                details={
                    "circuit_breaker_active": True,
                    "triggered_at": (
                        env.circuit_breaker_triggered_at.isoformat()
                        if env.circuit_breaker_triggered_at else None
                    ),
                    "message": "Circuit breaker has been triggered",
                },
            )
        
        return None
    
    def _check_volatility(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check volatility conditions."""
        env = guard_input.environmental_context
        
        # Check volatility regime
        if env.volatility_regime:
            regime_upper = env.volatility_regime.upper()
            blocked_upper = [r.upper() for r in self._config.volatility_regimes_blocked]
            
            if regime_upper in blocked_upper:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.EE_CIRCUIT_BREAKER_TRIGGERED,
                    severity=BlockSeverity.HIGH,
                    details={
                        "volatility_regime": env.volatility_regime,
                        "blocked_regimes": self._config.volatility_regimes_blocked,
                        "message": f"Volatility regime '{env.volatility_regime}' blocks trading",
                    },
                )
        
        # Check numeric volatility
        if env.current_volatility is not None:
            if env.current_volatility > self._config.max_volatility_for_trading:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.EE_CIRCUIT_BREAKER_TRIGGERED,
                    severity=BlockSeverity.HIGH,
                    details={
                        "current_volatility": env.current_volatility,
                        "max_volatility": self._config.max_volatility_for_trading,
                        "message": f"Volatility {env.current_volatility:.1%} exceeds limit {self._config.max_volatility_for_trading:.1%}",
                    },
                )
        
        return None
    
    def _check_liquidity(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check liquidity conditions."""
        env = guard_input.environmental_context
        
        if env.liquidity_score is not None:
            if env.liquidity_score < self._config.min_liquidity_score:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.EE_CIRCUIT_BREAKER_TRIGGERED,
                    severity=BlockSeverity.MEDIUM,
                    details={
                        "liquidity_score": env.liquidity_score,
                        "min_required": self._config.min_liquidity_score,
                        "message": f"Liquidity score {env.liquidity_score:.2f} below minimum {self._config.min_liquidity_score}",
                    },
                )
        
        return None
    
    def _check_spread(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check bid-ask spread."""
        env = guard_input.environmental_context
        
        if env.current_spread_pct is not None:
            if env.current_spread_pct > self._config.max_spread_pct:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.EE_CIRCUIT_BREAKER_TRIGGERED,
                    severity=BlockSeverity.MEDIUM,
                    details={
                        "spread_pct": env.current_spread_pct,
                        "max_spread": self._config.max_spread_pct,
                        "message": f"Spread {env.current_spread_pct:.2f}% exceeds limit {self._config.max_spread_pct}%",
                    },
                )
        
        return None
