"""
Chaos Test Case Definitions.

============================================================
PURPOSE
============================================================
Predefined chaos test cases organized by category.

Each test case defines:
- What fault to inject
- Where to inject it
- Expected system reaction
- Recovery expectations

============================================================
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List

from .models import (
    FaultCategory,
    DataFaultType,
    ApiFaultType,
    ProcessFaultType,
    ExecutionFaultType,
    SystemFaultType,
    FaultIntensity,
    FaultDefinition,
    ChaosTestCase,
    ExpectedSystemState,
    ExpectedTradeGuardDecision,
)


# ============================================================
# TEST CASE FACTORY
# ============================================================

def create_fault_definition(
    category: FaultCategory,
    fault_type: str,
    injection_point: str,
    name: str,
    description: str,
    intensity: FaultIntensity = FaultIntensity.ALWAYS,
    duration_seconds: float = None,
    parameters: dict = None,
) -> FaultDefinition:
    """Create a fault definition."""
    return FaultDefinition(
        fault_id=str(uuid.uuid4()),
        category=category,
        fault_type=fault_type,
        name=name,
        description=description,
        injection_point=injection_point,
        intensity=intensity,
        duration_seconds=duration_seconds,
        parameters=parameters or {},
    )


def create_test_case(
    name: str,
    description: str,
    fault_definition: FaultDefinition,
    expected_system_state: ExpectedSystemState,
    expected_trade_guard_decision: ExpectedTradeGuardDecision,
    expected_alerts: List[str] = None,
    should_recover: bool = True,
    recovery_timeout_seconds: float = 60.0,
    priority: int = 1,
    tags: List[str] = None,
) -> ChaosTestCase:
    """Create a chaos test case."""
    return ChaosTestCase(
        test_id=str(uuid.uuid4()),
        name=name,
        description=description,
        fault_definition=fault_definition,
        expected_system_state=expected_system_state,
        expected_trade_guard_decision=expected_trade_guard_decision,
        expected_alerts=expected_alerts or [],
        should_recover=should_recover,
        recovery_timeout_seconds=recovery_timeout_seconds,
        priority=priority,
        tags=tags or [],
    )


# ============================================================
# DATA FAULT TEST CASES
# ============================================================

def get_data_fault_test_cases() -> List[ChaosTestCase]:
    """Get all data fault test cases."""
    return [
        # Missing price data
        create_test_case(
            name="Missing Price Data",
            description="Inject missing price data fault - system must halt trading",
            fault_definition=create_fault_definition(
                category=FaultCategory.DATA,
                fault_type=DataFaultType.MISSING_DATA.value,
                injection_point="data_pipeline.fetch_price",
                name="Missing Price Data",
                description="Simulate missing price data from exchange",
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
            expected_alerts=["Data source stale", "Price data missing"],
            priority=1,
            tags=["data", "critical", "price"],
        ),
        
        # Corrupted price data
        create_test_case(
            name="Corrupted Price Data",
            description="Inject corrupted price data - system must detect and reject",
            fault_definition=create_fault_definition(
                category=FaultCategory.DATA,
                fault_type=DataFaultType.CORRUPTED_DATA.value,
                injection_point="data_pipeline.process_price",
                name="Corrupted Price",
                description="Simulate corrupted price values",
                parameters={"corruption_type": "flip_sign"},
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
            expected_alerts=["Data validation failed"],
            priority=1,
            tags=["data", "critical", "validation"],
        ),
        
        # Stale market data
        create_test_case(
            name="Stale Market Data",
            description="Market data becomes stale - no trading allowed",
            fault_definition=create_fault_definition(
                category=FaultCategory.DATA,
                fault_type=DataFaultType.STALE_DATA.value,
                injection_point="data_pipeline.get_orderbook",
                name="Stale Orderbook",
                description="Simulate stale orderbook data",
                parameters={"stale_seconds": 300},
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
            expected_alerts=["Data freshness alert"],
            priority=1,
            tags=["data", "freshness"],
        ),
        
        # Delayed data
        create_test_case(
            name="Delayed Market Data",
            description="Market data delayed beyond threshold",
            fault_definition=create_fault_definition(
                category=FaultCategory.DATA,
                fault_type=DataFaultType.DELAYED_DATA.value,
                injection_point="data_pipeline.stream_trades",
                name="Delayed Trades",
                description="Simulate delayed trade stream",
                parameters={"delay_seconds": 10},
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.REDUCE_SIZE,
            expected_alerts=["Data latency alert"],
            priority=2,
            tags=["data", "latency"],
        ),
        
        # Out of range values
        create_test_case(
            name="Out of Range Price",
            description="Price value outside valid range - must be rejected",
            fault_definition=create_fault_definition(
                category=FaultCategory.DATA,
                fault_type=DataFaultType.OUT_OF_RANGE.value,
                injection_point="data_pipeline.validate_price",
                name="Invalid Price Range",
                description="Simulate extreme price values",
                parameters={"target_fields": ["price", "bid", "ask"]},
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
            expected_alerts=["Price validation failed"],
            priority=1,
            tags=["data", "validation", "critical"],
        ),
    ]


# ============================================================
# API FAULT TEST CASES
# ============================================================

def get_api_fault_test_cases() -> List[ChaosTestCase]:
    """Get all API fault test cases."""
    return [
        # Exchange API timeout
        create_test_case(
            name="Exchange API Timeout",
            description="Exchange API times out - graceful handling required",
            fault_definition=create_fault_definition(
                category=FaultCategory.API,
                fault_type=ApiFaultType.TIMEOUT.value,
                injection_point="exchange.api_request",
                name="API Timeout",
                description="Simulate exchange API timeout",
                parameters={"timeout_seconds": 30},
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
            expected_alerts=["Exchange connectivity issue"],
            priority=1,
            tags=["api", "exchange", "connectivity"],
        ),
        
        # Rate limit exceeded
        create_test_case(
            name="Rate Limit Exceeded",
            description="Exchange rate limit hit - must back off",
            fault_definition=create_fault_definition(
                category=FaultCategory.API,
                fault_type=ApiFaultType.RATE_LIMIT.value,
                injection_point="exchange.submit_order",
                name="Rate Limited",
                description="Simulate rate limit response",
                parameters={"retry_after": 60},
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.REDUCE_SIZE,
            expected_alerts=["Rate limit warning"],
            priority=2,
            tags=["api", "rate_limit"],
        ),
        
        # Authentication failure
        create_test_case(
            name="Authentication Failure",
            description="API key becomes invalid - emergency stop",
            fault_definition=create_fault_definition(
                category=FaultCategory.API,
                fault_type=ApiFaultType.AUTH_FAILURE.value,
                injection_point="exchange.authenticate",
                name="Auth Failed",
                description="Simulate authentication failure",
                parameters={"error_type": "invalid_key"},
            ),
            expected_system_state=ExpectedSystemState.EMERGENCY_STOP,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.HALT_TRADING,
            expected_alerts=["CRITICAL: Authentication failed"],
            priority=1,
            tags=["api", "auth", "critical"],
        ),
        
        # Connection refused
        create_test_case(
            name="Exchange Connection Refused",
            description="Cannot connect to exchange",
            fault_definition=create_fault_definition(
                category=FaultCategory.API,
                fault_type=ApiFaultType.CONNECTION_REFUSED.value,
                injection_point="exchange.connect",
                name="Connection Refused",
                description="Simulate connection refused",
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
            expected_alerts=["Exchange connection failed"],
            priority=1,
            tags=["api", "connectivity"],
        ),
        
        # Invalid response
        create_test_case(
            name="Invalid API Response",
            description="Exchange returns garbage response",
            fault_definition=create_fault_definition(
                category=FaultCategory.API,
                fault_type=ApiFaultType.INVALID_RESPONSE.value,
                injection_point="exchange.parse_response",
                name="Invalid Response",
                description="Simulate malformed response",
                parameters={"response_type": "garbage"},
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
            expected_alerts=["Response parsing failed"],
            priority=2,
            tags=["api", "parsing"],
        ),
    ]


# ============================================================
# PROCESS FAULT TEST CASES
# ============================================================

def get_process_fault_test_cases() -> List[ChaosTestCase]:
    """Get all process fault test cases."""
    return [
        # Module crash
        create_test_case(
            name="Signal Generator Crash",
            description="Signal generator module crashes",
            fault_definition=create_fault_definition(
                category=FaultCategory.PROCESS,
                fault_type=ProcessFaultType.MODULE_CRASH.value,
                injection_point="signal_generator.process",
                name="Module Crash",
                description="Simulate signal generator crash",
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
            expected_alerts=["Module unhealthy: signal_generator"],
            priority=1,
            tags=["process", "crash"],
        ),
        
        # High latency
        create_test_case(
            name="High Processing Latency",
            description="Signal processing becomes slow",
            fault_definition=create_fault_definition(
                category=FaultCategory.PROCESS,
                fault_type=ProcessFaultType.HIGH_LATENCY.value,
                injection_point="signal_generator.analyze",
                name="High Latency",
                description="Simulate processing delay",
                parameters={"min_latency_ms": 5000, "max_latency_ms": 10000},
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.REDUCE_SIZE,
            expected_alerts=["Processing latency alert"],
            priority=2,
            tags=["process", "latency"],
        ),
        
        # Heartbeat miss
        create_test_case(
            name="Risk Controller Heartbeat Miss",
            description="Risk controller stops sending heartbeats",
            fault_definition=create_fault_definition(
                category=FaultCategory.PROCESS,
                fault_type=ProcessFaultType.HEARTBEAT_MISS.value,
                injection_point="risk_controller.heartbeat",
                name="Heartbeat Miss",
                description="Simulate heartbeat failure",
                parameters={"delay_seconds": 60},
            ),
            expected_system_state=ExpectedSystemState.EMERGENCY_STOP,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.HALT_TRADING,
            expected_alerts=["CRITICAL: Risk controller unresponsive"],
            priority=1,
            tags=["process", "heartbeat", "critical"],
        ),
        
        # Queue overflow
        create_test_case(
            name="Order Queue Overflow",
            description="Order queue becomes full",
            fault_definition=create_fault_definition(
                category=FaultCategory.PROCESS,
                fault_type=ProcessFaultType.QUEUE_OVERFLOW.value,
                injection_point="execution_engine.queue_order",
                name="Queue Overflow",
                description="Simulate queue overflow",
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
            expected_alerts=["Order queue full"],
            priority=2,
            tags=["process", "queue"],
        ),
    ]


# ============================================================
# EXECUTION FAULT TEST CASES
# ============================================================

def get_execution_fault_test_cases() -> List[ChaosTestCase]:
    """Get all execution fault test cases."""
    return [
        # Order rejection
        create_test_case(
            name="Order Rejected - Insufficient Balance",
            description="Order rejected due to insufficient balance",
            fault_definition=create_fault_definition(
                category=FaultCategory.EXECUTION,
                fault_type=ExecutionFaultType.ORDER_REJECTED.value,
                injection_point="execution_engine.submit_order",
                name="Order Rejected",
                description="Simulate order rejection",
                parameters={"reason": "insufficient_balance"},
            ),
            expected_system_state=ExpectedSystemState.RUNNING,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
            expected_alerts=["Order rejected"],
            priority=2,
            tags=["execution", "rejection"],
        ),
        
        # Partial fill stuck
        create_test_case(
            name="Partial Fill Stuck",
            description="Order partially fills but remaining never executes",
            fault_definition=create_fault_definition(
                category=FaultCategory.EXECUTION,
                fault_type=ExecutionFaultType.PARTIAL_FILL_STUCK.value,
                injection_point="execution_engine.monitor_order",
                name="Partial Fill Stuck",
                description="Simulate stuck partial fill",
                parameters={"fill_percentage": 30},
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
            expected_alerts=["Order stuck in partial fill"],
            priority=1,
            tags=["execution", "partial_fill", "critical"],
        ),
        
        # Network disconnect during execution
        create_test_case(
            name="Network Disconnect During Order",
            description="Network fails while order is being submitted",
            fault_definition=create_fault_definition(
                category=FaultCategory.EXECUTION,
                fault_type=ExecutionFaultType.NETWORK_DISCONNECT.value,
                injection_point="execution_engine.submit_order",
                name="Network Disconnect",
                description="Simulate network failure during order",
                parameters={"disconnect_point": "during"},
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.HALT_TRADING,
            expected_alerts=["CRITICAL: Order status unknown"],
            priority=1,
            tags=["execution", "network", "critical"],
        ),
        
        # Position mismatch
        create_test_case(
            name="Position State Mismatch",
            description="Local position state doesn't match exchange",
            fault_definition=create_fault_definition(
                category=FaultCategory.EXECUTION,
                fault_type=ExecutionFaultType.POSITION_MISMATCH.value,
                injection_point="reconciliation.check_positions",
                name="Position Mismatch",
                description="Simulate position state divergence",
            ),
            expected_system_state=ExpectedSystemState.EMERGENCY_STOP,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.HALT_TRADING,
            expected_alerts=["CRITICAL: Position mismatch detected"],
            priority=1,
            tags=["execution", "reconciliation", "critical"],
        ),
        
        # Exchange maintenance
        create_test_case(
            name="Exchange Under Maintenance",
            description="Exchange goes into maintenance mode",
            fault_definition=create_fault_definition(
                category=FaultCategory.EXECUTION,
                fault_type=ExecutionFaultType.EXCHANGE_MAINTENANCE.value,
                injection_point="exchange.check_status",
                name="Exchange Maintenance",
                description="Simulate exchange maintenance",
                parameters={"duration_minutes": 30},
            ),
            expected_system_state=ExpectedSystemState.PAUSED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.HALT_TRADING,
            expected_alerts=["Exchange under maintenance"],
            priority=2,
            tags=["execution", "maintenance"],
        ),
    ]


# ============================================================
# SYSTEM FAULT TEST CASES
# ============================================================

def get_system_fault_test_cases() -> List[ChaosTestCase]:
    """Get all system fault test cases."""
    return [
        # Database unavailable
        create_test_case(
            name="Database Unavailable",
            description="Cannot connect to database",
            fault_definition=create_fault_definition(
                category=FaultCategory.SYSTEM,
                fault_type=SystemFaultType.DATABASE_UNAVAILABLE.value,
                injection_point="database.connect",
                name="DB Unavailable",
                description="Simulate database failure",
                parameters={"error_type": "connection_refused"},
            ),
            expected_system_state=ExpectedSystemState.EMERGENCY_STOP,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.HALT_TRADING,
            expected_alerts=["CRITICAL: Database unavailable"],
            priority=1,
            tags=["system", "database", "critical"],
        ),
        
        # Clock drift
        create_test_case(
            name="Clock Drift Detection",
            description="System clock drifts significantly",
            fault_definition=create_fault_definition(
                category=FaultCategory.SYSTEM,
                fault_type=SystemFaultType.CLOCK_DRIFT.value,
                injection_point="system.get_time",
                name="Clock Drift",
                description="Simulate clock drift",
                parameters={"drift_seconds": 300, "direction": "backward"},
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
            expected_alerts=["Clock drift detected"],
            priority=2,
            tags=["system", "clock"],
        ),
        
        # Network partition
        create_test_case(
            name="Network Partition",
            description="Network partition isolates the system",
            fault_definition=create_fault_definition(
                category=FaultCategory.SYSTEM,
                fault_type=SystemFaultType.NETWORK_PARTITION.value,
                injection_point="network.outbound",
                name="Network Partition",
                description="Simulate network partition",
                parameters={"partition_type": "complete"},
            ),
            expected_system_state=ExpectedSystemState.EMERGENCY_STOP,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.HALT_TRADING,
            expected_alerts=["CRITICAL: Network connectivity lost"],
            priority=1,
            tags=["system", "network", "critical"],
        ),
        
        # Redis unavailable
        create_test_case(
            name="Redis Cache Unavailable",
            description="Redis cache becomes unavailable",
            fault_definition=create_fault_definition(
                category=FaultCategory.SYSTEM,
                fault_type=SystemFaultType.REDIS_UNAVAILABLE.value,
                injection_point="cache.connect",
                name="Redis Unavailable",
                description="Simulate Redis failure",
            ),
            expected_system_state=ExpectedSystemState.DEGRADED,
            expected_trade_guard_decision=ExpectedTradeGuardDecision.REDUCE_SIZE,
            expected_alerts=["Cache unavailable"],
            priority=2,
            tags=["system", "cache"],
        ),
    ]


# ============================================================
# GET ALL TEST CASES
# ============================================================

def get_all_test_cases() -> List[ChaosTestCase]:
    """Get all predefined test cases."""
    return (
        get_data_fault_test_cases() +
        get_api_fault_test_cases() +
        get_process_fault_test_cases() +
        get_execution_fault_test_cases() +
        get_system_fault_test_cases()
    )


def get_critical_test_cases() -> List[ChaosTestCase]:
    """Get only critical (priority 1) test cases."""
    return [tc for tc in get_all_test_cases() if tc.priority == 1]


def get_test_cases_by_category(category: FaultCategory) -> List[ChaosTestCase]:
    """Get test cases by fault category."""
    return [
        tc for tc in get_all_test_cases()
        if tc.fault_definition.category == category
    ]


def get_test_cases_by_tag(tag: str) -> List[ChaosTestCase]:
    """Get test cases by tag."""
    return [tc for tc in get_all_test_cases() if tag in tc.tags]
