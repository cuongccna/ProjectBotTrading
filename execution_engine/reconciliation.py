"""
Execution Engine - Reconciliation.

============================================================
PURPOSE
============================================================
Reconciles internal order state with exchange state.

RESPONSIBILITIES:
- Sync order states with exchange
- Detect state mismatches
- Reconcile fills and quantities
- Handle stale orders
- Detect ghost orders (on exchange but not tracked)

CRITICAL INVARIANT:
    "Exchange state is authoritative for order status."

============================================================
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Set, Callable, Awaitable, Any
from decimal import Decimal
from dataclasses import dataclass, field
from enum import Enum

from .types import (
    OrderRecord,
    OrderState,
    AccountState,
    PositionInfo,
)
from .config import ReconciliationConfig
from .adapters import ExchangeAdapter, QueryOrderRequest


logger = logging.getLogger(__name__)


# ============================================================
# RECONCILIATION TYPES
# ============================================================

class MismatchType(Enum):
    """Types of reconciliation mismatches."""
    
    STATE_MISMATCH = "STATE_MISMATCH"
    """Order state differs from exchange."""
    
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    """Filled quantity differs."""
    
    PRICE_MISMATCH = "PRICE_MISMATCH"
    """Average price differs."""
    
    GHOST_ORDER = "GHOST_ORDER"
    """Order on exchange but not tracked locally."""
    
    MISSING_ORDER = "MISSING_ORDER"
    """Order tracked locally but not on exchange."""
    
    STALE_ORDER = "STALE_ORDER"
    """Order has been active too long."""
    
    POSITION_MISMATCH = "POSITION_MISMATCH"
    """Position differs from expected."""


class MismatchSeverity(Enum):
    """Severity of mismatch."""
    
    INFO = "INFO"
    """Informational, auto-resolved."""
    
    WARNING = "WARNING"
    """Needs attention but not critical."""
    
    ERROR = "ERROR"
    """Significant mismatch."""
    
    CRITICAL = "CRITICAL"
    """Critical mismatch, may require halt."""


@dataclass
class ReconciliationMismatch:
    """A detected mismatch."""
    
    mismatch_type: MismatchType
    """Type of mismatch."""
    
    severity: MismatchSeverity
    """Severity level."""
    
    order_id: Optional[str] = None
    """Related order ID."""
    
    symbol: Optional[str] = None
    """Related symbol."""
    
    expected_value: Optional[str] = None
    """Expected value."""
    
    actual_value: Optional[str] = None
    """Actual value."""
    
    message: str = ""
    """Human-readable message."""
    
    auto_resolved: bool = False
    """Whether mismatch was auto-resolved."""
    
    resolution: Optional[str] = None
    """How it was resolved."""
    
    detected_at: datetime = field(default_factory=datetime.utcnow)
    """When detected."""


@dataclass
class ReconciliationResult:
    """Result of a reconciliation run."""
    
    run_id: str
    """Unique run identifier."""
    
    started_at: datetime
    """When reconciliation started."""
    
    completed_at: datetime = field(default_factory=datetime.utcnow)
    """When reconciliation completed."""
    
    orders_checked: int = 0
    """Number of orders checked."""
    
    orders_synced: int = 0
    """Number of orders synced."""
    
    mismatches: List[ReconciliationMismatch] = field(default_factory=list)
    """Detected mismatches."""
    
    errors: List[str] = field(default_factory=list)
    """Errors during reconciliation."""
    
    @property
    def success(self) -> bool:
        """Whether reconciliation was successful."""
        return len(self.errors) == 0
    
    @property
    def has_critical(self) -> bool:
        """Whether there are critical mismatches."""
        return any(m.severity == MismatchSeverity.CRITICAL for m in self.mismatches)
    
    @property
    def unresolved_count(self) -> int:
        """Count of unresolved mismatches."""
        return sum(1 for m in self.mismatches if not m.auto_resolved)


# ============================================================
# RECONCILIATION ENGINE
# ============================================================

class ReconciliationEngine:
    """
    Reconciles internal state with exchange.
    
    Runs periodically to detect and resolve state mismatches.
    
    SAFETY:
    - Exchange state is authoritative
    - Mismatches are logged and alerted
    - Critical mismatches can trigger freeze
    """
    
    def __init__(
        self,
        config: ReconciliationConfig,
        adapter: ExchangeAdapter,
        get_tracked_orders: Callable[[], List[OrderRecord]],
        on_order_sync: Callable[[OrderRecord, Dict[str, Any]], Awaitable[None]] = None,
        on_mismatch: Callable[[ReconciliationMismatch], Awaitable[None]] = None,
        on_critical: Callable[[str], Awaitable[None]] = None,
    ):
        """
        Initialize reconciliation engine.
        
        Args:
            config: Reconciliation configuration
            adapter: Exchange adapter
            get_tracked_orders: Callable to get tracked orders
            on_order_sync: Callback when order is synced
            on_mismatch: Callback on mismatch detected
            on_critical: Callback on critical mismatch
        """
        self._config = config
        self._adapter = adapter
        self._get_tracked_orders = get_tracked_orders
        self._on_order_sync = on_order_sync
        self._on_mismatch = on_mismatch
        self._on_critical = on_critical
        
        # Reconciliation history
        self._history: List[ReconciliationResult] = []
        self._max_history = 100
        
        # Run counter
        self._run_counter = 0
        
        # Lock
        self._lock = asyncio.Lock()
    
    async def reconcile(self) -> ReconciliationResult:
        """
        Run a reconciliation pass.
        
        Returns:
            ReconciliationResult
        """
        async with self._lock:
            self._run_counter += 1
            run_id = f"REC_{self._run_counter:06d}"
            
            result = ReconciliationResult(
                run_id=run_id,
                started_at=datetime.utcnow(),
            )
            
            logger.debug(f"Starting reconciliation run {run_id}")
            
            try:
                # Get tracked orders
                tracked_orders = self._get_tracked_orders()
                active_orders = [o for o in tracked_orders if o.state.is_active()]
                
                result.orders_checked = len(active_orders)
                
                # Reconcile each active order
                for order in active_orders:
                    try:
                        mismatches = await self._reconcile_order(order)
                        result.mismatches.extend(mismatches)
                        
                        if any(not m.auto_resolved for m in mismatches):
                            result.orders_synced += 1
                            
                    except Exception as e:
                        result.errors.append(f"Error reconciling {order.order_id}: {e}")
                        logger.error(f"Reconciliation error for {order.order_id}: {e}")
                
                # Check for ghost orders
                ghost_mismatches = await self._check_ghost_orders(tracked_orders)
                result.mismatches.extend(ghost_mismatches)
                
                # Check for stale orders
                stale_mismatches = self._check_stale_orders(active_orders)
                result.mismatches.extend(stale_mismatches)
                
            except Exception as e:
                result.errors.append(f"Reconciliation failed: {e}")
                logger.error(f"Reconciliation run {run_id} failed: {e}")
            
            result.completed_at = datetime.utcnow()
            
            # Store in history
            self._history.append(result)
            if len(self._history) > self._max_history:
                self._history.pop(0)
            
            # Handle critical mismatches
            if result.has_critical:
                logger.critical(f"Reconciliation {run_id}: Critical mismatches detected!")
                if self._on_critical and self._config.freeze_on_critical_mismatch:
                    await self._on_critical(
                        f"Critical reconciliation mismatch: {result.unresolved_count} issues"
                    )
            
            # Notify mismatches
            if self._on_mismatch:
                for mismatch in result.mismatches:
                    if not mismatch.auto_resolved:
                        await self._on_mismatch(mismatch)
            
            logger.info(
                f"Reconciliation {run_id} complete: "
                f"{result.orders_checked} checked, "
                f"{result.orders_synced} synced, "
                f"{len(result.mismatches)} mismatches"
            )
            
            return result
    
    async def _reconcile_order(self, order: OrderRecord) -> List[ReconciliationMismatch]:
        """Reconcile a single order with exchange."""
        mismatches: List[ReconciliationMismatch] = []
        
        if not order.exchange_order_id:
            # Not yet submitted - nothing to reconcile
            return mismatches
        
        try:
            # Query order on exchange
            response = await self._adapter.query_order(
                QueryOrderRequest(
                    symbol=order.symbol,
                    exchange_order_id=order.exchange_order_id,
                )
            )
            
            if not response.found:
                # Order not found on exchange
                if order.state.is_active():
                    mismatches.append(ReconciliationMismatch(
                        mismatch_type=MismatchType.MISSING_ORDER,
                        severity=MismatchSeverity.ERROR,
                        order_id=order.order_id,
                        symbol=order.symbol,
                        expected_value=order.state.value,
                        actual_value="NOT_FOUND",
                        message=f"Order {order.order_id} not found on exchange",
                    ))
                return mismatches
            
            # Check state
            exchange_status = response.status
            if self._state_differs(order.state, exchange_status):
                mismatches.append(ReconciliationMismatch(
                    mismatch_type=MismatchType.STATE_MISMATCH,
                    severity=MismatchSeverity.WARNING,
                    order_id=order.order_id,
                    symbol=order.symbol,
                    expected_value=order.state.value,
                    actual_value=exchange_status,
                    message=f"State mismatch: local={order.state.value}, exchange={exchange_status}",
                    auto_resolved=True,
                    resolution="Synced to exchange state",
                ))
            
            # Check quantity
            if self._quantity_differs(order.filled_quantity, response.filled_quantity):
                deviation = abs(response.filled_quantity - order.filled_quantity)
                mismatches.append(ReconciliationMismatch(
                    mismatch_type=MismatchType.QUANTITY_MISMATCH,
                    severity=MismatchSeverity.WARNING,
                    order_id=order.order_id,
                    symbol=order.symbol,
                    expected_value=str(order.filled_quantity),
                    actual_value=str(response.filled_quantity),
                    message=f"Quantity mismatch: deviation={deviation}",
                    auto_resolved=True,
                    resolution="Updated to exchange quantity",
                ))
            
            # Check average price
            if order.average_fill_price and response.average_price:
                if self._price_differs(order.average_fill_price, response.average_price):
                    mismatches.append(ReconciliationMismatch(
                        mismatch_type=MismatchType.PRICE_MISMATCH,
                        severity=MismatchSeverity.WARNING,
                        order_id=order.order_id,
                        symbol=order.symbol,
                        expected_value=str(order.average_fill_price),
                        actual_value=str(response.average_price),
                        message="Average fill price mismatch",
                        auto_resolved=True,
                        resolution="Updated to exchange price",
                    ))
            
            # Sync the order if auto-sync is enabled
            if self._config.auto_sync_orders and mismatches:
                sync_data = {
                    "filled_quantity": response.filled_quantity,
                    "remaining_quantity": response.remaining_quantity,
                    "average_price": response.average_price,
                    "status": exchange_status,
                }
                
                if self._on_order_sync:
                    await self._on_order_sync(order, sync_data)
                    
        except Exception as e:
            logger.error(f"Failed to reconcile order {order.order_id}: {e}")
            raise
        
        return mismatches
    
    async def _check_ghost_orders(
        self,
        tracked_orders: List[OrderRecord],
    ) -> List[ReconciliationMismatch]:
        """Check for orders on exchange not tracked locally."""
        mismatches: List[ReconciliationMismatch] = []
        
        try:
            # Get all open orders from exchange
            exchange_orders = await self._adapter.get_open_orders()
            
            # Get tracked exchange order IDs
            tracked_ids: Set[str] = {
                o.exchange_order_id
                for o in tracked_orders
                if o.exchange_order_id
            }
            
            # Find ghost orders
            for exchange_order in exchange_orders:
                if exchange_order.get("orderId") not in tracked_ids:
                    mismatches.append(ReconciliationMismatch(
                        mismatch_type=MismatchType.GHOST_ORDER,
                        severity=MismatchSeverity.WARNING,
                        symbol=exchange_order.get("symbol"),
                        message=f"Untracked order on exchange: {exchange_order.get('orderId')}",
                    ))
                    
        except Exception as e:
            logger.error(f"Failed to check ghost orders: {e}")
        
        return mismatches
    
    def _check_stale_orders(
        self,
        active_orders: List[OrderRecord],
    ) -> List[ReconciliationMismatch]:
        """Check for stale orders."""
        mismatches: List[ReconciliationMismatch] = []
        
        # Define stale threshold (configurable)
        stale_threshold = timedelta(hours=24)
        now = datetime.utcnow()
        
        for order in active_orders:
            if order.submitted_at:
                age = now - order.submitted_at
                if age > stale_threshold:
                    mismatches.append(ReconciliationMismatch(
                        mismatch_type=MismatchType.STALE_ORDER,
                        severity=MismatchSeverity.WARNING,
                        order_id=order.order_id,
                        symbol=order.symbol,
                        message=f"Order stale: submitted {age.total_seconds() / 3600:.1f} hours ago",
                    ))
        
        return mismatches
    
    def _state_differs(self, local_state: OrderState, exchange_status: str) -> bool:
        """Check if states differ meaningfully."""
        # Map common exchange statuses
        status_map = {
            "NEW": OrderState.SUBMITTED,
            "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
            "FILLED": OrderState.FILLED,
            "CANCELED": OrderState.CANCELED,
            "REJECTED": OrderState.REJECTED,
            "EXPIRED": OrderState.EXPIRED,
        }
        
        expected_state = status_map.get(exchange_status.upper())
        if expected_state is None:
            return False  # Unknown status, skip
        
        return local_state != expected_state
    
    def _quantity_differs(self, local: Decimal, exchange: Decimal) -> bool:
        """Check if quantities differ beyond tolerance."""
        if local == exchange:
            return False
        
        tolerance_pct = self._config.quantity_mismatch_tolerance_pct
        if local == 0:
            return exchange > 0
        
        diff_pct = abs(local - exchange) / local * 100
        return diff_pct > tolerance_pct
    
    def _price_differs(self, local: Decimal, exchange: Decimal) -> bool:
        """Check if prices differ beyond tolerance."""
        if local == exchange:
            return False
        
        tolerance_pct = self._config.price_mismatch_tolerance_pct
        if local == 0:
            return exchange > 0
        
        diff_pct = abs(local - exchange) / local * 100
        return diff_pct > tolerance_pct
    
    def get_last_result(self) -> Optional[ReconciliationResult]:
        """Get last reconciliation result."""
        return self._history[-1] if self._history else None
    
    def get_history(self, limit: int = 10) -> List[ReconciliationResult]:
        """Get reconciliation history."""
        return self._history[-limit:]
