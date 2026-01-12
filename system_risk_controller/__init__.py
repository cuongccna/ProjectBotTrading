"""
System Risk Controller - Package.

============================================================
                    ⚠️  WARNING  ⚠️
============================================================

THIS MODULE HAS ABSOLUTE AUTHORITY OVER THE ENTIRE SYSTEM.

It can:
- HALT all trading immediately
- OVERRIDE all other components
- PREVENT any trading activity
- FORCE position closure in emergency

NOTHING CAN BYPASS THIS CONTROLLER.

============================================================
                    CRITICAL PRINCIPLE
============================================================

    "If the system cannot TRUST its own data, state, or 
     execution, IT MUST STOP."

    Profit is irrelevant.
    Continuity is irrelevant.
    Safety is absolute.

============================================================
                       SYSTEM STATES
============================================================

RUNNING:
    Normal operation. Trading allowed.

DEGRADED:
    Reduced functionality. Trading with caution.

HALTED_SOFT:
    Pause new trades. Allow position management.

HALTED_HARD:
    Freeze trading. Cancel pending orders.
    MANUAL RESUME REQUIRED.

EMERGENCY_LOCKDOWN:
    Close positions. Full lockdown.
    MANUAL RESUME REQUIRED + CONFIRMATION.

============================================================
                       HALT LEVELS
============================================================

SOFT (Level 1):
    - Pause new position opening
    - Allow position management
    - Auto-resume possible

HARD (Level 2):
    - Cancel all pending orders
    - Freeze position changes
    - MANUAL RESUME REQUIRED

EMERGENCY (Level 3):
    - Close all positions immediately
    - Disable all execution
    - MANUAL RESUME REQUIRED + CONFIRMATION

============================================================
                     TRIGGER CATEGORIES
============================================================

DATA_INTEGRITY (DI_):
    Missing data, stale data, schema errors

PROCESSING (PR_):
    Pipeline failures, inconsistent state

EXECUTION (EX_):
    Order rejections, position mismatch, slippage

CONTROL (CT_):
    Drawdown limits, leverage limits, loss limits

INFRASTRUCTURE (IF_):
    VPS issues, network, database, disk, memory

MANUAL (MN_):
    Operator halt, emergency stop, maintenance

INTERNAL (IN_):
    Controller errors, state corruption

============================================================
                        USAGE
============================================================

```python
from system_risk_controller import (
    SystemRiskController,
    SystemRiskControllerConfig,
    get_controller,
    init_controller,
)

# Initialize controller
config = SystemRiskControllerConfig()
controller = init_controller(config)

# Start monitoring
await controller.start()

# Check before trading
if controller.can_trade():
    # OK to trade
else:
    # System is halted

# Manual halt
await controller.request_halt(
    trigger=HaltTrigger.MN_OPERATOR_HALT,
    level=HaltLevel.HARD,
    reason="Suspicious activity",
    operator="admin",
)

# Manual resume
await controller.request_resume(ResumeRequest(
    operator="admin",
    reason="Issue resolved",
    acknowledged=True,
))

await controller.stop()
```

============================================================
"""

# Types
from .types import (
    SystemState,
    HaltLevel,
    TriggerCategory,
    HaltTrigger,
    HaltEvent,
    StateTransition,
    MonitorResult,
    SystemHealthSnapshot,
    ResumeRequest,
    SystemRiskControllerError,
    InvalidStateTransitionError,
    ResumeNotAllowedError,
)

# Configuration
from .config import (
    DataIntegrityConfig,
    ProcessingConfig,
    ExecutionConfig,
    ControlConfig,
    InfrastructureConfig,
    AlertingConfig,
    MonitorTimingConfig,
    ResumeConfig,
    DataRealityGuardConfig,
    SystemRiskControllerConfig,
)

# State Machine
from .state_machine import (
    StateMachine,
    StateGuard,
    ALLOWED_TRANSITIONS,
    MANUAL_RESUME_REQUIRED,
    HALT_LEVEL_TO_STATE,
    STATE_SEVERITY,
)

# Engine
from .engine import (
    SystemRiskController,
    get_controller,
    init_controller,
    require_trading_allowed,
    require_not_halted,
)

# Monitors
from .monitors import (
    BaseMonitor,
    MonitorMeta,
    DataIntegrityMonitor,
    DataStateSnapshot,
    ProcessingMonitor,
    ProcessingStateSnapshot,
    ExecutionMonitor,
    ExecutionStateSnapshot,
    ControlMonitor,
    ControlStateSnapshot,
    InfrastructureMonitor,
    InfrastructureStateSnapshot,
)

# Alerting
from .alerting import (
    Alert,
    AlertPriority,
    AlertSender,
    TelegramAlertSender,
    ConsoleAlertSender,
    AlertingService,
)

# Repository
from .repository import SystemRiskControllerRepository

# Models
from .models import (
    HaltEventModel,
    StateTransitionModel,
    ResumeRequestModel,
    SystemStateSnapshotModel,
)

# Guards
from .guards.data_reality import (
    DataRealityGuard,
    DataRealityCheckResult,
)


__all__ = [
    # Types
    "SystemState",
    "HaltLevel",
    "TriggerCategory",
    "HaltTrigger",
    "HaltEvent",
    "StateTransition",
    "MonitorResult",
    "SystemHealthSnapshot",
    "ResumeRequest",
    "SystemRiskControllerError",
    "InvalidStateTransitionError",
    "ResumeNotAllowedError",
    # Configuration
    "DataIntegrityConfig",
    "ProcessingConfig",
    "ExecutionConfig",
    "ControlConfig",
    "InfrastructureConfig",
    "AlertingConfig",
    "MonitorTimingConfig",
    "ResumeConfig",
    "DataRealityGuardConfig",
    "SystemRiskControllerConfig",
    # State Machine
    "StateMachine",
    "StateGuard",
    "ALLOWED_TRANSITIONS",
    "MANUAL_RESUME_REQUIRED",
    "HALT_LEVEL_TO_STATE",
    "STATE_SEVERITY",
    # Engine
    "SystemRiskController",
    "get_controller",
    "init_controller",
    "require_trading_allowed",
    "require_not_halted",
    # Monitors
    "BaseMonitor",
    "MonitorMeta",
    "DataIntegrityMonitor",
    "DataStateSnapshot",
    "ProcessingMonitor",
    "ProcessingStateSnapshot",
    "ExecutionMonitor",
    "ExecutionStateSnapshot",
    "ControlMonitor",
    "ControlStateSnapshot",
    "InfrastructureMonitor",
    "InfrastructureStateSnapshot",
    # Alerting
    "Alert",
    "AlertPriority",
    "AlertSender",
    "TelegramAlertSender",
    "ConsoleAlertSender",
    "AlertingService",
    # Repository
    "SystemRiskControllerRepository",
    # Models
    "HaltEventModel",
    "StateTransitionModel",
    "ResumeRequestModel",
    "SystemStateSnapshotModel",
    # Guards
    "DataRealityGuard",
    "DataRealityCheckResult",
]
