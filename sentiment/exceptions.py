"""
Sentiment Source Exceptions - Custom error hierarchy.

These exceptions are for internal logging only.
Sentiment sources NEVER raise to caller - they return empty/None.
"""

from datetime import datetime
from typing import Any, Optional


class SentimentSourceError(Exception):
    """Base exception for all sentiment source errors."""
    
    def __init__(
        self,
        message: str,
        source_name: str = "",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.source_name = source_name
        self.details = details or {}
        self.timestamp = datetime.utcnow()
        super().__init__(self.message)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "source_name": self.source_name,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class RateLimitError(SentimentSourceError):
    """Rate limit exceeded for the sentiment source."""
    
    def __init__(
        self,
        message: str,
        source_name: str = "",
        retry_after_seconds: Optional[int] = None,
        rate_limit_type: str = "request",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, source_name, details)
        self.retry_after_seconds = retry_after_seconds
        self.rate_limit_type = rate_limit_type  # "request", "daily", "hourly"
    
    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "retry_after_seconds": self.retry_after_seconds,
            "rate_limit_type": self.rate_limit_type,
        })
        return data


class FetchError(SentimentSourceError):
    """Failed to fetch data from the sentiment source."""
    
    def __init__(
        self,
        message: str,
        source_name: str = "",
        status_code: Optional[int] = None,
        url: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, source_name, details)
        self.status_code = status_code
        self.url = url
    
    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "status_code": self.status_code,
            "url": self.url,
        })
        return data


class ParseError(SentimentSourceError):
    """Failed to parse response from sentiment source."""
    
    def __init__(
        self,
        message: str,
        source_name: str = "",
        raw_data: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, source_name, details)
        self.raw_data = raw_data[:500] if raw_data else None  # Truncate for safety
    
    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "raw_data_preview": self.raw_data[:100] if self.raw_data else None,
        })
        return data


class AuthenticationError(SentimentSourceError):
    """Authentication failed for the sentiment source."""
    pass


class ValidationError(SentimentSourceError):
    """Invalid request parameters."""
    pass


class CacheError(SentimentSourceError):
    """Cache operation failed."""
    pass


class NormalizationError(SentimentSourceError):
    """Failed to normalize sentiment data to standard format."""
    
    def __init__(
        self,
        message: str,
        source_name: str = "",
        raw_value: Optional[Any] = None,
        target_field: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, source_name, details)
        self.raw_value = raw_value
        self.target_field = target_field
    
    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "raw_value": str(self.raw_value)[:100] if self.raw_value else None,
            "target_field": self.target_field,
        })
        return data


class SourceUnavailableError(SentimentSourceError):
    """Source is temporarily or permanently unavailable."""
    
    def __init__(
        self,
        message: str,
        source_name: str = "",
        is_permanent: bool = False,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, source_name, details)
        self.is_permanent = is_permanent
    
    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "is_permanent": self.is_permanent,
        })
        return data


class QuotaExhaustedError(SentimentSourceError):
    """Daily/monthly quota exhausted for the source."""
    
    def __init__(
        self,
        message: str,
        source_name: str = "",
        quota_type: str = "daily",
        reset_time: Optional[datetime] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, source_name, details)
        self.quota_type = quota_type
        self.reset_time = reset_time
    
    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "quota_type": self.quota_type,
            "reset_time": self.reset_time.isoformat() if self.reset_time else None,
        })
        return data
