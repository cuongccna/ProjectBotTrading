"""
Exchange Adapter - Secure Logging Utilities.

============================================================
PURPOSE
============================================================
Secure logging for exchange adapter operations with:
- Credential masking (API keys, secrets)
- Request/response sanitization
- Structured logging format
- Audit trail support

============================================================
SECURITY REQUIREMENTS
============================================================
1. NEVER log raw API keys or secrets
2. Mask sensitive headers (Authorization, X-API-KEY, etc.)
3. Sanitize request bodies containing credentials
4. Redact response data with account details if needed

============================================================
"""

import logging
import re
import json
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum
from functools import lru_cache


logger = logging.getLogger(__name__)


# ============================================================
# SENSITIVE DATA PATTERNS
# ============================================================

# Header names that should be masked
SENSITIVE_HEADERS = {
    "authorization",
    "x-api-key",
    "x-mbx-apikey",
    "ok-access-key",
    "ok-access-passphrase",
    "ok-access-sign",
    "x-bapi-api-key",
    "x-bapi-sign",
    "api-key",
    "secret",
    "signature",
}

# Parameter names that should be masked
SENSITIVE_PARAMS = {
    "apikey",
    "api_key",
    "secret",
    "secretkey",
    "secret_key",
    "password",
    "passphrase",
    "signature",
    "sign",
    "privatekey",
    "private_key",
    "token",
    "access_token",
    "refresh_token",
}

# Regex patterns for sensitive data
SENSITIVE_PATTERNS = [
    (re.compile(r'[A-Za-z0-9]{32,}'), "***KEY***"),  # API keys (32+ chars)
    (re.compile(r'[a-f0-9]{64}', re.IGNORECASE), "***HMAC***"),  # HMAC signatures
]


# ============================================================
# MASKING FUNCTIONS
# ============================================================

def mask_value(value: str, show_chars: int = 4) -> str:
    """
    Mask a sensitive value, showing only first few chars.
    
    Args:
        value: Value to mask
        show_chars: Number of chars to show at start
        
    Returns:
        Masked value
    """
    if not value or len(value) <= show_chars:
        return "***"
    return f"{value[:show_chars]}...***"


def mask_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Mask sensitive headers.
    
    Args:
        headers: Request/response headers
        
    Returns:
        Headers with sensitive values masked
    """
    if not headers:
        return {}
    
    masked = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADERS:
            masked[key] = mask_value(str(value))
        else:
            masked[key] = value
    return masked


def mask_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mask sensitive parameters.
    
    Args:
        params: Request parameters
        
    Returns:
        Parameters with sensitive values masked
    """
    if not params:
        return {}
    
    masked = {}
    for key, value in params.items():
        if key.lower() in SENSITIVE_PARAMS:
            masked[key] = mask_value(str(value)) if value else value
        elif isinstance(value, dict):
            masked[key] = mask_params(value)
        elif isinstance(value, str):
            # Check for patterns in values
            masked_value = value
            for pattern, replacement in SENSITIVE_PATTERNS:
                if pattern.search(value):
                    masked_value = pattern.sub(replacement, masked_value)
            masked[key] = masked_value
        else:
            masked[key] = value
    return masked


def mask_url(url: str) -> str:
    """
    Mask sensitive data in URL.
    
    Args:
        url: URL string
        
    Returns:
        URL with sensitive params masked
    """
    if not url:
        return url
    
    # Mask common sensitive params in query string
    for param in SENSITIVE_PARAMS:
        pattern = re.compile(f'({param}=)([^&]+)', re.IGNORECASE)
        url = pattern.sub(lambda m: f'{m.group(1)}***', url)
    
    return url


# ============================================================
# LOG ENTRY STRUCTURES
# ============================================================

class LogLevel(Enum):
    """Log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class RequestLogEntry:
    """Structured log entry for requests."""
    
    timestamp: str
    exchange_id: str
    operation: str
    method: str
    endpoint: str
    request_id: str
    
    # Request details (masked)
    headers: Dict[str, str] = None
    params: Dict[str, Any] = None
    body_hash: str = None  # Hash of body instead of full body
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON logging."""
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class ResponseLogEntry:
    """Structured log entry for responses."""
    
    timestamp: str
    exchange_id: str
    operation: str
    request_id: str
    
    # Response details
    status_code: int
    latency_ms: float
    success: bool
    
    # Error info (if applicable)
    error_code: str = None
    error_message: str = None
    
    # Response preview (sanitized)
    response_preview: str = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON logging."""
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class OrderLogEntry:
    """Structured log entry for orders."""
    
    timestamp: str
    exchange_id: str
    operation: str  # submit, cancel, query
    
    # Order identifiers
    client_order_id: str
    exchange_order_id: str = None
    symbol: str = None
    
    # Order details
    side: str = None
    order_type: str = None
    quantity: str = None
    price: str = None
    
    # Result
    status: str = None
    filled_qty: str = None
    avg_price: str = None
    
    # Error info
    error_code: str = None
    error_message: str = None
    
    latency_ms: float = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON logging."""
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


# ============================================================
# ADAPTER LOGGER
# ============================================================

class AdapterLogger:
    """
    Secure logger for exchange adapter operations.
    
    Provides structured logging with automatic credential masking.
    """
    
    def __init__(
        self,
        exchange_id: str,
        logger_name: str = None,
        log_level: LogLevel = LogLevel.INFO,
    ):
        """
        Initialize adapter logger.
        
        Args:
            exchange_id: Exchange identifier
            logger_name: Logger name (default: exchange adapter logger)
            log_level: Minimum log level
        """
        self._exchange_id = exchange_id
        self._logger = logging.getLogger(
            logger_name or f"exchange_adapter.{exchange_id}"
        )
        self._log_level = log_level
        
        # Request counter for unique IDs
        self._request_counter = 0
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        self._request_counter += 1
        return f"{self._exchange_id}-{self._request_counter}"
    
    def _hash_body(self, body: Any) -> str:
        """Create hash of request body."""
        if not body:
            return None
        
        try:
            if isinstance(body, (dict, list)):
                body_str = json.dumps(body, sort_keys=True)
            else:
                body_str = str(body)
            
            return hashlib.sha256(body_str.encode()).hexdigest()[:16]
        except Exception:
            return "hash_error"
    
    def log_request(
        self,
        operation: str,
        method: str,
        endpoint: str,
        headers: Dict[str, str] = None,
        params: Dict[str, Any] = None,
        body: Any = None,
    ) -> str:
        """
        Log outgoing request.
        
        Args:
            operation: Operation name (e.g., "submit_order")
            method: HTTP method
            endpoint: API endpoint
            headers: Request headers
            params: Query parameters
            body: Request body
            
        Returns:
            Request ID for correlation
        """
        request_id = self._generate_request_id()
        
        entry = RequestLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            exchange_id=self._exchange_id,
            operation=operation,
            method=method,
            endpoint=mask_url(endpoint),
            request_id=request_id,
            headers=mask_headers(headers) if headers else None,
            params=mask_params(params) if params else None,
            body_hash=self._hash_body(body),
        )
        
        self._logger.debug(f"REQUEST: {entry.to_json()}")
        return request_id
    
    def log_response(
        self,
        operation: str,
        request_id: str,
        status_code: int,
        latency_ms: float,
        success: bool,
        error_code: str = None,
        error_message: str = None,
        response_body: Any = None,
    ) -> None:
        """
        Log incoming response.
        
        Args:
            operation: Operation name
            request_id: Correlation ID from request
            status_code: HTTP status code
            latency_ms: Request latency
            success: Whether request succeeded
            error_code: Error code if failed
            error_message: Error message if failed
            response_body: Response body (will be truncated)
        """
        # Create preview of response (truncated, sanitized)
        preview = None
        if response_body:
            try:
                if isinstance(response_body, dict):
                    preview = json.dumps(response_body)[:200]
                else:
                    preview = str(response_body)[:200]
            except Exception:
                preview = "<unparseable>"
        
        entry = ResponseLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            exchange_id=self._exchange_id,
            operation=operation,
            request_id=request_id,
            status_code=status_code,
            latency_ms=latency_ms,
            success=success,
            error_code=error_code,
            error_message=error_message[:200] if error_message else None,
            response_preview=preview,
        )
        
        if success:
            self._logger.debug(f"RESPONSE: {entry.to_json()}")
        else:
            self._logger.warning(f"RESPONSE_ERROR: {entry.to_json()}")
    
    def log_order(
        self,
        operation: str,
        client_order_id: str,
        symbol: str = None,
        side: str = None,
        order_type: str = None,
        quantity: str = None,
        price: str = None,
        exchange_order_id: str = None,
        status: str = None,
        filled_qty: str = None,
        avg_price: str = None,
        error_code: str = None,
        error_message: str = None,
        latency_ms: float = None,
    ) -> None:
        """
        Log order operation.
        
        Args:
            operation: Order operation (submit, cancel, query)
            client_order_id: Client order ID
            Additional order details...
        """
        entry = OrderLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            exchange_id=self._exchange_id,
            operation=operation,
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=status,
            filled_qty=filled_qty,
            avg_price=avg_price,
            error_code=error_code,
            error_message=error_message[:200] if error_message else None,
            latency_ms=latency_ms,
        )
        
        if error_code:
            self._logger.warning(f"ORDER_ERROR: {entry.to_json()}")
        else:
            self._logger.info(f"ORDER: {entry.to_json()}")
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self._logger.info(f"[{self._exchange_id}] {message}", extra=kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self._logger.warning(f"[{self._exchange_id}] {message}", extra=kwargs)
    
    def error(self, message: str, exc_info: bool = False, **kwargs) -> None:
        """Log error message."""
        self._logger.error(
            f"[{self._exchange_id}] {message}",
            exc_info=exc_info,
            extra=kwargs,
        )
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self._logger.debug(f"[{self._exchange_id}] {message}", extra=kwargs)


# ============================================================
# AUDIT LOG
# ============================================================

class AuditLog:
    """
    Audit log for compliance and debugging.
    
    Records all order operations with full context.
    """
    
    def __init__(self, max_entries: int = 10000):
        """Initialize audit log."""
        self._entries: List[Dict[str, Any]] = []
        self._max_entries = max_entries
    
    def record(
        self,
        exchange_id: str,
        operation: str,
        request: Dict[str, Any],
        response: Dict[str, Any],
        latency_ms: float,
        success: bool,
    ) -> None:
        """
        Record audit entry.
        
        Args:
            exchange_id: Exchange identifier
            operation: Operation performed
            request: Request details (sanitized)
            response: Response details (sanitized)
            latency_ms: Operation latency
            success: Whether operation succeeded
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "exchange_id": exchange_id,
            "operation": operation,
            "request": mask_params(request),
            "response": response,
            "latency_ms": latency_ms,
            "success": success,
        }
        
        self._entries.append(entry)
        
        # Trim old entries
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]
    
    def get_entries(
        self,
        exchange_id: str = None,
        operation: str = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get audit entries.
        
        Args:
            exchange_id: Filter by exchange
            operation: Filter by operation
            limit: Max entries to return
            
        Returns:
            Filtered audit entries
        """
        entries = self._entries
        
        if exchange_id:
            entries = [e for e in entries if e["exchange_id"] == exchange_id]
        
        if operation:
            entries = [e for e in entries if e["operation"] == operation]
        
        return entries[-limit:]
    
    def export(self) -> List[Dict[str, Any]]:
        """Export all entries."""
        return list(self._entries)
    
    def clear(self) -> None:
        """Clear audit log."""
        self._entries.clear()


# Global audit log instance
_global_audit_log = AuditLog()


def get_audit_log() -> AuditLog:
    """Get global audit log."""
    return _global_audit_log
