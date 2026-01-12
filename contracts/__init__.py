"""
Contracts Package.

============================================================
PURPOSE
============================================================
Formal contracts and enforcement mechanisms for the trading system.

CONTRACTS:
- Exchange Runtime Contract: Defines exchange behavior assumptions
- Exchange Enforcement: Runtime validation and anomaly detection

============================================================
USAGE
============================================================
```python
from contracts import (
    # Contract definitions
    EXCHANGE_AUTHORITY,
    INTERNAL_AUTHORITY,
    ProhibitedAssumption,
    ExchangeFailureType,
    
    # Enforcement
    expects_exchange_failure,
    reconcile_after,
    exchange_operation,
    get_anomaly_reporter,
)

# Decorate exchange operations
@expects_exchange_failure
async def submit_order(request):
    pass

# Report anomalies
reporter = get_anomaly_reporter()
await reporter.report(anomaly)
```

============================================================
"""

# Contract definitions
from .exchange_runtime_contract import (
    # Authority
    AuthorityDomain,
    AuthorityRule,
    EXCHANGE_AUTHORITY,
    INTERNAL_AUTHORITY,
    
    # Assumptions
    ProhibitedAssumption,
    
    # Failures
    ExchangeFailureType,
    
    # Reactions
    MandatoryReaction,
    
    # Execution realism
    ExecutionRealismRule,
    EXECUTION_REALISM,
    
    # Testing
    TestingRequirement,
    
    # Principles
    DESIGN_PRINCIPLES,
    
    # Helpers
    assert_exchange_authority,
    assert_internal_authority,
    validate_no_prohibited_assumption,
    
    # Version
    CONTRACT_VERSION,
    CONTRACT_DATE,
)

# Enforcement mechanisms
from .exchange_enforcement import (
    # Anomaly types
    AnomalyType,
    Anomaly,
    
    # Reporter
    AnomalyReporter,
    get_anomaly_reporter,
    
    # Decorators
    expects_exchange_failure,
    reconcile_after,
    never_assume,
    exchange_operation,
    
    # State divergence
    StateSnapshot,
    StateDivergenceDetector,
    
    # Timeout handling
    TimeoutState,
    TimeoutContext,
    TimeoutResolver,
    
    # Context manager
    exchange_operation_context,
)


__all__ = [
    # Authority
    "AuthorityDomain",
    "AuthorityRule",
    "EXCHANGE_AUTHORITY",
    "INTERNAL_AUTHORITY",
    
    # Assumptions
    "ProhibitedAssumption",
    
    # Failures
    "ExchangeFailureType",
    
    # Reactions
    "MandatoryReaction",
    
    # Execution realism
    "ExecutionRealismRule",
    "EXECUTION_REALISM",
    
    # Testing
    "TestingRequirement",
    
    # Principles
    "DESIGN_PRINCIPLES",
    
    # Contract helpers
    "assert_exchange_authority",
    "assert_internal_authority",
    "validate_no_prohibited_assumption",
    
    # Version
    "CONTRACT_VERSION",
    "CONTRACT_DATE",
    
    # Anomaly types
    "AnomalyType",
    "Anomaly",
    
    # Reporter
    "AnomalyReporter",
    "get_anomaly_reporter",
    
    # Decorators
    "expects_exchange_failure",
    "reconcile_after",
    "never_assume",
    "exchange_operation",
    
    # State divergence
    "StateSnapshot",
    "StateDivergenceDetector",
    
    # Timeout handling
    "TimeoutState",
    "TimeoutContext",
    "TimeoutResolver",
    
    # Context manager
    "exchange_operation_context",
]
