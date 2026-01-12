"""
On-chain Adapter Exceptions - Custom exception hierarchy.

All exceptions are designed to be non-blocking and fail-safe.
"""

from datetime import datetime
from typing import Any, Optional


class OnchainAdapterError(Exception):
    """Base exception for all on-chain adapter errors."""
    
    def __init__(
        self,
        message: str,
        adapter_name: Optional[str] = None,
        chain: Optional[str] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.adapter_name = adapter_name
        self.chain = chain
        self.original_error = original_error
        self.context = context or {}
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "adapter_name": self.adapter_name,
            "chain": self.chain,
            "original_error": str(self.original_error) if self.original_error else None,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
        }
    
    def __str__(self) -> str:
        parts = [f"{self.__class__.__name__}: {self.message}"]
        if self.adapter_name:
            parts.append(f"[adapter={self.adapter_name}]")
        if self.chain:
            parts.append(f"[chain={self.chain}]")
        if self.original_error:
            parts.append(f"(caused by: {self.original_error})")
        return " ".join(parts)


class FetchError(OnchainAdapterError):
    """Error during data fetching from provider API."""
    
    def __init__(
        self,
        message: str,
        adapter_name: Optional[str] = None,
        chain: Optional[str] = None,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        request_url: Optional[str] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, adapter_name, chain, original_error, context)
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


class RateLimitError(OnchainAdapterError):
    """Rate limit exceeded error."""
    
    def __init__(
        self,
        message: str,
        adapter_name: Optional[str] = None,
        chain: Optional[str] = None,
        retry_after_seconds: Optional[int] = None,
        limit_type: str = "request",  # request, daily, etc.
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, adapter_name, chain, original_error, context)
        self.retry_after_seconds = retry_after_seconds
        self.limit_type = limit_type
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "retry_after_seconds": self.retry_after_seconds,
            "limit_type": self.limit_type,
        })
        return data


class CacheError(OnchainAdapterError):
    """Error with cache operations."""
    
    def __init__(
        self,
        message: str,
        adapter_name: Optional[str] = None,
        cache_key: Optional[str] = None,
        operation: str = "read",  # read, write, invalidate
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, adapter_name, None, original_error, context)
        self.cache_key = cache_key
        self.operation = operation
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "cache_key": self.cache_key,
            "operation": self.operation,
        })
        return data


class NormalizationError(OnchainAdapterError):
    """Error during data normalization."""
    
    def __init__(
        self,
        message: str,
        adapter_name: Optional[str] = None,
        chain: Optional[str] = None,
        raw_data: Optional[Any] = None,
        field_name: Optional[str] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, adapter_name, chain, original_error, context)
        self.raw_data = raw_data
        self.field_name = field_name
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "raw_data": str(self.raw_data)[:500] if self.raw_data else None,
            "field_name": self.field_name,
        })
        return data


class ChainNotSupportedError(OnchainAdapterError):
    """Requested chain is not supported by the adapter."""
    
    def __init__(
        self,
        message: str,
        adapter_name: Optional[str] = None,
        chain: Optional[str] = None,
        supported_chains: Optional[list[str]] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, adapter_name, chain, original_error, context)
        self.supported_chains = supported_chains or []
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data["supported_chains"] = self.supported_chains
        return data


class NoAvailableAdapterError(OnchainAdapterError):
    """No adapter is available to fulfill the request."""
    
    def __init__(
        self,
        message: str,
        attempted_adapters: Optional[list[str]] = None,
        chain: Optional[str] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, None, chain, original_error, context)
        self.attempted_adapters = attempted_adapters or []
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data["attempted_adapters"] = self.attempted_adapters
        return data


class ConfigurationError(OnchainAdapterError):
    """Configuration error for adapter."""
    
    def __init__(
        self,
        message: str,
        adapter_name: Optional[str] = None,
        config_key: Optional[str] = None,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, adapter_name, None, original_error, context)
        self.config_key = config_key
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data["config_key"] = self.config_key
        return data
