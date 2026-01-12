"""
Chaos Testing & Fault Injection Module.

============================================================
INSTITUTIONAL-GRADE CRYPTO TRADING SYSTEM
Chaos Testing & Fault Injection Module
============================================================

PURPOSE:
--------
This module actively breaks the trading system to prove it survives
and fails safely. It validates:

1. System robustness under failure conditions
2. Capital safety under unexpected failures
3. Trade Guard enforcement
4. Proper alerting and recovery

PHILOSOPHY:
-----------
"If chaos testing didn't break anything, you didn't test hard enough."

This module exists to:
- Actively BREAK the system
- PROVE the system survives
- VERIFY capital remains safe
- VALIDATE all safety mechanisms work

============================================================
RUN MODES
============================================================

1. DRY_RUN
   - No faults actually injected
   - Validates test case structure
   - Use for development and CI/CD

2. STAGING
   - Full fault injection in isolated environment
   - Real faults, simulated infrastructure
   - Use for pre-production validation

3. SHADOW_PRODUCTION
   - Observe-only mode
   - No execution, no capital at risk
   - Use for production monitoring

============================================================
FAULT CATEGORIES
============================================================

1. DATA FAULTS
   - Missing data
   - Delayed data
   - Corrupted data
   - Stale data
   - Invalid format

2. API FAULTS
   - Timeout
   - Rate limit
   - Auth failure
   - Connection refused
   - Invalid response

3. PROCESS FAULTS
   - Module crash
   - High latency
   - Queue overflow
   - Heartbeat miss

4. EXECUTION FAULTS
   - Order rejected
   - Partial fill stuck
   - Network disconnect
   - Position mismatch

5. SYSTEM FAULTS
   - Database unavailable
   - Clock drift
   - Network partition
   - Redis unavailable

============================================================
FORBIDDEN BEHAVIORS
============================================================

The system MUST NEVER:
1. Trade with stale/corrupted data
2. Ignore Trade Guard decisions
3. Retry indefinitely
4. Crash silently
5. Continue after critical failure
6. Skip audit logging
7. Ignore rate limits
8. Skip reconciliation

============================================================
USAGE
============================================================

Basic usage:

    from chaos_testing import (
        RunMode,
        ChaosTestExecutor,
        get_all_test_cases,
        ReportGenerator,
    )
    
    # Create executor (defaults to DRY_RUN for safety)
    executor = ChaosTestExecutor(run_mode=RunMode.DRY_RUN)
    
    # Get predefined test cases
    test_cases = get_all_test_cases()
    
    # Run all tests
    test_run = await executor.execute_test_run(
        test_cases=test_cases,
        run_name="Nightly Chaos Tests",
    )
    
    # Generate report
    generator = ReportGenerator()
    report = generator.generate_report(test_run)
    
    print(f"Passed: {report.passed}")
    print(f"Tests: {test_run.passed_tests}/{test_run.total_tests}")

Run specific category:

    from chaos_testing import (
        get_test_cases_by_category,
        FaultCategory,
    )
    
    # Get only data fault tests
    data_tests = get_test_cases_by_category(FaultCategory.DATA)
    
    test_run = await executor.execute_test_run(data_tests)

Custom test case:

    from chaos_testing import (
        create_test_case,
        create_fault_definition,
        FaultCategory,
        DataFaultType,
        ExpectedSystemState,
        ExpectedTradeGuardDecision,
    )
    
    fault = create_fault_definition(
        category=FaultCategory.DATA,
        fault_type=DataFaultType.STALE_DATA.value,
        injection_point="data_pipeline.get_price",
        name="Custom Stale Data Test",
        description="Test custom stale data scenario",
    )
    
    test_case = create_test_case(
        name="Custom Stale Test",
        description="Custom test for specific stale scenario",
        fault_definition=fault,
        expected_system_state=ExpectedSystemState.DEGRADED,
        expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
    )

============================================================
"""

# Models
from .models import (
    RunMode,
    FaultCategory,
    DataFaultType,
    ApiFaultType,
    ProcessFaultType,
    ExecutionFaultType,
    SystemFaultType,
    FaultIntensity,
    FaultDefinition,
    ActiveFault,
    ChaosTestCase,
    ChaosTestResult,
    ChaosTestRun,
    ChaosReport,
    ExpectedSystemState,
    ExpectedTradeGuardDecision,
    ForbiddenBehavior,
    ForbiddenBehaviorViolation,
)

# Faults
from .faults import (
    FaultRegistry,
    get_fault_registry,
    BaseFaultInjector,
    DataFaultInjector,
    ApiFaultInjector,
    ProcessFaultInjector,
    ExecutionFaultInjector,
    SystemFaultInjector,
    ClockDriftSimulator,
    clock_drift,
    injection_point,
    fault_injection_scope,
    ChaosException,
    InjectedFaultException,
    TimeoutFaultException,
    ConnectionFaultException,
    DataFaultException,
    ExecutionFaultException,
)

# Test Cases
from .test_cases import (
    create_fault_definition,
    create_test_case,
    get_all_test_cases,
    get_critical_test_cases,
    get_test_cases_by_category,
    get_test_cases_by_tag,
    get_data_fault_test_cases,
    get_api_fault_test_cases,
    get_process_fault_test_cases,
    get_execution_fault_test_cases,
    get_system_fault_test_cases,
)

# Validator
from .validator import (
    ChaosValidator,
    SystemStateMonitor,
    TradeGuardMonitor,
    AlertMonitor,
    BehaviorMonitor,
    create_validator,
)

# Executor
from .executor import (
    ChaosTestExecutor,
    ChaosExecutionContext,
    create_executor,
)

# Reporter
from .reporter import (
    ReportGenerator,
    ReportStatistics,
    ReportRepository,
    RecommendationsEngine,
    create_report_generator,
    create_report_repository,
)

# Integration
from .integration import (
    OrchestratorAdapter,
    TradeGuardAdapter,
    MonitoringAdapter,
    MockOrchestratorAdapter,
    MockTradeGuardAdapter,
    MockMonitoringAdapter,
    ChaosIntegrationManager,
    create_mock_integration_manager,
    create_integration_manager,
)


__all__ = [
    # Run Modes
    "RunMode",
    
    # Fault Categories and Types
    "FaultCategory",
    "DataFaultType",
    "ApiFaultType",
    "ProcessFaultType",
    "ExecutionFaultType",
    "SystemFaultType",
    "FaultIntensity",
    
    # Fault Definitions
    "FaultDefinition",
    "ActiveFault",
    
    # Test Cases
    "ChaosTestCase",
    "ChaosTestResult",
    "ChaosTestRun",
    "ChaosReport",
    
    # Expected Behaviors
    "ExpectedSystemState",
    "ExpectedTradeGuardDecision",
    "ForbiddenBehavior",
    "ForbiddenBehaviorViolation",
    
    # Fault Infrastructure
    "FaultRegistry",
    "get_fault_registry",
    "BaseFaultInjector",
    "DataFaultInjector",
    "ApiFaultInjector",
    "ProcessFaultInjector",
    "ExecutionFaultInjector",
    "SystemFaultInjector",
    "ClockDriftSimulator",
    "clock_drift",
    
    # Decorators and Context Managers
    "injection_point",
    "fault_injection_scope",
    
    # Exceptions
    "ChaosException",
    "InjectedFaultException",
    "TimeoutFaultException",
    "ConnectionFaultException",
    "DataFaultException",
    "ExecutionFaultException",
    
    # Test Case Factories
    "create_fault_definition",
    "create_test_case",
    "get_all_test_cases",
    "get_critical_test_cases",
    "get_test_cases_by_category",
    "get_test_cases_by_tag",
    "get_data_fault_test_cases",
    "get_api_fault_test_cases",
    "get_process_fault_test_cases",
    "get_execution_fault_test_cases",
    "get_system_fault_test_cases",
    
    # Validator
    "ChaosValidator",
    "SystemStateMonitor",
    "TradeGuardMonitor",
    "AlertMonitor",
    "BehaviorMonitor",
    "create_validator",
    
    # Executor
    "ChaosTestExecutor",
    "ChaosExecutionContext",
    "create_executor",
    
    # Reporter
    "ReportGenerator",
    "ReportStatistics",
    "ReportRepository",
    "RecommendationsEngine",
    "create_report_generator",
    "create_report_repository",
    
    # Integration
    "OrchestratorAdapter",
    "TradeGuardAdapter",
    "MonitoringAdapter",
    "MockOrchestratorAdapter",
    "MockTradeGuardAdapter",
    "MockMonitoringAdapter",
    "ChaosIntegrationManager",
    "create_mock_integration_manager",
    "create_integration_manager",
]
