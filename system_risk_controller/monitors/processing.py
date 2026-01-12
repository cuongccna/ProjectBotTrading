"""
System Risk Controller - Processing Monitor.

============================================================
PURPOSE
============================================================
Monitors processing pipeline health.

HALT TRIGGERS:
- PR_FEATURE_PIPELINE_ERROR: Feature pipeline errors
- PR_INCONSISTENT_STATE: Inconsistent processing states
- PR_NON_DETERMINISTIC_OUTPUT: Non-deterministic outputs
- PR_VERSION_MISMATCH: Version mismatch
- PR_PROCESSING_TIMEOUT: Processing timeout

============================================================
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from ..types import (
    HaltTrigger,
    HaltLevel,
    TriggerCategory,
    MonitorResult,
)
from ..config import ProcessingConfig
from .base import (
    BaseMonitor,
    MonitorMeta,
    create_healthy_result,
    create_halt_result,
)


# ============================================================
# PROCESSING STATE SNAPSHOT
# ============================================================

@dataclass
class ProcessingStateSnapshot:
    """
    Snapshot of current processing state.
    """
    
    # Feature Pipeline
    feature_pipeline_healthy: bool = True
    """Whether feature pipeline is healthy."""
    
    feature_pipeline_lag_seconds: float = 0.0
    """Lag in feature pipeline."""
    
    feature_pipeline_errors_last_hour: int = 0
    """Errors in the last hour."""
    
    last_feature_update: Optional[datetime] = None
    """When features were last updated."""
    
    # Processing Status
    processing_in_progress: bool = False
    """Whether processing is currently running."""
    
    last_processing_time_seconds: float = 0.0
    """Time taken for last processing run."""
    
    processing_errors: List[str] = field(default_factory=list)
    """Recent processing errors."""
    
    # Consistency
    state_consistent: bool = True
    """Whether state is consistent."""
    
    inconsistency_details: Optional[str] = None
    """Details of any inconsistency."""
    
    # Determinism
    determinism_check_passed: bool = True
    """Whether last determinism check passed."""
    
    last_determinism_check: Optional[datetime] = None
    """When determinism was last checked."""
    
    # Version
    data_version: Optional[str] = None
    """Current data version."""
    
    model_version: Optional[str] = None
    """Current model version."""
    
    expected_data_version: Optional[str] = None
    """Expected data version."""
    
    expected_model_version: Optional[str] = None
    """Expected model version."""


# ============================================================
# PROCESSING MONITOR
# ============================================================

class ProcessingMonitor(BaseMonitor):
    """
    Monitors processing pipeline health.
    
    Checks:
    1. Feature pipeline health
    2. Feature pipeline lag
    3. Processing errors
    4. State consistency
    5. Determinism
    6. Version matching
    """
    
    def __init__(
        self,
        config: ProcessingConfig,
    ):
        """
        Initialize monitor.
        
        Args:
            config: Processing configuration
        """
        self._config = config
        self._last_processing_state: Optional[ProcessingStateSnapshot] = None
    
    @property
    def meta(self) -> MonitorMeta:
        return MonitorMeta(
            name="ProcessingMonitor",
            category=TriggerCategory.PROCESSING,
            description="Monitors processing pipeline health",
            is_critical=True,
        )
    
    def update_state(self, state: ProcessingStateSnapshot) -> None:
        """
        Update the processing state for monitoring.
        
        Args:
            state: Current processing state
        """
        self._last_processing_state = state
    
    def _check(self) -> MonitorResult:
        """
        Perform processing health checks.
        """
        if self._last_processing_state is None:
            return create_healthy_result(
                monitor_name=self.meta.name,
                metrics={"warning": "No processing state provided"},
            )
        
        state = self._last_processing_state
        now = datetime.utcnow()
        
        # Check 1: Feature Pipeline Health
        result = self._check_feature_pipeline_health(state)
        if result is not None:
            return result
        
        # Check 2: Feature Pipeline Lag
        result = self._check_feature_pipeline_lag(state)
        if result is not None:
            return result
        
        # Check 3: Processing Errors
        result = self._check_processing_errors(state)
        if result is not None:
            return result
        
        # Check 4: State Consistency
        result = self._check_state_consistency(state)
        if result is not None:
            return result
        
        # Check 5: Determinism
        result = self._check_determinism(state, now)
        if result is not None:
            return result
        
        # Check 6: Version Match
        result = self._check_version_match(state)
        if result is not None:
            return result
        
        # All checks passed
        return create_healthy_result(
            monitor_name=self.meta.name,
            metrics={
                "feature_pipeline_lag_seconds": state.feature_pipeline_lag_seconds,
                "feature_pipeline_errors_last_hour": state.feature_pipeline_errors_last_hour,
                "last_processing_time_seconds": state.last_processing_time_seconds,
                "state_consistent": state.state_consistent,
                "determinism_ok": state.determinism_check_passed,
            },
        )
    
    def _check_feature_pipeline_health(
        self,
        state: ProcessingStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check feature pipeline is healthy."""
        if not state.feature_pipeline_healthy:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.PR_FEATURE_PIPELINE_ERROR,
                halt_level=HaltLevel.HARD,
                message="Feature pipeline is unhealthy",
                details={"feature_pipeline_healthy": False},
            )
        return None
    
    def _check_feature_pipeline_lag(
        self,
        state: ProcessingStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check feature pipeline lag."""
        if state.feature_pipeline_lag_seconds > self._config.max_feature_pipeline_lag_seconds:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.PR_FEATURE_PIPELINE_ERROR,
                halt_level=HaltLevel.SOFT,
                message=f"Feature pipeline lag too high: {state.feature_pipeline_lag_seconds:.1f}s",
                details={
                    "lag_seconds": state.feature_pipeline_lag_seconds,
                    "max_lag": self._config.max_feature_pipeline_lag_seconds,
                },
            )
        return None
    
    def _check_processing_errors(
        self,
        state: ProcessingStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check processing error rate."""
        if state.feature_pipeline_errors_last_hour >= self._config.max_feature_pipeline_errors_per_hour:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.PR_FEATURE_PIPELINE_ERROR,
                halt_level=HaltLevel.SOFT,
                message=f"Too many feature pipeline errors: {state.feature_pipeline_errors_last_hour}/hour",
                details={
                    "errors_last_hour": state.feature_pipeline_errors_last_hour,
                    "threshold": self._config.max_feature_pipeline_errors_per_hour,
                },
            )
        return None
    
    def _check_state_consistency(
        self,
        state: ProcessingStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check processing state consistency."""
        if not state.state_consistent:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.PR_INCONSISTENT_STATE,
                halt_level=HaltLevel.HARD,
                message=f"Processing state inconsistency: {state.inconsistency_details}",
                details={"inconsistency": state.inconsistency_details},
            )
        return None
    
    def _check_determinism(
        self,
        state: ProcessingStateSnapshot,
        now: datetime,
    ) -> Optional[MonitorResult]:
        """Check processing determinism."""
        if not self._config.check_determinism:
            return None
        
        if not state.determinism_check_passed:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.PR_NON_DETERMINISTIC_OUTPUT,
                halt_level=HaltLevel.HARD,
                message="Non-deterministic processing output detected",
                details={"determinism_check_passed": False},
            )
        
        return None
    
    def _check_version_match(
        self,
        state: ProcessingStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check version matching."""
        if not self._config.enforce_version_match:
            return None
        
        # Check data version
        if (state.data_version is not None and 
            state.expected_data_version is not None and
            state.data_version != state.expected_data_version):
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.PR_VERSION_MISMATCH,
                halt_level=HaltLevel.SOFT,
                message=f"Data version mismatch: {state.data_version} != {state.expected_data_version}",
                details={
                    "data_version": state.data_version,
                    "expected": state.expected_data_version,
                },
            )
        
        # Check model version
        if (state.model_version is not None and
            state.expected_model_version is not None and
            state.model_version != state.expected_model_version):
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.PR_VERSION_MISMATCH,
                halt_level=HaltLevel.SOFT,
                message=f"Model version mismatch: {state.model_version} != {state.expected_model_version}",
                details={
                    "model_version": state.model_version,
                    "expected": state.expected_model_version,
                },
            )
        
        return None
