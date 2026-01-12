"""
Execution Engine - Repository.

============================================================
PURPOSE
============================================================
Database operations for execution persistence.

RESPONSIBILITIES:
- Save/load orders
- Save/load fills
- Save/load events
- Query execution history

CRITICAL REQUIREMENTS:
- All operations must be transactional
- All writes must be atomic
- Complete audit trail

============================================================
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import select, update, delete, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from .types import OrderRecord, OrderState, ExecutionResult
from .state_machine import StateTransitionEvent
from .alerting import Alert
from .reconciliation import ReconciliationResult, ReconciliationMismatch
from .models import (
    ExecutionOrderModel,
    ExecutionFillModel,
    ExecutionEventModel,
    ExecutionAlertModel,
    ReconciliationLogModel,
)


logger = logging.getLogger(__name__)


# ============================================================
# EXECUTION REPOSITORY
# ============================================================

class ExecutionRepository:
    """
    Repository for execution data persistence.
    
    Handles all database operations for the execution engine.
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize repository.
        
        Args:
            session: SQLAlchemy async session
        """
        self._session = session
    
    # --------------------------------------------------------
    # ORDER OPERATIONS
    # --------------------------------------------------------
    
    async def save_order(self, order: OrderRecord) -> ExecutionOrderModel:
        """
        Save or update an order.
        
        Args:
            order: Order record to save
            
        Returns:
            Saved model
        """
        # Check if exists
        existing = await self.get_order_model(order.order_id)
        
        if existing:
            # Update existing
            existing.state = order.state.value
            existing.previous_state = order.previous_state.value if order.previous_state else None
            existing.exchange_order_id = order.exchange_order_id
            existing.filled_quantity = order.filled_quantity
            existing.remaining_quantity = order.remaining_quantity
            existing.average_fill_price = order.average_fill_price
            existing.commission = order.commission
            existing.commission_asset = order.commission_asset
            existing.submitted_at = order.submitted_at
            existing.filled_at = order.filled_at
            existing.completed_at = order.completed_at
            existing.retry_count = order.retry_count
            existing.last_error = order.last_error
            existing.exchange_error_code = order.exchange_error_code
            existing.updated_at = datetime.utcnow()
            
            await self._session.commit()
            return existing
        else:
            # Create new
            model = ExecutionOrderModel(
                order_id=order.order_id,
                intent_id=order.intent_id,
                exchange_order_id=order.exchange_order_id,
                client_order_id=order.client_order_id,
                state=order.state.value,
                previous_state=order.previous_state.value if order.previous_state else None,
                symbol=order.symbol,
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=order.quantity,
                price=order.price,
                stop_price=order.stop_price,
                time_in_force=order.time_in_force.value,
                position_side=order.position_side.value,
                reduce_only=order.reduce_only,
                filled_quantity=order.filled_quantity,
                remaining_quantity=order.remaining_quantity,
                average_fill_price=order.average_fill_price,
                commission=order.commission,
                commission_asset=order.commission_asset,
                created_at=order.created_at,
                submitted_at=order.submitted_at,
                filled_at=order.filled_at,
                completed_at=order.completed_at,
                retry_count=order.retry_count,
                last_error=order.last_error,
                exchange_error_code=order.exchange_error_code,
                strategy_id=order.strategy_id,
                exchange_id=order.exchange_id,
            )
            
            self._session.add(model)
            await self._session.commit()
            return model
    
    async def get_order_model(self, order_id: str) -> Optional[ExecutionOrderModel]:
        """Get order model by ID."""
        result = await self._session.execute(
            select(ExecutionOrderModel).where(ExecutionOrderModel.order_id == order_id)
        )
        return result.scalar_one_or_none()
    
    async def get_order(self, order_id: str) -> Optional[OrderRecord]:
        """Get order record by ID."""
        model = await self.get_order_model(order_id)
        if model:
            return self._model_to_order(model)
        return None
    
    async def get_orders_by_state(
        self,
        states: List[OrderState],
        limit: int = 100,
    ) -> List[OrderRecord]:
        """Get orders by state."""
        state_values = [s.value for s in states]
        result = await self._session.execute(
            select(ExecutionOrderModel)
            .where(ExecutionOrderModel.state.in_(state_values))
            .order_by(desc(ExecutionOrderModel.created_at))
            .limit(limit)
        )
        return [self._model_to_order(m) for m in result.scalars()]
    
    async def get_orders_by_symbol(
        self,
        symbol: str,
        limit: int = 100,
    ) -> List[OrderRecord]:
        """Get orders by symbol."""
        result = await self._session.execute(
            select(ExecutionOrderModel)
            .where(ExecutionOrderModel.symbol == symbol)
            .order_by(desc(ExecutionOrderModel.created_at))
            .limit(limit)
        )
        return [self._model_to_order(m) for m in result.scalars()]
    
    async def get_orders_by_strategy(
        self,
        strategy_id: str,
        limit: int = 100,
    ) -> List[OrderRecord]:
        """Get orders by strategy."""
        result = await self._session.execute(
            select(ExecutionOrderModel)
            .where(ExecutionOrderModel.strategy_id == strategy_id)
            .order_by(desc(ExecutionOrderModel.created_at))
            .limit(limit)
        )
        return [self._model_to_order(m) for m in result.scalars()]
    
    async def get_active_orders(self) -> List[OrderRecord]:
        """Get all active orders."""
        active_states = [
            OrderState.PENDING_VALIDATION.value,
            OrderState.PENDING_SUBMISSION.value,
            OrderState.SUBMITTED.value,
            OrderState.PARTIALLY_FILLED.value,
        ]
        result = await self._session.execute(
            select(ExecutionOrderModel)
            .where(ExecutionOrderModel.state.in_(active_states))
            .order_by(ExecutionOrderModel.created_at)
        )
        return [self._model_to_order(m) for m in result.scalars()]
    
    async def get_recent_orders(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> List[OrderRecord]:
        """Get recent orders."""
        since = datetime.utcnow() - timedelta(hours=hours)
        result = await self._session.execute(
            select(ExecutionOrderModel)
            .where(ExecutionOrderModel.created_at >= since)
            .order_by(desc(ExecutionOrderModel.created_at))
            .limit(limit)
        )
        return [self._model_to_order(m) for m in result.scalars()]
    
    def _model_to_order(self, model: ExecutionOrderModel) -> OrderRecord:
        """Convert model to order record."""
        from .types import OrderSide, OrderType, TimeInForce, PositionSide
        
        return OrderRecord(
            order_id=model.order_id,
            intent_id=model.intent_id,
            exchange_order_id=model.exchange_order_id,
            client_order_id=model.client_order_id,
            state=OrderState(model.state),
            previous_state=OrderState(model.previous_state) if model.previous_state else None,
            symbol=model.symbol,
            side=OrderSide(model.side),
            order_type=OrderType(model.order_type),
            quantity=model.quantity,
            price=model.price,
            stop_price=model.stop_price,
            time_in_force=TimeInForce(model.time_in_force),
            position_side=PositionSide(model.position_side),
            reduce_only=model.reduce_only,
            filled_quantity=model.filled_quantity,
            remaining_quantity=model.remaining_quantity,
            average_fill_price=model.average_fill_price,
            commission=model.commission,
            commission_asset=model.commission_asset,
            created_at=model.created_at,
            submitted_at=model.submitted_at,
            filled_at=model.filled_at,
            completed_at=model.completed_at,
            retry_count=model.retry_count,
            last_error=model.last_error,
            exchange_error_code=model.exchange_error_code,
            strategy_id=model.strategy_id,
            exchange_id=model.exchange_id,
        )
    
    # --------------------------------------------------------
    # FILL OPERATIONS
    # --------------------------------------------------------
    
    async def save_fill(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        commission: Decimal = Decimal("0"),
        commission_asset: str = None,
        trade_id: str = None,
        filled_at: datetime = None,
        is_maker: bool = False,
    ) -> ExecutionFillModel:
        """Save a fill record."""
        fill_id = str(uuid.uuid4())
        quote_quantity = quantity * price
        
        model = ExecutionFillModel(
            fill_id=fill_id,
            trade_id=trade_id,
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            quote_quantity=quote_quantity,
            commission=commission,
            commission_asset=commission_asset,
            filled_at=filled_at or datetime.utcnow(),
            is_maker=is_maker,
        )
        
        self._session.add(model)
        await self._session.commit()
        return model
    
    async def get_fills_for_order(self, order_id: str) -> List[ExecutionFillModel]:
        """Get all fills for an order."""
        result = await self._session.execute(
            select(ExecutionFillModel)
            .where(ExecutionFillModel.order_id == order_id)
            .order_by(ExecutionFillModel.filled_at)
        )
        return list(result.scalars())
    
    async def get_fills_by_symbol(
        self,
        symbol: str,
        since: datetime = None,
        limit: int = 100,
    ) -> List[ExecutionFillModel]:
        """Get fills by symbol."""
        query = select(ExecutionFillModel).where(ExecutionFillModel.symbol == symbol)
        
        if since:
            query = query.where(ExecutionFillModel.filled_at >= since)
        
        query = query.order_by(desc(ExecutionFillModel.filled_at)).limit(limit)
        
        result = await self._session.execute(query)
        return list(result.scalars())
    
    # --------------------------------------------------------
    # EVENT OPERATIONS
    # --------------------------------------------------------
    
    async def save_event(self, event: StateTransitionEvent) -> ExecutionEventModel:
        """Save a state transition event."""
        event_id = str(uuid.uuid4())
        
        model = ExecutionEventModel(
            event_id=event_id,
            order_id=event.order_id,
            from_state=event.from_state.value,
            to_state=event.to_state.value,
            reason=event.reason,
            exchange_update=event.exchange_update,
            details_json=json.dumps(event.details) if event.details else None,
            occurred_at=event.timestamp,
        )
        
        self._session.add(model)
        await self._session.commit()
        return model
    
    async def get_events_for_order(self, order_id: str) -> List[ExecutionEventModel]:
        """Get all events for an order."""
        result = await self._session.execute(
            select(ExecutionEventModel)
            .where(ExecutionEventModel.order_id == order_id)
            .order_by(ExecutionEventModel.occurred_at)
        )
        return list(result.scalars())
    
    # --------------------------------------------------------
    # ALERT OPERATIONS
    # --------------------------------------------------------
    
    async def save_alert(self, alert: Alert) -> ExecutionAlertModel:
        """Save an alert."""
        alert_id = str(uuid.uuid4())
        
        model = ExecutionAlertModel(
            alert_id=alert_id,
            alert_type=alert.alert_type.value,
            severity=alert.severity.value,
            message=alert.message,
            details_json=json.dumps(alert.details) if alert.details else None,
            order_id=alert.order_id,
            symbol=alert.symbol,
            created_at=alert.timestamp,
        )
        
        self._session.add(model)
        await self._session.commit()
        return model
    
    async def mark_alert_sent(self, alert_id: str) -> None:
        """Mark an alert as sent."""
        await self._session.execute(
            update(ExecutionAlertModel)
            .where(ExecutionAlertModel.alert_id == alert_id)
            .values(sent=True, sent_at=datetime.utcnow())
        )
        await self._session.commit()
    
    async def acknowledge_alert(self, alert_id: str, by: str = None) -> None:
        """Acknowledge an alert."""
        await self._session.execute(
            update(ExecutionAlertModel)
            .where(ExecutionAlertModel.alert_id == alert_id)
            .values(
                acknowledged=True,
                acknowledged_at=datetime.utcnow(),
                acknowledged_by=by,
            )
        )
        await self._session.commit()
    
    async def get_unacknowledged_alerts(
        self,
        severity: str = None,
        limit: int = 100,
    ) -> List[ExecutionAlertModel]:
        """Get unacknowledged alerts."""
        query = select(ExecutionAlertModel).where(
            ExecutionAlertModel.acknowledged == False
        )
        
        if severity:
            query = query.where(ExecutionAlertModel.severity == severity)
        
        query = query.order_by(desc(ExecutionAlertModel.created_at)).limit(limit)
        
        result = await self._session.execute(query)
        return list(result.scalars())
    
    # --------------------------------------------------------
    # RECONCILIATION OPERATIONS
    # --------------------------------------------------------
    
    async def save_reconciliation_result(
        self,
        result: ReconciliationResult,
    ) -> ReconciliationLogModel:
        """Save reconciliation result."""
        model = ReconciliationLogModel(
            run_id=result.run_id,
            orders_checked=result.orders_checked,
            orders_synced=result.orders_synced,
            mismatches_found=len(result.mismatches),
            mismatches_resolved=sum(1 for m in result.mismatches if m.auto_resolved),
            errors_count=len(result.errors),
            success=result.success,
            has_critical=result.has_critical,
            errors_json=json.dumps(result.errors) if result.errors else None,
            mismatches_json=json.dumps([
                {
                    "type": m.mismatch_type.value,
                    "severity": m.severity.value,
                    "order_id": m.order_id,
                    "message": m.message,
                }
                for m in result.mismatches
            ]) if result.mismatches else None,
            started_at=result.started_at,
            completed_at=result.completed_at,
        )
        
        self._session.add(model)
        await self._session.commit()
        return model
    
    async def get_recent_reconciliation_logs(
        self,
        limit: int = 10,
    ) -> List[ReconciliationLogModel]:
        """Get recent reconciliation logs."""
        result = await self._session.execute(
            select(ReconciliationLogModel)
            .order_by(desc(ReconciliationLogModel.started_at))
            .limit(limit)
        )
        return list(result.scalars())
    
    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------
    
    async def get_execution_stats(
        self,
        since: datetime = None,
        symbol: str = None,
    ) -> Dict[str, Any]:
        """Get execution statistics."""
        if since is None:
            since = datetime.utcnow() - timedelta(hours=24)
        
        query = select(ExecutionOrderModel).where(
            ExecutionOrderModel.created_at >= since
        )
        
        if symbol:
            query = query.where(ExecutionOrderModel.symbol == symbol)
        
        result = await self._session.execute(query)
        orders = list(result.scalars())
        
        # Calculate stats
        total = len(orders)
        by_state = {}
        total_volume = Decimal("0")
        total_commission = Decimal("0")
        
        for order in orders:
            state = order.state
            by_state[state] = by_state.get(state, 0) + 1
            
            if order.filled_quantity and order.average_fill_price:
                total_volume += order.filled_quantity * order.average_fill_price
            
            total_commission += order.commission or Decimal("0")
        
        return {
            "total_orders": total,
            "by_state": by_state,
            "total_volume_quote": str(total_volume),
            "total_commission": str(total_commission),
            "since": since.isoformat(),
        }
