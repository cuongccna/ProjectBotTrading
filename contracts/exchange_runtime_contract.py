"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                      EXCHANGE RUNTIME CONTRACT                               ║
║                                                                              ║
║  This document defines the HARD BOUNDARY between the internal trading        ║
║  system and external crypto exchanges.                                       ║
║                                                                              ║
║  PURPOSE: Codify what exchanges ARE and ARE NOT.                             ║
║  SCOPE: All internal modules that interact with exchanges.                   ║
║  AUTHORITY: This contract supersedes any optimistic assumptions.             ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

============================================================
FUNDAMENTAL DEFINITION
============================================================

An EXCHANGE is:
    - An EXTERNAL system
    - An UNTRUSTED system
    - A NONDETERMINISTIC system
    - A PROBABILISTIC system
    - A SOVEREIGN system (it does not answer to us)

An EXCHANGE is NOT:
    - A module we control
    - A service we can improve
    - A reliable partner
    - A predictable system
    - A fair system

============================================================
EXCHANGE BEHAVIORAL AXIOMS
============================================================

The following statements are ALWAYS TRUE:

1. REJECTION IS NORMAL
   - Exchanges CAN reject valid orders
   - Exchanges CAN reject orders without reason
   - Exchanges CAN reject orders after acceptance

2. PARTIAL FILLS ARE NORMAL
   - Orders may fill partially
   - Orders may never complete
   - Partial fills may stop at any amount

3. DELAYS ARE NORMAL
   - Responses may take seconds
   - Responses may take minutes
   - Responses may never arrive

4. OUTAGES ARE NORMAL
   - Exchanges go offline without notice
   - Exchanges return with changed state
   - Maintenance windows are unpredictable

5. INCONSISTENCY IS NORMAL
   - Timestamps may be wrong
   - Balances may be stale
   - Order status may be incorrect
   - Different endpoints may disagree

6. LIMITS ARE HIDDEN
   - Rate limits may change
   - Position limits may be undocumented
   - Order size limits may vary by time

============================================================
"""

from enum import Enum, auto
from typing import Final
from dataclasses import dataclass


# ============================================================
# AUTHORITY BOUNDARIES
# ============================================================

class AuthorityDomain(Enum):
    """
    Defines WHO has final authority over WHAT.
    
    These boundaries are ABSOLUTE and NON-NEGOTIABLE.
    """
    
    EXCHANGE = auto()   # Exchange has final say
    INTERNAL = auto()   # Our system has final say


@dataclass(frozen=True)
class AuthorityRule:
    """Immutable authority assignment."""
    domain: AuthorityDomain
    description: str


# ============================================================
# EXCHANGE AUTHORITY (Exchange decides, we accept)
# ============================================================

EXCHANGE_AUTHORITY: Final[dict] = {
    
    "fill_price": AuthorityRule(
        AuthorityDomain.EXCHANGE,
        "Exchange determines actual execution price. "
        "We CANNOT dictate fill price. "
        "We MUST accept whatever price exchange provides."
    ),
    
    "fill_quantity": AuthorityRule(
        AuthorityDomain.EXCHANGE,
        "Exchange determines how much gets filled. "
        "We CANNOT force full fills. "
        "We MUST accept partial fills or zero fills."
    ),
    
    "execution_timing": AuthorityRule(
        AuthorityDomain.EXCHANGE,
        "Exchange determines WHEN execution happens. "
        "We CANNOT control latency. "
        "We MUST accept delayed or instant execution."
    ),
    
    "order_acceptance": AuthorityRule(
        AuthorityDomain.EXCHANGE,
        "Exchange determines IF order is accepted. "
        "We CANNOT force acceptance. "
        "We MUST handle rejections gracefully."
    ),
    
    "market_state": AuthorityRule(
        AuthorityDomain.EXCHANGE,
        "Exchange determines if market is open. "
        "We CANNOT trade halted symbols. "
        "We MUST respect trading suspensions."
    ),
    
    "fee_structure": AuthorityRule(
        AuthorityDomain.EXCHANGE,
        "Exchange determines fees charged. "
        "We CANNOT negotiate fees at runtime. "
        "We MUST accept fee deductions."
    ),
    
    "liquidation": AuthorityRule(
        AuthorityDomain.EXCHANGE,
        "Exchange determines liquidation. "
        "We CANNOT prevent forced liquidation. "
        "We MUST handle liquidation events."
    ),
}


# ============================================================
# INTERNAL AUTHORITY (We decide, exchange accepts)
# ============================================================

INTERNAL_AUTHORITY: Final[dict] = {
    
    "order_submission": AuthorityRule(
        AuthorityDomain.INTERNAL,
        "WE decide whether to submit orders. "
        "Exchange cannot force us to trade. "
        "We control order initiation."
    ),
    
    "order_cancellation": AuthorityRule(
        AuthorityDomain.INTERNAL,
        "WE decide whether to cancel orders. "
        "We can attempt cancellation anytime. "
        "We control cancellation requests."
    ),
    
    "trading_halt": AuthorityRule(
        AuthorityDomain.INTERNAL,
        "WE decide whether to stop trading. "
        "We can halt all activity instantly. "
        "We control system shutdown."
    ),
    
    "risk_limits": AuthorityRule(
        AuthorityDomain.INTERNAL,
        "WE define our risk boundaries. "
        "We enforce position limits internally. "
        "We control exposure thresholds."
    ),
    
    "exchange_selection": AuthorityRule(
        AuthorityDomain.INTERNAL,
        "WE decide which exchanges to use. "
        "We can disconnect from any exchange. "
        "We control exchange connectivity."
    ),
    
    "order_parameters": AuthorityRule(
        AuthorityDomain.INTERNAL,
        "WE define order parameters before submission. "
        "We control size, price, type, side. "
        "We validate before sending."
    ),
}


# ============================================================
# PROHIBITED ASSUMPTIONS
# ============================================================

class ProhibitedAssumption(Enum):
    """
    Assumptions that internal code MUST NEVER make.
    
    Violating these assumptions leads to catastrophic failures.
    """
    
    # Order execution assumptions
    ORDERS_WILL_FILL = "Never assume orders will be filled"
    ORDERS_FILL_IMMEDIATELY = "Never assume immediate fills"
    ORDERS_FILL_AT_PRICE = "Never assume fills at requested price"
    ORDERS_FILL_COMPLETELY = "Never assume full quantity fills"
    
    # Status assumptions
    STATUS_IS_ACCURATE = "Never assume order status is current"
    STATUS_IS_FINAL = "Never assume status won't change"
    BALANCE_IS_CURRENT = "Never assume balance is real-time"
    POSITION_IS_ACCURATE = "Never assume position is accurate"
    
    # Availability assumptions
    EXCHANGE_IS_ONLINE = "Never assume exchange is available"
    ENDPOINT_IS_WORKING = "Never assume endpoint responds"
    WEBSOCKET_IS_CONNECTED = "Never assume WS is alive"
    API_IS_CONSISTENT = "Never assume API consistency"
    
    # Performance assumptions
    LATENCY_IS_LOW = "Never assume low latency"
    LATENCY_IS_STABLE = "Never assume stable latency"
    THROUGHPUT_IS_HIGH = "Never assume high throughput"
    RATE_LIMITS_ARE_KNOWN = "Never assume rate limits are documented"
    
    # Market assumptions
    LIQUIDITY_EXISTS = "Never assume liquidity is available"
    SPREAD_IS_TIGHT = "Never assume tight spreads"
    PRICE_IS_FAIR = "Never assume fair pricing"
    MARKET_IS_OPEN = "Never assume market is open"


# ============================================================
# FAILURE TAXONOMY
# ============================================================

class ExchangeFailureType(Enum):
    """
    Classification of exchange failures.
    
    All internal modules MUST handle ALL of these.
    """
    
    # Network layer
    NETWORK_TIMEOUT = "Request timed out"
    NETWORK_DISCONNECT = "Connection lost"
    NETWORK_DNS_FAILURE = "DNS resolution failed"
    NETWORK_SSL_ERROR = "SSL/TLS error"
    
    # Rate limiting
    RATE_LIMIT_EXCEEDED = "Too many requests"
    RATE_LIMIT_IP_BAN = "IP temporarily banned"
    RATE_LIMIT_ACCOUNT_BAN = "Account rate limited"
    
    # Authentication
    AUTH_INVALID_KEY = "API key invalid"
    AUTH_EXPIRED_KEY = "API key expired"
    AUTH_INVALID_SIGNATURE = "Signature mismatch"
    AUTH_IP_RESTRICTED = "IP not whitelisted"
    AUTH_PERMISSION_DENIED = "Insufficient permissions"
    
    # Order failures
    ORDER_REJECTED = "Order rejected by exchange"
    ORDER_INVALID_SYMBOL = "Symbol not found or invalid"
    ORDER_INVALID_QUANTITY = "Quantity validation failed"
    ORDER_INVALID_PRICE = "Price validation failed"
    ORDER_MIN_NOTIONAL = "Below minimum notional"
    ORDER_MAX_POSITION = "Exceeds position limit"
    ORDER_INSUFFICIENT_MARGIN = "Not enough margin"
    ORDER_INSUFFICIENT_BALANCE = "Not enough balance"
    ORDER_REDUCE_ONLY_REJECTED = "Reduce-only order rejected"
    ORDER_POST_ONLY_REJECTED = "Post-only would take"
    ORDER_DUPLICATE = "Duplicate client order ID"
    ORDER_NOT_FOUND = "Order does not exist"
    ORDER_ALREADY_FILLED = "Order already executed"
    ORDER_ALREADY_CANCELED = "Order already canceled"
    
    # Market failures
    MARKET_HALTED = "Trading halted"
    MARKET_SUSPENDED = "Market suspended"
    MARKET_CLOSED = "Market closed"
    MARKET_DELISTED = "Symbol delisted"
    
    # Exchange internal
    EXCHANGE_INTERNAL_ERROR = "Exchange internal error"
    EXCHANGE_MAINTENANCE = "Under maintenance"
    EXCHANGE_OVERLOADED = "Exchange overloaded"
    EXCHANGE_DATA_STALE = "Data is stale"
    
    # Silent failures
    ORDER_SILENTLY_DROPPED = "Order accepted but never processed"
    FILL_NOT_REPORTED = "Fill occurred but not reported"
    CANCEL_NOT_PROCESSED = "Cancel accepted but not executed"
    
    # State divergence
    STATE_DIVERGENCE = "Internal state differs from exchange"
    BALANCE_MISMATCH = "Balance doesn't match expected"
    POSITION_MISMATCH = "Position doesn't match expected"


# ============================================================
# MANDATORY SYSTEM REACTIONS
# ============================================================

class MandatoryReaction(Enum):
    """
    Required system responses to exchange events.
    
    These reactions are NON-OPTIONAL.
    """
    
    # On any exchange error
    LOG_FULL_CONTEXT = "Log complete error context with timestamp"
    REPORT_UPSTREAM = "Report to monitoring/alerting system"
    RECORD_METRICS = "Record in metrics for analysis"
    
    # On order rejection
    NEVER_RETRY_SILENTLY = "Never retry without explicit approval"
    PRESERVE_REJECTION_REASON = "Keep rejection reason for audit"
    UPDATE_INTERNAL_STATE = "Mark order as failed internally"
    
    # On partial fill
    UPDATE_REMAINING = "Track remaining quantity"
    RECONCILE_POSITION = "Reconcile position after fill"
    NOTIFY_STRATEGY = "Inform strategy layer of partial"
    
    # On timeout
    ASSUME_UNKNOWN = "Assume order state is UNKNOWN"
    QUERY_BEFORE_RETRY = "Query status before any retry"
    NEVER_ASSUME_FAILED = "Never assume timeout = failure"
    
    # On state divergence
    HALT_IF_CRITICAL = "Halt trading if divergence is critical"
    RECONCILE_IMMEDIATELY = "Trigger immediate reconciliation"
    ALERT_HUMAN = "Alert human operators"
    
    # On exchange outage
    CACHE_PENDING_ACTIONS = "Cache any pending actions"
    RECONNECT_WITH_BACKOFF = "Reconnect with exponential backoff"
    RECONCILE_ON_RECONNECT = "Full reconciliation after reconnect"


# ============================================================
# EXECUTION REALISM REQUIREMENTS
# ============================================================

@dataclass(frozen=True)
class ExecutionRealismRule:
    """Rules for realistic execution handling."""
    rule: str
    rationale: str
    violation_consequence: str


EXECUTION_REALISM: Final[list] = [
    
    ExecutionRealismRule(
        rule="Every order is ASYNCHRONOUS",
        rationale="Exchange processing is not instantaneous",
        violation_consequence="Race conditions, state corruption"
    ),
    
    ExecutionRealismRule(
        rule="Every order may be PARTIALLY FILLED",
        rationale="Liquidity may not cover full size",
        violation_consequence="Incorrect position tracking"
    ),
    
    ExecutionRealismRule(
        rule="Every order may be REJECTED",
        rationale="Exchange can reject for any reason",
        violation_consequence="Dangling order states"
    ),
    
    ExecutionRealismRule(
        rule="Every fill must be RECONCILED",
        rationale="Exchange state is source of truth",
        violation_consequence="State divergence, incorrect risk"
    ),
    
    ExecutionRealismRule(
        rule="Every price is INDICATIVE until filled",
        rationale="Market moves, slippage occurs",
        violation_consequence="Incorrect P&L calculation"
    ),
    
    ExecutionRealismRule(
        rule="Every balance check may be STALE",
        rationale="Balance endpoints have latency",
        violation_consequence="Insufficient funds errors"
    ),
    
    ExecutionRealismRule(
        rule="Every position query may be DELAYED",
        rationale="Position updates are not instant",
        violation_consequence="Risk limit breaches"
    ),
    
    ExecutionRealismRule(
        rule="Every timestamp may be INACCURATE",
        rationale="Exchange clocks may drift",
        violation_consequence="Incorrect time-based logic"
    ),
]


# ============================================================
# TESTING REQUIREMENTS
# ============================================================

class TestingRequirement(Enum):
    """
    What MUST be tested for exchange interactions.
    
    All scenarios are NORMAL, not edge cases.
    """
    
    # Failures to simulate
    TEST_NETWORK_TIMEOUT = "Simulate 30s+ timeouts"
    TEST_RATE_LIMIT = "Simulate rate limit responses"
    TEST_EXCHANGE_DOWN = "Simulate complete outage"
    TEST_PARTIAL_FILL = "Simulate 10%, 50%, 90% fills"
    TEST_ZERO_FILL = "Simulate order acceptance with no fill"
    TEST_ORDER_REJECTION = "Simulate various rejection reasons"
    TEST_SLIPPAGE = "Simulate 0.1%, 1%, 5% slippage"
    TEST_STATE_DIVERGENCE = "Simulate position mismatches"
    TEST_STALE_DATA = "Simulate delayed responses"
    TEST_DUPLICATE_MESSAGES = "Simulate duplicate fill reports"
    TEST_OUT_OF_ORDER = "Simulate out-of-order messages"
    TEST_MALFORMED_RESPONSE = "Simulate invalid JSON"
    TEST_RECONNECTION = "Simulate disconnect/reconnect cycles"
    
    # Stress scenarios
    STRESS_HIGH_LATENCY = "Test with 5s latency"
    STRESS_LOW_LIQUIDITY = "Test with minimal fills"
    STRESS_HIGH_VOLATILITY = "Test with rapid price changes"
    STRESS_RAPID_ORDERS = "Test rapid order submission"


# ============================================================
# DESIGN PRINCIPLES
# ============================================================

DESIGN_PRINCIPLES: Final[dict] = {
    
    "SURVIVE_THE_EXCHANGE": """
        The system survives the exchange.
        The exchange does not adapt to the system.
        We are guests in their house.
    """,
    
    "DEFEND_DONT_TRUST": """
        Code must DEFEND against the exchange.
        Code must NOT trust the exchange.
        Every response is potentially wrong.
    """,
    
    "ASSUME_THE_WORST": """
        Assume the worst-case scenario.
        Design for failure, not success.
        Hope is not a strategy.
    """,
    
    "RECONCILE_CONSTANTLY": """
        Exchange state is the source of truth.
        Internal state is a cache.
        Reconciliation is continuous.
    """,
    
    "FAIL_LOUDLY": """
        Never hide failures.
        Never self-correct silently.
        Always report anomalies upstream.
    """,
    
    "GRACEFUL_DEGRADATION": """
        Partial functionality beats total failure.
        Safe mode beats crash.
        Reduced trading beats no trading.
    """,
}


# ============================================================
# CONTRACT ENFORCEMENT
# ============================================================

def assert_exchange_authority(decision: str) -> None:
    """
    Assert that a decision respects exchange authority.
    
    Call this before any operation that depends on exchange behavior.
    """
    if decision in EXCHANGE_AUTHORITY:
        # This is the exchange's decision - we cannot override
        pass


def assert_internal_authority(decision: str) -> None:
    """
    Assert that a decision is within internal authority.
    
    Call this before any operation we control.
    """
    if decision in INTERNAL_AUTHORITY:
        # This is our decision - we have full control
        pass


def validate_no_prohibited_assumption(code_path: str, assumption: ProhibitedAssumption) -> None:
    """
    Validate that code does not make a prohibited assumption.
    
    Use in code reviews and static analysis.
    """
    raise AssertionError(
        f"PROHIBITED ASSUMPTION DETECTED\n"
        f"Code path: {code_path}\n"
        f"Assumption: {assumption.value}\n"
        f"This assumption is NEVER safe to make."
    )


# ============================================================
# CONTRACT VERSION
# ============================================================

CONTRACT_VERSION: Final[str] = "1.0.0"
CONTRACT_DATE: Final[str] = "2026-01-11"
CONTRACT_AUTHOR: Final[str] = "System Architecture"

"""
============================================================
END OF CONTRACT
============================================================

This contract MUST be understood by all developers.
This contract MUST be referenced in code reviews.
This contract MUST guide all exchange-related design.

The exchange is not our friend.
The exchange is not our enemy.
The exchange is reality.

We do not fight reality.
We survive it.

============================================================
"""
