"""
Core Module - Exceptions.

============================================================
RESPONSIBILITY
============================================================
Defines all custom exceptions for the trading system.

- Provides clear exception hierarchy
- Enables specific error handling
- Supports error categorization for alerting
- Includes context for debugging

============================================================
EXCEPTION HIERARCHY
============================================================
TradingException (base)
├── ConfigurationError
├── DataError
│   ├── DataIngestionError
│   ├── DataValidationError
│   └── DataStalenessError
├── RiskError
│   ├── RiskLimitExceeded
│   ├── VetoError
│   └── DrawdownLimitError
├── ExecutionError
│   ├── OrderError
│   ├── ExchangeError
│   └── InsufficientBalanceError
├── SystemError
│   ├── StateTransitionError
│   ├── DatabaseError
│   └── CommunicationError
└── EmergencyStopError

============================================================
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# ============================================================
# SEVERITY LEVELS
# ============================================================

class Severity(Enum):
    """Exception severity levels for alerting."""
    
    LOW = "low"
    """Minor issue, informational."""
    
    MEDIUM = "medium"
    """Moderate issue, requires attention."""
    
    HIGH = "high"
    """Serious issue, may impact operations."""
    
    CRITICAL = "critical"
    """Critical issue, requires immediate action."""


# ============================================================
# ERROR CLASSIFICATION
# ============================================================

class ErrorClassification(Enum):
    """Classification of error recoverability."""
    
    RECOVERABLE = "recoverable"
    """Error can be recovered from automatically."""
    
    TRANSIENT = "transient"
    """Temporary error, retry may succeed."""
    
    NON_RECOVERABLE = "non_recoverable"
    """Permanent error, requires intervention."""


# ============================================================
# BASE EXCEPTION
# ============================================================

class TradingException(Exception):
    """
    Base exception for all trading system errors.
    
    All exceptions carry:
    - severity: for alerting
    - context: for debugging
    - recoverable: for error handling decisions
    - timestamp: when the error occurred
    """
    
    default_severity: Severity = Severity.MEDIUM
    default_recoverable: bool = True
    default_classification: ErrorClassification = ErrorClassification.RECOVERABLE
    
    def __init__(
        self,
        message: str,
        severity: Optional[Severity] = None,
        context: Optional[Dict[str, Any]] = None,
        recoverable: Optional[bool] = None,
        classification: Optional[ErrorClassification] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        
        self.message = message
        self.severity = severity or self.default_severity
        self.context = context or {}
        self.recoverable = recoverable if recoverable is not None else self.default_recoverable
        self.classification = classification or self.default_classification
        self.cause = cause
        self.timestamp = datetime.now(timezone.utc)
        
        if cause:
            self.context["cause_type"] = type(cause).__name__
            self.context["cause_message"] = str(cause)
    
    @property
    def is_recoverable(self) -> bool:
        """Check if error is recoverable."""
        return self.classification in (
            ErrorClassification.RECOVERABLE,
            ErrorClassification.TRANSIENT,
        )
    
    @property
    def requires_immediate_action(self) -> bool:
        """Check if error requires immediate action."""
        return self.severity in (Severity.HIGH, Severity.CRITICAL)
    
    @property
    def should_halt_system(self) -> bool:
        """Check if error should halt the system."""
        return (
            self.severity == Severity.CRITICAL and
            self.classification == ErrorClassification.NON_RECOVERABLE
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize exception for logging/storage."""
        return {
            "type": type(self).__name__,
            "message": self.message,
            "severity": self.severity.value,
            "recoverable": self.recoverable,
            "classification": self.classification.value,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "cause": str(self.cause) if self.cause else None,
        }
    
    def to_log_format(self) -> str:
        """Format exception for structured logging."""
        ctx_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
        return (
            f"[{self.severity.value.upper()}] {type(self).__name__}: {self.message}"
            f" | recoverable={self.recoverable}"
            f" | {ctx_str}" if ctx_str else ""
        )


# ============================================================
# CONFIGURATION ERRORS
# ============================================================

class ConfigurationError(TradingException):
    """Error in configuration."""
    
    default_severity = Severity.HIGH
    default_recoverable = False
    default_classification = ErrorClassification.NON_RECOVERABLE
    
    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        expected_type: Optional[str] = None,
        actual_value: Optional[Any] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if config_key:
            context["config_key"] = config_key
        if expected_type:
            context["expected_type"] = expected_type
        if actual_value is not None:
            context["actual_value"] = str(actual_value)[:100]
        
        super().__init__(message, context=context, **kwargs)


class MissingConfigError(ConfigurationError):
    """Required configuration is missing."""
    
    def __init__(self, key: str, source: str = "config"):
        super().__init__(
            message=f"Missing required configuration: {key}",
            config_key=key,
            context={"source": source},
        )


class InvalidConfigError(ConfigurationError):
    """Configuration value is invalid."""
    
    def __init__(self, key: str, value: Any, reason: str):
        super().__init__(
            message=f"Invalid configuration for {key}: {reason}",
            config_key=key,
            actual_value=value,
            context={"reason": reason},
        )


# ============================================================
# DATA ERRORS
# ============================================================

class DataError(TradingException):
    """Base class for data-related errors."""
    
    default_severity = Severity.MEDIUM
    default_recoverable = True
    default_classification = ErrorClassification.TRANSIENT


class DataIngestionError(DataError):
    """Failed to ingest data."""
    
    def __init__(
        self,
        message: str,
        source: Optional[str] = None,
        endpoint: Optional[str] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if source:
            context["source"] = source
        if endpoint:
            context["endpoint"] = endpoint
        
        super().__init__(message, context=context, **kwargs)


class DataValidationError(DataError):
    """Data failed validation."""
    
    default_recoverable = False
    default_classification = ErrorClassification.RECOVERABLE
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        expected: Optional[Any] = None,
        actual: Optional[Any] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if field:
            context["field"] = field
        if expected is not None:
            context["expected"] = str(expected)
        if actual is not None:
            context["actual"] = str(actual)[:100]
        
        super().__init__(message, context=context, **kwargs)


class DataStalenessError(DataError):
    """Data is too old."""
    
    default_severity = Severity.HIGH
    
    def __init__(
        self,
        message: str,
        data_type: Optional[str] = None,
        age_seconds: Optional[float] = None,
        max_age_seconds: Optional[float] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if data_type:
            context["data_type"] = data_type
        if age_seconds is not None:
            context["age_seconds"] = age_seconds
        if max_age_seconds is not None:
            context["max_age_seconds"] = max_age_seconds
        
        super().__init__(message, context=context, **kwargs)


# ============================================================
# RISK ERRORS
# ============================================================

class RiskError(TradingException):
    """Base class for risk-related errors."""
    
    default_severity = Severity.HIGH
    default_recoverable = False
    default_classification = ErrorClassification.NON_RECOVERABLE


class RiskLimitExceeded(RiskError):
    """Risk threshold breached."""
    
    def __init__(
        self,
        message: str,
        limit_type: Optional[str] = None,
        current_value: Optional[float] = None,
        limit_value: Optional[float] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if limit_type:
            context["limit_type"] = limit_type
        if current_value is not None:
            context["current_value"] = current_value
        if limit_value is not None:
            context["limit_value"] = limit_value
        
        super().__init__(message, context=context, **kwargs)


class VetoError(RiskError):
    """Trade vetoed by risk rules."""
    
    def __init__(
        self,
        message: str,
        veto_source: Optional[str] = None,
        veto_reason: Optional[str] = None,
        trade_id: Optional[str] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if veto_source:
            context["veto_source"] = veto_source
        if veto_reason:
            context["veto_reason"] = veto_reason
        if trade_id:
            context["trade_id"] = trade_id
        
        super().__init__(message, context=context, **kwargs)


class DrawdownLimitError(RiskError):
    """Drawdown limit hit."""
    
    default_severity = Severity.CRITICAL
    
    def __init__(
        self,
        message: str,
        drawdown_type: Optional[str] = None,
        current_drawdown: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if drawdown_type:
            context["drawdown_type"] = drawdown_type
        if current_drawdown is not None:
            context["current_drawdown"] = current_drawdown
        if max_drawdown is not None:
            context["max_drawdown"] = max_drawdown
        
        super().__init__(message, context=context, **kwargs)


# ============================================================
# EXECUTION ERRORS
# ============================================================

class ExecutionError(TradingException):
    """Base class for execution-related errors."""
    
    default_severity = Severity.HIGH
    default_recoverable = True
    default_classification = ErrorClassification.TRANSIENT


class OrderError(ExecutionError):
    """Order placement failed."""
    
    def __init__(
        self,
        message: str,
        order_id: Optional[str] = None,
        symbol: Optional[str] = None,
        order_type: Optional[str] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if order_id:
            context["order_id"] = order_id
        if symbol:
            context["symbol"] = symbol
        if order_type:
            context["order_type"] = order_type
        
        super().__init__(message, context=context, **kwargs)


class ExchangeError(ExecutionError):
    """Exchange API error."""
    
    def __init__(
        self,
        message: str,
        exchange: Optional[str] = None,
        error_code: Optional[str] = None,
        endpoint: Optional[str] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if exchange:
            context["exchange"] = exchange
        if error_code:
            context["error_code"] = error_code
        if endpoint:
            context["endpoint"] = endpoint
        
        super().__init__(message, context=context, **kwargs)


class InsufficientBalanceError(ExecutionError):
    """Not enough balance for operation."""
    
    default_recoverable = False
    default_classification = ErrorClassification.NON_RECOVERABLE
    
    def __init__(
        self,
        message: str,
        asset: Optional[str] = None,
        required: Optional[float] = None,
        available: Optional[float] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if asset:
            context["asset"] = asset
        if required is not None:
            context["required"] = required
        if available is not None:
            context["available"] = available
        
        super().__init__(message, context=context, **kwargs)


# ============================================================
# SYSTEM ERRORS
# ============================================================

class SystemError(TradingException):
    """Base class for system-related errors."""
    
    default_severity = Severity.HIGH
    default_recoverable = True
    default_classification = ErrorClassification.TRANSIENT


class StateTransitionError(SystemError):
    """Invalid state transition."""
    
    default_recoverable = False
    
    def __init__(
        self,
        message: str,
        from_state: Optional[str] = None,
        to_state: Optional[str] = None,
        reason: Optional[str] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if from_state:
            context["from_state"] = from_state
        if to_state:
            context["to_state"] = to_state
        if reason:
            context["reason"] = reason
        
        super().__init__(message, context=context, **kwargs)


class DatabaseError(SystemError):
    """Database operation failed."""
    
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        table: Optional[str] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if operation:
            context["operation"] = operation
        if table:
            context["table"] = table
        
        super().__init__(message, context=context, **kwargs)


class CommunicationError(SystemError):
    """External communication failed."""
    
    def __init__(
        self,
        message: str,
        service: Optional[str] = None,
        endpoint: Optional[str] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if service:
            context["service"] = service
        if endpoint:
            context["endpoint"] = endpoint
        
        super().__init__(message, context=context, **kwargs)


# ============================================================
# EMERGENCY STOP
# ============================================================

class EmergencyStopError(TradingException):
    """
    Emergency stop triggered.
    Always CRITICAL, always non-recoverable, triggers shutdown.
    """
    
    default_severity = Severity.CRITICAL
    default_recoverable = False
    default_classification = ErrorClassification.NON_RECOVERABLE
    
    def __init__(
        self,
        message: str,
        trigger: Optional[str] = None,
        operator: Optional[str] = None,
        **kwargs,
    ):
        kwargs["severity"] = Severity.CRITICAL
        kwargs["recoverable"] = False
        kwargs["classification"] = ErrorClassification.NON_RECOVERABLE
        
        context = kwargs.pop("context", {})
        
        if trigger:
            context["trigger"] = trigger
        if operator:
            context["operator"] = operator
        
        context["emergency_stop"] = True
        
        super().__init__(message, context=context, **kwargs)
    
    @property
    def should_halt_system(self) -> bool:
        """Emergency stop always halts system."""
        return True


# ============================================================
# ORCHESTRATION ERRORS
# ============================================================

class OrchestrationError(TradingException):
    """Base class for orchestration-related errors."""
    
    default_severity = Severity.HIGH
    default_recoverable = False
    default_classification = ErrorClassification.NON_RECOVERABLE


class StartupError(OrchestrationError):
    """System startup failed."""
    
    def __init__(
        self,
        message: str,
        stage: Optional[str] = None,
        module: Optional[str] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if stage:
            context["stage"] = stage
        if module:
            context["module"] = module
        
        super().__init__(message, context=context, **kwargs)


class ShutdownError(OrchestrationError):
    """System shutdown failed."""
    
    default_severity = Severity.MEDIUM
    default_recoverable = True
    
    def __init__(
        self,
        message: str,
        module: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if module:
            context["module"] = module
        if timeout_seconds is not None:
            context["timeout_seconds"] = timeout_seconds
        
        super().__init__(message, context=context, **kwargs)


class ModuleError(OrchestrationError):
    """Module execution error."""
    
    default_recoverable = True
    default_classification = ErrorClassification.TRANSIENT
    
    def __init__(
        self,
        message: str,
        module_name: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if module_name:
            context["module_name"] = module_name
        if operation:
            context["operation"] = operation
        
        super().__init__(message, context=context, **kwargs)


class PipelineError(OrchestrationError):
    """Execution pipeline error."""
    
    def __init__(
        self,
        message: str,
        stage: Optional[str] = None,
        pipeline: Optional[str] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        
        if stage:
            context["stage"] = stage
        if pipeline:
            context["pipeline"] = pipeline
        
        super().__init__(message, context=context, **kwargs)


# ============================================================
# EXCEPTION UTILITIES
# ============================================================

def classify_exception(exc: Exception) -> ErrorClassification:
    """Classify an exception for error handling."""
    if isinstance(exc, TradingException):
        return exc.classification
    
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return ErrorClassification.TRANSIENT
    
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return ErrorClassification.RECOVERABLE
    
    if isinstance(exc, (SystemExit, KeyboardInterrupt, MemoryError)):
        return ErrorClassification.NON_RECOVERABLE
    
    return ErrorClassification.RECOVERABLE


def wrap_exception(
    exc: Exception,
    wrapper_class: type = TradingException,
    message: Optional[str] = None,
    **kwargs,
) -> TradingException:
    """Wrap a standard exception in a TradingException."""
    msg = message or f"{type(exc).__name__}: {exc}"
    return wrapper_class(message=msg, cause=exc, **kwargs)


__all__ = [
    "Severity",
    "ErrorClassification",
    "TradingException",
    "ConfigurationError",
    "MissingConfigError",
    "InvalidConfigError",
    "DataError",
    "DataIngestionError",
    "DataValidationError",
    "DataStalenessError",
    "RiskError",
    "RiskLimitExceeded",
    "VetoError",
    "DrawdownLimitError",
    "ExecutionError",
    "OrderError",
    "ExchangeError",
    "InsufficientBalanceError",
    "SystemError",
    "StateTransitionError",
    "DatabaseError",
    "CommunicationError",
    "EmergencyStopError",
    "OrchestrationError",
    "StartupError",
    "ShutdownError",
    "ModuleError",
    "PipelineError",
    "classify_exception",
    "wrap_exception",
]
