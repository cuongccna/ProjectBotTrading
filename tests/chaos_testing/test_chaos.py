"""
Tests for Chaos Testing Module.

============================================================
TEST COVERAGE
============================================================
1. Model validation tests
2. Fault injector tests
3. Validator tests
4. Executor tests
5. Reporter tests
6. Integration tests
============================================================
"""

import asyncio
import pytest
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List
from decimal import Decimal

# Import all chaos testing components
from chaos_testing import (
    # Run Modes
    RunMode,
    
    # Fault Categories and Types
    FaultCategory,
    DataFaultType,
    ApiFaultType,
    ProcessFaultType,
    ExecutionFaultType,
    SystemFaultType,
    FaultIntensity,
    
    # Fault Definitions
    FaultDefinition,
    ActiveFault,
    
    # Test Cases
    ChaosTestCase,
    ChaosTestResult,
    ChaosTestRun,
    ChaosReport,
    
    # Expected Behaviors
    ExpectedSystemState,
    ExpectedTradeGuardDecision,
    ForbiddenBehavior,
    ForbiddenBehaviorViolation,
    
    # Fault Infrastructure
    FaultRegistry,
    get_fault_registry,
    DataFaultInjector,
    ApiFaultInjector,
    ProcessFaultInjector,
    ExecutionFaultInjector,
    SystemFaultInjector,
    ClockDriftSimulator,
    clock_drift,
    
    # Decorators and Context Managers
    injection_point,
    fault_injection_scope,
    
    # Exceptions
    ChaosException,
    InjectedFaultException,
    TimeoutFaultException,
    ConnectionFaultException,
    DataFaultException,
    ExecutionFaultException,
    
    # Test Case Factories
    create_fault_definition,
    create_test_case,
    get_all_test_cases,
    get_critical_test_cases,
    get_test_cases_by_category,
    get_test_cases_by_tag,
    
    # Validator
    ChaosValidator,
    SystemStateMonitor,
    TradeGuardMonitor,
    AlertMonitor,
    BehaviorMonitor,
    create_validator,
    
    # Executor
    ChaosTestExecutor,
    create_executor,
    
    # Reporter
    ReportGenerator,
    ReportStatistics,
    create_report_generator,
    
    # Integration
    MockOrchestratorAdapter,
    MockTradeGuardAdapter,
    MockMonitoringAdapter,
    ChaosIntegrationManager,
    create_mock_integration_manager,
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def fault_registry():
    """Create a fresh fault registry for each test."""
    registry = FaultRegistry()
    yield registry
    registry.clear_all()


@pytest.fixture
def sample_fault_definition():
    """Create a sample fault definition."""
    return create_fault_definition(
        category=FaultCategory.DATA,
        fault_type=DataFaultType.STALE_DATA.value,
        injection_point="test.injection.point",
        name="Test Stale Data Fault",
        description="Test fault for unit testing",
        intensity=FaultIntensity.ALWAYS,
        duration_seconds=5.0,
        parameters={"stale_seconds": 60},
    )


@pytest.fixture
def sample_test_case(sample_fault_definition):
    """Create a sample test case."""
    return create_test_case(
        name="Test Case 1",
        description="A sample test case",
        fault_definition=sample_fault_definition,
        expected_system_state=ExpectedSystemState.DEGRADED,
        expected_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
        expected_alerts=["Data freshness alert"],
        priority=1,
        tags=["test", "data"],
    )


@pytest.fixture
def validator():
    """Create a validator with fresh monitors."""
    return create_validator()


@pytest.fixture
def executor():
    """Create an executor in DRY_RUN mode."""
    return create_executor(RunMode.DRY_RUN)


@pytest.fixture
def report_generator():
    """Create a report generator."""
    return create_report_generator()


# ============================================================
# MODEL TESTS
# ============================================================

class TestModels:
    """Test chaos testing data models."""
    
    def test_run_mode_values(self):
        """Test RunMode enum values."""
        assert RunMode.DRY_RUN.value == "dry_run"
        assert RunMode.STAGING.value == "staging"
        assert RunMode.SHADOW_PRODUCTION.value == "shadow_production"
    
    def test_fault_category_values(self):
        """Test FaultCategory enum values."""
        assert len(FaultCategory) == 5
        assert FaultCategory.DATA.value == "data"
        assert FaultCategory.API.value == "api"
        assert FaultCategory.PROCESS.value == "process"
        assert FaultCategory.EXECUTION.value == "execution"
        assert FaultCategory.SYSTEM.value == "system"
    
    def test_fault_intensity_values(self):
        """Test FaultIntensity enum values."""
        assert FaultIntensity.LOW.value == 0.1
        assert FaultIntensity.MEDIUM.value == 0.5
        assert FaultIntensity.HIGH.value == 0.9
        assert FaultIntensity.ALWAYS.value == 1.0
    
    def test_expected_system_state_values(self):
        """Test ExpectedSystemState enum values."""
        assert ExpectedSystemState.RUNNING.value == "running"
        assert ExpectedSystemState.DEGRADED.value == "degraded"
        assert ExpectedSystemState.PAUSED.value == "paused"
        assert ExpectedSystemState.EMERGENCY_STOP.value == "emergency_stop"
    
    def test_forbidden_behavior_values(self):
        """Test ForbiddenBehavior enum values."""
        assert len(ForbiddenBehavior) == 8
        assert ForbiddenBehavior.TRADE_WITH_STALE_DATA in ForbiddenBehavior
        assert ForbiddenBehavior.IGNORE_TRADE_GUARD in ForbiddenBehavior
    
    def test_fault_definition_creation(self, sample_fault_definition):
        """Test FaultDefinition creation."""
        assert sample_fault_definition.category == FaultCategory.DATA
        assert sample_fault_definition.fault_type == DataFaultType.STALE_DATA.value
        assert sample_fault_definition.intensity == FaultIntensity.ALWAYS
        assert sample_fault_definition.parameters["stale_seconds"] == 60
    
    def test_test_case_creation(self, sample_test_case):
        """Test ChaosTestCase creation."""
        assert sample_test_case.name == "Test Case 1"
        assert sample_test_case.expected_system_state == ExpectedSystemState.DEGRADED
        assert sample_test_case.expected_trade_guard_decision == ExpectedTradeGuardDecision.BLOCK
        assert "test" in sample_test_case.tags
    
    def test_forbidden_behavior_violation(self):
        """Test ForbiddenBehaviorViolation creation."""
        violation = ForbiddenBehaviorViolation(
            behavior=ForbiddenBehavior.TRADE_WITH_STALE_DATA,
            description="Trading with stale data",
            detected_at=datetime.utcnow(),
            evidence={"stale_seconds": 120},
        )
        assert violation.behavior == ForbiddenBehavior.TRADE_WITH_STALE_DATA
        assert "stale_seconds" in violation.evidence


# ============================================================
# FAULT REGISTRY TESTS
# ============================================================

class TestFaultRegistry:
    """Test FaultRegistry."""
    
    def test_singleton_behavior(self):
        """Test that get_fault_registry returns singleton."""
        registry1 = get_fault_registry()
        registry2 = get_fault_registry()
        assert registry1 is registry2
    
    def test_register_fault(self, fault_registry, sample_fault_definition):
        """Test registering a fault."""
        active_fault = ActiveFault(
            fault_id=sample_fault_definition.fault_id,
            definition=sample_fault_definition,
            started_at=datetime.utcnow(),
        )
        fault_registry.register(active_fault)
        
        assert fault_registry.is_active(sample_fault_definition.fault_id)
    
    def test_deactivate_fault(self, fault_registry, sample_fault_definition):
        """Test deactivating a fault."""
        active_fault = ActiveFault(
            fault_id=sample_fault_definition.fault_id,
            definition=sample_fault_definition,
            started_at=datetime.utcnow(),
        )
        fault_registry.register(active_fault)
        fault_registry.deactivate(sample_fault_definition.fault_id)
        
        assert not fault_registry.is_active(sample_fault_definition.fault_id)
    
    def test_get_active_faults(self, fault_registry, sample_fault_definition):
        """Test getting active faults."""
        active_fault = ActiveFault(
            fault_id=sample_fault_definition.fault_id,
            definition=sample_fault_definition,
            started_at=datetime.utcnow(),
        )
        fault_registry.register(active_fault)
        
        active = fault_registry.get_active_faults()
        assert len(active) == 1
        assert active[0].fault_id == sample_fault_definition.fault_id


# ============================================================
# FAULT INJECTOR TESTS
# ============================================================

class TestDataFaultInjector:
    """Test DataFaultInjector."""
    
    @pytest.fixture
    def injector(self, fault_registry):
        return DataFaultInjector(fault_registry)
    
    @pytest.mark.asyncio
    async def test_execute_stale_data(self, injector):
        """Test stale data fault injection."""
        with pytest.raises(DataFaultException):
            await injector.execute_stale_data(stale_seconds=300)
    
    @pytest.mark.asyncio
    async def test_execute_missing_data(self, injector):
        """Test missing data fault injection."""
        with pytest.raises(DataFaultException):
            await injector.execute_missing_data()
    
    @pytest.mark.asyncio
    async def test_execute_corrupted_data(self, injector):
        """Test corrupted data fault injection."""
        with pytest.raises(DataFaultException):
            await injector.execute_corrupted_data()


class TestApiFaultInjector:
    """Test ApiFaultInjector."""
    
    @pytest.fixture
    def injector(self, fault_registry):
        return ApiFaultInjector(fault_registry)
    
    @pytest.mark.asyncio
    async def test_execute_timeout(self, injector):
        """Test timeout fault injection."""
        with pytest.raises(TimeoutFaultException):
            await injector.execute_timeout(timeout_seconds=1)
    
    @pytest.mark.asyncio
    async def test_execute_rate_limit(self, injector):
        """Test rate limit fault injection."""
        with pytest.raises(ConnectionFaultException):
            await injector.execute_rate_limit(retry_after=60)
    
    @pytest.mark.asyncio
    async def test_execute_auth_failure(self, injector):
        """Test auth failure fault injection."""
        with pytest.raises(ConnectionFaultException):
            await injector.execute_auth_failure()


class TestExecutionFaultInjector:
    """Test ExecutionFaultInjector."""
    
    @pytest.fixture
    def injector(self, fault_registry):
        return ExecutionFaultInjector(fault_registry)
    
    @pytest.mark.asyncio
    async def test_execute_order_rejected(self, injector):
        """Test order rejected fault injection."""
        with pytest.raises(ExecutionFaultException):
            await injector.execute_order_rejected(reason="insufficient_balance")
    
    @pytest.mark.asyncio
    async def test_execute_partial_fill_stuck(self, injector):
        """Test partial fill stuck fault injection."""
        with pytest.raises(ExecutionFaultException):
            await injector.execute_partial_fill_stuck(fill_percentage=30)


# ============================================================
# VALIDATOR TESTS
# ============================================================

class TestSystemStateMonitor:
    """Test SystemStateMonitor."""
    
    def test_update_state(self):
        """Test state update."""
        monitor = SystemStateMonitor()
        monitor.update_state(ExpectedSystemState.RUNNING)
        
        assert monitor.get_current_state() == ExpectedSystemState.RUNNING
    
    def test_state_history(self):
        """Test state history tracking."""
        monitor = SystemStateMonitor()
        monitor.update_state(ExpectedSystemState.RUNNING)
        monitor.update_state(ExpectedSystemState.DEGRADED)
        
        history = monitor.get_state_history()
        assert len(history) == 2
        assert history[1][1] == ExpectedSystemState.DEGRADED


class TestTradeGuardMonitor:
    """Test TradeGuardMonitor."""
    
    def test_record_decision(self):
        """Test recording decisions."""
        monitor = TradeGuardMonitor()
        monitor.record_decision(
            ExpectedTradeGuardDecision.BLOCK,
            reason="Test block"
        )
        
        assert monitor.get_last_decision() == ExpectedTradeGuardDecision.BLOCK
    
    def test_had_decision(self):
        """Test checking for decision."""
        monitor = TradeGuardMonitor()
        monitor.record_decision(ExpectedTradeGuardDecision.BLOCK, "")
        
        assert monitor.had_decision(ExpectedTradeGuardDecision.BLOCK)
        assert not monitor.had_decision(ExpectedTradeGuardDecision.ALLOW)


class TestAlertMonitor:
    """Test AlertMonitor."""
    
    def test_record_alert(self):
        """Test recording alerts."""
        monitor = AlertMonitor()
        monitor.record_alert("CRITICAL", "Test alert")
        
        alerts = monitor.get_alerts()
        assert len(alerts) == 1
        assert alerts[0][2] == "Test alert"
    
    def test_has_alert_containing(self):
        """Test checking for alert content."""
        monitor = AlertMonitor()
        monitor.record_alert("WARNING", "Data freshness alert")
        
        assert monitor.has_alert_containing("freshness")
        assert not monitor.has_alert_containing("timeout")


class TestBehaviorMonitor:
    """Test BehaviorMonitor."""
    
    def test_record_trade_event(self):
        """Test recording trade events."""
        monitor = BehaviorMonitor()
        monitor.record_event("trade", {"order_id": "123"})
        
        now = datetime.utcnow()
        trades = monitor.get_trading_events_during(
            now - timedelta(seconds=10),
            now + timedelta(seconds=10)
        )
        assert len(trades) == 1
    
    def test_record_retry_event(self):
        """Test recording retry events."""
        monitor = BehaviorMonitor()
        for i in range(5):
            monitor.record_event("retry", {"operation": "test_op"})
        
        assert monitor.get_retry_count("test_op") == 5


class TestChaosValidator:
    """Test ChaosValidator."""
    
    def test_check_trade_with_stale_data(self, validator):
        """Test detection of trading with stale data."""
        now = datetime.utcnow()
        
        # Set data as stale
        validator.set_data_stale(now - timedelta(seconds=60))
        
        # Record trade during stale period
        validator._behavior_monitor.record_event("trade", {"order_id": "123"})
        
        violation = validator.check_trade_with_stale_data(
            now - timedelta(seconds=120),
            now
        )
        
        assert violation is not None
        assert violation.behavior == ForbiddenBehavior.TRADE_WITH_STALE_DATA
    
    def test_check_infinite_retry(self, validator):
        """Test detection of infinite retry."""
        for i in range(15):
            validator._behavior_monitor.record_event(
                "retry",
                {"operation": "test_op"}
            )
        
        violation = validator.check_infinite_retry()
        
        assert violation is not None
        assert violation.behavior == ForbiddenBehavior.INFINITE_RETRY
    
    def test_check_silent_crash(self, validator):
        """Test detection of silent crash."""
        # No alerts recorded
        violation = validator.check_silent_crash(module_crashed=True)
        
        assert violation is not None
        assert violation.behavior == ForbiddenBehavior.SILENT_CRASH
    
    def test_no_violation_when_alert_present(self, validator):
        """Test no violation when alert is present."""
        validator._alert_monitor.record_alert("CRITICAL", "Module crashed")
        
        violation = validator.check_silent_crash(module_crashed=True)
        
        assert violation is None


# ============================================================
# EXECUTOR TESTS
# ============================================================

class TestChaosTestExecutor:
    """Test ChaosTestExecutor."""
    
    @pytest.mark.asyncio
    async def test_execute_test_dry_run(self, executor, sample_test_case):
        """Test executing a test in DRY_RUN mode."""
        result = await executor.execute_test(sample_test_case)
        
        assert result is not None
        assert result.test_case == sample_test_case
        # In DRY_RUN, tests pass because state is simulated
        assert result.passed
    
    @pytest.mark.asyncio
    async def test_execute_test_run(self, executor, sample_test_case):
        """Test executing a batch of tests."""
        test_cases = [sample_test_case]
        
        test_run = await executor.execute_test_run(
            test_cases=test_cases,
            run_name="Test Run",
        )
        
        assert test_run.total_tests == 1
        assert test_run.run_mode == RunMode.DRY_RUN
    
    @pytest.mark.asyncio
    async def test_execute_test_run_stop_on_failure(self, executor):
        """Test stop on first failure."""
        test_cases = get_all_test_cases()[:3]
        
        test_run = await executor.execute_test_run(
            test_cases=test_cases,
            run_name="Test Run",
            stop_on_first_failure=True,
        )
        
        assert test_run.total_tests == 3
    
    def test_change_run_mode(self, executor):
        """Test changing run mode."""
        assert executor.run_mode == RunMode.DRY_RUN
        
        executor.set_run_mode(RunMode.STAGING)
        
        assert executor.run_mode == RunMode.STAGING


# ============================================================
# TEST CASE LIBRARY TESTS
# ============================================================

class TestTestCaseLibrary:
    """Test predefined test case library."""
    
    def test_get_all_test_cases(self):
        """Test getting all test cases."""
        all_cases = get_all_test_cases()
        
        assert len(all_cases) >= 20  # At least 20 predefined
        assert all(isinstance(tc, ChaosTestCase) for tc in all_cases)
    
    def test_get_critical_test_cases(self):
        """Test getting critical test cases."""
        critical = get_critical_test_cases()
        
        assert all(tc.priority == 1 for tc in critical)
    
    def test_get_test_cases_by_category(self):
        """Test getting test cases by category."""
        data_cases = get_test_cases_by_category(FaultCategory.DATA)
        
        assert len(data_cases) >= 1
        assert all(
            tc.fault_definition.category == FaultCategory.DATA
            for tc in data_cases
        )
    
    def test_get_test_cases_by_tag(self):
        """Test getting test cases by tag."""
        critical_cases = get_test_cases_by_tag("critical")
        
        assert len(critical_cases) >= 1
        assert all("critical" in tc.tags for tc in critical_cases)


# ============================================================
# REPORTER TESTS
# ============================================================

class TestReportGenerator:
    """Test ReportGenerator."""
    
    @pytest.fixture
    def sample_test_run(self, sample_test_case):
        """Create a sample test run."""
        result = ChaosTestResult(
            result_id=str(uuid.uuid4()),
            test_case=sample_test_case,
            passed=True,
            actual_system_state=ExpectedSystemState.DEGRADED,
            actual_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
            alerts_generated=["Data freshness alert"],
            forbidden_behavior_violations=[],
            started_at=datetime.utcnow() - timedelta(seconds=5),
            ended_at=datetime.utcnow(),
        )
        
        return ChaosTestRun(
            run_id=str(uuid.uuid4()),
            run_mode=RunMode.DRY_RUN,
            name="Test Run",
            started_at=datetime.utcnow() - timedelta(seconds=10),
            ended_at=datetime.utcnow(),
            test_results=[result],
            total_tests=1,
            passed_tests=1,
            failed_tests=0,
        )
    
    def test_generate_report(self, report_generator, sample_test_run):
        """Test generating a full report."""
        report = report_generator.generate_report(sample_test_run)
        
        assert report is not None
        assert report.test_run == sample_test_run
        assert report.passed
        assert "run_name" in report.summary
    
    def test_generate_summary_report(self, report_generator, sample_test_run):
        """Test generating a summary report."""
        summary = report_generator.generate_summary_report(sample_test_run)
        
        assert summary["passed"]
        assert summary["total"] == 1
        assert summary["passed_count"] == 1
    
    def test_generate_failure_report(self, report_generator, sample_test_run):
        """Test generating a failure report."""
        failure_report = report_generator.generate_failure_report(sample_test_run)
        
        assert failure_report["total_failures"] == 0


class TestReportStatistics:
    """Test ReportStatistics."""
    
    def test_compute_stats(self, sample_test_case):
        """Test computing statistics."""
        results = [
            ChaosTestResult(
                result_id=str(uuid.uuid4()),
                test_case=sample_test_case,
                passed=True,
                actual_system_state=ExpectedSystemState.DEGRADED,
                actual_trade_guard_decision=ExpectedTradeGuardDecision.BLOCK,
                alerts_generated=[],
                forbidden_behavior_violations=[],
                started_at=datetime.utcnow() - timedelta(seconds=5),
                ended_at=datetime.utcnow(),
            ),
            ChaosTestResult(
                result_id=str(uuid.uuid4()),
                test_case=sample_test_case,
                passed=False,
                actual_system_state=None,
                actual_trade_guard_decision=None,
                alerts_generated=[],
                forbidden_behavior_violations=[],
                started_at=datetime.utcnow() - timedelta(seconds=5),
                ended_at=datetime.utcnow(),
                error_message="Test failure",
            ),
        ]
        
        stats = ReportStatistics(results)
        
        assert stats.total_tests == 2
        assert stats.passed_tests == 1
        assert stats.failed_tests == 1
        assert stats.pass_rate == 50.0


# ============================================================
# INTEGRATION TESTS
# ============================================================

class TestIntegration:
    """Test integration components."""
    
    def test_mock_orchestrator_adapter(self):
        """Test MockOrchestratorAdapter."""
        adapter = MockOrchestratorAdapter()
        
        assert asyncio.run(adapter.get_system_state()) == ExpectedSystemState.RUNNING
        
        adapter.set_state(ExpectedSystemState.DEGRADED)
        assert asyncio.run(adapter.get_system_state()) == ExpectedSystemState.DEGRADED
    
    def test_mock_trade_guard_adapter(self):
        """Test MockTradeGuardAdapter."""
        adapter = MockTradeGuardAdapter()
        
        adapter.set_decision(ExpectedTradeGuardDecision.BLOCK, "Test")
        assert asyncio.run(adapter.get_last_decision()) == ExpectedTradeGuardDecision.BLOCK
        assert asyncio.run(adapter.is_trading_allowed())
    
    def test_mock_monitoring_adapter(self):
        """Test MockMonitoringAdapter."""
        adapter = MockMonitoringAdapter()
        
        asyncio.run(adapter.send_alert("CRITICAL", "Test alert"))
        
        alerts = asyncio.run(
            adapter.get_recent_alerts(datetime.utcnow() - timedelta(seconds=60))
        )
        assert len(alerts) == 1
    
    @pytest.mark.asyncio
    async def test_integration_manager_wire(self):
        """Test wiring integration manager."""
        state_monitor = SystemStateMonitor()
        trade_guard_monitor = TradeGuardMonitor()
        alert_monitor = AlertMonitor()
        behavior_monitor = BehaviorMonitor()
        
        manager = create_mock_integration_manager(
            state_monitor,
            trade_guard_monitor,
            alert_monitor,
            behavior_monitor,
        )
        
        await manager.wire()
        
        # Initial state should be RUNNING
        assert state_monitor.get_current_state() == ExpectedSystemState.RUNNING


# ============================================================
# CLOCK DRIFT SIMULATOR TESTS
# ============================================================

class TestClockDriftSimulator:
    """Test ClockDriftSimulator."""
    
    def test_clock_drift_forward(self):
        """Test clock drift forward."""
        simulator = ClockDriftSimulator()
        
        with simulator.drift(seconds=3600):  # 1 hour forward
            drifted = simulator.get_current_time()
            actual = datetime.utcnow()
            
            # Should be approximately 1 hour ahead
            diff = (drifted - actual).total_seconds()
            assert 3590 < diff < 3610
    
    def test_clock_drift_backward(self):
        """Test clock drift backward."""
        simulator = ClockDriftSimulator()
        
        with simulator.drift(seconds=-3600):  # 1 hour backward
            drifted = simulator.get_current_time()
            actual = datetime.utcnow()
            
            # Should be approximately 1 hour behind
            diff = (actual - drifted).total_seconds()
            assert 3590 < diff < 3610
    
    def test_clock_drift_context_cleanup(self):
        """Test clock drift cleanup after context."""
        simulator = ClockDriftSimulator()
        
        with simulator.drift(seconds=3600):
            pass
        
        # After context, should be back to normal
        drifted = simulator.get_current_time()
        actual = datetime.utcnow()
        diff = abs((drifted - actual).total_seconds())
        assert diff < 1


# ============================================================
# INJECTION POINT DECORATOR TESTS
# ============================================================

class TestInjectionPoint:
    """Test injection_point decorator."""
    
    @pytest.mark.asyncio
    async def test_injection_point_without_fault(self, fault_registry):
        """Test injection point when no fault is active."""
        @injection_point("test.point")
        async def test_function():
            return "success"
        
        result = await test_function()
        assert result == "success"


# ============================================================
# FAULT INJECTION SCOPE TESTS
# ============================================================

class TestFaultInjectionScope:
    """Test fault_injection_scope context manager."""
    
    @pytest.mark.asyncio
    async def test_scope_activates_fault(self, fault_registry, sample_fault_definition):
        """Test that scope activates fault."""
        active_fault = ActiveFault(
            fault_id=sample_fault_definition.fault_id,
            definition=sample_fault_definition,
            started_at=datetime.utcnow(),
        )
        
        async with fault_injection_scope(active_fault, fault_registry):
            assert fault_registry.is_active(sample_fault_definition.fault_id)
        
        # After scope, fault should be inactive
        assert not fault_registry.is_active(sample_fault_definition.fault_id)


# ============================================================
# END-TO-END TESTS
# ============================================================

class TestEndToEnd:
    """End-to-end integration tests."""
    
    @pytest.mark.asyncio
    async def test_full_chaos_test_cycle(self):
        """Test a complete chaos testing cycle."""
        # 1. Create executor
        executor = create_executor(RunMode.DRY_RUN)
        
        # 2. Get test cases
        test_cases = get_critical_test_cases()[:5]
        
        # 3. Execute tests
        test_run = await executor.execute_test_run(
            test_cases=test_cases,
            run_name="E2E Test Run",
        )
        
        # 4. Generate report
        generator = create_report_generator()
        report = generator.generate_report(test_run)
        
        # 5. Validate
        assert test_run.total_tests == 5
        assert report.test_run == test_run
        assert "run_name" in report.summary
    
    @pytest.mark.asyncio
    async def test_category_specific_testing(self):
        """Test running tests for a specific category."""
        executor = create_executor(RunMode.DRY_RUN)
        
        data_tests = get_test_cases_by_category(FaultCategory.DATA)
        
        test_run = await executor.execute_test_run(
            test_cases=data_tests,
            run_name="Data Fault Tests",
        )
        
        assert all(
            r.test_case.fault_definition.category == FaultCategory.DATA
            for r in test_run.test_results
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
