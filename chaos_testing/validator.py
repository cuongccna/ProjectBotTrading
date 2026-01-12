"""
Chaos Test Validator.

============================================================
PURPOSE
============================================================
Validates system reactions to injected faults.

This module verifies that:
1. System transitions to expected state
2. Trade Guard makes correct decision
3. Expected alerts are generated
4. No forbidden behaviors occur
5. System recovers properly

============================================================
FORBIDDEN BEHAVIORS
============================================================
The validator actively checks for these violations:

1. TRADE_WITH_STALE_DATA - Trading when data is stale
2. IGNORE_TRADE_GUARD - Bypassing Trade Guard decisions
3. INFINITE_RETRY - Retrying indefinitely without backoff
4. SILENT_CRASH - Crashing without alerting
5. CONTINUE_AFTER_CRITICAL - Operating after critical failure
6. MISSING_AUDIT_TRAIL - Not logging security events
7. IGNORE_RATE_LIMIT - Not respecting rate limits
8. SKIP_RECONCILIATION - Not verifying position state

============================================================
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .models import (
    ChaosTestCase,
    ChaosTestResult,
    ExpectedSystemState,
    ExpectedTradeGuardDecision,
    ForbiddenBehavior,
    ForbiddenBehaviorViolation,
)


logger = logging.getLogger(__name__)


# ============================================================
# SYSTEM STATE MONITOR
# ============================================================

class SystemStateMonitor:
    """Monitors and tracks system state changes."""
    
    def __init__(self):
        self._current_state: Optional[ExpectedSystemState] = None
        self._state_history: List[Tuple[datetime, ExpectedSystemState]] = []
        self._state_callbacks: List[Callable] = []
        
    def update_state(self, new_state: ExpectedSystemState) -> None:
        """Update the current system state."""
        self._state_history.append((datetime.utcnow(), new_state))
        self._current_state = new_state
        
        for callback in self._state_callbacks:
            try:
                callback(new_state)
            except Exception as e:
                logger.error(f"State callback error: {e}")
    
    def get_current_state(self) -> Optional[ExpectedSystemState]:
        """Get current system state."""
        return self._current_state
    
    def get_state_history(self) -> List[Tuple[datetime, ExpectedSystemState]]:
        """Get state transition history."""
        return list(self._state_history)
    
    def register_callback(self, callback: Callable) -> None:
        """Register a state change callback."""
        self._state_callbacks.append(callback)
    
    def clear(self) -> None:
        """Clear state history."""
        self._state_history.clear()
        self._current_state = None


# ============================================================
# TRADE GUARD MONITOR
# ============================================================

class TradeGuardMonitor:
    """Monitors Trade Guard decisions."""
    
    def __init__(self):
        self._decisions: List[Tuple[datetime, ExpectedTradeGuardDecision, str]] = []
        self._last_decision: Optional[ExpectedTradeGuardDecision] = None
        
    def record_decision(
        self,
        decision: ExpectedTradeGuardDecision,
        reason: str = "",
    ) -> None:
        """Record a Trade Guard decision."""
        self._decisions.append((datetime.utcnow(), decision, reason))
        self._last_decision = decision
    
    def get_last_decision(self) -> Optional[ExpectedTradeGuardDecision]:
        """Get most recent decision."""
        return self._last_decision
    
    def get_all_decisions(self) -> List[Tuple[datetime, ExpectedTradeGuardDecision, str]]:
        """Get all recorded decisions."""
        return list(self._decisions)
    
    def had_decision(self, decision: ExpectedTradeGuardDecision) -> bool:
        """Check if a specific decision was made."""
        return any(d[1] == decision for d in self._decisions)
    
    def clear(self) -> None:
        """Clear decision history."""
        self._decisions.clear()
        self._last_decision = None


# ============================================================
# ALERT MONITOR
# ============================================================

class AlertMonitor:
    """Monitors generated alerts."""
    
    def __init__(self):
        self._alerts: List[Tuple[datetime, str, str]] = []  # (timestamp, tier, message)
        
    def record_alert(self, tier: str, message: str) -> None:
        """Record an alert."""
        self._alerts.append((datetime.utcnow(), tier, message))
    
    def get_alerts(self) -> List[Tuple[datetime, str, str]]:
        """Get all recorded alerts."""
        return list(self._alerts)
    
    def get_alert_messages(self) -> List[str]:
        """Get all alert messages."""
        return [a[2] for a in self._alerts]
    
    def has_alert_containing(self, substring: str) -> bool:
        """Check if any alert contains substring."""
        return any(substring.lower() in a[2].lower() for a in self._alerts)
    
    def clear(self) -> None:
        """Clear recorded alerts."""
        self._alerts.clear()


# ============================================================
# BEHAVIOR MONITOR
# ============================================================

class BehaviorMonitor:
    """Monitors for forbidden behaviors."""
    
    def __init__(self):
        self._events: List[Dict[str, Any]] = []
        self._trading_events: List[Dict[str, Any]] = []
        self._retry_counts: Dict[str, int] = {}
        self._last_reconciliation: Optional[datetime] = None
        self._audit_events: List[Dict[str, Any]] = []
        
    def record_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Record a system event."""
        event = {
            "timestamp": datetime.utcnow(),
            "type": event_type,
            "data": data,
        }
        self._events.append(event)
        
        if event_type == "trade":
            self._trading_events.append(event)
        elif event_type == "retry":
            operation = data.get("operation", "unknown")
            self._retry_counts[operation] = self._retry_counts.get(operation, 0) + 1
        elif event_type == "reconciliation":
            self._last_reconciliation = datetime.utcnow()
        elif event_type == "audit":
            self._audit_events.append(event)
    
    def get_trading_events_during(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Dict[str, Any]]:
        """Get trading events within time window."""
        return [
            e for e in self._trading_events
            if start_time <= e["timestamp"] <= end_time
        ]
    
    def get_retry_count(self, operation: str) -> int:
        """Get retry count for operation."""
        return self._retry_counts.get(operation, 0)
    
    def get_last_reconciliation(self) -> Optional[datetime]:
        """Get last reconciliation time."""
        return self._last_reconciliation
    
    def get_audit_events(self) -> List[Dict[str, Any]]:
        """Get audit events."""
        return list(self._audit_events)
    
    def clear(self) -> None:
        """Clear all monitoring data."""
        self._events.clear()
        self._trading_events.clear()
        self._retry_counts.clear()
        self._last_reconciliation = None
        self._audit_events.clear()


# ============================================================
# CHAOS VALIDATOR
# ============================================================

class ChaosValidator:
    """
    Validates system behavior during chaos testing.
    
    This is the core validation engine that verifies the system
    behaves correctly when faults are injected.
    """
    
    # Maximum allowed retries before flagging infinite retry
    MAX_ALLOWED_RETRIES = 10
    
    # Maximum time without reconciliation (seconds)
    MAX_RECONCILIATION_GAP = 300
    
    def __init__(
        self,
        state_monitor: SystemStateMonitor,
        trade_guard_monitor: TradeGuardMonitor,
        alert_monitor: AlertMonitor,
        behavior_monitor: BehaviorMonitor,
    ):
        self._state_monitor = state_monitor
        self._trade_guard_monitor = trade_guard_monitor
        self._alert_monitor = alert_monitor
        self._behavior_monitor = behavior_monitor
        
        self._data_stale_since: Optional[datetime] = None
        self._critical_failure_since: Optional[datetime] = None
        self._trade_guard_blocked: bool = False
        self._rate_limited_until: Optional[datetime] = None
    
    def set_data_stale(self, stale_since: datetime) -> None:
        """Mark data as stale."""
        self._data_stale_since = stale_since
    
    def clear_data_stale(self) -> None:
        """Clear stale data flag."""
        self._data_stale_since = None
    
    def set_critical_failure(self, since: datetime) -> None:
        """Mark critical failure."""
        self._critical_failure_since = since
    
    def clear_critical_failure(self) -> None:
        """Clear critical failure."""
        self._critical_failure_since = None
    
    def set_trade_guard_blocked(self, blocked: bool) -> None:
        """Set Trade Guard block status."""
        self._trade_guard_blocked = blocked
    
    def set_rate_limited(self, until: datetime) -> None:
        """Set rate limit expiry."""
        self._rate_limited_until = until
    
    # ========================================================
    # FORBIDDEN BEHAVIOR CHECKS
    # ========================================================
    
    def check_trade_with_stale_data(
        self,
        test_start_time: datetime,
        test_end_time: datetime,
    ) -> Optional[ForbiddenBehaviorViolation]:
        """Check for trading with stale data."""
        if self._data_stale_since is None:
            return None
        
        # Get trading events during stale period
        trades = self._behavior_monitor.get_trading_events_during(
            self._data_stale_since,
            test_end_time,
        )
        
        if trades:
            return ForbiddenBehaviorViolation(
                behavior=ForbiddenBehavior.TRADE_WITH_STALE_DATA,
                description="Trading occurred with stale data",
                detected_at=trades[0]["timestamp"],
                evidence={
                    "data_stale_since": self._data_stale_since.isoformat(),
                    "trades_during_stale": len(trades),
                    "first_trade": trades[0],
                },
            )
        return None
    
    def check_ignore_trade_guard(
        self,
        test_start_time: datetime,
        test_end_time: datetime,
    ) -> Optional[ForbiddenBehaviorViolation]:
        """Check for ignoring Trade Guard decisions."""
        if not self._trade_guard_blocked:
            return None
        
        # Get trading events while blocked
        trades = self._behavior_monitor.get_trading_events_during(
            test_start_time,
            test_end_time,
        )
        
        if trades:
            return ForbiddenBehaviorViolation(
                behavior=ForbiddenBehavior.IGNORE_TRADE_GUARD,
                description="Trading occurred while Trade Guard blocked",
                detected_at=trades[0]["timestamp"],
                evidence={
                    "trades_while_blocked": len(trades),
                    "first_trade": trades[0],
                },
            )
        return None
    
    def check_infinite_retry(self) -> Optional[ForbiddenBehaviorViolation]:
        """Check for infinite retry loops."""
        for operation, count in self._behavior_monitor._retry_counts.items():
            if count > self.MAX_ALLOWED_RETRIES:
                return ForbiddenBehaviorViolation(
                    behavior=ForbiddenBehavior.INFINITE_RETRY,
                    description=f"Excessive retries for operation: {operation}",
                    detected_at=datetime.utcnow(),
                    evidence={
                        "operation": operation,
                        "retry_count": count,
                        "max_allowed": self.MAX_ALLOWED_RETRIES,
                    },
                )
        return None
    
    def check_silent_crash(
        self,
        module_crashed: bool,
    ) -> Optional[ForbiddenBehaviorViolation]:
        """Check for crashes without alerts."""
        if not module_crashed:
            return None
        
        # Check if any alert was generated
        alerts = self._alert_monitor.get_alerts()
        if not alerts:
            return ForbiddenBehaviorViolation(
                behavior=ForbiddenBehavior.SILENT_CRASH,
                description="Module crashed without generating alert",
                detected_at=datetime.utcnow(),
                evidence={"alert_count": 0},
            )
        return None
    
    def check_continue_after_critical(
        self,
        test_end_time: datetime,
    ) -> Optional[ForbiddenBehaviorViolation]:
        """Check for continued operation after critical failure."""
        if self._critical_failure_since is None:
            return None
        
        trades = self._behavior_monitor.get_trading_events_during(
            self._critical_failure_since,
            test_end_time,
        )
        
        if trades:
            return ForbiddenBehaviorViolation(
                behavior=ForbiddenBehavior.CONTINUE_AFTER_CRITICAL,
                description="Trading continued after critical failure",
                detected_at=trades[0]["timestamp"],
                evidence={
                    "critical_failure_at": self._critical_failure_since.isoformat(),
                    "trades_after": len(trades),
                },
            )
        return None
    
    def check_missing_audit_trail(
        self,
        required_events: List[str],
    ) -> Optional[ForbiddenBehaviorViolation]:
        """Check for missing audit trail."""
        audit_events = self._behavior_monitor.get_audit_events()
        audit_types = {e["data"].get("event_type") for e in audit_events}
        
        missing = set(required_events) - audit_types
        if missing:
            return ForbiddenBehaviorViolation(
                behavior=ForbiddenBehavior.MISSING_AUDIT_TRAIL,
                description="Required audit events missing",
                detected_at=datetime.utcnow(),
                evidence={
                    "required": list(required_events),
                    "found": list(audit_types),
                    "missing": list(missing),
                },
            )
        return None
    
    def check_ignore_rate_limit(
        self,
        test_end_time: datetime,
    ) -> Optional[ForbiddenBehaviorViolation]:
        """Check for ignoring rate limits."""
        if self._rate_limited_until is None:
            return None
        
        if test_end_time < self._rate_limited_until:
            # Still within rate limit window
            trades = self._behavior_monitor.get_trading_events_during(
                datetime.utcnow(),
                self._rate_limited_until,
            )
            if trades:
                return ForbiddenBehaviorViolation(
                    behavior=ForbiddenBehavior.IGNORE_RATE_LIMIT,
                    description="Trading during rate limit period",
                    detected_at=trades[0]["timestamp"],
                    evidence={
                        "rate_limited_until": self._rate_limited_until.isoformat(),
                        "trades_during": len(trades),
                    },
                )
        return None
    
    def check_skip_reconciliation(
        self,
        test_duration: timedelta,
    ) -> Optional[ForbiddenBehaviorViolation]:
        """Check for skipped reconciliation."""
        last_recon = self._behavior_monitor.get_last_reconciliation()
        
        if last_recon is None and test_duration.total_seconds() > self.MAX_RECONCILIATION_GAP:
            return ForbiddenBehaviorViolation(
                behavior=ForbiddenBehavior.SKIP_RECONCILIATION,
                description="No reconciliation performed during test",
                detected_at=datetime.utcnow(),
                evidence={
                    "test_duration_seconds": test_duration.total_seconds(),
                    "max_gap_seconds": self.MAX_RECONCILIATION_GAP,
                },
            )
        
        if last_recon:
            gap = (datetime.utcnow() - last_recon).total_seconds()
            if gap > self.MAX_RECONCILIATION_GAP:
                return ForbiddenBehaviorViolation(
                    behavior=ForbiddenBehavior.SKIP_RECONCILIATION,
                    description="Reconciliation gap too long",
                    detected_at=datetime.utcnow(),
                    evidence={
                        "last_reconciliation": last_recon.isoformat(),
                        "gap_seconds": gap,
                        "max_gap_seconds": self.MAX_RECONCILIATION_GAP,
                    },
                )
        return None
    
    # ========================================================
    # FULL VALIDATION
    # ========================================================
    
    async def validate_test_case(
        self,
        test_case: ChaosTestCase,
        test_start_time: datetime,
        test_end_time: datetime,
        module_crashed: bool = False,
    ) -> ChaosTestResult:
        """
        Validate a chaos test case result.
        
        Returns a ChaosTestResult with:
        - Whether expected state was reached
        - Whether Trade Guard made correct decision
        - Whether expected alerts were generated
        - Any forbidden behavior violations
        - Overall pass/fail
        """
        import uuid
        
        violations: List[ForbiddenBehaviorViolation] = []
        validation_errors: List[str] = []
        
        # Check expected system state
        current_state = self._state_monitor.get_current_state()
        state_ok = current_state == test_case.expected_system_state
        if not state_ok:
            validation_errors.append(
                f"Expected state {test_case.expected_system_state.value}, "
                f"got {current_state.value if current_state else 'None'}"
            )
        
        # Check Trade Guard decision
        last_decision = self._trade_guard_monitor.get_last_decision()
        trade_guard_ok = last_decision == test_case.expected_trade_guard_decision
        if not trade_guard_ok:
            validation_errors.append(
                f"Expected Trade Guard decision {test_case.expected_trade_guard_decision.value}, "
                f"got {last_decision.value if last_decision else 'None'}"
            )
        
        # Check expected alerts
        alerts_ok = True
        for expected_alert in test_case.expected_alerts:
            if not self._alert_monitor.has_alert_containing(expected_alert):
                alerts_ok = False
                validation_errors.append(f"Missing expected alert: {expected_alert}")
        
        # Check forbidden behaviors
        test_duration = test_end_time - test_start_time
        
        violation = self.check_trade_with_stale_data(test_start_time, test_end_time)
        if violation:
            violations.append(violation)
        
        violation = self.check_ignore_trade_guard(test_start_time, test_end_time)
        if violation:
            violations.append(violation)
        
        violation = self.check_infinite_retry()
        if violation:
            violations.append(violation)
        
        violation = self.check_silent_crash(module_crashed)
        if violation:
            violations.append(violation)
        
        violation = self.check_continue_after_critical(test_end_time)
        if violation:
            violations.append(violation)
        
        violation = self.check_ignore_rate_limit(test_end_time)
        if violation:
            violations.append(violation)
        
        # Determine pass/fail
        passed = (
            state_ok and
            trade_guard_ok and
            alerts_ok and
            len(violations) == 0
        )
        
        return ChaosTestResult(
            result_id=str(uuid.uuid4()),
            test_case=test_case,
            passed=passed,
            actual_system_state=current_state,
            actual_trade_guard_decision=last_decision,
            alerts_generated=self._alert_monitor.get_alert_messages(),
            forbidden_behavior_violations=violations,
            started_at=test_start_time,
            ended_at=test_end_time,
            error_message="; ".join(validation_errors) if validation_errors else None,
        )
    
    def reset(self) -> None:
        """Reset validator state."""
        self._data_stale_since = None
        self._critical_failure_since = None
        self._trade_guard_blocked = False
        self._rate_limited_until = None
        
        self._state_monitor.clear()
        self._trade_guard_monitor.clear()
        self._alert_monitor.clear()
        self._behavior_monitor.clear()


# ============================================================
# FACTORY FUNCTION
# ============================================================

def create_validator() -> ChaosValidator:
    """Create a fully wired ChaosValidator."""
    return ChaosValidator(
        state_monitor=SystemStateMonitor(),
        trade_guard_monitor=TradeGuardMonitor(),
        alert_monitor=AlertMonitor(),
        behavior_monitor=BehaviorMonitor(),
    )
