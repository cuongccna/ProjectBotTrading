"""
System Risk Controller - Data Integrity Monitor.

============================================================
PURPOSE
============================================================
Monitors data integrity and freshness.

HALT TRIGGERS:
- DI_MISSING_CRITICAL_DATA: Critical data missing
- DI_STALE_DATA: Data too old
- DI_SCHEMA_MISMATCH: Invalid data structure
- DI_INGESTION_FAILURE: Repeated ingestion failures
- DI_CORRUPTED_PAYLOAD: Corrupted data detected

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
from ..config import DataIntegrityConfig
from .base import (
    BaseMonitor,
    MonitorMeta,
    create_healthy_result,
    create_halt_result,
)


# ============================================================
# DATA STATE SNAPSHOT
# ============================================================

@dataclass
class DataStateSnapshot:
    """
    Snapshot of current data state.
    
    This is provided to the monitor for checking.
    """
    
    # Market Data
    market_data_available: bool = True
    """Whether market data is available."""
    
    market_data_timestamp: Optional[datetime] = None
    """Timestamp of latest market data."""
    
    market_data_symbols_count: int = 0
    """Number of symbols with data."""
    
    expected_symbols_count: int = 0
    """Expected number of symbols."""
    
    # Ingestion Status
    last_ingestion_success: Optional[datetime] = None
    """When last ingestion succeeded."""
    
    ingestion_failures_last_hour: int = 0
    """Failures in the last hour."""
    
    consecutive_ingestion_failures: int = 0
    """Consecutive failures."""
    
    # Schema/Validation
    schema_errors_detected: bool = False
    """Whether schema errors were detected."""
    
    schema_error_details: Optional[str] = None
    """Details of schema errors."""
    
    # Data Quality
    data_completeness_pct: float = 100.0
    """Percentage of expected data that is present."""
    
    # Price Anomalies
    price_anomalies_detected: bool = False
    """Whether price anomalies were detected."""
    
    price_anomaly_details: Optional[Dict[str, Any]] = None
    """Details of price anomalies."""


# ============================================================
# DATA INTEGRITY MONITOR
# ============================================================

class DataIntegrityMonitor(BaseMonitor):
    """
    Monitors data integrity.
    
    Checks:
    1. Market data availability
    2. Market data freshness
    3. Ingestion success rate
    4. Schema validity
    5. Data quality/completeness
    6. Price anomalies
    """
    
    def __init__(
        self,
        config: DataIntegrityConfig,
    ):
        """
        Initialize monitor.
        
        Args:
            config: Data integrity configuration
        """
        self._config = config
        self._consecutive_missing_count = 0
        self._last_data_state: Optional[DataStateSnapshot] = None
    
    @property
    def meta(self) -> MonitorMeta:
        return MonitorMeta(
            name="DataIntegrityMonitor",
            category=TriggerCategory.DATA_INTEGRITY,
            description="Monitors data integrity and freshness",
            is_critical=True,
        )
    
    def update_state(self, state: DataStateSnapshot) -> None:
        """
        Update the data state for monitoring.
        
        Args:
            state: Current data state
        """
        self._last_data_state = state
    
    def _check(self) -> MonitorResult:
        """
        Perform data integrity checks.
        """
        if self._last_data_state is None:
            # No state provided - this is a problem
            self._consecutive_missing_count += 1
            
            if self._consecutive_missing_count >= self._config.market_data_missing_halt_threshold:
                return create_halt_result(
                    monitor_name=self.meta.name,
                    trigger=HaltTrigger.DI_MISSING_CRITICAL_DATA,
                    halt_level=HaltLevel.HARD,
                    message="No data state available for monitoring",
                    details={
                        "consecutive_missing": self._consecutive_missing_count,
                        "threshold": self._config.market_data_missing_halt_threshold,
                    },
                )
            
            return create_healthy_result(
                monitor_name=self.meta.name,
                metrics={"warning": "No data state provided"},
            )
        
        # Reset missing count
        self._consecutive_missing_count = 0
        state = self._last_data_state
        now = datetime.utcnow()
        
        # Check 1: Market Data Availability
        result = self._check_market_data_available(state)
        if result is not None:
            return result
        
        # Check 2: Market Data Freshness
        result = self._check_market_data_freshness(state, now)
        if result is not None:
            return result
        
        # Check 3: Ingestion Failures
        result = self._check_ingestion_failures(state)
        if result is not None:
            return result
        
        # Check 4: Schema Errors
        result = self._check_schema_errors(state)
        if result is not None:
            return result
        
        # Check 5: Data Completeness
        result = self._check_data_completeness(state)
        if result is not None:
            return result
        
        # Check 6: Price Anomalies
        result = self._check_price_anomalies(state)
        if result is not None:
            return result
        
        # All checks passed
        return create_healthy_result(
            monitor_name=self.meta.name,
            metrics={
                "market_data_age_seconds": (
                    (now - state.market_data_timestamp).total_seconds()
                    if state.market_data_timestamp else None
                ),
                "symbols_count": state.market_data_symbols_count,
                "data_completeness_pct": state.data_completeness_pct,
                "ingestion_failures_last_hour": state.ingestion_failures_last_hour,
            },
        )
    
    def _check_market_data_available(
        self,
        state: DataStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check market data is available."""
        if not state.market_data_available:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.DI_MISSING_CRITICAL_DATA,
                halt_level=HaltLevel.HARD,
                message="Market data is not available",
                details={"market_data_available": False},
            )
        return None
    
    def _check_market_data_freshness(
        self,
        state: DataStateSnapshot,
        now: datetime,
    ) -> Optional[MonitorResult]:
        """Check market data is fresh."""
        if state.market_data_timestamp is None:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.DI_STALE_DATA,
                halt_level=HaltLevel.HARD,
                message="Market data timestamp is missing",
            )
        
        age_seconds = (now - state.market_data_timestamp).total_seconds()
        
        if age_seconds > self._config.max_market_data_age_seconds:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.DI_STALE_DATA,
                halt_level=HaltLevel.HARD,
                message=f"Market data is stale: {age_seconds:.1f}s old (max: {self._config.max_market_data_age_seconds}s)",
                details={
                    "age_seconds": age_seconds,
                    "max_age_seconds": self._config.max_market_data_age_seconds,
                    "timestamp": state.market_data_timestamp.isoformat(),
                },
            )
        
        return None
    
    def _check_ingestion_failures(
        self,
        state: DataStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check ingestion failure rate."""
        # Consecutive failures
        if state.consecutive_ingestion_failures >= self._config.max_consecutive_ingestion_failures:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.DI_INGESTION_FAILURE,
                halt_level=HaltLevel.HARD,
                message=f"Too many consecutive ingestion failures: {state.consecutive_ingestion_failures}",
                details={
                    "consecutive_failures": state.consecutive_ingestion_failures,
                    "threshold": self._config.max_consecutive_ingestion_failures,
                },
            )
        
        # Hourly failures
        if state.ingestion_failures_last_hour >= self._config.max_ingestion_failures_per_hour:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.DI_INGESTION_FAILURE,
                halt_level=HaltLevel.SOFT,
                message=f"Too many ingestion failures in last hour: {state.ingestion_failures_last_hour}",
                details={
                    "failures_last_hour": state.ingestion_failures_last_hour,
                    "threshold": self._config.max_ingestion_failures_per_hour,
                },
            )
        
        return None
    
    def _check_schema_errors(
        self,
        state: DataStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check for schema errors."""
        if not self._config.enforce_schema_validation:
            return None
        
        if state.schema_errors_detected:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.DI_SCHEMA_MISMATCH,
                halt_level=HaltLevel.HARD,
                message=f"Schema errors detected: {state.schema_error_details}",
                details={"schema_error": state.schema_error_details},
            )
        
        return None
    
    def _check_data_completeness(
        self,
        state: DataStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check data completeness."""
        if state.data_completeness_pct < self._config.min_data_completeness_pct:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.DI_MISSING_CRITICAL_DATA,
                halt_level=HaltLevel.SOFT,
                message=f"Data completeness below threshold: {state.data_completeness_pct:.1f}% (min: {self._config.min_data_completeness_pct}%)",
                details={
                    "completeness_pct": state.data_completeness_pct,
                    "min_required": self._config.min_data_completeness_pct,
                },
            )
        
        return None
    
    def _check_price_anomalies(
        self,
        state: DataStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check for price anomalies."""
        if state.price_anomalies_detected:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.DI_CORRUPTED_PAYLOAD,
                halt_level=HaltLevel.HARD,
                message="Price anomalies detected - possible data corruption",
                details=state.price_anomaly_details or {},
            )
        
        return None
