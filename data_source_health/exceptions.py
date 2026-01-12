"""
Data Source Health - Exceptions.

============================================================
CUSTOM EXCEPTIONS
============================================================

All exceptions for health scoring module:
- HealthScoringError: Base exception
- SourceNotFoundError: Source not registered
- MetricRecordError: Failed to record metric
- EvaluationError: Failed to evaluate health
- ConfigurationError: Invalid configuration

============================================================
FAILURE SAFETY
============================================================

Per requirements:
- This module must NEVER crash the system
- If scoring fails, assume worst-case (CRITICAL)
- All exceptions must be caught and handled gracefully

============================================================
"""

from typing import Any, Dict, Optional


class HealthScoringError(Exception):
    """
    Base exception for health scoring errors.
    
    All health scoring exceptions inherit from this class.
    """
    
    def __init__(
        self,
        message: str,
        source_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize exception.
        
        Args:
            message: Error message
            source_name: Name of the affected source
            details: Additional error details
        """
        self.message = message
        self.source_name = source_name
        self.details = details or {}
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        """Format the error message."""
        if self.source_name:
            return f"[{self.source_name}] {self.message}"
        return self.message
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "source_name": self.source_name,
            "details": self.details,
        }


class SourceNotFoundError(HealthScoringError):
    """
    Raised when a data source is not registered.
    
    This is a recoverable error - the source should be registered.
    """
    
    def __init__(
        self,
        source_name: str,
        available_sources: Optional[list] = None,
    ) -> None:
        """
        Initialize exception.
        
        Args:
            source_name: Name of the missing source
            available_sources: List of registered sources
        """
        message = f"Source not found: {source_name}"
        details = {}
        if available_sources:
            details["available_sources"] = available_sources
            message += f". Available: {', '.join(available_sources)}"
        
        super().__init__(
            message=message,
            source_name=source_name,
            details=details,
        )


class MetricRecordError(HealthScoringError):
    """
    Raised when a metric cannot be recorded.
    
    This should not crash the system - metrics are best-effort.
    """
    
    def __init__(
        self,
        source_name: str,
        metric_name: str,
        reason: str,
        value: Any = None,
    ) -> None:
        """
        Initialize exception.
        
        Args:
            source_name: Name of the source
            metric_name: Name of the metric
            reason: Why recording failed
            value: The value that failed to record
        """
        message = f"Failed to record metric '{metric_name}': {reason}"
        details = {
            "metric_name": metric_name,
            "reason": reason,
        }
        if value is not None:
            details["value"] = str(value)
        
        super().__init__(
            message=message,
            source_name=source_name,
            details=details,
        )


class EvaluationError(HealthScoringError):
    """
    Raised when health evaluation fails.
    
    Per requirements: If scoring fails, assume worst-case (CRITICAL).
    """
    
    def __init__(
        self,
        source_name: str,
        dimension: Optional[str] = None,
        reason: str = "Unknown error",
        original_exception: Optional[Exception] = None,
    ) -> None:
        """
        Initialize exception.
        
        Args:
            source_name: Name of the source
            dimension: Which dimension failed (if applicable)
            reason: Why evaluation failed
            original_exception: The underlying exception
        """
        if dimension:
            message = f"Failed to evaluate {dimension}: {reason}"
        else:
            message = f"Evaluation failed: {reason}"
        
        details = {
            "reason": reason,
        }
        if dimension:
            details["dimension"] = dimension
        if original_exception:
            details["original_exception"] = str(original_exception)
            details["exception_type"] = type(original_exception).__name__
        
        super().__init__(
            message=message,
            source_name=source_name,
            details=details,
        )
        
        self.dimension = dimension
        self.original_exception = original_exception


class ConfigurationError(HealthScoringError):
    """
    Raised when configuration is invalid.
    
    Should be caught at startup and fixed before trading.
    """
    
    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        expected_value: Optional[str] = None,
        actual_value: Optional[str] = None,
    ) -> None:
        """
        Initialize exception.
        
        Args:
            message: Error message
            config_key: Which config key is invalid
            expected_value: What was expected
            actual_value: What was provided
        """
        details = {}
        if config_key:
            details["config_key"] = config_key
        if expected_value:
            details["expected"] = expected_value
        if actual_value:
            details["actual"] = actual_value
        
        super().__init__(
            message=message,
            details=details,
        )


class DimensionScoringError(HealthScoringError):
    """
    Raised when a specific dimension cannot be scored.
    
    Individual dimension failures should not prevent overall scoring.
    """
    
    def __init__(
        self,
        source_name: str,
        dimension: str,
        reason: str,
    ) -> None:
        """
        Initialize exception.
        
        Args:
            source_name: Name of the source
            dimension: Which dimension failed
            reason: Why scoring failed
        """
        message = f"Cannot score {dimension}: {reason}"
        details = {
            "dimension": dimension,
            "reason": reason,
        }
        
        super().__init__(
            message=message,
            source_name=source_name,
            details=details,
        )
        
        self.dimension = dimension


class InsufficientDataError(HealthScoringError):
    """
    Raised when there's not enough data to calculate a score.
    
    This is not necessarily an error - new sources need time to collect data.
    """
    
    def __init__(
        self,
        source_name: str,
        required_samples: int,
        actual_samples: int,
    ) -> None:
        """
        Initialize exception.
        
        Args:
            source_name: Name of the source
            required_samples: Minimum required samples
            actual_samples: Samples actually available
        """
        message = f"Insufficient data: need {required_samples}, have {actual_samples}"
        details = {
            "required_samples": required_samples,
            "actual_samples": actual_samples,
        }
        
        super().__init__(
            message=message,
            source_name=source_name,
            details=details,
        )


class AlertNotificationError(HealthScoringError):
    """
    Raised when an alert cannot be sent.
    
    Should not prevent health scoring from continuing.
    """
    
    def __init__(
        self,
        alert_type: str,
        reason: str,
        original_exception: Optional[Exception] = None,
    ) -> None:
        """
        Initialize exception.
        
        Args:
            alert_type: Type of alert that failed
            reason: Why sending failed
            original_exception: The underlying exception
        """
        message = f"Failed to send {alert_type} alert: {reason}"
        details = {
            "alert_type": alert_type,
            "reason": reason,
        }
        if original_exception:
            details["original_exception"] = str(original_exception)
        
        super().__init__(
            message=message,
            details=details,
        )
