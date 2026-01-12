"""
Product Data Packaging - Access Control.

============================================================
PURPOSE
============================================================
Control access to data products:
1. Rate limiting
2. Request logging
3. Read-only enforcement
4. API key validation (placeholder)

============================================================
CRITICAL CONSTRAINTS
============================================================
- All access is READ-ONLY
- No direct database exposure
- Every request must be logged
- Rate limits must be enforced

============================================================
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import hashlib
import logging
import time
import uuid


from .models import (
    ProductType,
    RateLimitConfig,
    AccessLog,
    ExportRequest,
    create_default_rate_limit,
)


logger = logging.getLogger(__name__)


# ============================================================
# ACCESS LEVEL
# ============================================================

class AccessLevel(Enum):
    """Access level for clients."""
    NONE = "none"
    READ_ONLY = "read_only"
    INTERNAL = "internal"


class RequestDenialReason(Enum):
    """Reasons for denying a request."""
    RATE_LIMIT_MINUTE = "rate_limit_per_minute_exceeded"
    RATE_LIMIT_HOUR = "rate_limit_per_hour_exceeded"
    RATE_LIMIT_DAY = "rate_limit_per_day_exceeded"
    DATA_LIMIT = "data_points_limit_exceeded"
    TIME_RANGE_LIMIT = "time_range_limit_exceeded"
    INVALID_API_KEY = "invalid_api_key"
    ACCESS_DENIED = "access_denied"
    PRODUCT_NOT_AVAILABLE = "product_not_available"


# ============================================================
# RATE LIMITER
# ============================================================

@dataclass
class RateLimitBucket:
    """Bucket for tracking rate limits."""
    count: int = 0
    reset_at: datetime = field(default_factory=datetime.utcnow)


class RateLimiter:
    """
    Implements rate limiting for API access.
    
    Uses a sliding window approach.
    """
    
    def __init__(self, config: RateLimitConfig):
        self._config = config
        
        # Per-client buckets
        self._minute_buckets: Dict[str, RateLimitBucket] = defaultdict(RateLimitBucket)
        self._hour_buckets: Dict[str, RateLimitBucket] = defaultdict(RateLimitBucket)
        self._day_buckets: Dict[str, RateLimitBucket] = defaultdict(RateLimitBucket)
    
    def check_limit(self, client_id: str) -> Tuple[bool, Optional[RequestDenialReason], int]:
        """
        Check if a request is within rate limits.
        
        Returns (allowed, denial_reason, retry_after_seconds)
        """
        now = datetime.utcnow()
        
        # Check minute limit
        minute_bucket = self._get_or_reset_bucket(
            self._minute_buckets,
            client_id,
            now,
            timedelta(minutes=1),
        )
        
        if minute_bucket.count >= self._config.requests_per_minute:
            retry_after = int((minute_bucket.reset_at - now).total_seconds())
            return False, RequestDenialReason.RATE_LIMIT_MINUTE, max(1, retry_after)
        
        # Check hour limit
        hour_bucket = self._get_or_reset_bucket(
            self._hour_buckets,
            client_id,
            now,
            timedelta(hours=1),
        )
        
        if hour_bucket.count >= self._config.requests_per_hour:
            retry_after = int((hour_bucket.reset_at - now).total_seconds())
            return False, RequestDenialReason.RATE_LIMIT_HOUR, max(1, retry_after)
        
        # Check day limit
        day_bucket = self._get_or_reset_bucket(
            self._day_buckets,
            client_id,
            now,
            timedelta(days=1),
        )
        
        if day_bucket.count >= self._config.requests_per_day:
            retry_after = int((day_bucket.reset_at - now).total_seconds())
            return False, RequestDenialReason.RATE_LIMIT_DAY, max(1, retry_after)
        
        # All limits passed
        return True, None, 0
    
    def record_request(self, client_id: str) -> None:
        """Record a successful request."""
        now = datetime.utcnow()
        
        self._minute_buckets[client_id] = self._get_or_reset_bucket(
            self._minute_buckets, client_id, now, timedelta(minutes=1)
        )
        self._minute_buckets[client_id].count += 1
        
        self._hour_buckets[client_id] = self._get_or_reset_bucket(
            self._hour_buckets, client_id, now, timedelta(hours=1)
        )
        self._hour_buckets[client_id].count += 1
        
        self._day_buckets[client_id] = self._get_or_reset_bucket(
            self._day_buckets, client_id, now, timedelta(days=1)
        )
        self._day_buckets[client_id].count += 1
    
    def _get_or_reset_bucket(
        self,
        buckets: Dict[str, RateLimitBucket],
        client_id: str,
        now: datetime,
        window: timedelta,
    ) -> RateLimitBucket:
        """Get bucket, resetting if window has passed."""
        bucket = buckets.get(client_id)
        
        if bucket is None or now >= bucket.reset_at:
            bucket = RateLimitBucket(
                count=0,
                reset_at=now + window,
            )
            buckets[client_id] = bucket
        
        return bucket
    
    def get_remaining(self, client_id: str) -> Dict[str, int]:
        """Get remaining requests for a client."""
        now = datetime.utcnow()
        
        minute_bucket = self._get_or_reset_bucket(
            self._minute_buckets, client_id, now, timedelta(minutes=1)
        )
        hour_bucket = self._get_or_reset_bucket(
            self._hour_buckets, client_id, now, timedelta(hours=1)
        )
        day_bucket = self._get_or_reset_bucket(
            self._day_buckets, client_id, now, timedelta(days=1)
        )
        
        return {
            "per_minute": max(0, self._config.requests_per_minute - minute_bucket.count),
            "per_hour": max(0, self._config.requests_per_hour - hour_bucket.count),
            "per_day": max(0, self._config.requests_per_day - day_bucket.count),
        }


# ============================================================
# ACCESS LOGGER
# ============================================================

class AccessLogger:
    """
    Logs all access to data products.
    
    CRITICAL: Every export request must be logged.
    """
    
    def __init__(self, max_log_entries: int = 100000):
        self._logs: List[AccessLog] = []
        self._max_entries = max_log_entries
    
    def log_request(
        self,
        requester_id: str,
        product_id: str,
        product_type: ProductType,
        action: str,
        time_range_start: Optional[datetime] = None,
        time_range_end: Optional[datetime] = None,
        record_count: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
    ) -> AccessLog:
        """Log an access request."""
        # Hash the IP address for privacy
        ip_hash = None
        if ip_address:
            ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:16]
        
        log_entry = AccessLog(
            log_id=f"log_{uuid.uuid4().hex[:8]}",
            requester_id=requester_id,
            product_id=product_id,
            product_type=product_type,
            action=action,
            time_range_start=time_range_start,
            time_range_end=time_range_end,
            record_count=record_count,
            success=success,
            error_message=error_message,
            ip_address_hash=ip_hash,
            processing_time_ms=processing_time_ms,
        )
        
        self._logs.append(log_entry)
        
        # Trim if too many logs
        if len(self._logs) > self._max_entries:
            self._logs = self._logs[-self._max_entries:]
        
        # Also log to standard logger
        log_msg = (
            f"Access: {action} by {requester_id} for {product_type.value} "
            f"(success={success})"
        )
        if success:
            logger.info(log_msg)
        else:
            logger.warning(f"{log_msg} - {error_message}")
        
        return log_entry
    
    def get_logs(
        self,
        requester_id: Optional[str] = None,
        product_type: Optional[ProductType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        success_only: bool = False,
        limit: int = 100,
    ) -> List[AccessLog]:
        """Query access logs."""
        filtered = self._logs
        
        if requester_id:
            filtered = [l for l in filtered if l.requester_id == requester_id]
        
        if product_type:
            filtered = [l for l in filtered if l.product_type == product_type]
        
        if start_time:
            filtered = [l for l in filtered if l.timestamp >= start_time]
        
        if end_time:
            filtered = [l for l in filtered if l.timestamp <= end_time]
        
        if success_only:
            filtered = [l for l in filtered if l.success]
        
        return filtered[-limit:]
    
    def get_statistics(
        self,
        requester_id: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get access statistics."""
        logs = self._logs
        
        if requester_id:
            logs = [l for l in logs if l.requester_id == requester_id]
        
        if since:
            logs = [l for l in logs if l.timestamp >= since]
        
        if not logs:
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "by_product_type": {},
            }
        
        by_product = defaultdict(int)
        for log in logs:
            by_product[log.product_type.value] += 1
        
        successful = sum(1 for l in logs if l.success)
        
        return {
            "total_requests": len(logs),
            "successful_requests": successful,
            "failed_requests": len(logs) - successful,
            "success_rate": successful / len(logs) if logs else 0,
            "by_product_type": dict(by_product),
            "average_processing_time_ms": (
                sum(l.processing_time_ms for l in logs if l.processing_time_ms) /
                len([l for l in logs if l.processing_time_ms])
                if any(l.processing_time_ms for l in logs) else 0
            ),
        }


# ============================================================
# REQUEST VALIDATOR
# ============================================================

class RequestValidator:
    """Validates export requests."""
    
    def __init__(self, rate_limit_config: RateLimitConfig):
        self._config = rate_limit_config
    
    def validate(
        self,
        request: ExportRequest,
    ) -> Tuple[bool, Optional[RequestDenialReason], str]:
        """
        Validate a request.
        
        Returns (valid, denial_reason, error_message)
        """
        # Check data points limit
        # (This is a rough estimate, actual count determined during extraction)
        time_range = request.end_time - request.start_time
        time_range_days = time_range.total_seconds() / 86400
        
        # Check time range limit
        if time_range_days > self._config.max_time_range_days:
            return (
                False,
                RequestDenialReason.TIME_RANGE_LIMIT,
                f"Time range {time_range_days:.1f} days exceeds limit of "
                f"{self._config.max_time_range_days} days",
            )
        
        # Check for valid time range
        if request.start_time >= request.end_time:
            return (
                False,
                RequestDenialReason.ACCESS_DENIED,
                "Start time must be before end time",
            )
        
        # Check for future data
        if request.end_time > datetime.utcnow():
            return (
                False,
                RequestDenialReason.ACCESS_DENIED,
                "Cannot request future data",
            )
        
        return True, None, ""


# ============================================================
# READ-ONLY ENFORCER
# ============================================================

class ReadOnlyEnforcer:
    """
    Enforces read-only access.
    
    CRITICAL: No write operations are allowed.
    """
    
    # Allowed operations (all read-only)
    ALLOWED_OPERATIONS: Set[str] = {
        "export",
        "query",
        "schema_fetch",
        "list_products",
        "get_metadata",
        "check_availability",
    }
    
    # Denied operations (any write)
    DENIED_OPERATIONS: Set[str] = {
        "write",
        "update",
        "delete",
        "create",
        "modify",
        "insert",
        "truncate",
        "drop",
    }
    
    @classmethod
    def check_operation(cls, operation: str) -> Tuple[bool, str]:
        """Check if an operation is allowed."""
        op_lower = operation.lower()
        
        # Check denied list first
        for denied in cls.DENIED_OPERATIONS:
            if denied in op_lower:
                return False, f"Write operation '{operation}' is not allowed"
        
        # Check if in allowed list
        if op_lower in cls.ALLOWED_OPERATIONS:
            return True, ""
        
        # Unknown operations are denied by default
        return False, f"Unknown operation '{operation}' is not allowed"
    
    @classmethod
    def wrap_safe(cls, operation: str, func):
        """
        Wrap a function to enforce read-only access.
        
        Raises ValueError if operation is not allowed.
        """
        allowed, error = cls.check_operation(operation)
        if not allowed:
            raise ValueError(error)
        return func


# ============================================================
# ACCESS CONTROLLER
# ============================================================

@dataclass
class AccessCheckResult:
    """Result of an access check."""
    allowed: bool
    denial_reason: Optional[RequestDenialReason] = None
    error_message: str = ""
    retry_after_seconds: int = 0
    remaining_requests: Optional[Dict[str, int]] = None


class AccessController:
    """
    Main access controller.
    
    Combines rate limiting, logging, and validation.
    """
    
    def __init__(
        self,
        rate_limit_config: Optional[RateLimitConfig] = None,
        available_products: Optional[Set[ProductType]] = None,
    ):
        self._config = rate_limit_config or create_default_rate_limit()
        self._available_products = available_products or set(ProductType)
        
        self._rate_limiter = RateLimiter(self._config)
        self._logger = AccessLogger()
        self._validator = RequestValidator(self._config)
    
    def check_access(
        self,
        client_id: str,
        request: ExportRequest,
    ) -> AccessCheckResult:
        """
        Check if a request should be allowed.
        
        Returns AccessCheckResult with decision.
        """
        # Check read-only
        allowed, error = ReadOnlyEnforcer.check_operation("export")
        if not allowed:
            return AccessCheckResult(
                allowed=False,
                denial_reason=RequestDenialReason.ACCESS_DENIED,
                error_message=error,
            )
        
        # Check rate limits
        rate_allowed, denial_reason, retry_after = self._rate_limiter.check_limit(
            client_id
        )
        
        if not rate_allowed:
            return AccessCheckResult(
                allowed=False,
                denial_reason=denial_reason,
                error_message=f"Rate limit exceeded. Retry after {retry_after} seconds.",
                retry_after_seconds=retry_after,
                remaining_requests=self._rate_limiter.get_remaining(client_id),
            )
        
        # Check product availability
        if request.product_type not in self._available_products:
            return AccessCheckResult(
                allowed=False,
                denial_reason=RequestDenialReason.PRODUCT_NOT_AVAILABLE,
                error_message=f"Product {request.product_type.value} is not available",
            )
        
        # Validate request
        valid, denial_reason, error = self._validator.validate(request)
        if not valid:
            return AccessCheckResult(
                allowed=False,
                denial_reason=denial_reason,
                error_message=error,
            )
        
        # All checks passed
        return AccessCheckResult(
            allowed=True,
            remaining_requests=self._rate_limiter.get_remaining(client_id),
        )
    
    def record_access(
        self,
        client_id: str,
        request: ExportRequest,
        success: bool,
        record_count: int = 0,
        error_message: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
    ) -> AccessLog:
        """Record an access after it completes."""
        # Record in rate limiter
        if success:
            self._rate_limiter.record_request(client_id)
        
        # Log the access
        return self._logger.log_request(
            requester_id=client_id,
            product_id=request.product_id,
            product_type=request.product_type,
            action="export",
            time_range_start=request.start_time,
            time_range_end=request.end_time,
            record_count=record_count,
            success=success,
            error_message=error_message,
            processing_time_ms=processing_time_ms,
        )
    
    def get_access_logs(
        self,
        client_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AccessLog]:
        """Get access logs."""
        return self._logger.get_logs(requester_id=client_id, limit=limit)
    
    def get_statistics(
        self,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get access statistics."""
        return self._logger.get_statistics(requester_id=client_id)


# ============================================================
# API KEY MANAGER (PLACEHOLDER)
# ============================================================

class ApiKeyManager:
    """
    Manages API keys for access control.
    
    NOTE: This is a placeholder. Real implementation would
    integrate with a proper authentication system.
    """
    
    def __init__(self):
        self._keys: Dict[str, Dict[str, Any]] = {}
    
    def register_key(
        self,
        api_key: str,
        client_id: str,
        tier: str = "basic",
        rate_limit_multiplier: float = 1.0,
    ) -> None:
        """Register an API key."""
        key_hash = self._hash_key(api_key)
        self._keys[key_hash] = {
            "client_id": client_id,
            "tier": tier,
            "rate_limit_multiplier": rate_limit_multiplier,
            "created_at": datetime.utcnow(),
            "last_used": None,
        }
    
    def validate_key(self, api_key: str) -> Tuple[bool, Optional[str]]:
        """
        Validate an API key.
        
        Returns (valid, client_id)
        """
        key_hash = self._hash_key(api_key)
        
        if key_hash not in self._keys:
            return False, None
        
        key_data = self._keys[key_hash]
        key_data["last_used"] = datetime.utcnow()
        
        return True, key_data["client_id"]
    
    def _hash_key(self, api_key: str) -> str:
        """Hash an API key for storage."""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    def revoke_key(self, api_key: str) -> bool:
        """Revoke an API key."""
        key_hash = self._hash_key(api_key)
        if key_hash in self._keys:
            del self._keys[key_hash]
            return True
        return False


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_rate_limiter(config: Optional[RateLimitConfig] = None) -> RateLimiter:
    """Create a rate limiter."""
    return RateLimiter(config or create_default_rate_limit())


def create_access_logger(max_entries: int = 100000) -> AccessLogger:
    """Create an access logger."""
    return AccessLogger(max_log_entries=max_entries)


def create_access_controller(
    rate_limit_config: Optional[RateLimitConfig] = None,
) -> AccessController:
    """Create an access controller."""
    return AccessController(rate_limit_config=rate_limit_config)


def create_request_validator(
    rate_limit_config: Optional[RateLimitConfig] = None,
) -> RequestValidator:
    """Create a request validator."""
    return RequestValidator(rate_limit_config or create_default_rate_limit())


def create_api_key_manager() -> ApiKeyManager:
    """Create an API key manager."""
    return ApiKeyManager()
