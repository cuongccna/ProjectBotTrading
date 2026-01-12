"""
Execution Engine Package.

============================================================
PURPOSE
============================================================
Handles all trade execution for approved decisions.

CRITICAL PRINCIPLE:
    "Execution Engine is REACTIVE, not decision-making."
    "It executes only after Trade Guard Absolute returns EXECUTE."

AUTHORITY BOUNDARIES:
    CAN:
        - Submit orders to exchange
        - Cancel orders
        - Query order status
        - Retry on transient failures
        
    MUST NOT:
        - Override Trade Guard decisions
        - Resize trades
        - Generate trade ideas
        - Bypass System Risk Controller HALT

============================================================
MODULES
============================================================
- types: Order types, states, intents, results
- config: Execution configuration
- errors: Error taxonomy and codes
- state_machine: Order lifecycle management
- validation: Pre-execution validation
- adapters: Exchange adapters (Binance, Mock)
- order_manager: Order submission and tracking
- execution_service: Main execution orchestrator
- execution_validator: Post-execution validation
- reconciliation: State reconciliation with exchange
- alerting: Telegram alerts
- models: ORM models for persistence
- repository: Database operations

============================================================
"""

# ============================================================
# TYPES
# ============================================================
from .types import (
    # Enums
    OrderSide,
    OrderType,
    TimeInForce,
    PositionSide,
    OrderState,
    ExecutionResultCode,
    # Dataclasses
    OrderIntent,
    ExecutionResult,
    OrderRecord,
    AccountState,
    AccountBalance,
    PositionInfo,
    SymbolRules,
    # Exceptions
    ExecutionEngineError,
    ValidationError,
    SubmissionError,
    ReconciliationError,
    ExchangeError,
    HaltStateError,
    ApprovalError,
)

# ============================================================
# CONFIGURATION
# ============================================================
from .config import (
    RetryConfig,
    RateLimitConfig,
    TimeoutConfig,
    ValidationConfig,
    ReconciliationConfig,
    IdempotencyConfig,
    PartialFillConfig,
    ExchangeConfig,
    ExecutionEngineConfig,
)

# ============================================================
# ERRORS
# ============================================================
from .errors import (
    ErrorCategory,
    ErrorSeverity,
    ErrorCodeInfo,
    ERROR_CODES,
    get_error_info,
    map_binance_error,
    is_retryable,
    should_escalate,
    RETRYABLE_ERROR_CODES,
    ESCALATION_ERROR_CODES,
    CRITICAL_ERROR_CODES,
)

# ============================================================
# STATE MACHINE
# ============================================================
from .state_machine import (
    VALID_TRANSITIONS,
    StateTransitionEvent,
    TransitionGuard,
    OrderStateMachine,
)

# ============================================================
# VALIDATION
# ============================================================
from .validation import (
    ValidationResult,
    PreExecutionValidator,
)

# ============================================================
# ADAPTERS
# ============================================================
from .adapters import (
    ExchangeAdapter,
    SubmitOrderRequest,
    SubmitOrderResponse,
    QueryOrderRequest,
    QueryOrderResponse,
    CancelOrderRequest,
    CancelOrderResponse,
    FillInfo,
    BinanceAdapter,
    MockExchangeAdapter,
    map_exchange_status_to_order_state,
)

# ============================================================
# CORE COMPONENTS
# ============================================================
from .order_manager import OrderManager
from .execution_service import ExecutionService, ExecutionEngine
from .execution_validator import (
    ValidationCheckType,
    ValidationCheck,
    PostExecutionValidationResult,
    PostExecutionValidatorConfig,
    PostExecutionValidator,
)

# ============================================================
# RECONCILIATION
# ============================================================
from .reconciliation import (
    MismatchType,
    MismatchSeverity,
    ReconciliationMismatch,
    ReconciliationResult,
    ReconciliationEngine,
)

# ============================================================
# ALERTING
# ============================================================
from .alerting import (
    AlertSeverity,
    AlertType,
    Alert,
    ExecutionAlertingConfig,
    TelegramAlerter,
    create_execution_failed_alert,
    create_execution_rejected_alert,
    create_slippage_alert,
    create_reconciliation_alert,
    create_system_error_alert,
)

# ============================================================
# MODELS
# ============================================================
from .models import (
    ExecutionOrderModel,
    ExecutionFillModel,
    ExecutionEventModel,
    ExecutionAlertModel,
    ReconciliationLogModel,
)

# ============================================================
# REPOSITORY
# ============================================================
from .repository import ExecutionRepository


# ============================================================
# VERSION
# ============================================================
__version__ = "1.0.0"


# ============================================================
# ALL EXPORTS
# ============================================================
__all__ = [
    # Types
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "PositionSide",
    "OrderState",
    "ExecutionResultCode",
    "OrderIntent",
    "ExecutionResult",
    "OrderRecord",
    "AccountState",
    "AccountBalance",
    "PositionInfo",
    "SymbolRules",
    "ExecutionEngineError",
    "ValidationError",
    "SubmissionError",
    "ReconciliationError",
    "ExchangeError",
    "HaltStateError",
    "ApprovalError",
    # Config
    "RetryConfig",
    "RateLimitConfig",
    "TimeoutConfig",
    "ValidationConfig",
    "ReconciliationConfig",
    "IdempotencyConfig",
    "PartialFillConfig",
    "ExchangeConfig",
    "ExecutionEngineConfig",
    # Errors
    "ErrorCategory",
    "ErrorSeverity",
    "ErrorCodeInfo",
    "ERROR_CODES",
    "get_error_info",
    "map_binance_error",
    "is_retryable",
    "should_escalate",
    "RETRYABLE_ERROR_CODES",
    "ESCALATION_ERROR_CODES",
    "CRITICAL_ERROR_CODES",
    # State Machine
    "VALID_TRANSITIONS",
    "StateTransitionEvent",
    "TransitionGuard",
    "OrderStateMachine",
    # Validation
    "ValidationResult",
    "PreExecutionValidator",
    # Adapters
    "ExchangeAdapter",
    "SubmitOrderRequest",
    "SubmitOrderResponse",
    "QueryOrderRequest",
    "QueryOrderResponse",
    "CancelOrderRequest",
    "CancelOrderResponse",
    "FillInfo",
    "BinanceAdapter",
    "MockExchangeAdapter",
    "map_exchange_status_to_order_state",
    # Core
    "OrderManager",
    "ExecutionService",
    "ExecutionEngine",
    "ValidationCheckType",
    "ValidationCheck",
    "PostExecutionValidationResult",
    "PostExecutionValidatorConfig",
    "PostExecutionValidator",
    # Reconciliation
    "MismatchType",
    "MismatchSeverity",
    "ReconciliationMismatch",
    "ReconciliationResult",
    "ReconciliationEngine",
    # Alerting
    "AlertSeverity",
    "AlertType",
    "Alert",
    "ExecutionAlertingConfig",
    "TelegramAlerter",
    "create_execution_failed_alert",
    "create_execution_rejected_alert",
    "create_slippage_alert",
    "create_reconciliation_alert",
    "create_system_error_alert",
    # Models
    "ExecutionOrderModel",
    "ExecutionFillModel",
    "ExecutionEventModel",
    "ExecutionAlertModel",
    "ReconciliationLogModel",
    # Repository
    "ExecutionRepository",
]
