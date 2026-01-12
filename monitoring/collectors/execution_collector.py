"""
Execution & Signal Collectors.

============================================================
PURPOSE
============================================================
Read-only collectors for execution tracking and signal visibility.

PRINCIPLES:
- Complete audit trail from signal to fill
- NO hidden states or derived values
- All data directly from source stores
- Traceable end-to-end

============================================================
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List

from ..models import (
    SignalRecord,
    OrderRecord,
)
from .base import BaseCollector


logger = logging.getLogger(__name__)


# ============================================================
# SIGNAL COLLECTOR
# ============================================================

class SignalCollector(BaseCollector):
    """
    Collects signal records for visibility.
    
    READ-ONLY: Only reads from signal stores.
    """
    
    def __init__(
        self,
        signal_store: Any = None,  # Read-only signal store
    ):
        """Initialize signal collector."""
        super().__init__("signals")
        self._signal_store = signal_store
    
    async def collect(self, limit: int = 100) -> List[SignalRecord]:
        """Collect recent signals."""
        if self._signal_store is None:
            return []
        
        try:
            signals = await self._signal_store.get_recent_signals(limit=limit)
            if signals is None:
                return []
            
            records = []
            for sig in signals:
                records.append(self._to_record(sig))
            
            return records
        except Exception as e:
            logger.error(f"Error collecting signals: {e}")
            return []
    
    def _to_record(self, sig: Dict[str, Any]) -> SignalRecord:
        """Convert signal dict to record."""
        return SignalRecord(
            signal_id=sig.get("id", "unknown"),
            strategy_name=sig.get("strategy", "unknown"),
            signal_type=sig.get("type", "unknown"),
            symbol=sig.get("symbol", "unknown"),
            exchange=sig.get("exchange", "unknown"),
            direction=sig.get("direction", "unknown"),
            strength=sig.get("strength"),
            generated_at=sig.get("generated_at"),
            processed=sig.get("processed", False),
            processed_at=sig.get("processed_at"),
            resulted_in_order=sig.get("resulted_in_order", False),
            order_id=sig.get("order_id"),
            rejection_reason=sig.get("rejection_reason"),
            source_data_timestamp=sig.get("source_data_timestamp"),
            source_data_hash=sig.get("source_data_hash"),
            metadata=sig.get("metadata") or {},
        )
    
    async def get_signal(self, signal_id: str) -> Optional[SignalRecord]:
        """Get a single signal by ID."""
        if self._signal_store is None:
            return None
        
        try:
            sig = await self._signal_store.get_signal(signal_id)
            if sig is None:
                return None
            return self._to_record(sig)
        except Exception as e:
            logger.error(f"Error getting signal {signal_id}: {e}")
            return None
    
    async def get_signals_by_strategy(
        self,
        strategy_name: str,
        limit: int = 50,
    ) -> List[SignalRecord]:
        """Get signals for a specific strategy."""
        if self._signal_store is None:
            return []
        
        try:
            signals = await self._signal_store.get_signals_by_strategy(
                strategy=strategy_name,
                limit=limit,
            )
            if signals is None:
                return []
            
            return [self._to_record(s) for s in signals]
        except Exception as e:
            logger.error(f"Error getting signals for {strategy_name}: {e}")
            return []
    
    async def get_pending_signals(self) -> List[SignalRecord]:
        """Get signals that haven't been processed."""
        if self._signal_store is None:
            return []
        
        try:
            signals = await self._signal_store.get_pending_signals()
            if signals is None:
                return []
            
            return [self._to_record(s) for s in signals]
        except Exception as e:
            logger.error(f"Error getting pending signals: {e}")
            return []


# ============================================================
# ORDER COLLECTOR
# ============================================================

class OrderCollector(BaseCollector):
    """
    Collects order and execution records.
    
    READ-ONLY: Only reads from order stores.
    """
    
    def __init__(
        self,
        order_store: Any = None,  # Read-only order store
    ):
        """Initialize order collector."""
        super().__init__("orders")
        self._order_store = order_store
    
    async def collect(self, limit: int = 100) -> List[OrderRecord]:
        """Collect recent orders."""
        if self._order_store is None:
            return []
        
        try:
            orders = await self._order_store.get_recent_orders(limit=limit)
            if orders is None:
                return []
            
            records = []
            for order in orders:
                records.append(self._to_record(order))
            
            return records
        except Exception as e:
            logger.error(f"Error collecting orders: {e}")
            return []
    
    def _to_record(self, order: Dict[str, Any]) -> OrderRecord:
        """Convert order dict to record."""
        # Calculate slippage if we have both requested and fill prices
        slippage = None
        requested_price = order.get("requested_price")
        avg_fill_price = order.get("avg_fill_price")
        if requested_price and avg_fill_price:
            slippage = abs(avg_fill_price - requested_price)
        
        return OrderRecord(
            order_id=order.get("id", "unknown"),
            internal_order_id=order.get("internal_id"),
            exchange_order_id=order.get("exchange_id"),
            symbol=order.get("symbol", "unknown"),
            exchange=order.get("exchange", "unknown"),
            side=order.get("side", "unknown"),
            order_type=order.get("type", "unknown"),
            status=order.get("status", "unknown"),
            requested_quantity=order.get("requested_quantity"),
            filled_quantity=order.get("filled_quantity"),
            remaining_quantity=order.get("remaining_quantity"),
            requested_price=requested_price,
            avg_fill_price=avg_fill_price,
            slippage=slippage,
            fees=order.get("fees"),
            created_at=order.get("created_at"),
            submitted_at=order.get("submitted_at"),
            acknowledged_at=order.get("acknowledged_at"),
            filled_at=order.get("filled_at"),
            cancelled_at=order.get("cancelled_at"),
            source_signal_id=order.get("signal_id"),
            source_strategy=order.get("strategy"),
            rejection_reason=order.get("rejection_reason"),
            cancel_reason=order.get("cancel_reason"),
            fills=order.get("fills") or [],
            time_in_force=order.get("time_in_force"),
            is_reduce_only=order.get("reduce_only", False),
        )
    
    async def get_order(self, order_id: str) -> Optional[OrderRecord]:
        """Get a single order by ID."""
        if self._order_store is None:
            return None
        
        try:
            order = await self._order_store.get_order(order_id)
            if order is None:
                return None
            return self._to_record(order)
        except Exception as e:
            logger.error(f"Error getting order {order_id}: {e}")
            return None
    
    async def get_active_orders(self) -> List[OrderRecord]:
        """Get all active (open) orders."""
        if self._order_store is None:
            return []
        
        try:
            orders = await self._order_store.get_active_orders()
            if orders is None:
                return []
            
            return [self._to_record(o) for o in orders]
        except Exception as e:
            logger.error(f"Error getting active orders: {e}")
            return []
    
    async def get_orders_by_symbol(
        self,
        symbol: str,
        limit: int = 50,
    ) -> List[OrderRecord]:
        """Get orders for a specific symbol."""
        if self._order_store is None:
            return []
        
        try:
            orders = await self._order_store.get_orders_by_symbol(
                symbol=symbol,
                limit=limit,
            )
            if orders is None:
                return []
            
            return [self._to_record(o) for o in orders]
        except Exception as e:
            logger.error(f"Error getting orders for {symbol}: {e}")
            return []
    
    async def get_orders_by_strategy(
        self,
        strategy: str,
        limit: int = 50,
    ) -> List[OrderRecord]:
        """Get orders for a specific strategy."""
        if self._order_store is None:
            return []
        
        try:
            orders = await self._order_store.get_orders_by_strategy(
                strategy=strategy,
                limit=limit,
            )
            if orders is None:
                return []
            
            return [self._to_record(o) for o in orders]
        except Exception as e:
            logger.error(f"Error getting orders for strategy {strategy}: {e}")
            return []


# ============================================================
# EXECUTION METRICS COLLECTOR
# ============================================================

class ExecutionMetricsCollector(BaseCollector):
    """
    Collects execution quality metrics.
    
    READ-ONLY: Only reads and aggregates from order stores.
    """
    
    def __init__(
        self,
        order_store: Any = None,
    ):
        """Initialize execution metrics collector."""
        super().__init__("execution_metrics")
        self._order_store = order_store
    
    async def collect(self) -> Dict[str, Any]:
        """Collect execution metrics."""
        if self._order_store is None:
            return {}
        
        try:
            # Get recent orders for metrics
            orders = await self._order_store.get_recent_orders(limit=1000)
            if not orders:
                return {}
            
            return {
                "total_orders": len(orders),
                "fill_rate": self._calculate_fill_rate(orders),
                "avg_slippage": self._calculate_avg_slippage(orders),
                "avg_fill_time_ms": self._calculate_avg_fill_time(orders),
                "rejection_rate": self._calculate_rejection_rate(orders),
                "cancel_rate": self._calculate_cancel_rate(orders),
                "by_exchange": self._metrics_by_exchange(orders),
                "by_symbol": self._metrics_by_symbol(orders),
            }
        except Exception as e:
            logger.error(f"Error collecting execution metrics: {e}")
            return {}
    
    def _calculate_fill_rate(self, orders: List[Dict]) -> Optional[Decimal]:
        """Calculate fill rate."""
        if not orders:
            return None
        
        filled = sum(1 for o in orders if o.get("status") == "FILLED")
        return Decimal(str(filled / len(orders))) if orders else None
    
    def _calculate_avg_slippage(self, orders: List[Dict]) -> Optional[Decimal]:
        """Calculate average slippage."""
        slippages = []
        
        for order in orders:
            requested = order.get("requested_price")
            filled = order.get("avg_fill_price")
            
            if requested and filled and requested > 0:
                slippage_pct = abs(filled - requested) / requested * 100
                slippages.append(slippage_pct)
        
        if not slippages:
            return None
        
        return Decimal(str(sum(slippages) / len(slippages)))
    
    def _calculate_avg_fill_time(self, orders: List[Dict]) -> Optional[float]:
        """Calculate average fill time in milliseconds."""
        times = []
        
        for order in orders:
            submitted = order.get("submitted_at")
            filled = order.get("filled_at")
            
            if submitted and filled:
                delta = (filled - submitted).total_seconds() * 1000
                times.append(delta)
        
        if not times:
            return None
        
        return sum(times) / len(times)
    
    def _calculate_rejection_rate(self, orders: List[Dict]) -> Optional[Decimal]:
        """Calculate rejection rate."""
        if not orders:
            return None
        
        rejected = sum(1 for o in orders if o.get("status") == "REJECTED")
        return Decimal(str(rejected / len(orders)))
    
    def _calculate_cancel_rate(self, orders: List[Dict]) -> Optional[Decimal]:
        """Calculate cancel rate."""
        if not orders:
            return None
        
        cancelled = sum(1 for o in orders if o.get("status") == "CANCELLED")
        return Decimal(str(cancelled / len(orders)))
    
    def _metrics_by_exchange(self, orders: List[Dict]) -> Dict[str, Dict]:
        """Calculate metrics by exchange."""
        by_exchange: Dict[str, List] = {}
        
        for order in orders:
            exchange = order.get("exchange", "unknown")
            if exchange not in by_exchange:
                by_exchange[exchange] = []
            by_exchange[exchange].append(order)
        
        result = {}
        for exchange, exchange_orders in by_exchange.items():
            result[exchange] = {
                "order_count": len(exchange_orders),
                "fill_rate": self._calculate_fill_rate(exchange_orders),
                "avg_slippage": self._calculate_avg_slippage(exchange_orders),
            }
        
        return result
    
    def _metrics_by_symbol(
        self,
        orders: List[Dict],
        top_n: int = 10,
    ) -> Dict[str, Dict]:
        """Calculate metrics by symbol (top N by volume)."""
        by_symbol: Dict[str, List] = {}
        
        for order in orders:
            symbol = order.get("symbol", "unknown")
            if symbol not in by_symbol:
                by_symbol[symbol] = []
            by_symbol[symbol].append(order)
        
        # Sort by order count and take top N
        sorted_symbols = sorted(
            by_symbol.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:top_n]
        
        result = {}
        for symbol, symbol_orders in sorted_symbols:
            result[symbol] = {
                "order_count": len(symbol_orders),
                "fill_rate": self._calculate_fill_rate(symbol_orders),
                "avg_slippage": self._calculate_avg_slippage(symbol_orders),
            }
        
        return result
