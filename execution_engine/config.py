"""
Execution Engine - Configuration.

============================================================
PURPOSE
============================================================
All configuration for the Execution Engine.

CRITICAL CONSTRAINTS:
- No blind retries
- No infinite loops
- Deterministic behavior

============================================================
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from decimal import Decimal


# ============================================================
# RETRY CONFIGURATION
# ============================================================

@dataclass
class RetryConfig:
    """
    Retry configuration for order submission.
    
    SAFETY: Limited retries with exponential backoff.
    """
    
    max_retries: int = 3
    """Maximum number of retry attempts."""
    
    initial_delay_seconds: float = 1.0
    """Initial delay before first retry."""
    
    max_delay_seconds: float = 30.0
    """Maximum delay between retries."""
    
    backoff_multiplier: float = 2.0
    """Exponential backoff multiplier."""
    
    retry_on_timeout: bool = True
    """Whether to retry on timeout errors."""
    
    retry_on_network_error: bool = True
    """Whether to retry on network errors."""
    
    retry_on_rate_limit: bool = True
    """Whether to retry on rate limit errors."""
    
    # SAFETY: Never retry on these
    never_retry_codes: List[str] = field(default_factory=lambda: [
        "INSUFFICIENT_BALANCE",
        "INVALID_ORDER",
        "POSITION_NOT_FOUND",
        "MARKET_CLOSED",
    ])
    """Error codes that should never trigger retry."""


# ============================================================
# RATE LIMIT CONFIGURATION
# ============================================================

@dataclass
class RateLimitConfig:
    """
    Rate limit configuration.
    
    Respects exchange rate limits to avoid bans.
    """
    
    orders_per_second: float = 5.0
    """Maximum orders per second."""
    
    orders_per_minute: int = 100
    """Maximum orders per minute."""
    
    weight_per_minute: int = 1200
    """Maximum API weight per minute (Binance-style)."""
    
    order_weight: int = 1
    """Weight per order request."""
    
    query_weight: int = 1
    """Weight per query request."""
    
    burst_limit: int = 10
    """Maximum burst of orders."""
    
    cooldown_seconds: float = 60.0
    """Cooldown period after hitting limit."""


# ============================================================
# TIMEOUT CONFIGURATION
# ============================================================

@dataclass
class TimeoutConfig:
    """
    Timeout configuration.
    """
    
    connection_timeout_seconds: float = 5.0
    """Connection timeout."""
    
    read_timeout_seconds: float = 30.0
    """Read timeout for responses."""
    
    order_submission_timeout_seconds: float = 10.0
    """Timeout for order submission."""
    
    order_cancel_timeout_seconds: float = 10.0
    """Timeout for order cancellation."""
    
    query_timeout_seconds: float = 5.0
    """Timeout for queries."""
    
    reconciliation_timeout_seconds: float = 30.0
    """Timeout for reconciliation operations."""


# ============================================================
# VALIDATION CONFIGURATION
# ============================================================

@dataclass
class ValidationConfig:
    """
    Pre-execution validation configuration.
    """
    
    # Approval validation
    max_approval_age_seconds: float = 60.0
    """Maximum age of approval token."""
    
    require_valid_approval: bool = True
    """Whether to require valid approval token."""
    
    # Balance validation
    min_balance_buffer_pct: Decimal = Decimal("5.0")
    """Minimum balance buffer percentage."""
    
    validate_balance: bool = True
    """Whether to validate balance before submission."""
    
    # Symbol validation
    validate_symbol_rules: bool = True
    """Whether to validate against symbol rules."""
    
    auto_round_quantity: bool = True
    """Whether to auto-round quantity to valid step."""
    
    auto_round_price: bool = True
    """Whether to auto-round price to valid tick."""
    
    # Notional validation
    min_notional_buffer_pct: Decimal = Decimal("10.0")
    """Buffer above minimum notional."""
    
    # HALT state
    block_on_halt: bool = True
    """Whether to block execution on HALT state."""


# ============================================================
# RECONCILIATION CONFIGURATION
# ============================================================

@dataclass
class ReconciliationConfig:
    """
    Reconciliation configuration.
    """
    
    enabled: bool = True
    """Whether reconciliation is enabled."""
    
    interval_seconds: float = 60.0
    """Reconciliation interval."""
    
    # Mismatch thresholds
    quantity_mismatch_tolerance_pct: Decimal = Decimal("0.1")
    """Tolerance for quantity mismatch (percentage)."""
    
    price_mismatch_tolerance_pct: Decimal = Decimal("0.1")
    """Tolerance for price mismatch (percentage)."""
    
    # Actions
    auto_sync_orders: bool = True
    """Whether to auto-sync order states."""
    
    freeze_on_critical_mismatch: bool = True
    """Whether to freeze on critical mismatch."""
    
    escalate_after_failures: int = 3
    """Escalate after this many reconciliation failures."""


# ============================================================
# IDEMPOTENCY CONFIGURATION
# ============================================================

@dataclass
class IdempotencyConfig:
    """
    Idempotency configuration.
    
    Prevents duplicate order submissions.
    """
    
    enabled: bool = True
    """Whether idempotency is enabled."""
    
    client_order_id_prefix: str = "BOT_"
    """Prefix for client order IDs."""
    
    dedup_window_seconds: float = 300.0
    """Window for deduplication check."""
    
    check_pending_orders: bool = True
    """Whether to check pending orders for duplicates."""


# ============================================================
# PARTIAL FILL CONFIGURATION
# ============================================================

@dataclass
class PartialFillConfig:
    """
    Partial fill handling configuration.
    """
    
    allow_partial_fills: bool = True
    """Whether to allow partial fills."""
    
    min_fill_ratio: Decimal = Decimal("0.1")
    """Minimum acceptable fill ratio."""
    
    cancel_on_stale_partial: bool = True
    """Whether to cancel stale partial fills."""
    
    stale_partial_seconds: float = 300.0
    """Time after which partial fill is considered stale."""
    
    complete_partial_with_market: bool = False
    """Whether to complete stale partial with market order."""


# ============================================================
# ALERTING CONFIGURATION
# ============================================================

@dataclass
class ExecutionAlertingConfig:
    """
    Alerting configuration for execution events.
    """
    
    telegram_enabled: bool = True
    """Whether Telegram alerts are enabled."""
    
    alert_on_rejection: bool = True
    """Alert on order rejection."""
    
    alert_on_failure: bool = True
    """Alert on execution failure."""
    
    alert_on_reconciliation_mismatch: bool = True
    """Alert on reconciliation mismatch."""
    
    alert_on_stale_order: bool = True
    """Alert on stale orders."""
    
    min_alert_interval_seconds: float = 60.0
    """Minimum interval between similar alerts."""


# ============================================================
# EXCHANGE CONFIGURATION
# ============================================================

@dataclass
class ExchangeConfig:
    """
    Exchange-specific configuration.
    """
    
    exchange_id: str = "binance_futures"
    """Exchange identifier."""
    
    testnet: bool = False
    """Whether to use testnet."""
    
    # Endpoints
    rest_url: str = "https://fapi.binance.com"
    """REST API base URL."""
    
    ws_url: str = "wss://fstream.binance.com"
    """WebSocket URL."""
    
    # Credentials (loaded from env)
    api_key_env: str = "BINANCE_API_KEY"
    """Environment variable for API key."""
    
    api_secret_env: str = "BINANCE_API_SECRET"
    """Environment variable for API secret."""
    
    # Features
    hedge_mode: bool = False
    """Whether account is in hedge mode."""
    
    margin_type: str = "CROSS"
    """Margin type (CROSS or ISOLATED)."""


# ============================================================
# MASTER CONFIGURATION
# ============================================================

@dataclass
class ExecutionEngineConfig:
    """
    Master configuration for Execution Engine.
    """
    
    # Sub-configs
    retry: RetryConfig = field(default_factory=RetryConfig)
    """Retry configuration."""
    
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    """Rate limit configuration."""
    
    timeout: TimeoutConfig = field(default_factory=TimeoutConfig)
    """Timeout configuration."""
    
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    """Validation configuration."""
    
    reconciliation: ReconciliationConfig = field(default_factory=ReconciliationConfig)
    """Reconciliation configuration."""
    
    idempotency: IdempotencyConfig = field(default_factory=IdempotencyConfig)
    """Idempotency configuration."""
    
    partial_fill: PartialFillConfig = field(default_factory=PartialFillConfig)
    """Partial fill configuration."""
    
    alerting: ExecutionAlertingConfig = field(default_factory=ExecutionAlertingConfig)
    """Alerting configuration."""
    
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    """Exchange configuration."""
    
    # Global settings
    enabled: bool = True
    """Whether execution is enabled."""
    
    dry_run: bool = False
    """Whether to run in dry-run mode (no real orders)."""
    
    log_all_orders: bool = True
    """Whether to log all order operations."""
    
    persist_all_events: bool = True
    """Whether to persist all events to database."""
    
    @classmethod
    def for_testing(cls) -> "ExecutionEngineConfig":
        """Get configuration for testing."""
        return cls(
            exchange=ExchangeConfig(testnet=True),
            dry_run=True,
            retry=RetryConfig(max_retries=1),
            validation=ValidationConfig(require_valid_approval=False),
        )
    
    @classmethod
    def for_production(cls) -> "ExecutionEngineConfig":
        """Get configuration for production."""
        return cls(
            exchange=ExchangeConfig(testnet=False),
            dry_run=False,
            retry=RetryConfig(max_retries=3),
            validation=ValidationConfig(require_valid_approval=True),
            reconciliation=ReconciliationConfig(
                enabled=True,
                freeze_on_critical_mismatch=True,
            ),
        )
