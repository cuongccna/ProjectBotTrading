"""
Execution Engine - Adapters Package.

============================================================
PURPOSE
============================================================
Exchange adapter implementations.

AVAILABLE ADAPTERS:
- BinanceAdapter: Binance Futures API
- OKXAdapter: OKX Futures/Perpetual API
- BybitAdapter: Bybit V5 Unified API
- MockExchangeAdapter: For testing

UTILITIES:
- AdapterFactory: Factory for creating adapters
- AdapterPool: Manage multiple adapters
- AdapterMetrics: Metrics collection
- AdapterLogger: Secure logging

ERROR HANDLING:
- ExchangeError: Unified error representation
- ErrorCategory: Standardized error categories
- Error mapping functions per exchange

============================================================
"""

# Base types
from .base import (
    ExchangeAdapter,
    SubmitOrderRequest,
    SubmitOrderResponse,
    QueryOrderRequest,
    QueryOrderResponse,
    CancelOrderRequest,
    CancelOrderResponse,
    FillInfo,
    BalanceInfo,
    RateLimitStatus,
    map_exchange_status_to_order_state,
)

# Adapters
from .binance import BinanceAdapter
from .okx import OKXAdapter
from .bybit import BybitAdapter
from .mock import MockExchangeAdapter, MockConfig

# Factory
from .factory import (
    AdapterFactory,
    AdapterConfig,
    AdapterPool,
    ExchangeId,
    create_adapter,
    create_connected_adapter,
)

# Errors
from .errors import (
    ExchangeError,
    ExchangeException,
    ErrorCategory,
    RetryEligibility,
    map_exchange_error,
    map_binance_error,
    map_okx_error,
    map_bybit_error,
    create_network_error,
    create_timeout_error,
    create_rate_limit_error,
)

# Metrics
from .metrics import (
    AdapterMetrics,
    MetricsAggregator,
    MetricType,
    get_global_aggregator,
)

# Logging
from .logging_utils import (
    AdapterLogger,
    AuditLog,
    get_audit_log,
    mask_headers,
    mask_params,
    mask_value,
)

# WebSocket
from .websocket_base import (
    WebSocketBase,
    WebSocketConfig,
    ConnectionState,
    BinanceWebSocket,
    OKXWebSocket,
    BybitWebSocket,
)


__all__ = [
    # Base
    "ExchangeAdapter",
    "SubmitOrderRequest",
    "SubmitOrderResponse",
    "QueryOrderRequest",
    "QueryOrderResponse",
    "CancelOrderRequest",
    "CancelOrderResponse",
    "FillInfo",
    "BalanceInfo",
    "RateLimitStatus",
    "map_exchange_status_to_order_state",
    # Adapters
    "BinanceAdapter",
    "OKXAdapter",
    "BybitAdapter",
    "MockExchangeAdapter",
    "MockConfig",
    # Factory
    "AdapterFactory",
    "AdapterConfig",
    "AdapterPool",
    "ExchangeId",
    "create_adapter",
    "create_connected_adapter",
    # Errors
    "ExchangeError",
    "ExchangeException",
    "ErrorCategory",
    "RetryEligibility",
    "map_exchange_error",
    "map_binance_error",
    "map_okx_error",
    "map_bybit_error",
    "create_network_error",
    "create_timeout_error",
    "create_rate_limit_error",
    # Metrics
    "AdapterMetrics",
    "MetricsAggregator",
    "MetricType",
    "get_global_aggregator",
    # Logging
    "AdapterLogger",
    "AuditLog",
    "get_audit_log",
    "mask_headers",
    "mask_params",
    "mask_value",
    # WebSocket
    "WebSocketBase",
    "WebSocketConfig",
    "ConnectionState",
    "BinanceWebSocket",
    "OKXWebSocket",
    "BybitWebSocket",
]
