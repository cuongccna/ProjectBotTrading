"""
Smart Money Confidence - Exceptions.

============================================================
CUSTOM EXCEPTIONS
============================================================

All exceptions inherit from SmartMoneyConfidenceError.

============================================================
"""


class SmartMoneyConfidenceError(Exception):
    """Base exception for Smart Money Confidence module."""
    pass


class InsufficientDataError(SmartMoneyConfidenceError):
    """
    Raised when there is not enough data to calculate confidence.
    
    This is NOT an error condition - it means we should return a neutral signal.
    """
    def __init__(self, message: str, available: int = 0, required: int = 0):
        self.available = available
        self.required = required
        super().__init__(message)


class InvalidActivityError(SmartMoneyConfidenceError):
    """Raised when an activity record is invalid."""
    pass


class InvalidWalletError(SmartMoneyConfidenceError):
    """Raised when a wallet profile is invalid."""
    pass


class ConfigurationError(SmartMoneyConfidenceError):
    """Raised when configuration is invalid."""
    pass


class WalletNotFoundError(SmartMoneyConfidenceError):
    """Raised when a wallet profile is not found."""
    def __init__(self, address: str):
        self.address = address
        super().__init__(f"Wallet not found: {address}")


class CalculationError(SmartMoneyConfidenceError):
    """Raised when confidence calculation fails."""
    pass


class NoiseFilterError(SmartMoneyConfidenceError):
    """Raised when noise filtering fails."""
    pass


class ClusterAnalysisError(SmartMoneyConfidenceError):
    """Raised when cluster analysis fails."""
    pass


class DataSourceError(SmartMoneyConfidenceError):
    """Raised when data source operations fail."""
    pass


class CacheError(SmartMoneyConfidenceError):
    """Raised when cache operations fail."""
    pass
