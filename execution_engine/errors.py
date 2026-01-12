"""
Execution Engine - Error Taxonomy.

============================================================
PURPOSE
============================================================
Comprehensive error classification for execution failures.

ERROR CATEGORIES:
1. Validation Errors - Pre-execution checks failed
2. Submission Errors - Order submission failed
3. Exchange Errors - Exchange rejected/failed
4. Network Errors - Communication failures
5. Internal Errors - System errors
6. Blocked Errors - Blocked by safety systems

RETRYABLE vs NON-RETRYABLE:
- Retryable: Transient errors that may succeed on retry
- Non-retryable: Permanent errors that will fail again

============================================================
"""

from enum import Enum
from typing import Optional, Dict, Any, Set
from dataclasses import dataclass


# ============================================================
# ERROR CATEGORIES
# ============================================================

class ErrorCategory(Enum):
    """Error category classification."""
    
    VALIDATION = "VALIDATION"
    """Pre-execution validation failed."""
    
    SUBMISSION = "SUBMISSION"
    """Order submission failed."""
    
    EXCHANGE = "EXCHANGE"
    """Exchange rejected or failed."""
    
    NETWORK = "NETWORK"
    """Network/communication error."""
    
    TIMEOUT = "TIMEOUT"
    """Request timed out."""
    
    RATE_LIMIT = "RATE_LIMIT"
    """Rate limit exceeded."""
    
    AUTHENTICATION = "AUTHENTICATION"
    """Authentication failed."""
    
    INTERNAL = "INTERNAL"
    """Internal system error."""
    
    BLOCKED = "BLOCKED"
    """Blocked by safety systems."""
    
    RECONCILIATION = "RECONCILIATION"
    """State reconciliation error."""


class ErrorSeverity(Enum):
    """Error severity levels."""
    
    WARNING = "WARNING"
    """Non-critical, informational."""
    
    ERROR = "ERROR"
    """Standard error, needs attention."""
    
    CRITICAL = "CRITICAL"
    """Critical error, may need halt."""
    
    FATAL = "FATAL"
    """Fatal error, requires immediate action."""


# ============================================================
# ERROR CODE REGISTRY
# ============================================================

@dataclass
class ErrorCodeInfo:
    """Information about an error code."""
    
    code: str
    """Error code."""
    
    category: ErrorCategory
    """Error category."""
    
    severity: ErrorSeverity
    """Error severity."""
    
    is_retryable: bool
    """Whether this error is retryable."""
    
    description: str
    """Human-readable description."""
    
    recommended_action: str
    """Recommended action to take."""
    
    escalate_to_controller: bool = False
    """Whether to escalate to System Risk Controller."""


# Error code registry
ERROR_CODES: Dict[str, ErrorCodeInfo] = {
    # ========== VALIDATION ERRORS ==========
    "VAL_INVALID_APPROVAL": ErrorCodeInfo(
        code="VAL_INVALID_APPROVAL",
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Trade Guard approval is invalid or missing",
        recommended_action="Obtain new approval from Trade Guard",
    ),
    "VAL_EXPIRED_APPROVAL": ErrorCodeInfo(
        code="VAL_EXPIRED_APPROVAL",
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Trade Guard approval has expired",
        recommended_action="Obtain new approval from Trade Guard",
    ),
    "VAL_HALT_STATE": ErrorCodeInfo(
        code="VAL_HALT_STATE",
        category=ErrorCategory.BLOCKED,
        severity=ErrorSeverity.CRITICAL,
        is_retryable=False,
        description="System is in HALT state",
        recommended_action="Wait for system resume",
    ),
    "VAL_INSUFFICIENT_BALANCE": ErrorCodeInfo(
        code="VAL_INSUFFICIENT_BALANCE",
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Insufficient balance for order",
        recommended_action="Reduce order size or deposit funds",
    ),
    "VAL_INVALID_SYMBOL": ErrorCodeInfo(
        code="VAL_INVALID_SYMBOL",
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Symbol is invalid or not tradeable",
        recommended_action="Verify symbol configuration",
    ),
    "VAL_INVALID_QUANTITY": ErrorCodeInfo(
        code="VAL_INVALID_QUANTITY",
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Order quantity is invalid",
        recommended_action="Adjust quantity to valid range",
    ),
    "VAL_INVALID_PRICE": ErrorCodeInfo(
        code="VAL_INVALID_PRICE",
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Order price is invalid",
        recommended_action="Adjust price to valid range",
    ),
    "VAL_BELOW_MIN_NOTIONAL": ErrorCodeInfo(
        code="VAL_BELOW_MIN_NOTIONAL",
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Order value below minimum notional",
        recommended_action="Increase order size",
    ),
    
    # ========== SUBMISSION ERRORS ==========
    "SUB_DUPLICATE_ORDER": ErrorCodeInfo(
        code="SUB_DUPLICATE_ORDER",
        category=ErrorCategory.SUBMISSION,
        severity=ErrorSeverity.WARNING,
        is_retryable=False,
        description="Duplicate order detected",
        recommended_action="Check existing orders",
    ),
    "SUB_ORDER_REJECTED": ErrorCodeInfo(
        code="SUB_ORDER_REJECTED",
        category=ErrorCategory.SUBMISSION,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Order rejected during submission",
        recommended_action="Review rejection reason",
    ),
    
    # ========== EXCHANGE ERRORS ==========
    "EXC_INSUFFICIENT_MARGIN": ErrorCodeInfo(
        code="EXC_INSUFFICIENT_MARGIN",
        category=ErrorCategory.EXCHANGE,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Insufficient margin on exchange",
        recommended_action="Reduce position size or add margin",
    ),
    "EXC_POSITION_LIMIT": ErrorCodeInfo(
        code="EXC_POSITION_LIMIT",
        category=ErrorCategory.EXCHANGE,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Position limit exceeded",
        recommended_action="Reduce position size",
    ),
    "EXC_MARKET_CLOSED": ErrorCodeInfo(
        code="EXC_MARKET_CLOSED",
        category=ErrorCategory.EXCHANGE,
        severity=ErrorSeverity.WARNING,
        is_retryable=False,
        description="Market is closed or in maintenance",
        recommended_action="Wait for market to open",
    ),
    "EXC_SYMBOL_NOT_TRADING": ErrorCodeInfo(
        code="EXC_SYMBOL_NOT_TRADING",
        category=ErrorCategory.EXCHANGE,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Symbol is not in trading status",
        recommended_action="Check symbol status",
    ),
    "EXC_ORDER_NOT_FOUND": ErrorCodeInfo(
        code="EXC_ORDER_NOT_FOUND",
        category=ErrorCategory.EXCHANGE,
        severity=ErrorSeverity.WARNING,
        is_retryable=False,
        description="Order not found on exchange",
        recommended_action="Reconcile order state",
    ),
    "EXC_UNKNOWN_ERROR": ErrorCodeInfo(
        code="EXC_UNKNOWN_ERROR",
        category=ErrorCategory.EXCHANGE,
        severity=ErrorSeverity.ERROR,
        is_retryable=True,
        description="Unknown exchange error",
        recommended_action="Retry or investigate",
    ),
    
    # ========== NETWORK ERRORS ==========
    "NET_CONNECTION_FAILED": ErrorCodeInfo(
        code="NET_CONNECTION_FAILED",
        category=ErrorCategory.NETWORK,
        severity=ErrorSeverity.ERROR,
        is_retryable=True,
        description="Failed to connect to exchange",
        recommended_action="Check network and retry",
    ),
    "NET_CONNECTION_RESET": ErrorCodeInfo(
        code="NET_CONNECTION_RESET",
        category=ErrorCategory.NETWORK,
        severity=ErrorSeverity.WARNING,
        is_retryable=True,
        description="Connection was reset",
        recommended_action="Retry connection",
    ),
    "NET_DNS_FAILURE": ErrorCodeInfo(
        code="NET_DNS_FAILURE",
        category=ErrorCategory.NETWORK,
        severity=ErrorSeverity.ERROR,
        is_retryable=True,
        description="DNS resolution failed",
        recommended_action="Check DNS and network",
    ),
    
    # ========== TIMEOUT ERRORS ==========
    "TMO_CONNECTION": ErrorCodeInfo(
        code="TMO_CONNECTION",
        category=ErrorCategory.TIMEOUT,
        severity=ErrorSeverity.WARNING,
        is_retryable=True,
        description="Connection timeout",
        recommended_action="Retry with backoff",
    ),
    "TMO_READ": ErrorCodeInfo(
        code="TMO_READ",
        category=ErrorCategory.TIMEOUT,
        severity=ErrorSeverity.WARNING,
        is_retryable=True,
        description="Read timeout",
        recommended_action="Retry with backoff",
    ),
    "TMO_ORDER_CONFIRMATION": ErrorCodeInfo(
        code="TMO_ORDER_CONFIRMATION",
        category=ErrorCategory.TIMEOUT,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Order confirmation timeout - state unknown",
        recommended_action="Query order status before retry",
        escalate_to_controller=True,
    ),
    
    # ========== RATE LIMIT ERRORS ==========
    "RTE_ORDER_LIMIT": ErrorCodeInfo(
        code="RTE_ORDER_LIMIT",
        category=ErrorCategory.RATE_LIMIT,
        severity=ErrorSeverity.WARNING,
        is_retryable=True,
        description="Order rate limit exceeded",
        recommended_action="Wait and retry",
    ),
    "RTE_API_WEIGHT": ErrorCodeInfo(
        code="RTE_API_WEIGHT",
        category=ErrorCategory.RATE_LIMIT,
        severity=ErrorSeverity.WARNING,
        is_retryable=True,
        description="API weight limit exceeded",
        recommended_action="Wait for limit reset",
    ),
    "RTE_IP_BANNED": ErrorCodeInfo(
        code="RTE_IP_BANNED",
        category=ErrorCategory.RATE_LIMIT,
        severity=ErrorSeverity.CRITICAL,
        is_retryable=False,
        description="IP has been banned",
        recommended_action="Investigate and contact support",
        escalate_to_controller=True,
    ),
    
    # ========== AUTHENTICATION ERRORS ==========
    "AUT_INVALID_KEY": ErrorCodeInfo(
        code="AUT_INVALID_KEY",
        category=ErrorCategory.AUTHENTICATION,
        severity=ErrorSeverity.CRITICAL,
        is_retryable=False,
        description="API key is invalid",
        recommended_action="Check API credentials",
        escalate_to_controller=True,
    ),
    "AUT_EXPIRED_KEY": ErrorCodeInfo(
        code="AUT_EXPIRED_KEY",
        category=ErrorCategory.AUTHENTICATION,
        severity=ErrorSeverity.CRITICAL,
        is_retryable=False,
        description="API key has expired",
        recommended_action="Renew API credentials",
        escalate_to_controller=True,
    ),
    "AUT_SIGNATURE_FAILED": ErrorCodeInfo(
        code="AUT_SIGNATURE_FAILED",
        category=ErrorCategory.AUTHENTICATION,
        severity=ErrorSeverity.ERROR,
        is_retryable=True,
        description="Signature verification failed",
        recommended_action="Check timestamp sync",
    ),
    "AUT_PERMISSION_DENIED": ErrorCodeInfo(
        code="AUT_PERMISSION_DENIED",
        category=ErrorCategory.AUTHENTICATION,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Permission denied for operation",
        recommended_action="Check API permissions",
    ),
    
    # ========== INTERNAL ERRORS ==========
    "INT_STATE_CORRUPTION": ErrorCodeInfo(
        code="INT_STATE_CORRUPTION",
        category=ErrorCategory.INTERNAL,
        severity=ErrorSeverity.FATAL,
        is_retryable=False,
        description="Internal state corruption detected",
        recommended_action="Immediate halt and investigation",
        escalate_to_controller=True,
    ),
    "INT_UNEXPECTED_ERROR": ErrorCodeInfo(
        code="INT_UNEXPECTED_ERROR",
        category=ErrorCategory.INTERNAL,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Unexpected internal error",
        recommended_action="Investigate error logs",
    ),
    "INT_SERIALIZATION_ERROR": ErrorCodeInfo(
        code="INT_SERIALIZATION_ERROR",
        category=ErrorCategory.INTERNAL,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Failed to serialize/deserialize data",
        recommended_action="Check data formats",
    ),
    
    # ========== RECONCILIATION ERRORS ==========
    "REC_STATE_MISMATCH": ErrorCodeInfo(
        code="REC_STATE_MISMATCH",
        category=ErrorCategory.RECONCILIATION,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Local state does not match exchange",
        recommended_action="Sync state with exchange",
    ),
    "REC_QUANTITY_MISMATCH": ErrorCodeInfo(
        code="REC_QUANTITY_MISMATCH",
        category=ErrorCategory.RECONCILIATION,
        severity=ErrorSeverity.CRITICAL,
        is_retryable=False,
        description="Position quantity mismatch detected",
        recommended_action="Immediate reconciliation required",
        escalate_to_controller=True,
    ),
    "REC_ORPHAN_ORDER": ErrorCodeInfo(
        code="REC_ORPHAN_ORDER",
        category=ErrorCategory.RECONCILIATION,
        severity=ErrorSeverity.WARNING,
        is_retryable=False,
        description="Orphan order detected on exchange",
        recommended_action="Review and cancel if needed",
    ),
    "REC_MISSING_ORDER": ErrorCodeInfo(
        code="REC_MISSING_ORDER",
        category=ErrorCategory.RECONCILIATION,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description="Expected order not found on exchange",
        recommended_action="Investigate order status",
    ),
}


# ============================================================
# EXCHANGE ERROR CODE MAPPING
# ============================================================

# Binance error code to internal error code mapping
BINANCE_ERROR_MAPPING: Dict[int, str] = {
    # Order errors
    -1013: "VAL_INVALID_QUANTITY",  # Invalid quantity
    -1021: "AUT_SIGNATURE_FAILED",  # Timestamp outside recvWindow
    -1022: "AUT_SIGNATURE_FAILED",  # Signature invalid
    -2010: "SUB_ORDER_REJECTED",  # NEW_ORDER_REJECTED
    -2011: "EXC_ORDER_NOT_FOUND",  # CANCEL_REJECTED (order not found)
    -2014: "VAL_INVALID_APPROVAL",  # Invalid API-key format
    -2015: "AUT_INVALID_KEY",  # Invalid API-key, IP, or permissions
    
    # Margin/position errors
    -2018: "EXC_INSUFFICIENT_MARGIN",  # Balance insufficient
    -2019: "EXC_INSUFFICIENT_MARGIN",  # Margin insufficient
    -2020: "VAL_BELOW_MIN_NOTIONAL",  # Notional less than minimum
    -2021: "EXC_POSITION_LIMIT",  # Position side error
    -2022: "VAL_INVALID_QUANTITY",  # Invalid order quantity
    
    # Rate limit errors
    -1003: "RTE_API_WEIGHT",  # Too many requests
    -1015: "RTE_ORDER_LIMIT",  # Too many orders
    
    # Symbol errors
    -1121: "VAL_INVALID_SYMBOL",  # Invalid symbol
    -4001: "VAL_INVALID_PRICE",  # Invalid price
    -4003: "VAL_INVALID_QUANTITY",  # Quantity less than minimum
    -4014: "VAL_INVALID_PRICE",  # Price not increased by tick size
    -4015: "VAL_INVALID_QUANTITY",  # Quantity step error
    
    # Market status
    -4164: "EXC_MARKET_CLOSED",  # Trading halted
}


def get_error_info(code: str) -> ErrorCodeInfo:
    """
    Get error info for a code.
    
    Args:
        code: Error code
        
    Returns:
        ErrorCodeInfo or default unknown error
    """
    return ERROR_CODES.get(code, ErrorCodeInfo(
        code=code,
        category=ErrorCategory.INTERNAL,
        severity=ErrorSeverity.ERROR,
        is_retryable=False,
        description=f"Unknown error: {code}",
        recommended_action="Investigate error",
    ))


def map_binance_error(binance_code: int) -> str:
    """
    Map Binance error code to internal error code.
    
    Args:
        binance_code: Binance error code
        
    Returns:
        Internal error code
    """
    return BINANCE_ERROR_MAPPING.get(binance_code, "EXC_UNKNOWN_ERROR")


def is_retryable(code: str) -> bool:
    """Check if an error code is retryable."""
    info = get_error_info(code)
    return info.is_retryable


def should_escalate(code: str) -> bool:
    """Check if an error should be escalated to System Risk Controller."""
    info = get_error_info(code)
    return info.escalate_to_controller


# ============================================================
# RETRYABLE ERROR SETS
# ============================================================

RETRYABLE_ERROR_CODES: Set[str] = {
    code for code, info in ERROR_CODES.items() if info.is_retryable
}

ESCALATION_ERROR_CODES: Set[str] = {
    code for code, info in ERROR_CODES.items() if info.escalate_to_controller
}

CRITICAL_ERROR_CODES: Set[str] = {
    code for code, info in ERROR_CODES.items() 
    if info.severity in {ErrorSeverity.CRITICAL, ErrorSeverity.FATAL}
}
