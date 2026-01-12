"""
Smart Money Exceptions - Error hierarchy for graceful degradation.

These exceptions are for internal use only.
Smart money tracking NEVER raises to caller - degrades gracefully.
"""

from datetime import datetime
from typing import Any, Optional

from .models import Chain


class SmartMoneyError(Exception):
    """Base exception for all smart money module errors."""
    
    def __init__(
        self,
        message: str,
        chain: Optional[Chain] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.chain = chain
        self.details = details or {}
        self.timestamp = datetime.utcnow()
        super().__init__(self.message)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "chain": self.chain.value if self.chain else None,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class RateLimitError(SmartMoneyError):
    """Rate limit exceeded for blockchain API."""
    
    def __init__(
        self,
        message: str,
        chain: Optional[Chain] = None,
        retry_after_seconds: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, chain, details)
        self.retry_after_seconds = retry_after_seconds


class RPCError(SmartMoneyError):
    """RPC node connection or response error."""
    
    def __init__(
        self,
        message: str,
        chain: Optional[Chain] = None,
        rpc_url: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, chain, details)
        self.rpc_url = rpc_url
        self.status_code = status_code


class APIError(SmartMoneyError):
    """External API (Etherscan, etc.) error."""
    
    def __init__(
        self,
        message: str,
        chain: Optional[Chain] = None,
        api_name: str = "",
        status_code: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, chain, details)
        self.api_name = api_name
        self.status_code = status_code


class WalletNotFoundError(SmartMoneyError):
    """Wallet not found in registry."""
    
    def __init__(
        self,
        address: str,
        chain: Optional[Chain] = None,
    ) -> None:
        super().__init__(
            f"Wallet not found: {address}",
            chain,
        )
        self.address = address


class ParseError(SmartMoneyError):
    """Failed to parse blockchain data."""
    
    def __init__(
        self,
        message: str,
        chain: Optional[Chain] = None,
        raw_data: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, chain, details)
        self.raw_data = raw_data[:500] if raw_data else None


class StorageError(SmartMoneyError):
    """Database/storage operation error."""
    pass


class ConfigurationError(SmartMoneyError):
    """Invalid configuration."""
    pass


class TrackerUnavailableError(SmartMoneyError):
    """Tracker for a chain is unavailable."""
    
    def __init__(
        self,
        chain: Chain,
        reason: str = "Unknown",
    ) -> None:
        super().__init__(
            f"Tracker unavailable for {chain.value}: {reason}",
            chain,
        )
        self.reason = reason
