"""
Data Source Exceptions - Custom exception hierarchy for market data sources.

Provides fail-safe exception handling with no unhandled exceptions.
"""

from datetime import datetime
from typing import Any, Optional


class DataSourceError(Exception):
    """Base exception for all data source errors."""
    
    def __init__(
        self,
        message: str,
        source_name: Optional[str] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.source_name = source_name
        self.original_error = original_error
        self.context = context or {}
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "source_name": self.source_name,
            "original_error": str(self.original_error) if self.original_error else None,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
        }
    
    def __str__(self) -> str:
        parts = [f"{self.__class__.__name__}: {self.message}"]
        if self.source_name:
            parts.append(f"[source={self.source_name}]")
        if self.original_error:
            parts.append(f"(caused by: {self.original_error})")
        return " ".join(parts)


class FetchError(DataSourceError):
    """Error during data fetching from provider API."""
    
    def __init__(
        self,
        message: str,
        source_name: Optional[str] = None,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        request_url: Optional[str] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, source_name, original_error, context)
        self.status_code = status_code
        self.response_body = response_body
        self.request_url = request_url
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "status_code": self.status_code,
            "response_body": self.response_body,
            "request_url": self.request_url,
        })
        return data
    
    def is_rate_limited(self) -> bool:
        """Check if error is due to rate limiting."""
        return self.status_code == 429
    
    def is_server_error(self) -> bool:
        """Check if error is server-side."""
        return self.status_code is not None and 500 <= self.status_code < 600
    
    def is_client_error(self) -> bool:
        """Check if error is client-side."""
        return self.status_code is not None and 400 <= self.status_code < 500


class NormalizationError(DataSourceError):
    """Error during data normalization."""
    
    def __init__(
        self,
        message: str,
        source_name: Optional[str] = None,
        raw_data: Optional[Any] = None,
        field_name: Optional[str] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, source_name, original_error, context)
        self.raw_data = raw_data
        self.field_name = field_name
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "raw_data": str(self.raw_data)[:500] if self.raw_data else None,  # Truncate
            "field_name": self.field_name,
        })
        return data


class HealthCheckError(DataSourceError):
    """Error during health check."""
    
    def __init__(
        self,
        message: str,
        source_name: Optional[str] = None,
        latency_ms: Optional[float] = None,
        timeout: bool = False,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, source_name, original_error, context)
        self.latency_ms = latency_ms
        self.timeout = timeout
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "latency_ms": self.latency_ms,
            "timeout": self.timeout,
        })
        return data


class RateLimitError(FetchError):
    """Rate limit exceeded error."""
    
    def __init__(
        self,
        message: str,
        source_name: Optional[str] = None,
        retry_after_seconds: Optional[int] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message,
            source_name,
            status_code=429,
            original_error=original_error,
            context=context,
        )
        self.retry_after_seconds = retry_after_seconds
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data["retry_after_seconds"] = self.retry_after_seconds
        return data


class SourceUnavailableError(DataSourceError):
    """Data source is completely unavailable."""
    
    def __init__(
        self,
        message: str,
        source_name: Optional[str] = None,
        consecutive_failures: int = 0,
        last_successful: Optional[datetime] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, source_name, original_error, context)
        self.consecutive_failures = consecutive_failures
        self.last_successful = last_successful
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "consecutive_failures": self.consecutive_failures,
            "last_successful": self.last_successful.isoformat() if self.last_successful else None,
        })
        return data


class NoAvailableSourceError(DataSourceError):
    """No data source is available to fulfill the request."""
    
    def __init__(
        self,
        message: str,
        attempted_sources: Optional[list[str]] = None,
        symbol: Optional[str] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, None, original_error, context)
        self.attempted_sources = attempted_sources or []
        self.symbol = symbol
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "attempted_sources": self.attempted_sources,
            "symbol": self.symbol,
        })
        return data


class ConfigurationError(DataSourceError):
    """Configuration error for data source."""
    
    def __init__(
        self,
        message: str,
        source_name: Optional[str] = None,
        config_key: Optional[str] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, source_name, original_error, context)
        self.config_key = config_key
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data["config_key"] = self.config_key
        return data
