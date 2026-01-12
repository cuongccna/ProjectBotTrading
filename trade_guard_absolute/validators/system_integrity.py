"""
Trade Guard Absolute - System Integrity Validator.

============================================================
PURPOSE
============================================================
Validates that all system data is fresh, consistent, and 
synchronized.

CHECKS:
- SI_MISSING_MARKET_DATA: No market data available
- SI_STALE_MARKET_DATA: Market data too old
- SI_FEATURE_PIPELINE_DESYNC: Feature pipeline out of sync
- SI_CLOCK_DRIFT: System clock drifted from NTP
- SI_DUPLICATE_REQUEST: Duplicate trade request detected

============================================================
"""

from datetime import datetime
from typing import Optional, Set

from ..types import (
    GuardInput,
    ValidationResult,
    BlockReason,
    BlockSeverity,
    BlockCategory,
)
from ..config import SystemIntegrityConfig
from .base import (
    BaseValidator,
    ValidatorMeta,
    create_pass_result,
    create_block_result,
)


class SystemIntegrityValidator(BaseValidator):
    """
    Validates system integrity.
    
    Ensures all data sources are fresh and synchronized.
    """
    
    def __init__(
        self,
        config: SystemIntegrityConfig,
    ):
        """
        Initialize validator.
        
        Args:
            config: System integrity configuration
        """
        self._config = config
        self._seen_request_ids: Set[str] = set()
        self._request_timestamps: dict = {}  # request_id -> timestamp
    
    @property
    def meta(self) -> ValidatorMeta:
        return ValidatorMeta(
            name="SystemIntegrityValidator",
            category=BlockCategory.SYSTEM_INTEGRITY,
            description="Validates system data freshness and synchronization",
            is_critical=True,
        )
    
    def _validate(self, guard_input: GuardInput) -> ValidationResult:
        """
        Validate system integrity.
        
        Checks performed:
        1. Market data presence and freshness
        2. Feature pipeline synchronization
        3. Clock drift
        4. Request timestamp validity
        5. Duplicate request detection
        """
        now = datetime.utcnow()
        
        # Check 1: Duplicate Request
        result = self._check_duplicate_request(guard_input, now)
        if result is not None:
            return result
        
        # Check 2: Request Timestamp
        result = self._check_request_timestamp(guard_input, now)
        if result is not None:
            return result
        
        # Check 3: Market Data
        result = self._check_market_data(guard_input, now)
        if result is not None:
            return result
        
        # Check 4: Feature Pipeline
        result = self._check_feature_pipeline(guard_input, now)
        if result is not None:
            return result
        
        # Check 5: Clock Drift
        result = self._check_clock_drift(guard_input)
        if result is not None:
            return result
        
        # All checks passed
        return create_pass_result(
            validator_name=self.meta.name,
            details={
                "market_data_age_seconds": (now - guard_input.system_state.market_data_timestamp).total_seconds(),
                "feature_pipeline_synced": guard_input.system_state.feature_pipeline_synced,
                "clock_drift_ms": guard_input.system_state.clock_drift_ms,
            },
        )
    
    def _check_duplicate_request(
        self,
        guard_input: GuardInput,
        now: datetime,
    ) -> Optional[ValidationResult]:
        """Check for duplicate request."""
        request_id = guard_input.trade_intent.request_id
        
        # Clean old entries
        self._cleanup_request_cache(now)
        
        # Check if seen
        if request_id in self._seen_request_ids:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SI_DUPLICATE_REQUEST,
                severity=BlockSeverity.HIGH,
                details={
                    "request_id": request_id,
                    "message": "Duplicate request detected",
                },
            )
        
        # Add to cache
        self._seen_request_ids.add(request_id)
        self._request_timestamps[request_id] = now
        
        return None
    
    def _cleanup_request_cache(self, now: datetime) -> None:
        """Remove expired entries from request cache."""
        window = self._config.duplicate_window_seconds
        expired = []
        
        for request_id, timestamp in self._request_timestamps.items():
            age = (now - timestamp).total_seconds()
            if age > window:
                expired.append(request_id)
        
        for request_id in expired:
            self._seen_request_ids.discard(request_id)
            del self._request_timestamps[request_id]
    
    def _check_request_timestamp(
        self,
        guard_input: GuardInput,
        now: datetime,
    ) -> Optional[ValidationResult]:
        """Check request timestamp is valid."""
        request_time = guard_input.trade_intent.timestamp
        age_seconds = (now - request_time).total_seconds()
        
        # Too old
        if age_seconds > self._config.max_request_age_seconds:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SI_STALE_MARKET_DATA,
                severity=BlockSeverity.MEDIUM,
                details={
                    "request_timestamp": request_time.isoformat(),
                    "age_seconds": age_seconds,
                    "max_age_seconds": self._config.max_request_age_seconds,
                    "message": f"Request is {age_seconds:.1f}s old",
                },
            )
        
        # In the future
        if age_seconds < -self._config.max_future_timestamp_seconds:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SI_CLOCK_DRIFT,
                severity=BlockSeverity.HIGH,
                details={
                    "request_timestamp": request_time.isoformat(),
                    "now": now.isoformat(),
                    "future_seconds": abs(age_seconds),
                    "message": "Request timestamp is in the future",
                },
            )
        
        return None
    
    def _check_market_data(
        self,
        guard_input: GuardInput,
        now: datetime,
    ) -> Optional[ValidationResult]:
        """Check market data presence and freshness."""
        state = guard_input.system_state
        
        # Check presence
        if state.market_data_available is False:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SI_MISSING_MARKET_DATA,
                severity=BlockSeverity.CRITICAL,
                details={
                    "symbol": guard_input.trade_intent.symbol,
                    "message": "No market data available",
                },
            )
        
        # Check freshness
        market_data_age = (now - state.market_data_timestamp).total_seconds()
        
        if market_data_age > self._config.max_market_data_age_seconds:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SI_STALE_MARKET_DATA,
                severity=BlockSeverity.HIGH,
                details={
                    "market_data_age_seconds": market_data_age,
                    "max_age_seconds": self._config.max_market_data_age_seconds,
                    "market_data_timestamp": state.market_data_timestamp.isoformat(),
                    "message": f"Market data is {market_data_age:.1f}s old",
                },
            )
        
        # Check symbol coverage
        if state.symbol_coverage_pct is not None:
            if state.symbol_coverage_pct < self._config.min_symbol_coverage_pct:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.SI_MISSING_MARKET_DATA,
                    severity=BlockSeverity.HIGH,
                    details={
                        "symbol_coverage_pct": state.symbol_coverage_pct,
                        "min_coverage_pct": self._config.min_symbol_coverage_pct,
                        "message": "Symbol coverage below threshold",
                    },
                )
        
        return None
    
    def _check_feature_pipeline(
        self,
        guard_input: GuardInput,
        now: datetime,
    ) -> Optional[ValidationResult]:
        """Check feature pipeline synchronization."""
        if not self._config.require_feature_sync:
            return None
        
        state = guard_input.system_state
        
        # Check sync status
        if not state.feature_pipeline_synced:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SI_FEATURE_PIPELINE_DESYNC,
                severity=BlockSeverity.HIGH,
                details={
                    "feature_pipeline_synced": False,
                    "message": "Feature pipeline is not synchronized",
                },
            )
        
        # Check lag if available
        if state.feature_pipeline_lag_seconds is not None:
            if state.feature_pipeline_lag_seconds > self._config.max_feature_pipeline_lag_seconds:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.SI_FEATURE_PIPELINE_DESYNC,
                    severity=BlockSeverity.HIGH,
                    details={
                        "feature_pipeline_lag_seconds": state.feature_pipeline_lag_seconds,
                        "max_lag_seconds": self._config.max_feature_pipeline_lag_seconds,
                        "message": f"Feature pipeline lag: {state.feature_pipeline_lag_seconds:.1f}s",
                    },
                )
        
        return None
    
    def _check_clock_drift(
        self,
        guard_input: GuardInput,
    ) -> Optional[ValidationResult]:
        """Check system clock drift."""
        if not self._config.require_ntp_sync:
            return None
        
        state = guard_input.system_state
        
        # Check NTP sync if available
        if hasattr(state, 'ntp_synced') and state.ntp_synced is False:
            return create_block_result(
                validator_name=self.meta.name,
                reason=BlockReason.SI_CLOCK_DRIFT,
                severity=BlockSeverity.HIGH,
                details={
                    "ntp_synced": False,
                    "message": "System clock not synchronized with NTP",
                },
            )
        
        # Check drift magnitude
        if state.clock_drift_ms is not None:
            if abs(state.clock_drift_ms) > self._config.max_clock_drift_ms:
                return create_block_result(
                    validator_name=self.meta.name,
                    reason=BlockReason.SI_CLOCK_DRIFT,
                    severity=BlockSeverity.HIGH,
                    details={
                        "clock_drift_ms": state.clock_drift_ms,
                        "max_drift_ms": self._config.max_clock_drift_ms,
                        "message": f"Clock drift: {state.clock_drift_ms}ms",
                    },
                )
        
        return None
    
    def clear_cache(self) -> None:
        """Clear the request cache. For testing."""
        self._seen_request_ids.clear()
        self._request_timestamps.clear()
