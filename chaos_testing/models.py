"""
Chaos Testing Models.

============================================================
PURPOSE
============================================================
Data models for chaos testing and fault injection.

PHILOSOPHY:
- Assume everything will fail
- Failure is normal, survival is success
- A safe failure is better than a profitable bug
- No silent failure is allowed

============================================================
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum, auto
from typing import Dict, Any, Optional, List, Callable


# ============================================================
# RUN MODES
# ============================================================

class RunMode(Enum):
    """Chaos testing run modes."""
    DRY_RUN = "DRY_RUN"                    # No execution, validation only
    STAGING = "STAGING"                     # Full execution in staging
    SHADOW_PRODUCTION = "SHADOW_PRODUCTION" # Observe only, no actions


# ============================================================
# FAULT CATEGORIES
# ============================================================

class FaultCategory(Enum):
    """Categories of faults that can be injected."""
    DATA = "DATA"               # Data layer faults
    API = "API"                 # API/external dependency faults
    PROCESS = "PROCESS"         # Process/module faults
    EXECUTION = "EXECUTION"     # Order execution faults
    SYSTEM = "SYSTEM"           # Infrastructure faults


class DataFaultType(Enum):
    """Data layer fault types."""
    MISSING_DATA = "MISSING_DATA"
    DELAYED_DATA = "DELAYED_DATA"
    CORRUPTED_DATA = "CORRUPTED_DATA"
    PARTIAL_UPDATE = "PARTIAL_UPDATE"
    DUPLICATE_RECORDS = "DUPLICATE_RECORDS"
    STALE_DATA = "STALE_DATA"
    INVALID_FORMAT = "INVALID_FORMAT"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    NULL_VALUES = "NULL_VALUES"


class ApiFaultType(Enum):
    """API fault types."""
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    AUTH_FAILURE = "AUTH_FAILURE"
    CONNECTION_REFUSED = "CONNECTION_REFUSED"
    SSL_ERROR = "SSL_ERROR"
    DNS_FAILURE = "DNS_FAILURE"
    HTTP_500 = "HTTP_500"
    HTTP_503 = "HTTP_503"
    MALFORMED_JSON = "MALFORMED_JSON"


class ProcessFaultType(Enum):
    """Process fault types."""
    MODULE_CRASH = "MODULE_CRASH"
    INFINITE_LOOP = "INFINITE_LOOP"
    HIGH_LATENCY = "HIGH_LATENCY"
    MEMORY_EXHAUSTION = "MEMORY_EXHAUSTION"
    DEADLOCK = "DEADLOCK"
    UNHANDLED_EXCEPTION = "UNHANDLED_EXCEPTION"
    QUEUE_OVERFLOW = "QUEUE_OVERFLOW"
    HEARTBEAT_MISS = "HEARTBEAT_MISS"


class ExecutionFaultType(Enum):
    """Execution fault types."""
    ORDER_REJECTED = "ORDER_REJECTED"
    PARTIAL_FILL_STUCK = "PARTIAL_FILL_STUCK"
    DUPLICATE_EXECUTION = "DUPLICATE_EXECUTION"
    NETWORK_DISCONNECT = "NETWORK_DISCONNECT"
    FILL_TIMEOUT = "FILL_TIMEOUT"
    PRICE_SLIPPAGE = "PRICE_SLIPPAGE"
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    POSITION_MISMATCH = "POSITION_MISMATCH"
    EXCHANGE_MAINTENANCE = "EXCHANGE_MAINTENANCE"


class SystemFaultType(Enum):
    """System/infrastructure fault types."""
    CLOCK_DRIFT = "CLOCK_DRIFT"
    DISK_FULL = "DISK_FULL"
    CPU_SPIKE = "CPU_SPIKE"
    PROCESS_KILLED = "PROCESS_KILLED"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    REDIS_UNAVAILABLE = "REDIS_UNAVAILABLE"
    NETWORK_PARTITION = "NETWORK_PARTITION"
    CONFIG_CORRUPTION = "CONFIG_CORRUPTION"


# ============================================================
# FAULT INTENSITY
# ============================================================

class FaultIntensity(Enum):
    """Intensity level of fault injection."""
    LOW = "LOW"           # Occasional faults (10% probability)
    MEDIUM = "MEDIUM"     # Regular faults (50% probability)
    HIGH = "HIGH"         # Frequent faults (90% probability)
    ALWAYS = "ALWAYS"     # Every operation fails


# ============================================================
# EXPECTED SYSTEM STATES
# ============================================================

class ExpectedSystemState(Enum):
    """Expected system state after fault injection."""
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    PAUSED = "PAUSED"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    RECOVERING = "RECOVERING"


class ExpectedTradeGuardDecision(Enum):
    """Expected Trade Guard decision."""
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REDUCE_SIZE = "REDUCE_SIZE"
    CLOSE_POSITIONS = "CLOSE_POSITIONS"
    HALT_TRADING = "HALT_TRADING"


# ============================================================
# FAULT DEFINITION
# ============================================================

@dataclass
class FaultDefinition:
    """
    Definition of a fault to inject.
    
    This is the blueprint for a fault, not an active injection.
    """
    fault_id: str
    category: FaultCategory
    fault_type: str  # One of the FaultType enums
    name: str
    description: str
    
    # Injection configuration
    injection_point: str  # Module/function/layer to inject at
    intensity: FaultIntensity = FaultIntensity.ALWAYS
    duration_seconds: Optional[float] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Scheduling
    schedule_type: str = "immediate"  # immediate, delayed, periodic
    delay_seconds: float = 0
    period_seconds: Optional[float] = None
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


# ============================================================
# FAULT INJECTION STATE
# ============================================================

@dataclass
class ActiveFault:
    """
    An actively injected fault.
    """
    injection_id: str
    fault_definition: FaultDefinition
    injected_at: datetime
    expires_at: Optional[datetime]
    injection_count: int = 0
    last_triggered: Optional[datetime] = None
    is_active: bool = True
    
    def should_trigger(self, intensity: FaultIntensity) -> bool:
        """Determine if fault should trigger based on intensity."""
        import random
        probability = {
            FaultIntensity.LOW: 0.1,
            FaultIntensity.MEDIUM: 0.5,
            FaultIntensity.HIGH: 0.9,
            FaultIntensity.ALWAYS: 1.0,
        }
        return random.random() < probability.get(intensity, 1.0)


# ============================================================
# CHAOS TEST CASE
# ============================================================

@dataclass
class ChaosTestCase:
    """
    A chaos test case definition.
    
    Each test case defines:
    - What fault to inject
    - Where to inject it
    - What the expected system reaction should be
    """
    test_id: str
    name: str
    description: str
    
    # Fault specification
    fault_definition: FaultDefinition
    
    # Expected reactions
    expected_system_state: ExpectedSystemState
    expected_trade_guard_decision: ExpectedTradeGuardDecision
    expected_alerts: List[str] = field(default_factory=list)
    
    # Recovery expectations
    should_recover: bool = True
    recovery_timeout_seconds: float = 60.0
    expected_recovery_state: ExpectedSystemState = ExpectedSystemState.RUNNING
    
    # Validation
    validation_timeout_seconds: float = 30.0
    validation_checks: List[str] = field(default_factory=list)
    
    # Metadata
    priority: int = 1  # 1 = highest
    tags: List[str] = field(default_factory=list)
    enabled: bool = True
    
    # Pre/post conditions
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)


# ============================================================
# TEST EXECUTION RESULTS
# ============================================================

class TestResult(Enum):
    """Test result status."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    check_name: str
    passed: bool
    expected: Any
    actual: Any
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ChaosTestResult:
    """
    Result of executing a chaos test case.
    """
    result_id: str
    test_case: ChaosTestCase
    run_id: str
    
    # Execution
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    
    # Result
    result: TestResult = TestResult.PASSED
    
    # System reactions observed
    observed_system_state: Optional[str] = None
    observed_trade_guard_decision: Optional[str] = None
    observed_alerts: List[str] = field(default_factory=list)
    
    # Validation results
    validation_results: List[ValidationResult] = field(default_factory=list)
    
    # Recovery
    recovery_observed: bool = False
    recovery_time_seconds: Optional[float] = None
    
    # Errors
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    
    # Logs
    logs: List[Dict[str, Any]] = field(default_factory=list)
    
    def is_passed(self) -> bool:
        """Check if test passed."""
        return self.result == TestResult.PASSED


# ============================================================
# CHAOS TEST RUN
# ============================================================

@dataclass
class ChaosTestRun:
    """
    A complete chaos test run (multiple test cases).
    """
    run_id: str
    run_mode: RunMode
    
    # Configuration
    test_cases: List[ChaosTestCase]
    parallel_execution: bool = False
    stop_on_first_failure: bool = False
    
    # Execution
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Results
    results: List[ChaosTestResult] = field(default_factory=list)
    
    # Summary
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    error_tests: int = 0
    
    # Metadata
    triggered_by: str = "manual"
    environment: str = "staging"
    notes: str = ""
    
    def update_summary(self) -> None:
        """Update summary counts from results."""
        self.total_tests = len(self.results)
        self.passed_tests = sum(1 for r in self.results if r.result == TestResult.PASSED)
        self.failed_tests = sum(1 for r in self.results if r.result == TestResult.FAILED)
        self.skipped_tests = sum(1 for r in self.results if r.result == TestResult.SKIPPED)
        self.error_tests = sum(1 for r in self.results if r.result == TestResult.ERROR)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_tests == 0:
            return 0.0
        return self.passed_tests / self.total_tests
    
    @property
    def all_passed(self) -> bool:
        """Check if all tests passed."""
        return self.failed_tests == 0 and self.error_tests == 0


# ============================================================
# CHAOS REPORT
# ============================================================

@dataclass
class ChaosReport:
    """
    Comprehensive chaos test report.
    """
    report_id: str
    run: ChaosTestRun
    generated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Summary
    overall_result: TestResult = TestResult.PASSED
    
    # Analysis
    critical_failures: List[ChaosTestResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    # Coverage
    fault_categories_tested: List[str] = field(default_factory=list)
    modules_tested: List[str] = field(default_factory=list)
    
    # Metrics
    avg_detection_time_ms: Optional[float] = None
    avg_recovery_time_seconds: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "report_id": self.report_id,
            "run_id": self.run.run_id,
            "generated_at": self.generated_at.isoformat(),
            "overall_result": self.overall_result.value,
            "summary": {
                "total_tests": self.run.total_tests,
                "passed": self.run.passed_tests,
                "failed": self.run.failed_tests,
                "skipped": self.run.skipped_tests,
                "errors": self.run.error_tests,
                "success_rate": self.run.success_rate,
            },
            "critical_failures": [
                {
                    "test_id": r.test_case.test_id,
                    "name": r.test_case.name,
                    "error": r.error_message,
                }
                for r in self.critical_failures
            ],
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "coverage": {
                "fault_categories": self.fault_categories_tested,
                "modules": self.modules_tested,
            },
            "metrics": {
                "avg_detection_time_ms": self.avg_detection_time_ms,
                "avg_recovery_time_seconds": self.avg_recovery_time_seconds,
            },
        }


# ============================================================
# FORBIDDEN BEHAVIORS (CRITICAL)
# ============================================================

class ForbiddenBehavior(Enum):
    """
    Behaviors that must NEVER occur during chaos testing.
    
    If any of these are detected, the test MUST fail.
    """
    TRADE_WITH_STALE_DATA = "TRADE_WITH_STALE_DATA"
    TRADE_WITH_CORRUPTED_DATA = "TRADE_WITH_CORRUPTED_DATA"
    IGNORE_TRADE_GUARD = "IGNORE_TRADE_GUARD"
    INFINITE_RETRY = "INFINITE_RETRY"
    SILENT_CRASH = "SILENT_CRASH"
    CONTINUE_AFTER_CRITICAL_FAILURE = "CONTINUE_AFTER_CRITICAL_FAILURE"
    EXECUTE_WITHOUT_VALIDATION = "EXECUTE_WITHOUT_VALIDATION"
    BYPASS_RISK_LIMITS = "BYPASS_RISK_LIMITS"


@dataclass
class ForbiddenBehaviorViolation:
    """
    Record of a forbidden behavior violation.
    
    This is a CRITICAL finding.
    """
    violation_id: str
    behavior: ForbiddenBehavior
    detected_at: datetime
    context: Dict[str, Any]
    evidence: str
    severity: str = "CRITICAL"
