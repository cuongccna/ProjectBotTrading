"""
System Risk Controller - Guards.

============================================================
PURPOSE
============================================================
Pre-execution guards that CANNOT be bypassed.

Guards run BEFORE any strategy or execution and validate
critical system invariants.

============================================================
GUARDS
============================================================
- DataRealityGuard: Validates market data freshness and accuracy

============================================================
"""

from .data_reality import (
    DataRealityGuard,
    DataRealityGuardConfig,
    DataRealityCheckResult,
    run_data_reality_check,
)


__all__ = [
    "DataRealityGuard",
    "DataRealityGuardConfig",
    "DataRealityCheckResult",
    "run_data_reality_check",
]
