"""
Exchange Contract Enforcement.

============================================================
PURPOSE
============================================================
Runtime and static enforcement of Exchange Runtime Contract.

COMPONENTS:
1. Decorators for contract-aware code
2. Validators for exchange operations
3. Anomaly detection and reporting
4. Contract compliance checking

============================================================
USAGE
============================================================
```python
@expects_exchange_failure
async def submit_order(request: OrderRequest) -> OrderResponse:
    # Code that interacts with exchange
    pass

@reconcile_after
async def cancel_order(order_id: str) -> bool:
    # Code that modifies exchange state
    pass
```

============================================================
"""

import asyncio
import functools
import logging
import time
from datetime import datetime, timedelta
from typing import (
    Any, Callable, Dict, List, Optional, Set, TypeVar, Union,
    Awaitable, Tuple
)
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager

from .exchange_runtime_contract import (
    ExchangeFailureType,
    ProhibitedAssumption,
    MandatoryReaction,
    AuthorityDomain,
    EXCHANGE_AUTHORITY,
    INTERNAL_AUTHORITY,
)


logger = logging.getLogger(__name__)


# ============================================================
# TYPE DEFINITIONS
# ============================================================

T = TypeVar("T")
AsyncFunc = Callable[..., Awaitable[T]]
SyncFunc = Callable[..., T]


# ============================================================
# ANOMALY TYPES
# ============================================================

class AnomalyType(Enum):
    """Types of exchange anomalies."""
    
    # Response anomalies
    UNEXPECTED_RESPONSE = "unexpected_response"
    INCONSISTENT_DATA = "inconsistent_data"
    STALE_DATA = "stale_data"
    
    # Timing anomalies
    EXCESSIVE_LATENCY = "excessive_latency"
    CLOCK_DRIFT = "clock_drift"
    
    # State anomalies
    STATE_DIVERGENCE = "state_divergence"
    BALANCE_MISMATCH = "balance_mismatch"
    POSITION_MISMATCH = "position_mismatch"
    ORDER_STATE_MISMATCH = "order_state_mismatch"
    
    # Behavior anomalies
    SILENT_FAILURE = "silent_failure"
    UNEXPLAINED_REJECTION = "unexplained_rejection"
    MISSING_FILL_REPORT = "missing_fill_report"
    DUPLICATE_MESSAGE = "duplicate_message"
    
    # Rate anomalies
    UNEXPECTED_RATE_LIMIT = "unexpected_rate_limit"
    RATE_LIMIT_ESCALATION = "rate_limit_escalation"


@dataclass
class Anomaly:
    """Detected exchange anomaly."""
    
    type: AnomalyType
    exchange_id: str
    timestamp: datetime
    description: str
    context: Dict[str, Any]
    severity: str = "warning"  # info, warning, error, critical
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "exchange_id": self.exchange_id,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "context": self.context,
            "severity": self.severity,
        }


# ============================================================
# ANOMALY REPORTER
# ============================================================

class AnomalyReporter:
    """
    Central anomaly reporting system.
    
    All exchange anomalies MUST be reported here.
    This ensures mandatory reactions are triggered.
    """
    
    _instance: Optional["AnomalyReporter"] = None
    
    def __init__(self):
        self._anomalies: List[Anomaly] = []
        self._handlers: List[Callable[[Anomaly], Awaitable[None]]] = []
        self._max_history = 10000
        self._critical_count = 0
        self._last_hour_anomalies: List[Anomaly] = []
    
    @classmethod
    def get_instance(cls) -> "AnomalyReporter":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def report(self, anomaly: Anomaly) -> None:
        """
        Report an anomaly.
        
        This triggers all mandatory reactions.
        """
        # Log full context (MANDATORY)
        logger.log(
            logging.CRITICAL if anomaly.severity == "critical" else
            logging.ERROR if anomaly.severity == "error" else
            logging.WARNING,
            f"EXCHANGE ANOMALY: {anomaly.type.value} - {anomaly.description}",
            extra={"anomaly": anomaly.to_dict()},
        )
        
        # Store anomaly
        self._anomalies.append(anomaly)
        if len(self._anomalies) > self._max_history:
            self._anomalies = self._anomalies[-self._max_history:]
        
        # Track critical anomalies
        if anomaly.severity == "critical":
            self._critical_count += 1
        
        # Track hourly anomalies
        self._cleanup_hourly()
        self._last_hour_anomalies.append(anomaly)
        
        # Notify all handlers
        for handler in self._handlers:
            try:
                await handler(anomaly)
            except Exception as e:
                logger.error(f"Anomaly handler failed: {e}")
    
    def add_handler(self, handler: Callable[[Anomaly], Awaitable[None]]) -> None:
        """Add anomaly handler."""
        self._handlers.append(handler)
    
    def get_recent(self, limit: int = 100) -> List[Anomaly]:
        """Get recent anomalies."""
        return self._anomalies[-limit:]
    
    def get_by_exchange(self, exchange_id: str) -> List[Anomaly]:
        """Get anomalies for specific exchange."""
        return [a for a in self._anomalies if a.exchange_id == exchange_id]
    
    def get_critical_count(self) -> int:
        """Get count of critical anomalies."""
        return self._critical_count
    
    def get_hourly_rate(self) -> int:
        """Get anomalies in last hour."""
        self._cleanup_hourly()
        return len(self._last_hour_anomalies)
    
    def _cleanup_hourly(self) -> None:
        """Remove anomalies older than 1 hour."""
        cutoff = datetime.utcnow() - timedelta(hours=1)
        self._last_hour_anomalies = [
            a for a in self._last_hour_anomalies
            if a.timestamp > cutoff
        ]
    
    def should_halt(self) -> Tuple[bool, str]:
        """
        Determine if trading should halt based on anomalies.
        
        Returns:
            (should_halt, reason)
        """
        # Critical anomaly threshold
        if self._critical_count >= 3:
            return True, f"Too many critical anomalies: {self._critical_count}"
        
        # Hourly rate threshold
        hourly = self.get_hourly_rate()
        if hourly >= 50:
            return True, f"Too many anomalies in last hour: {hourly}"
        
        return False, ""


def get_anomaly_reporter() -> AnomalyReporter:
    """Get global anomaly reporter."""
    return AnomalyReporter.get_instance()


# ============================================================
# CONTRACT DECORATORS
# ============================================================

def expects_exchange_failure(func: AsyncFunc) -> AsyncFunc:
    """
    Decorator for functions that interact with exchanges.
    
    Enforces:
    - All exchange failures are caught
    - All failures are reported
    - No silent failures
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        exchange_id = kwargs.get("exchange_id", "unknown")
        operation = func.__name__
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs)
            return result
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            
            # Classify the failure
            failure_type = _classify_exception(e)
            
            # Report anomaly
            anomaly = Anomaly(
                type=AnomalyType.UNEXPECTED_RESPONSE,
                exchange_id=exchange_id,
                timestamp=datetime.utcnow(),
                description=f"{operation} failed: {str(e)}",
                context={
                    "operation": operation,
                    "exception_type": type(e).__name__,
                    "failure_type": failure_type.value if failure_type else "unknown",
                    "latency_ms": latency_ms,
                },
                severity="error",
            )
            
            await get_anomaly_reporter().report(anomaly)
            
            # Re-raise - never swallow
            raise
    
    return wrapper


def reconcile_after(func: AsyncFunc) -> AsyncFunc:
    """
    Decorator that ensures reconciliation after state-modifying operations.
    
    Operations that modify exchange state (orders, cancels) MUST
    trigger reconciliation.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        result = await func(*args, **kwargs)
        
        # Mark that reconciliation is needed
        # The execution engine should check this flag
        wrapper._needs_reconciliation = True
        wrapper._last_operation_time = time.time()
        
        return result
    
    wrapper._needs_reconciliation = False
    wrapper._last_operation_time = 0
    
    return wrapper


def never_assume(assumption: ProhibitedAssumption):
    """
    Decorator that documents and validates against prohibited assumptions.
    
    Use this to mark code that COULD make a bad assumption but doesn't.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # This is documentation - the assumption check is in the code
            return func(*args, **kwargs)
        
        # Attach metadata
        wrapper._prohibited_assumption = assumption
        wrapper._assumption_documented = True
        
        return wrapper
    return decorator


def exchange_operation(
    operation_type: str,
    requires_reconciliation: bool = False,
    max_latency_ms: int = 30000,
):
    """
    Comprehensive decorator for exchange operations.
    
    Args:
        operation_type: Type of operation (order, query, etc.)
        requires_reconciliation: Whether to flag for reconciliation
        max_latency_ms: Maximum expected latency before anomaly
    """
    def decorator(func: AsyncFunc) -> AsyncFunc:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            exchange_id = kwargs.get("exchange_id", "unknown")
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                
                # Check latency
                latency_ms = (time.time() - start_time) * 1000
                if latency_ms > max_latency_ms:
                    anomaly = Anomaly(
                        type=AnomalyType.EXCESSIVE_LATENCY,
                        exchange_id=exchange_id,
                        timestamp=datetime.utcnow(),
                        description=f"{operation_type} took {latency_ms:.0f}ms",
                        context={
                            "operation": operation_type,
                            "latency_ms": latency_ms,
                            "threshold_ms": max_latency_ms,
                        },
                        severity="warning",
                    )
                    await get_anomaly_reporter().report(anomaly)
                
                # Flag for reconciliation
                if requires_reconciliation:
                    wrapper._needs_reconciliation = True
                
                return result
                
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                
                anomaly = Anomaly(
                    type=AnomalyType.UNEXPECTED_RESPONSE,
                    exchange_id=exchange_id,
                    timestamp=datetime.utcnow(),
                    description=f"{operation_type} failed: {str(e)}",
                    context={
                        "operation": operation_type,
                        "latency_ms": latency_ms,
                        "exception": str(e),
                    },
                    severity="error",
                )
                await get_anomaly_reporter().report(anomaly)
                
                raise
        
        wrapper._operation_type = operation_type
        wrapper._needs_reconciliation = False
        
        return wrapper
    return decorator


# ============================================================
# STATE DIVERGENCE DETECTION
# ============================================================

@dataclass
class StateSnapshot:
    """Snapshot of exchange state."""
    
    timestamp: datetime
    exchange_id: str
    balances: Dict[str, str]  # asset -> amount
    positions: Dict[str, Dict[str, str]]  # symbol -> position info
    open_orders: Dict[str, Dict[str, str]]  # order_id -> order info


class StateDivergenceDetector:
    """
    Detects divergence between internal and exchange state.
    
    This is critical for the RECONCILE_CONSTANTLY principle.
    """
    
    def __init__(self):
        self._internal_state: Dict[str, StateSnapshot] = {}
        self._exchange_state: Dict[str, StateSnapshot] = {}
        self._divergence_threshold = 0.01  # 1% threshold
    
    def update_internal_state(
        self,
        exchange_id: str,
        balances: Dict = None,
        positions: Dict = None,
        orders: Dict = None,
    ) -> None:
        """Update internal state snapshot."""
        self._internal_state[exchange_id] = StateSnapshot(
            timestamp=datetime.utcnow(),
            exchange_id=exchange_id,
            balances=balances or {},
            positions=positions or {},
            open_orders=orders or {},
        )
    
    def update_exchange_state(
        self,
        exchange_id: str,
        balances: Dict = None,
        positions: Dict = None,
        orders: Dict = None,
    ) -> None:
        """Update exchange state snapshot."""
        self._exchange_state[exchange_id] = StateSnapshot(
            timestamp=datetime.utcnow(),
            exchange_id=exchange_id,
            balances=balances or {},
            positions=positions or {},
            open_orders=orders or {},
        )
    
    async def check_divergence(self, exchange_id: str) -> List[Anomaly]:
        """
        Check for state divergence.
        
        Returns list of detected anomalies.
        """
        anomalies = []
        
        internal = self._internal_state.get(exchange_id)
        exchange = self._exchange_state.get(exchange_id)
        
        if not internal or not exchange:
            return anomalies
        
        # Check balance divergence
        for asset, internal_balance in internal.balances.items():
            exchange_balance = exchange.balances.get(asset, "0")
            
            try:
                internal_val = float(internal_balance)
                exchange_val = float(exchange_balance)
                
                if internal_val > 0:
                    diff_pct = abs(internal_val - exchange_val) / internal_val
                    
                    if diff_pct > self._divergence_threshold:
                        anomalies.append(Anomaly(
                            type=AnomalyType.BALANCE_MISMATCH,
                            exchange_id=exchange_id,
                            timestamp=datetime.utcnow(),
                            description=f"{asset} balance divergence: {diff_pct:.2%}",
                            context={
                                "asset": asset,
                                "internal": internal_balance,
                                "exchange": exchange_balance,
                                "difference_pct": diff_pct,
                            },
                            severity="error" if diff_pct > 0.05 else "warning",
                        ))
            except (ValueError, TypeError):
                pass
        
        # Check position divergence
        for symbol, internal_pos in internal.positions.items():
            exchange_pos = exchange.positions.get(symbol, {})
            
            internal_qty = float(internal_pos.get("quantity", 0))
            exchange_qty = float(exchange_pos.get("quantity", 0))
            
            if internal_qty != exchange_qty:
                anomalies.append(Anomaly(
                    type=AnomalyType.POSITION_MISMATCH,
                    exchange_id=exchange_id,
                    timestamp=datetime.utcnow(),
                    description=f"{symbol} position mismatch",
                    context={
                        "symbol": symbol,
                        "internal_qty": internal_qty,
                        "exchange_qty": exchange_qty,
                    },
                    severity="critical",
                ))
        
        # Report all anomalies
        reporter = get_anomaly_reporter()
        for anomaly in anomalies:
            await reporter.report(anomaly)
        
        return anomalies


# ============================================================
# TIMEOUT HANDLING
# ============================================================

class TimeoutState(Enum):
    """State of a timed-out operation."""
    
    UNKNOWN = "unknown"           # We don't know what happened
    CONFIRMED_SUCCESS = "success"  # Confirmed the operation succeeded
    CONFIRMED_FAILURE = "failure"  # Confirmed the operation failed
    STILL_PENDING = "pending"      # Operation is still processing


@dataclass
class TimeoutContext:
    """Context for handling timeouts correctly."""
    
    operation: str
    started_at: datetime
    timeout_at: datetime
    exchange_id: str
    
    # For orders
    client_order_id: Optional[str] = None
    symbol: Optional[str] = None
    
    # Resolution
    state: TimeoutState = TimeoutState.UNKNOWN
    resolved_at: Optional[datetime] = None


class TimeoutResolver:
    """
    Resolves timed-out exchange operations.
    
    Implements: NEVER_ASSUME_FAILED reaction.
    """
    
    def __init__(self):
        self._pending_timeouts: Dict[str, TimeoutContext] = {}
    
    def register_timeout(
        self,
        operation_id: str,
        context: TimeoutContext,
    ) -> None:
        """Register a timed-out operation for resolution."""
        self._pending_timeouts[operation_id] = context
        
        logger.warning(
            f"Timeout registered: {context.operation} - {operation_id}",
            extra={"context": context.__dict__},
        )
    
    async def resolve_timeout(
        self,
        operation_id: str,
        state: TimeoutState,
    ) -> None:
        """Resolve a timed-out operation."""
        if operation_id not in self._pending_timeouts:
            return
        
        context = self._pending_timeouts[operation_id]
        context.state = state
        context.resolved_at = datetime.utcnow()
        
        logger.info(
            f"Timeout resolved: {operation_id} -> {state.value}",
            extra={"context": context.__dict__},
        )
        
        del self._pending_timeouts[operation_id]
    
    def get_pending(self) -> List[TimeoutContext]:
        """Get all pending timeout resolutions."""
        return list(self._pending_timeouts.values())
    
    def get_unresolved_count(self) -> int:
        """Get count of unresolved timeouts."""
        return len(self._pending_timeouts)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _classify_exception(e: Exception) -> Optional[ExchangeFailureType]:
    """Classify exception into failure type."""
    error_str = str(e).lower()
    
    if "timeout" in error_str:
        return ExchangeFailureType.NETWORK_TIMEOUT
    elif "rate limit" in error_str or "too many" in error_str:
        return ExchangeFailureType.RATE_LIMIT_EXCEEDED
    elif "auth" in error_str or "signature" in error_str:
        return ExchangeFailureType.AUTH_INVALID_SIGNATURE
    elif "insufficient" in error_str:
        return ExchangeFailureType.ORDER_INSUFFICIENT_MARGIN
    elif "not found" in error_str:
        return ExchangeFailureType.ORDER_NOT_FOUND
    elif "rejected" in error_str:
        return ExchangeFailureType.ORDER_REJECTED
    
    return None


@asynccontextmanager
async def exchange_operation_context(
    exchange_id: str,
    operation: str,
):
    """
    Context manager for exchange operations.
    
    Usage:
        async with exchange_operation_context("binance", "submit_order"):
            response = await adapter.submit_order(request)
    """
    start_time = time.time()
    reporter = get_anomaly_reporter()
    
    try:
        yield
        
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        
        anomaly = Anomaly(
            type=AnomalyType.UNEXPECTED_RESPONSE,
            exchange_id=exchange_id,
            timestamp=datetime.utcnow(),
            description=f"{operation} failed: {str(e)}",
            context={
                "operation": operation,
                "latency_ms": latency_ms,
                "exception": str(e),
            },
            severity="error",
        )
        
        await reporter.report(anomaly)
        raise
    
    finally:
        latency_ms = (time.time() - start_time) * 1000
        
        # Report excessive latency
        if latency_ms > 30000:
            anomaly = Anomaly(
                type=AnomalyType.EXCESSIVE_LATENCY,
                exchange_id=exchange_id,
                timestamp=datetime.utcnow(),
                description=f"{operation} took {latency_ms:.0f}ms",
                context={
                    "operation": operation,
                    "latency_ms": latency_ms,
                },
                severity="warning",
            )
            await reporter.report(anomaly)
