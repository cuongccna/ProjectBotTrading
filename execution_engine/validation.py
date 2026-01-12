"""
Execution Engine - Pre-Execution Validation.

============================================================
PURPOSE
============================================================
Validates order intents before submission.

VALIDATION STEPS:
1. Verify Trade Guard Absolute approval token
2. Verify System Risk Controller is not in HALT
3. Verify account balance and margin availability
4. Verify symbol, order type, and exchange rules

CRITICAL PRINCIPLE:
    "No blind execution. Every order must pass validation."

============================================================
"""

import logging
from datetime import datetime
from typing import Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass

from .types import (
    OrderIntent,
    OrderType,
    AccountState,
    SymbolRules,
    ValidationError,
    HaltStateError,
    ApprovalError,
    ExecutionResultCode,
)
from .config import ValidationConfig


logger = logging.getLogger(__name__)


# ============================================================
# VALIDATION RESULT
# ============================================================

@dataclass
class ValidationResult:
    """Result of pre-execution validation."""
    
    is_valid: bool
    """Whether validation passed."""
    
    error_code: Optional[str] = None
    """Error code if invalid."""
    
    error_message: Optional[str] = None
    """Error message if invalid."""
    
    adjusted_quantity: Optional[Decimal] = None
    """Adjusted quantity (if auto-rounding applied)."""
    
    adjusted_price: Optional[Decimal] = None
    """Adjusted price (if auto-rounding applied)."""
    
    warnings: list = None
    """Non-fatal warnings."""
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


# ============================================================
# VALIDATOR
# ============================================================

class PreExecutionValidator:
    """
    Validates order intents before submission.
    
    All validation failures are deterministic and logged.
    """
    
    def __init__(
        self,
        config: ValidationConfig,
        is_system_halted: callable = None,
    ):
        """
        Initialize validator.
        
        Args:
            config: Validation configuration
            is_system_halted: Callable that returns True if system is halted
        """
        self._config = config
        self._is_system_halted = is_system_halted or (lambda: False)
    
    def validate(
        self,
        intent: OrderIntent,
        account_state: AccountState,
        symbol_rules: SymbolRules,
    ) -> ValidationResult:
        """
        Validate an order intent.
        
        Args:
            intent: Order intent to validate
            account_state: Current account state
            symbol_rules: Symbol trading rules
            
        Returns:
            ValidationResult
        """
        warnings = []
        adjusted_quantity = intent.quantity
        adjusted_price = intent.price
        
        # 1. Check HALT state first (highest priority)
        if self._config.block_on_halt:
            result = self._validate_halt_state()
            if not result.is_valid:
                return result
        
        # 2. Validate approval token
        if self._config.require_valid_approval:
            result = self._validate_approval(intent)
            if not result.is_valid:
                return result
        
        # 3. Validate symbol
        result = self._validate_symbol(intent, symbol_rules)
        if not result.is_valid:
            return result
        
        # 4. Validate and adjust quantity
        if self._config.validate_symbol_rules:
            result = self._validate_quantity(intent, symbol_rules)
            if not result.is_valid:
                if self._config.auto_round_quantity and result.adjusted_quantity:
                    adjusted_quantity = result.adjusted_quantity
                    warnings.append(f"Quantity adjusted from {intent.quantity} to {adjusted_quantity}")
                else:
                    return result
        
        # 5. Validate and adjust price
        if intent.price is not None and self._config.validate_symbol_rules:
            result = self._validate_price(intent, symbol_rules)
            if not result.is_valid:
                if self._config.auto_round_price and result.adjusted_price:
                    adjusted_price = result.adjusted_price
                    warnings.append(f"Price adjusted from {intent.price} to {adjusted_price}")
                else:
                    return result
        
        # 6. Validate notional
        result = self._validate_notional(intent, symbol_rules, adjusted_quantity, adjusted_price)
        if not result.is_valid:
            return result
        
        # 7. Validate balance
        if self._config.validate_balance:
            result = self._validate_balance(intent, account_state, adjusted_quantity, adjusted_price)
            if not result.is_valid:
                return result
        
        # All validations passed
        return ValidationResult(
            is_valid=True,
            adjusted_quantity=adjusted_quantity if adjusted_quantity != intent.quantity else None,
            adjusted_price=adjusted_price if adjusted_price != intent.price else None,
            warnings=warnings,
        )
    
    def _validate_halt_state(self) -> ValidationResult:
        """Check if system is halted."""
        if self._is_system_halted():
            logger.warning("Validation failed: System is in HALT state")
            return ValidationResult(
                is_valid=False,
                error_code="VAL_HALT_STATE",
                error_message="System is in HALT state - execution blocked",
            )
        return ValidationResult(is_valid=True)
    
    def _validate_approval(self, intent: OrderIntent) -> ValidationResult:
        """Validate Trade Guard approval."""
        if not intent.approval_token:
            logger.warning(f"Validation failed: Missing approval token for {intent.intent_id}")
            return ValidationResult(
                is_valid=False,
                error_code="VAL_INVALID_APPROVAL",
                error_message="Missing Trade Guard approval token",
            )
        
        if not intent.is_approval_valid():
            age_seconds = (datetime.utcnow() - intent.approval_timestamp).total_seconds()
            logger.warning(
                f"Validation failed: Expired approval for {intent.intent_id} "
                f"(age={age_seconds:.1f}s)"
            )
            return ValidationResult(
                is_valid=False,
                error_code="VAL_EXPIRED_APPROVAL",
                error_message=f"Trade Guard approval has expired (age={age_seconds:.1f}s)",
            )
        
        return ValidationResult(is_valid=True)
    
    def _validate_symbol(
        self,
        intent: OrderIntent,
        rules: SymbolRules,
    ) -> ValidationResult:
        """Validate symbol is tradeable."""
        if rules.status != "TRADING":
            logger.warning(
                f"Validation failed: Symbol {intent.symbol} status is {rules.status}"
            )
            return ValidationResult(
                is_valid=False,
                error_code="VAL_INVALID_SYMBOL",
                error_message=f"Symbol {intent.symbol} is not trading (status={rules.status})",
            )
        
        return ValidationResult(is_valid=True)
    
    def _validate_quantity(
        self,
        intent: OrderIntent,
        rules: SymbolRules,
    ) -> ValidationResult:
        """Validate and potentially adjust quantity."""
        quantity = intent.quantity
        
        # Check minimum
        if quantity < rules.min_quantity:
            logger.warning(
                f"Validation failed: Quantity {quantity} < min {rules.min_quantity}"
            )
            return ValidationResult(
                is_valid=False,
                error_code="VAL_INVALID_QUANTITY",
                error_message=f"Quantity {quantity} below minimum {rules.min_quantity}",
            )
        
        # Check maximum
        if rules.max_quantity > 0 and quantity > rules.max_quantity:
            logger.warning(
                f"Validation failed: Quantity {quantity} > max {rules.max_quantity}"
            )
            return ValidationResult(
                is_valid=False,
                error_code="VAL_INVALID_QUANTITY",
                error_message=f"Quantity {quantity} exceeds maximum {rules.max_quantity}",
            )
        
        # Check step size
        if rules.quantity_step > 0:
            rounded = rules.round_quantity(quantity)
            if rounded != quantity:
                # Return with adjusted quantity
                return ValidationResult(
                    is_valid=False,
                    error_code="VAL_INVALID_QUANTITY",
                    error_message=f"Quantity {quantity} not on step size {rules.quantity_step}",
                    adjusted_quantity=rounded,
                )
        
        return ValidationResult(is_valid=True)
    
    def _validate_price(
        self,
        intent: OrderIntent,
        rules: SymbolRules,
    ) -> ValidationResult:
        """Validate and potentially adjust price."""
        price = intent.price
        
        if price is None:
            return ValidationResult(is_valid=True)
        
        # Check minimum
        if price < rules.min_price:
            logger.warning(
                f"Validation failed: Price {price} < min {rules.min_price}"
            )
            return ValidationResult(
                is_valid=False,
                error_code="VAL_INVALID_PRICE",
                error_message=f"Price {price} below minimum {rules.min_price}",
            )
        
        # Check maximum
        if rules.max_price > 0 and price > rules.max_price:
            logger.warning(
                f"Validation failed: Price {price} > max {rules.max_price}"
            )
            return ValidationResult(
                is_valid=False,
                error_code="VAL_INVALID_PRICE",
                error_message=f"Price {price} exceeds maximum {rules.max_price}",
            )
        
        # Check tick size
        if rules.price_step > 0:
            rounded = rules.round_price(price)
            if rounded != price:
                return ValidationResult(
                    is_valid=False,
                    error_code="VAL_INVALID_PRICE",
                    error_message=f"Price {price} not on tick size {rules.price_step}",
                    adjusted_price=rounded,
                )
        
        return ValidationResult(is_valid=True)
    
    def _validate_notional(
        self,
        intent: OrderIntent,
        rules: SymbolRules,
        quantity: Decimal,
        price: Optional[Decimal],
    ) -> ValidationResult:
        """Validate minimum notional."""
        if rules.min_notional <= 0:
            return ValidationResult(is_valid=True)
        
        # For market orders, we don't have a price
        # This will be validated by the exchange
        if intent.order_type == OrderType.MARKET and price is None:
            return ValidationResult(is_valid=True)
        
        # Calculate notional
        effective_price = price or Decimal("0")
        if effective_price <= 0:
            return ValidationResult(is_valid=True)
        
        notional = quantity * effective_price
        min_with_buffer = rules.min_notional * (
            1 + self._config.min_notional_buffer_pct / 100
        )
        
        if notional < min_with_buffer:
            logger.warning(
                f"Validation failed: Notional {notional} < min {min_with_buffer}"
            )
            return ValidationResult(
                is_valid=False,
                error_code="VAL_BELOW_MIN_NOTIONAL",
                error_message=f"Order value {notional} below minimum {rules.min_notional}",
            )
        
        return ValidationResult(is_valid=True)
    
    def _validate_balance(
        self,
        intent: OrderIntent,
        account_state: AccountState,
        quantity: Decimal,
        price: Optional[Decimal],
    ) -> ValidationResult:
        """Validate sufficient balance."""
        # Get quote asset balance (usually USDT)
        quote_balance = account_state.get_balance("USDT")
        
        # For futures, check available margin
        available = account_state.available_margin
        if available is None or available <= 0:
            available = quote_balance.free
        
        # Estimate required margin (very rough, actual depends on leverage)
        effective_price = price or Decimal("0")
        if effective_price <= 0:
            # Can't validate without price
            return ValidationResult(is_valid=True)
        
        notional = quantity * effective_price
        
        # Assume some buffer
        required_with_buffer = notional * (self._config.min_balance_buffer_pct / 100)
        
        if available < required_with_buffer:
            logger.warning(
                f"Validation failed: Available margin {available} < required {required_with_buffer}"
            )
            return ValidationResult(
                is_valid=False,
                error_code="VAL_INSUFFICIENT_BALANCE",
                error_message=f"Insufficient margin: {available} available, ~{required_with_buffer} required",
            )
        
        return ValidationResult(is_valid=True)


# ============================================================
# VALIDATION HELPERS
# ============================================================

def validate_order_intent(
    intent: OrderIntent,
    account_state: AccountState,
    symbol_rules: SymbolRules,
    config: ValidationConfig,
    is_system_halted: callable = None,
) -> ValidationResult:
    """
    Convenience function for validating an order intent.
    
    Args:
        intent: Order intent
        account_state: Current account state
        symbol_rules: Symbol rules
        config: Validation configuration
        is_system_halted: Callable to check halt state
        
    Returns:
        ValidationResult
    """
    validator = PreExecutionValidator(config, is_system_halted)
    return validator.validate(intent, account_state, symbol_rules)
