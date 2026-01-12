"""
Exchange Adapter - Error Handling and Mapping.

============================================================
PURPOSE
============================================================
Standardized error handling for exchange adapters with:
- Unified error taxonomy across exchanges
- Exchange-specific error code mapping
- Retry eligibility classification
- Error context preservation

============================================================
ERROR CATEGORIES
============================================================
1. NETWORK         - Connection issues, timeouts
2. RATE_LIMIT      - Too many requests
3. AUTHENTICATION  - Invalid credentials
4. INVALID_ORDER   - Order validation failures
5. INSUFFICIENT    - Insufficient margin/balance
6. EXCHANGE_ERROR  - Exchange internal errors
7. UNKNOWN         - Unclassified errors

============================================================
"""

import logging
from enum import Enum
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass


logger = logging.getLogger(__name__)


# ============================================================
# ERROR TAXONOMY
# ============================================================

class ErrorCategory(Enum):
    """Standardized error categories."""
    
    NETWORK = "NETWORK"
    RATE_LIMIT = "RATE_LIMIT"
    AUTHENTICATION = "AUTHENTICATION"
    INVALID_ORDER = "INVALID_ORDER"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    EXCHANGE_ERROR = "EXCHANGE_ERROR"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
    POSITION_NOT_FOUND = "POSITION_NOT_FOUND"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    INVALID_PRICE = "INVALID_PRICE"
    MIN_NOTIONAL = "MIN_NOTIONAL"
    MAX_POSITION = "MAX_POSITION"
    MARKET_CLOSED = "MARKET_CLOSED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


class RetryEligibility(Enum):
    """Whether error is eligible for retry."""
    
    RETRY = "RETRY"           # Safe to retry
    NO_RETRY = "NO_RETRY"     # Should not retry
    BACKOFF = "BACKOFF"       # Retry with exponential backoff


# ============================================================
# EXCHANGE ERROR
# ============================================================

@dataclass
class ExchangeError:
    """
    Standardized exchange error.
    
    Provides unified error representation across exchanges.
    """
    
    # Core fields
    category: ErrorCategory
    code: str               # Normalized error code
    message: str            # Human-readable message
    
    # Retry info
    retry_eligible: RetryEligibility
    retry_after_ms: Optional[int] = None
    
    # Original error info
    exchange_code: Optional[str] = None     # Original exchange error code
    exchange_message: Optional[str] = None  # Original exchange message
    http_status: Optional[int] = None
    
    # Context
    exchange_id: Optional[str] = None
    operation: Optional[str] = None
    symbol: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "category": self.category.value,
            "code": self.code,
            "message": self.message,
            "retry_eligible": self.retry_eligible.value,
            "retry_after_ms": self.retry_after_ms,
            "exchange_code": self.exchange_code,
            "exchange_message": self.exchange_message,
            "http_status": self.http_status,
            "exchange_id": self.exchange_id,
            "operation": self.operation,
            "symbol": self.symbol,
        }
    
    def is_retryable(self) -> bool:
        """Check if error is retryable."""
        return self.retry_eligible in (RetryEligibility.RETRY, RetryEligibility.BACKOFF)
    
    def __str__(self) -> str:
        """String representation."""
        return f"[{self.category.value}] {self.code}: {self.message}"


class ExchangeException(Exception):
    """Exception wrapper for ExchangeError."""
    
    def __init__(self, error: ExchangeError):
        self.error = error
        super().__init__(str(error))


# ============================================================
# BINANCE ERROR MAPPING
# ============================================================

# Binance error codes to unified category
BINANCE_ERROR_MAP: Dict[int, Tuple[ErrorCategory, RetryEligibility]] = {
    # Rate limiting
    -1003: (ErrorCategory.RATE_LIMIT, RetryEligibility.BACKOFF),
    -1015: (ErrorCategory.RATE_LIMIT, RetryEligibility.BACKOFF),
    429: (ErrorCategory.RATE_LIMIT, RetryEligibility.BACKOFF),
    
    # Authentication
    -1002: (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    -1022: (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    -2014: (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    -2015: (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    
    # Order validation
    -1013: (ErrorCategory.INVALID_QUANTITY, RetryEligibility.NO_RETRY),
    -1021: (ErrorCategory.TIMEOUT, RetryEligibility.RETRY),
    -1100: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    -1101: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    -1102: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    -1111: (ErrorCategory.INVALID_QUANTITY, RetryEligibility.NO_RETRY),
    -1112: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    -1114: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    -1115: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    -1116: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    -1117: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    -1121: (ErrorCategory.SYMBOL_NOT_FOUND, RetryEligibility.NO_RETRY),
    
    # Insufficient funds/margin
    -2010: (ErrorCategory.INSUFFICIENT_FUNDS, RetryEligibility.NO_RETRY),
    -2018: (ErrorCategory.INSUFFICIENT_FUNDS, RetryEligibility.NO_RETRY),
    -2019: (ErrorCategory.INSUFFICIENT_MARGIN, RetryEligibility.NO_RETRY),
    
    # Order not found
    -2011: (ErrorCategory.ORDER_NOT_FOUND, RetryEligibility.NO_RETRY),
    -2013: (ErrorCategory.ORDER_NOT_FOUND, RetryEligibility.NO_RETRY),
    
    # Position
    -2021: (ErrorCategory.MAX_POSITION, RetryEligibility.NO_RETRY),
    -2022: (ErrorCategory.POSITION_NOT_FOUND, RetryEligibility.NO_RETRY),
    
    # Min notional
    -4164: (ErrorCategory.MIN_NOTIONAL, RetryEligibility.NO_RETRY),
    
    # Price
    -4014: (ErrorCategory.INVALID_PRICE, RetryEligibility.NO_RETRY),
    -4015: (ErrorCategory.INVALID_PRICE, RetryEligibility.NO_RETRY),
    
    # Exchange internal
    -1000: (ErrorCategory.EXCHANGE_ERROR, RetryEligibility.RETRY),
    -1001: (ErrorCategory.EXCHANGE_ERROR, RetryEligibility.RETRY),
    -1006: (ErrorCategory.EXCHANGE_ERROR, RetryEligibility.RETRY),
    -1007: (ErrorCategory.TIMEOUT, RetryEligibility.RETRY),
}


def map_binance_error(
    code: int,
    message: str,
    http_status: int = None,
) -> ExchangeError:
    """
    Map Binance error to unified format.
    
    Args:
        code: Binance error code
        message: Binance error message
        http_status: HTTP status code
        
    Returns:
        Unified ExchangeError
    """
    if code in BINANCE_ERROR_MAP:
        category, retry = BINANCE_ERROR_MAP[code]
    elif http_status == 429 or http_status == 418:
        category = ErrorCategory.RATE_LIMIT
        retry = RetryEligibility.BACKOFF
    elif http_status == 403 or http_status == 401:
        category = ErrorCategory.AUTHENTICATION
        retry = RetryEligibility.NO_RETRY
    elif http_status and http_status >= 500:
        category = ErrorCategory.EXCHANGE_ERROR
        retry = RetryEligibility.RETRY
    else:
        category = ErrorCategory.UNKNOWN
        retry = RetryEligibility.NO_RETRY
    
    return ExchangeError(
        category=category,
        code=f"BINANCE_{code}",
        message=message,
        retry_eligible=retry,
        exchange_code=str(code),
        exchange_message=message,
        http_status=http_status,
        exchange_id="binance",
    )


# ============================================================
# OKX ERROR MAPPING
# ============================================================

# OKX error codes to unified category
OKX_ERROR_MAP: Dict[str, Tuple[ErrorCategory, RetryEligibility]] = {
    # Rate limiting
    "50011": (ErrorCategory.RATE_LIMIT, RetryEligibility.BACKOFF),
    "50013": (ErrorCategory.RATE_LIMIT, RetryEligibility.BACKOFF),
    
    # Authentication
    "50101": (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    "50102": (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    "50103": (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    "50104": (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    "50105": (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    "50106": (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    "50107": (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    "50108": (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    "50109": (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    "50110": (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    "50111": (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    
    # Order validation
    "51000": (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    "51001": (ErrorCategory.SYMBOL_NOT_FOUND, RetryEligibility.NO_RETRY),
    "51002": (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    "51003": (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    "51004": (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    "51005": (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    "51006": (ErrorCategory.INVALID_QUANTITY, RetryEligibility.NO_RETRY),
    "51008": (ErrorCategory.INSUFFICIENT_FUNDS, RetryEligibility.NO_RETRY),
    "51009": (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    "51010": (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    "51011": (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    "51012": (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    "51016": (ErrorCategory.ORDER_NOT_FOUND, RetryEligibility.NO_RETRY),
    "51020": (ErrorCategory.INVALID_QUANTITY, RetryEligibility.NO_RETRY),
    "51023": (ErrorCategory.INVALID_PRICE, RetryEligibility.NO_RETRY),
    "51024": (ErrorCategory.INVALID_PRICE, RetryEligibility.NO_RETRY),
    "51025": (ErrorCategory.INVALID_PRICE, RetryEligibility.NO_RETRY),
    "51026": (ErrorCategory.INVALID_PRICE, RetryEligibility.NO_RETRY),
    "51030": (ErrorCategory.MIN_NOTIONAL, RetryEligibility.NO_RETRY),
    
    # Insufficient margin
    "51119": (ErrorCategory.INSUFFICIENT_MARGIN, RetryEligibility.NO_RETRY),
    "51120": (ErrorCategory.INSUFFICIENT_MARGIN, RetryEligibility.NO_RETRY),
    "51121": (ErrorCategory.INSUFFICIENT_MARGIN, RetryEligibility.NO_RETRY),
    
    # Position
    "51130": (ErrorCategory.MAX_POSITION, RetryEligibility.NO_RETRY),
    "51131": (ErrorCategory.POSITION_NOT_FOUND, RetryEligibility.NO_RETRY),
    
    # Exchange internal
    "50000": (ErrorCategory.EXCHANGE_ERROR, RetryEligibility.RETRY),
    "50001": (ErrorCategory.EXCHANGE_ERROR, RetryEligibility.RETRY),
    "50004": (ErrorCategory.TIMEOUT, RetryEligibility.RETRY),
}


def map_okx_error(
    code: str,
    message: str,
    http_status: int = None,
) -> ExchangeError:
    """
    Map OKX error to unified format.
    
    Args:
        code: OKX error code
        message: OKX error message
        http_status: HTTP status code
        
    Returns:
        Unified ExchangeError
    """
    if code in OKX_ERROR_MAP:
        category, retry = OKX_ERROR_MAP[code]
    elif http_status == 429:
        category = ErrorCategory.RATE_LIMIT
        retry = RetryEligibility.BACKOFF
    elif http_status == 403 or http_status == 401:
        category = ErrorCategory.AUTHENTICATION
        retry = RetryEligibility.NO_RETRY
    elif http_status and http_status >= 500:
        category = ErrorCategory.EXCHANGE_ERROR
        retry = RetryEligibility.RETRY
    else:
        category = ErrorCategory.UNKNOWN
        retry = RetryEligibility.NO_RETRY
    
    return ExchangeError(
        category=category,
        code=f"OKX_{code}",
        message=message,
        retry_eligible=retry,
        exchange_code=code,
        exchange_message=message,
        http_status=http_status,
        exchange_id="okx",
    )


# ============================================================
# BYBIT ERROR MAPPING
# ============================================================

# Bybit error codes to unified category (V5 API)
BYBIT_ERROR_MAP: Dict[int, Tuple[ErrorCategory, RetryEligibility]] = {
    # Rate limiting
    10006: (ErrorCategory.RATE_LIMIT, RetryEligibility.BACKOFF),
    10018: (ErrorCategory.RATE_LIMIT, RetryEligibility.BACKOFF),
    
    # Authentication
    10003: (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    10004: (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    10005: (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    33004: (ErrorCategory.AUTHENTICATION, RetryEligibility.NO_RETRY),
    
    # Order validation
    10001: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    10002: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    110001: (ErrorCategory.ORDER_NOT_FOUND, RetryEligibility.NO_RETRY),
    110003: (ErrorCategory.INVALID_QUANTITY, RetryEligibility.NO_RETRY),
    110004: (ErrorCategory.INVALID_PRICE, RetryEligibility.NO_RETRY),
    110005: (ErrorCategory.INVALID_PRICE, RetryEligibility.NO_RETRY),
    110006: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    110007: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    110008: (ErrorCategory.ORDER_NOT_FOUND, RetryEligibility.NO_RETRY),
    110009: (ErrorCategory.INVALID_PRICE, RetryEligibility.NO_RETRY),
    110010: (ErrorCategory.INVALID_QUANTITY, RetryEligibility.NO_RETRY),
    110011: (ErrorCategory.INVALID_QUANTITY, RetryEligibility.NO_RETRY),
    110012: (ErrorCategory.INSUFFICIENT_FUNDS, RetryEligibility.NO_RETRY),
    110013: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    110014: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    110015: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    110017: (ErrorCategory.INVALID_ORDER, RetryEligibility.NO_RETRY),
    110018: (ErrorCategory.INSUFFICIENT_MARGIN, RetryEligibility.NO_RETRY),
    110025: (ErrorCategory.INVALID_QUANTITY, RetryEligibility.NO_RETRY),
    110026: (ErrorCategory.MIN_NOTIONAL, RetryEligibility.NO_RETRY),
    
    # Symbol
    110072: (ErrorCategory.SYMBOL_NOT_FOUND, RetryEligibility.NO_RETRY),
    
    # Position
    110043: (ErrorCategory.MAX_POSITION, RetryEligibility.NO_RETRY),
    110044: (ErrorCategory.POSITION_NOT_FOUND, RetryEligibility.NO_RETRY),
    
    # Exchange internal
    10000: (ErrorCategory.EXCHANGE_ERROR, RetryEligibility.RETRY),
    10016: (ErrorCategory.EXCHANGE_ERROR, RetryEligibility.RETRY),
    10027: (ErrorCategory.TIMEOUT, RetryEligibility.RETRY),
}


def map_bybit_error(
    code: int,
    message: str,
    http_status: int = None,
) -> ExchangeError:
    """
    Map Bybit error to unified format.
    
    Args:
        code: Bybit error code
        message: Bybit error message
        http_status: HTTP status code
        
    Returns:
        Unified ExchangeError
    """
    if code in BYBIT_ERROR_MAP:
        category, retry = BYBIT_ERROR_MAP[code]
    elif http_status == 429:
        category = ErrorCategory.RATE_LIMIT
        retry = RetryEligibility.BACKOFF
    elif http_status == 403 or http_status == 401:
        category = ErrorCategory.AUTHENTICATION
        retry = RetryEligibility.NO_RETRY
    elif http_status and http_status >= 500:
        category = ErrorCategory.EXCHANGE_ERROR
        retry = RetryEligibility.RETRY
    else:
        category = ErrorCategory.UNKNOWN
        retry = RetryEligibility.NO_RETRY
    
    return ExchangeError(
        category=category,
        code=f"BYBIT_{code}",
        message=message,
        retry_eligible=retry,
        exchange_code=str(code),
        exchange_message=message,
        http_status=http_status,
        exchange_id="bybit",
    )


# ============================================================
# ERROR MAPPER FACTORY
# ============================================================

def map_exchange_error(
    exchange_id: str,
    code: Any,
    message: str,
    http_status: int = None,
) -> ExchangeError:
    """
    Map exchange error to unified format.
    
    Factory function that routes to exchange-specific mapper.
    
    Args:
        exchange_id: Exchange identifier
        code: Exchange error code
        message: Error message
        http_status: HTTP status code
        
    Returns:
        Unified ExchangeError
    """
    exchange_id = exchange_id.lower()
    
    if exchange_id == "binance":
        return map_binance_error(int(code), message, http_status)
    elif exchange_id == "okx":
        return map_okx_error(str(code), message, http_status)
    elif exchange_id == "bybit":
        return map_bybit_error(int(code), message, http_status)
    else:
        return ExchangeError(
            category=ErrorCategory.UNKNOWN,
            code=f"{exchange_id.upper()}_{code}",
            message=message,
            retry_eligible=RetryEligibility.NO_RETRY,
            exchange_code=str(code),
            exchange_message=message,
            http_status=http_status,
            exchange_id=exchange_id,
        )


# ============================================================
# NETWORK ERROR HELPERS
# ============================================================

def create_network_error(
    exchange_id: str,
    message: str,
    operation: str = None,
) -> ExchangeError:
    """Create network error."""
    return ExchangeError(
        category=ErrorCategory.NETWORK,
        code=f"{exchange_id.upper()}_NETWORK_ERROR",
        message=message,
        retry_eligible=RetryEligibility.RETRY,
        exchange_id=exchange_id,
        operation=operation,
    )


def create_timeout_error(
    exchange_id: str,
    timeout_ms: int,
    operation: str = None,
) -> ExchangeError:
    """Create timeout error."""
    return ExchangeError(
        category=ErrorCategory.TIMEOUT,
        code=f"{exchange_id.upper()}_TIMEOUT",
        message=f"Request timed out after {timeout_ms}ms",
        retry_eligible=RetryEligibility.RETRY,
        exchange_id=exchange_id,
        operation=operation,
    )


def create_rate_limit_error(
    exchange_id: str,
    retry_after_ms: int = None,
) -> ExchangeError:
    """Create rate limit error."""
    return ExchangeError(
        category=ErrorCategory.RATE_LIMIT,
        code=f"{exchange_id.upper()}_RATE_LIMIT",
        message="Rate limit exceeded",
        retry_eligible=RetryEligibility.BACKOFF,
        retry_after_ms=retry_after_ms,
        exchange_id=exchange_id,
    )
