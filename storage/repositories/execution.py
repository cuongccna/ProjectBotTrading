"""
Execution Repositories.

============================================================
PURPOSE
============================================================
Repositories for order execution. These handle order lifecycle,
execution results, and trade records.

============================================================
DATA LIFECYCLE
============================================================
- Stage: EXECUTION
- Mutability: APPEND-ONLY (state changes tracked separately)
- Full audit trail for compliance and reconciliation

============================================================
REPOSITORIES
============================================================
- OrderRepository: Order management and state tracking
- ExecutionResultRepository: Execution results and validation

============================================================
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import UUID

from sqlalchemy import select, and_, desc, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from storage.models.execution import (
    Order,
    OrderStateTransition,
    Execution,
    ExecutionValidation,
    TradeRecord,
)
from storage.repositories.base import BaseRepository
from storage.repositories.exceptions import (
    RecordNotFoundError,
    RepositoryException,
)


class OrderRepository(BaseRepository[Order]):
    """
    Repository for orders.
    
    ============================================================
    SCOPE
    ============================================================
    Manages Order and OrderStateTransition records. Complete
    order lifecycle from creation to completion or cancellation.
    
    ============================================================
    MODELS MANAGED
    ============================================================
    - Order: Core order records
    - OrderStateTransition: Order state change audit
    
    ============================================================
    IMMUTABILITY
    ============================================================
    Orders are APPEND-ONLY. State changes are tracked via
    OrderStateTransition records, not updates to Order.
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, Order, "OrderRepository")
    
    # =========================================================
    # ORDER OPERATIONS
    # =========================================================
    
    def create_order(
        self,
        decision_id: UUID,
        symbol: str,
        exchange: str,
        order_type: str,
        side: str,
        quantity: Decimal,
        price: Optional[Decimal],
        created_at: datetime,
        strategy_id: str,
        time_in_force: str = "GTC",
        stop_price: Optional[Decimal] = None,
        client_order_id: Optional[str] = None,
        state: str = "pending",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Order:
        """
        Create an order.
        
        Args:
            decision_id: Reference to trading decision
            symbol: Trading symbol
            exchange: Exchange identifier
            order_type: Order type (market, limit, stop)
            side: Order side (buy, sell)
            quantity: Order quantity
            price: Limit price (for limit orders)
            created_at: Creation timestamp
            strategy_id: Strategy identifier
            time_in_force: Time in force (GTC, IOC, FOK)
            stop_price: Stop price (for stop orders)
            client_order_id: Client-assigned order ID
            state: Initial state
            metadata: Additional metadata
            
        Returns:
            Created Order record
        """
        entity = Order(
            decision_id=decision_id,
            symbol=symbol,
            exchange=exchange,
            order_type=order_type,
            side=side,
            quantity=quantity,
            price=price,
            created_at=created_at,
            strategy_id=strategy_id,
            time_in_force=time_in_force,
            stop_price=stop_price,
            client_order_id=client_order_id,
            state=state,
            filled_quantity=Decimal("0"),
            metadata=metadata or {},
        )
        return self._add(entity)
    
    def get_order_by_id(self, order_id: UUID) -> Optional[Order]:
        """Get order by ID."""
        return self._get_by_id(order_id)
    
    def get_order_by_id_or_raise(self, order_id: UUID) -> Order:
        """Get order by ID, raising if not found."""
        return self._get_by_id_or_raise(order_id, "order_id")
    
    def get_order_by_client_id(
        self,
        client_order_id: str
    ) -> Optional[Order]:
        """
        Get order by client order ID.
        
        Args:
            client_order_id: Client-assigned order ID
            
        Returns:
            Order or None
        """
        stmt = select(Order).where(Order.client_order_id == client_order_id)
        return self._execute_scalar(stmt)
    
    def get_order_by_exchange_id(
        self,
        exchange: str,
        exchange_order_id: str
    ) -> Optional[Order]:
        """
        Get order by exchange order ID.
        
        Args:
            exchange: Exchange identifier
            exchange_order_id: Exchange-assigned order ID
            
        Returns:
            Order or None
        """
        stmt = select(Order).where(and_(
            Order.exchange == exchange,
            Order.exchange_order_id == exchange_order_id,
        ))
        return self._execute_scalar(stmt)
    
    def list_orders_by_decision(
        self,
        decision_id: UUID
    ) -> List[Order]:
        """
        List all orders for a decision.
        
        Args:
            decision_id: The decision UUID
            
        Returns:
            List of Order
        """
        stmt = (
            select(Order)
            .where(Order.decision_id == decision_id)
            .order_by(Order.created_at)
        )
        return self._execute_query(stmt)
    
    def list_orders_by_symbol(
        self,
        symbol: str,
        exchange: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 100
    ) -> List[Order]:
        """
        List orders by symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Optional exchange filter
            state: Optional state filter
            limit: Maximum records to return
            
        Returns:
            List of Order
        """
        conditions = [Order.symbol == symbol]
        if exchange:
            conditions.append(Order.exchange == exchange)
        if state:
            conditions.append(Order.state == state)
        
        stmt = (
            select(Order)
            .where(and_(*conditions))
            .order_by(desc(Order.created_at))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_orders_by_state(
        self,
        state: str,
        limit: int = 100
    ) -> List[Order]:
        """
        List orders by state.
        
        Args:
            state: Order state
            limit: Maximum records to return
            
        Returns:
            List of Order
        """
        stmt = (
            select(Order)
            .where(Order.state == state)
            .order_by(desc(Order.created_at))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_orders_by_strategy(
        self,
        strategy_id: str,
        limit: int = 100
    ) -> List[Order]:
        """
        List orders by strategy.
        
        Args:
            strategy_id: Strategy identifier
            limit: Maximum records to return
            
        Returns:
            List of Order
        """
        stmt = (
            select(Order)
            .where(Order.strategy_id == strategy_id)
            .order_by(desc(Order.created_at))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_open_orders(
        self,
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
        limit: int = 100
    ) -> List[Order]:
        """
        List open (active) orders.
        
        Args:
            symbol: Optional symbol filter
            exchange: Optional exchange filter
            limit: Maximum records to return
            
        Returns:
            List of open Order records
        """
        open_states = ["pending", "submitted", "partial"]
        conditions = [Order.state.in_(open_states)]
        if symbol:
            conditions.append(Order.symbol == symbol)
        if exchange:
            conditions.append(Order.exchange == exchange)
        
        stmt = (
            select(Order)
            .where(and_(*conditions))
            .order_by(Order.created_at)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_orders_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: Optional[str] = None,
        limit: int = 1000
    ) -> List[Order]:
        """
        List orders within a time range.
        
        Args:
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            symbol: Optional symbol filter
            limit: Maximum records to return
            
        Returns:
            List of Order
        """
        conditions = [
            Order.created_at >= start_time,
            Order.created_at < end_time,
        ]
        if symbol:
            conditions.append(Order.symbol == symbol)
        
        stmt = (
            select(Order)
            .where(and_(*conditions))
            .order_by(Order.created_at)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    # =========================================================
    # ORDER STATE TRANSITION OPERATIONS
    # =========================================================
    
    def record_order_state_transition(
        self,
        order_id: UUID,
        from_state: str,
        to_state: str,
        transitioned_at: datetime,
        reason: str,
        exchange_order_id: Optional[str] = None,
        exchange_message: Optional[str] = None,
        filled_quantity: Optional[Decimal] = None,
        filled_price: Optional[Decimal] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OrderStateTransition:
        """
        Record an order state transition.
        
        Args:
            order_id: Reference to order
            from_state: Previous state
            to_state: New state
            transitioned_at: Transition timestamp
            reason: Transition reason
            exchange_order_id: Exchange order ID if available
            exchange_message: Exchange message if available
            filled_quantity: Fill quantity if applicable
            filled_price: Fill price if applicable
            metadata: Additional metadata
            
        Returns:
            Created OrderStateTransition record
        """
        entity = OrderStateTransition(
            order_id=order_id,
            from_state=from_state,
            to_state=to_state,
            transitioned_at=transitioned_at,
            reason=reason,
            exchange_order_id=exchange_order_id,
            exchange_message=exchange_message,
            filled_quantity=filled_quantity,
            filled_price=filled_price,
            metadata=metadata or {},
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.info(
                f"Order {order_id}: {from_state} -> {to_state}"
            )
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_order_state_transition", {
                "order_id": str(order_id),
                "transition": f"{from_state} -> {to_state}"
            })
            raise
    
    def list_order_state_transitions(
        self,
        order_id: UUID
    ) -> List[OrderStateTransition]:
        """
        List all state transitions for an order.
        
        Args:
            order_id: The order UUID
            
        Returns:
            List of OrderStateTransition
        """
        stmt = (
            select(OrderStateTransition)
            .where(OrderStateTransition.order_id == order_id)
            .order_by(OrderStateTransition.transitioned_at)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_order_state_transitions", {
                "order_id": str(order_id)
            })
            raise


class ExecutionResultRepository(BaseRepository[Execution]):
    """
    Repository for execution results.
    
    ============================================================
    SCOPE
    ============================================================
    Manages Execution, ExecutionValidation, and TradeRecord.
    Complete execution audit trail including fills, validations,
    and final trade records.
    
    ============================================================
    MODELS MANAGED
    ============================================================
    - Execution: Individual execution/fill records
    - ExecutionValidation: Post-execution validation
    - TradeRecord: Consolidated trade records
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, Execution, "ExecutionResultRepository")
    
    # =========================================================
    # EXECUTION OPERATIONS
    # =========================================================
    
    def record_execution(
        self,
        order_id: UUID,
        executed_at: datetime,
        execution_price: Decimal,
        executed_quantity: Decimal,
        commission: Decimal,
        commission_asset: str,
        exchange_execution_id: str,
        execution_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Execution:
        """
        Record an execution/fill.
        
        Args:
            order_id: Reference to order
            executed_at: Execution timestamp
            execution_price: Execution price
            executed_quantity: Executed quantity
            commission: Commission amount
            commission_asset: Commission asset
            exchange_execution_id: Exchange execution ID
            execution_type: Execution type (fill, partial_fill)
            metadata: Additional metadata
            
        Returns:
            Created Execution record
        """
        entity = Execution(
            order_id=order_id,
            executed_at=executed_at,
            execution_price=execution_price,
            executed_quantity=executed_quantity,
            commission=commission,
            commission_asset=commission_asset,
            exchange_execution_id=exchange_execution_id,
            execution_type=execution_type,
            metadata=metadata or {},
        )
        return self._add(entity)
    
    def get_execution_by_id(
        self,
        execution_id: UUID
    ) -> Optional[Execution]:
        """Get execution by ID."""
        return self._get_by_id(execution_id)
    
    def get_execution_by_exchange_id(
        self,
        exchange_execution_id: str
    ) -> Optional[Execution]:
        """
        Get execution by exchange execution ID.
        
        Args:
            exchange_execution_id: Exchange execution ID
            
        Returns:
            Execution or None
        """
        stmt = select(Execution).where(
            Execution.exchange_execution_id == exchange_execution_id
        )
        return self._execute_scalar(stmt)
    
    def list_executions_by_order(
        self,
        order_id: UUID
    ) -> List[Execution]:
        """
        List all executions for an order.
        
        Args:
            order_id: The order UUID
            
        Returns:
            List of Execution
        """
        stmt = (
            select(Execution)
            .where(Execution.order_id == order_id)
            .order_by(Execution.executed_at)
        )
        return self._execute_query(stmt)
    
    def list_executions_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000
    ) -> List[Execution]:
        """
        List executions within a time range.
        
        Args:
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            limit: Maximum records to return
            
        Returns:
            List of Execution
        """
        stmt = (
            select(Execution)
            .where(and_(
                Execution.executed_at >= start_time,
                Execution.executed_at < end_time,
            ))
            .order_by(Execution.executed_at)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    # =========================================================
    # EXECUTION VALIDATION OPERATIONS
    # =========================================================
    
    def record_execution_validation(
        self,
        execution_id: UUID,
        validated_at: datetime,
        is_valid: bool,
        validator_version: str,
        checks_passed: List[str],
        checks_failed: List[str],
        discrepancies: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionValidation:
        """
        Record execution validation.
        
        Args:
            execution_id: Reference to execution
            validated_at: Validation timestamp
            is_valid: Whether execution is valid
            validator_version: Validator version
            checks_passed: List of passed checks
            checks_failed: List of failed checks
            discrepancies: Any discrepancies found
            metadata: Additional metadata
            
        Returns:
            Created ExecutionValidation record
        """
        entity = ExecutionValidation(
            execution_id=execution_id,
            validated_at=validated_at,
            is_valid=is_valid,
            validator_version=validator_version,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            discrepancies=discrepancies,
            metadata=metadata or {},
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.debug(
                f"Execution {execution_id} validation: {is_valid}"
            )
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_execution_validation", {
                "execution_id": str(execution_id)
            })
            raise
    
    def get_validation_by_execution(
        self,
        execution_id: UUID
    ) -> Optional[ExecutionValidation]:
        """
        Get validation for an execution.
        
        Args:
            execution_id: The execution UUID
            
        Returns:
            ExecutionValidation or None
        """
        stmt = select(ExecutionValidation).where(
            ExecutionValidation.execution_id == execution_id
        )
        try:
            result = self._session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            self._handle_db_error(e, "get_validation_by_execution", {
                "execution_id": str(execution_id)
            })
            raise
    
    def list_failed_validations(
        self,
        limit: int = 100
    ) -> List[ExecutionValidation]:
        """
        List failed execution validations.
        
        Args:
            limit: Maximum records to return
            
        Returns:
            List of failed ExecutionValidation records
        """
        stmt = (
            select(ExecutionValidation)
            .where(ExecutionValidation.is_valid == False)
            .order_by(desc(ExecutionValidation.validated_at))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_failed_validations", {})
            raise
    
    # =========================================================
    # TRADE RECORD OPERATIONS
    # =========================================================
    
    def record_trade(
        self,
        decision_id: UUID,
        symbol: str,
        exchange: str,
        side: str,
        strategy_id: str,
        entry_order_id: UUID,
        entry_price: Decimal,
        entry_quantity: Decimal,
        entry_time: datetime,
        entry_commission: Decimal,
        state: str = "open",
        exit_order_id: Optional[UUID] = None,
        exit_price: Optional[Decimal] = None,
        exit_quantity: Optional[Decimal] = None,
        exit_time: Optional[datetime] = None,
        exit_commission: Optional[Decimal] = None,
        pnl: Optional[Decimal] = None,
        pnl_percent: Optional[Decimal] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TradeRecord:
        """
        Record a trade.
        
        Args:
            decision_id: Reference to trading decision
            symbol: Trading symbol
            exchange: Exchange identifier
            side: Trade side (long, short)
            strategy_id: Strategy identifier
            entry_order_id: Entry order ID
            entry_price: Entry price
            entry_quantity: Entry quantity
            entry_time: Entry timestamp
            entry_commission: Entry commission
            state: Trade state (open, closed)
            exit_order_id: Exit order ID if closed
            exit_price: Exit price if closed
            exit_quantity: Exit quantity if closed
            exit_time: Exit timestamp if closed
            exit_commission: Exit commission if closed
            pnl: Profit/loss if closed
            pnl_percent: Profit/loss percentage if closed
            metadata: Additional metadata
            
        Returns:
            Created TradeRecord
        """
        entity = TradeRecord(
            decision_id=decision_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            strategy_id=strategy_id,
            entry_order_id=entry_order_id,
            entry_price=entry_price,
            entry_quantity=entry_quantity,
            entry_time=entry_time,
            entry_commission=entry_commission,
            state=state,
            exit_order_id=exit_order_id,
            exit_price=exit_price,
            exit_quantity=exit_quantity,
            exit_time=exit_time,
            exit_commission=exit_commission,
            pnl=pnl,
            pnl_percent=pnl_percent,
            metadata=metadata or {},
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.info(
                f"Trade recorded: {symbol} {side} @ {entry_price}"
            )
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_trade", {
                "symbol": symbol,
                "side": side
            })
            raise
    
    def get_trade_by_id(
        self,
        trade_id: UUID
    ) -> Optional[TradeRecord]:
        """Get trade record by ID."""
        stmt = select(TradeRecord).where(TradeRecord.id == trade_id)
        return self._execute_scalar(stmt)
    
    def get_trade_by_decision(
        self,
        decision_id: UUID
    ) -> Optional[TradeRecord]:
        """
        Get trade record by decision ID.
        
        Args:
            decision_id: The decision UUID
            
        Returns:
            TradeRecord or None
        """
        stmt = select(TradeRecord).where(TradeRecord.decision_id == decision_id)
        try:
            result = self._session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            self._handle_db_error(e, "get_trade_by_decision", {
                "decision_id": str(decision_id)
            })
            raise
    
    def list_trades_by_symbol(
        self,
        symbol: str,
        state: Optional[str] = None,
        limit: int = 100
    ) -> List[TradeRecord]:
        """
        List trades by symbol.
        
        Args:
            symbol: Trading symbol
            state: Optional state filter
            limit: Maximum records to return
            
        Returns:
            List of TradeRecord
        """
        conditions = [TradeRecord.symbol == symbol]
        if state:
            conditions.append(TradeRecord.state == state)
        
        stmt = (
            select(TradeRecord)
            .where(and_(*conditions))
            .order_by(desc(TradeRecord.entry_time))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_trades_by_symbol", {"symbol": symbol})
            raise
    
    def list_trades_by_strategy(
        self,
        strategy_id: str,
        state: Optional[str] = None,
        limit: int = 100
    ) -> List[TradeRecord]:
        """
        List trades by strategy.
        
        Args:
            strategy_id: Strategy identifier
            state: Optional state filter
            limit: Maximum records to return
            
        Returns:
            List of TradeRecord
        """
        conditions = [TradeRecord.strategy_id == strategy_id]
        if state:
            conditions.append(TradeRecord.state == state)
        
        stmt = (
            select(TradeRecord)
            .where(and_(*conditions))
            .order_by(desc(TradeRecord.entry_time))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_trades_by_strategy", {
                "strategy_id": strategy_id
            })
            raise
    
    def list_open_trades(
        self,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[TradeRecord]:
        """
        List open trades.
        
        Args:
            symbol: Optional symbol filter
            limit: Maximum records to return
            
        Returns:
            List of open TradeRecord records
        """
        conditions = [TradeRecord.state == "open"]
        if symbol:
            conditions.append(TradeRecord.symbol == symbol)
        
        stmt = (
            select(TradeRecord)
            .where(and_(*conditions))
            .order_by(TradeRecord.entry_time)
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_open_trades", {"symbol": symbol})
            raise
    
    def list_trades_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: Optional[str] = None,
        limit: int = 1000
    ) -> List[TradeRecord]:
        """
        List trades within a time range.
        
        Args:
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            symbol: Optional symbol filter
            limit: Maximum records to return
            
        Returns:
            List of TradeRecord
        """
        conditions = [
            TradeRecord.entry_time >= start_time,
            TradeRecord.entry_time < end_time,
        ]
        if symbol:
            conditions.append(TradeRecord.symbol == symbol)
        
        stmt = (
            select(TradeRecord)
            .where(and_(*conditions))
            .order_by(TradeRecord.entry_time)
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_trades_by_time_range", {
                "start": str(start_time),
                "end": str(end_time)
            })
            raise
    
    def list_closed_trades_with_pnl(
        self,
        min_pnl: Optional[Decimal] = None,
        max_pnl: Optional[Decimal] = None,
        limit: int = 100
    ) -> List[TradeRecord]:
        """
        List closed trades with PnL filter.
        
        Args:
            min_pnl: Minimum PnL filter
            max_pnl: Maximum PnL filter
            limit: Maximum records to return
            
        Returns:
            List of closed TradeRecord records
        """
        conditions = [TradeRecord.state == "closed"]
        if min_pnl is not None:
            conditions.append(TradeRecord.pnl >= min_pnl)
        if max_pnl is not None:
            conditions.append(TradeRecord.pnl <= max_pnl)
        
        stmt = (
            select(TradeRecord)
            .where(and_(*conditions))
            .order_by(desc(TradeRecord.exit_time))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_closed_trades_with_pnl", {})
            raise
