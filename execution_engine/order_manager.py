"""
Execution Engine - Order Manager.

============================================================
PURPOSE
============================================================
Manages order lifecycle from submission to completion.

RESPONSIBILITIES:
- Order submission with idempotency
- Order tracking and state management
- Retry logic with backoff
- Partial fill handling
- Order cancellation

SAFETY CONSTRAINTS:
- No blind retries (only retryable errors)
- No infinite loops (bounded retry count)
- Deterministic behavior

============================================================
ORDER LIFECYCLE
============================================================
PENDING_VALIDATION -> PENDING_SUBMISSION -> SUBMITTED -> 
    PARTIALLY_FILLED/FILLED -> COMPLETED
    
Any state can transition to:
- CANCELED (by user/system)
- EXPIRED (by exchange)
- REJECTED (by exchange)
- FAILED (internal error)

============================================================
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable, Awaitable
from decimal import Decimal
from dataclasses import dataclass, field
import uuid

from .types import (
    OrderIntent,
    OrderRecord,
    OrderState,
    OrderType,
    ExecutionResult,
    ExecutionResultCode,
    AccountState,
    SymbolRules,
    ExchangeError,
)
from .config import (
    ExecutionEngineConfig,
    RetryConfig,
    IdempotencyConfig,
    PartialFillConfig,
)
from .state_machine import OrderStateMachine, StateTransitionEvent
from .validation import PreExecutionValidator, ValidationResult
from .errors import get_error_info, is_retryable
from .adapters import (
    ExchangeAdapter,
    SubmitOrderRequest,
    SubmitOrderResponse,
    QueryOrderRequest,
    QueryOrderResponse,
    CancelOrderRequest,
    map_exchange_status_to_order_state,
)


logger = logging.getLogger(__name__)


# ============================================================
# ORDER MANAGER
# ============================================================

class OrderManager:
    """
    Manages order lifecycle.
    
    Handles:
    - Order creation from intents
    - Submission with retries
    - State tracking
    - Partial fills
    - Cancellation
    
    SAFETY PRINCIPLES:
    - Never retry non-retryable errors
    - Never exceed max retry count
    - Always persist state changes
    """
    
    def __init__(
        self,
        adapter: ExchangeAdapter,
        config: ExecutionEngineConfig,
        is_system_halted: Callable[[], bool] = None,
        on_state_change: Callable[[StateTransitionEvent], Awaitable[None]] = None,
    ):
        """
        Initialize order manager.
        
        Args:
            adapter: Exchange adapter
            config: Execution configuration
            is_system_halted: Callable to check halt state
            on_state_change: Callback for state changes
        """
        self._adapter = adapter
        self._config = config
        self._is_system_halted = is_system_halted or (lambda: False)
        self._on_state_change = on_state_change
        
        # Active orders by order_id
        self._orders: Dict[str, OrderRecord] = {}
        
        # State machines by order_id
        self._state_machines: Dict[str, OrderStateMachine] = {}
        
        # Client order ID to order_id mapping (for idempotency)
        self._client_order_map: Dict[str, str] = {}
        
        # Validator
        self._validator = PreExecutionValidator(
            config.validation,
            is_system_halted,
        )
        
        # Lock for order operations
        self._lock = asyncio.Lock()
    
    # --------------------------------------------------------
    # ORDER SUBMISSION
    # --------------------------------------------------------
    
    async def submit_order(
        self,
        intent: OrderIntent,
        account_state: AccountState,
        symbol_rules: SymbolRules,
    ) -> ExecutionResult:
        """
        Submit an order from an approved intent.
        
        This is the main entry point for order execution.
        
        Args:
            intent: Approved order intent from Trade Guard
            account_state: Current account state
            symbol_rules: Symbol trading rules
            
        Returns:
            ExecutionResult with outcome
        """
        async with self._lock:
            # 1. Check for duplicate (idempotency)
            if self._config.idempotency.enabled:
                existing = self._check_duplicate(intent)
                if existing:
                    logger.info(
                        f"Duplicate order detected: {existing.order_id} "
                        f"(client_order_id: {intent.client_order_id})"
                    )
                    return self._create_result_from_order(existing)
            
            # 2. Create order record
            order = self._create_order_from_intent(intent)
            state_machine = OrderStateMachine(order)
            
            # Add state change listener
            if self._on_state_change:
                state_machine.add_listener(
                    lambda e: asyncio.create_task(self._on_state_change(e))
                )
            
            # Track order
            self._orders[order.order_id] = order
            self._state_machines[order.order_id] = state_machine
            
            if order.client_order_id:
                self._client_order_map[order.client_order_id] = order.order_id
            
            logger.info(
                f"Created order {order.order_id}: {order.side.value} "
                f"{order.quantity} {order.symbol} @ {order.order_type.value}"
            )
            
            # 3. Validate
            validation = self._validator.validate(intent, account_state, symbol_rules)
            
            if not validation.is_valid:
                logger.warning(
                    f"Order {order.order_id} failed validation: "
                    f"{validation.error_code} - {validation.error_message}"
                )
                state_machine.mark_rejected(
                    reason=validation.error_message,
                    error_code=validation.error_code,
                )
                return self._create_result_from_order(
                    order,
                    result_code=self._map_validation_error(validation.error_code),
                )
            
            # 4. Apply adjustments from validation
            if validation.adjusted_quantity:
                order.quantity = validation.adjusted_quantity
                order.update_remaining()
                logger.info(f"Adjusted quantity for {order.order_id}: {validation.adjusted_quantity}")
            if validation.adjusted_price:
                order.price = validation.adjusted_price
                logger.info(f"Adjusted price for {order.order_id}: {validation.adjusted_price}")
            
            # Log warnings
            for warning in validation.warnings:
                logger.warning(f"Order {order.order_id} warning: {warning}")
            
            # 5. Mark as pending submission
            state_machine.mark_pending_submission()
            
            # 6. Submit with retries
            return await self._submit_with_retries(order, state_machine)
    
    async def _submit_with_retries(
        self,
        order: OrderRecord,
        state_machine: OrderStateMachine,
    ) -> ExecutionResult:
        """
        Submit order with retry logic.
        
        Implements exponential backoff with bounded retries.
        Only retries on retryable errors.
        """
        retry_config = self._config.retry
        delay = retry_config.initial_delay_seconds
        
        for attempt in range(retry_config.max_retries + 1):
            order.retry_count = attempt
            
            try:
                # Check halt state before each attempt
                if self._is_system_halted():
                    logger.warning(
                        f"Order {order.order_id}: System entered HALT state"
                    )
                    state_machine.mark_failed(
                        reason="System entered HALT state during submission",
                        error="VAL_HALT_STATE",
                    )
                    return self._create_result_from_order(
                        order,
                        result_code=ExecutionResultCode.BLOCKED_HALT_STATE,
                    )
                
                # Submit to exchange
                response = await self._submit_to_exchange(order)
                
                if response.success:
                    # Success! Update order with exchange response
                    state_machine.mark_submitted(
                        exchange_order_id=response.exchange_order_id,
                        reason="Order accepted by exchange",
                    )
                    
                    logger.info(
                        f"Order {order.order_id} submitted: "
                        f"exchange_id={response.exchange_order_id}"
                    )
                    
                    # Check if already filled (common for market orders)
                    if response.filled_quantity >= order.quantity:
                        state_machine.mark_filled(
                            filled_quantity=response.filled_quantity,
                            average_price=response.average_price,
                            reason="Immediate full fill",
                        )
                        state_machine.mark_completed()
                        return self._create_result_from_order(
                            order,
                            result_code=ExecutionResultCode.SUCCESS,
                        )
                    elif response.filled_quantity > Decimal("0"):
                        state_machine.mark_partially_filled(
                            filled_quantity=response.filled_quantity,
                            average_price=response.average_price,
                            reason="Immediate partial fill",
                        )
                        return self._create_result_from_order(
                            order,
                            result_code=ExecutionResultCode.PARTIAL_SUCCESS,
                        )
                    else:
                        # Order submitted, waiting for fill
                        return self._create_result_from_order(
                            order,
                            result_code=ExecutionResultCode.SUCCESS,
                        )
                else:
                    # Submission failed
                    error_code = response.error_code or "SUB_ORDER_REJECTED"
                    
                    # Check if retryable
                    if is_retryable(error_code) and attempt < retry_config.max_retries:
                        logger.warning(
                            f"Order {order.order_id} submission failed "
                            f"(attempt {attempt + 1}/{retry_config.max_retries + 1}): "
                            f"{response.error_message}. Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                        delay = min(
                            delay * retry_config.backoff_multiplier,
                            retry_config.max_delay_seconds
                        )
                        continue
                    
                    # Non-retryable or max retries reached
                    logger.error(
                        f"Order {order.order_id} rejected: "
                        f"{error_code} - {response.error_message}"
                    )
                    state_machine.mark_rejected(
                        reason=response.error_message or "Rejected by exchange",
                        error_code=error_code,
                    )
                    return self._create_result_from_order(
                        order,
                        result_code=self._map_exchange_error(error_code),
                        error_message=response.error_message,
                    )
                    
            except ExchangeError as e:
                error_code = e.code or "EXC_UNKNOWN_ERROR"
                order.last_error = str(e)
                order.exchange_error_code = error_code
                
                if e.is_retryable and attempt < retry_config.max_retries:
                    logger.warning(
                        f"Order {order.order_id} exchange error "
                        f"(attempt {attempt + 1}/{retry_config.max_retries + 1}): "
                        f"{e}. Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                    delay = min(
                        delay * retry_config.backoff_multiplier,
                        retry_config.max_delay_seconds
                    )
                    continue
                
                logger.error(f"Order {order.order_id} failed with exchange error: {e}")
                state_machine.mark_failed(
                    reason=str(e),
                    error=error_code,
                )
                return self._create_result_from_order(
                    order,
                    result_code=self._map_exchange_error(error_code),
                    error_message=str(e),
                )
            
            except asyncio.TimeoutError:
                error_code = "TMO_SUBMISSION_TIMEOUT"
                order.last_error = "Submission timeout"
                
                if attempt < retry_config.max_retries:
                    logger.warning(
                        f"Order {order.order_id} timed out "
                        f"(attempt {attempt + 1}/{retry_config.max_retries + 1}). "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                    delay = min(
                        delay * retry_config.backoff_multiplier,
                        retry_config.max_delay_seconds
                    )
                    continue
                
                logger.error(f"Order {order.order_id} timed out after max retries")
                state_machine.mark_failed(
                    reason="Submission timeout after max retries",
                    error=error_code,
                )
                return self._create_result_from_order(
                    order,
                    result_code=ExecutionResultCode.FAILED_TIMEOUT,
                    error_message="Submission timeout",
                )
            
            except Exception as e:
                # Unexpected error - do not retry
                logger.exception(f"Unexpected error submitting order {order.order_id}: {e}")
                state_machine.mark_failed(
                    reason=f"Internal error: {e}",
                    error="INT_UNEXPECTED_ERROR",
                )
                return self._create_result_from_order(
                    order,
                    result_code=ExecutionResultCode.FAILED_INTERNAL,
                    error_message=str(e),
                )
        
        # Should not reach here, but handle gracefully
        logger.error(f"Order {order.order_id} exhausted retries unexpectedly")
        state_machine.mark_failed(
            reason="Max retries exceeded",
            error="SUB_MAX_RETRIES",
        )
        return self._create_result_from_order(
            order,
            result_code=ExecutionResultCode.FAILED_INTERNAL,
            error_message="Max retries exceeded",
        )
    
    async def _submit_to_exchange(self, order: OrderRecord) -> SubmitOrderResponse:
        """Submit order to exchange via adapter."""
        request = SubmitOrderRequest(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            price=order.price,
            stop_price=order.stop_price,
            time_in_force=order.time_in_force,
            position_side=order.position_side,
            reduce_only=order.reduce_only,
            client_order_id=order.client_order_id,
        )
        
        timeout = self._config.timeout.order_submission_timeout_seconds
        return await asyncio.wait_for(
            self._adapter.submit_order(request),
            timeout=timeout,
        )
    
    # --------------------------------------------------------
    # ORDER CANCELLATION
    # --------------------------------------------------------
    
    async def cancel_order(
        self,
        order_id: str,
        reason: str = "User requested",
    ) -> ExecutionResult:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            reason: Cancellation reason
            
        Returns:
            ExecutionResult
        """
        async with self._lock:
            order = self._orders.get(order_id)
            if not order:
                logger.warning(f"Cancel failed: Order {order_id} not found")
                return ExecutionResult(
                    order_id=order_id,
                    result_code=ExecutionResultCode.FAILED_INTERNAL,
                    error_message="Order not found",
                )
            
            state_machine = self._state_machines.get(order_id)
            if not state_machine:
                logger.error(f"Cancel failed: State machine not found for {order_id}")
                return ExecutionResult(
                    order_id=order_id,
                    result_code=ExecutionResultCode.FAILED_INTERNAL,
                    error_message="State machine not found",
                )
            
            if not state_machine.can_cancel():
                logger.warning(
                    f"Cannot cancel order {order_id} in state {order.state.value}"
                )
                return ExecutionResult(
                    order_id=order_id,
                    result_code=ExecutionResultCode.FAILED_VALIDATION,
                    order_state=order.state,
                    error_message=f"Cannot cancel order in state {order.state.value}",
                )
            
            # Cancel on exchange if submitted
            if order.exchange_order_id:
                try:
                    response = await self._adapter.cancel_order(
                        CancelOrderRequest(
                            symbol=order.symbol,
                            exchange_order_id=order.exchange_order_id,
                        )
                    )
                    
                    if not response.success:
                        # May already be filled - sync state
                        logger.warning(
                            f"Cancel failed for {order_id}: {response.error_message}. "
                            "Syncing state..."
                        )
                        await self._sync_order_state(order, state_machine)
                        return self._create_result_from_order(order)
                    
                    logger.info(f"Order {order_id} canceled on exchange")
                        
                except ExchangeError as e:
                    logger.error(f"Error canceling order {order_id}: {e}")
                    # Try to sync state anyway
                    await self._sync_order_state(order, state_machine)
                    return self._create_result_from_order(order)
            
            state_machine.mark_canceled(reason)
            logger.info(f"Order {order_id} canceled: {reason}")
            return self._create_result_from_order(order)
    
    async def cancel_all_orders(
        self,
        symbol: Optional[str] = None,
        reason: str = "Cancel all orders",
    ) -> int:
        """
        Cancel all open orders.
        
        Args:
            symbol: Specific symbol or None for all
            reason: Cancellation reason
            
        Returns:
            Number of orders canceled
        """
        count = 0
        
        async with self._lock:
            for order_id, order in list(self._orders.items()):
                if symbol and order.symbol != symbol:
                    continue
                
                state_machine = self._state_machines.get(order_id)
                if state_machine and state_machine.can_cancel():
                    # Release lock for individual cancel
                    pass
        
        # Cancel outside lock
        for order_id, order in list(self._orders.items()):
            if symbol and order.symbol != symbol:
                continue
            
            state_machine = self._state_machines.get(order_id)
            if state_machine and state_machine.can_cancel():
                result = await self.cancel_order(order_id, reason)
                if result.order_state == OrderState.CANCELED:
                    count += 1
        
        logger.info(f"Canceled {count} orders (symbol={symbol or 'all'})")
        return count
    
    # --------------------------------------------------------
    # ORDER TRACKING
    # --------------------------------------------------------
    
    async def sync_order_state(self, order_id: str) -> Optional[OrderRecord]:
        """
        Sync order state with exchange.
        
        Args:
            order_id: Order ID to sync
            
        Returns:
            Updated order record or None
        """
        async with self._lock:
            order = self._orders.get(order_id)
            if not order:
                return None
            
            state_machine = self._state_machines.get(order_id)
            if not state_machine:
                return None
            
            await self._sync_order_state(order, state_machine)
            return order
    
    async def _sync_order_state(
        self,
        order: OrderRecord,
        state_machine: OrderStateMachine,
    ) -> None:
        """Sync order state with exchange (internal)."""
        if not order.exchange_order_id:
            return
        
        if state_machine.is_terminal():
            return
        
        try:
            response = await self._adapter.query_order(
                QueryOrderRequest(
                    symbol=order.symbol,
                    exchange_order_id=order.exchange_order_id,
                )
            )
            
            if not response.found:
                logger.warning(f"Order {order.order_id} not found on exchange")
                return
            
            # Update order from response
            order.filled_quantity = response.filled_quantity
            order.remaining_quantity = response.remaining_quantity
            order.average_fill_price = response.average_price
            order.last_update_at = datetime.utcnow()
            
            # Map exchange status to our state
            exchange_state = map_exchange_status_to_order_state(
                self._adapter.exchange_id,
                response.status,
            )
            
            # Transition if needed
            if exchange_state == OrderState.FILLED:
                if order.state != OrderState.FILLED:
                    state_machine.mark_filled(
                        filled_quantity=response.filled_quantity,
                        average_price=response.average_price,
                        reason="Synced from exchange",
                    )
                    state_machine.mark_completed()
                    logger.info(f"Order {order.order_id} filled (synced)")
                    
            elif exchange_state == OrderState.PARTIALLY_FILLED:
                if order.state != OrderState.PARTIALLY_FILLED:
                    state_machine.mark_partially_filled(
                        filled_quantity=response.filled_quantity,
                        average_price=response.average_price,
                        reason="Synced from exchange",
                    )
                    logger.info(
                        f"Order {order.order_id} partially filled: "
                        f"{response.filled_quantity}/{order.quantity}"
                    )
                    
            elif exchange_state == OrderState.CANCELED:
                state_machine.mark_canceled("Canceled on exchange", exchange_update=True)
                logger.info(f"Order {order.order_id} canceled (synced)")
                
            elif exchange_state == OrderState.EXPIRED:
                state_machine.mark_expired()
                logger.info(f"Order {order.order_id} expired (synced)")
                
            elif exchange_state == OrderState.REJECTED:
                state_machine.mark_rejected("Rejected by exchange")
                logger.warning(f"Order {order.order_id} rejected (synced)")
                
        except ExchangeError as e:
            logger.error(f"Error syncing order {order.order_id}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error syncing order {order.order_id}: {e}")
    
    async def sync_all_active_orders(self) -> int:
        """
        Sync all active orders with exchange.
        
        Returns:
            Number of orders synced
        """
        count = 0
        for order_id in list(self._orders.keys()):
            order = self._orders.get(order_id)
            if order and order.state.is_active():
                await self.sync_order_state(order_id)
                count += 1
        return count
    
    # --------------------------------------------------------
    # GETTERS
    # --------------------------------------------------------
    
    def get_order(self, order_id: str) -> Optional[OrderRecord]:
        """Get order by ID."""
        return self._orders.get(order_id)
    
    def get_order_by_client_id(self, client_order_id: str) -> Optional[OrderRecord]:
        """Get order by client order ID."""
        order_id = self._client_order_map.get(client_order_id)
        if order_id:
            return self._orders.get(order_id)
        return None
    
    def get_active_orders(self) -> List[OrderRecord]:
        """Get all active orders."""
        return [o for o in self._orders.values() if o.state.is_active()]
    
    def get_orders_by_symbol(self, symbol: str) -> List[OrderRecord]:
        """Get all orders for a symbol."""
        return [o for o in self._orders.values() if o.symbol == symbol]
    
    def get_orders_by_strategy(self, strategy_id: str) -> List[OrderRecord]:
        """Get all orders for a strategy."""
        return [o for o in self._orders.values() if o.strategy_id == strategy_id]
    
    def get_all_orders(self) -> List[OrderRecord]:
        """Get all orders."""
        return list(self._orders.values())
    
    # --------------------------------------------------------
    # HELPERS
    # --------------------------------------------------------
    
    def _check_duplicate(self, intent: OrderIntent) -> Optional[OrderRecord]:
        """Check for duplicate order (idempotency)."""
        if not intent.client_order_id:
            return None
        
        order_id = self._client_order_map.get(intent.client_order_id)
        if order_id:
            return self._orders.get(order_id)
        
        return None
    
    def _create_order_from_intent(self, intent: OrderIntent) -> OrderRecord:
        """Create order record from intent."""
        # Generate client order ID if not provided
        client_order_id = intent.client_order_id
        if not client_order_id and self._config.idempotency.enabled:
            prefix = self._config.idempotency.client_order_id_prefix
            client_order_id = f"{prefix}{uuid.uuid4().hex[:16]}"
        
        return OrderRecord(
            order_id=str(uuid.uuid4()),
            intent_id=intent.intent_id,
            client_order_id=client_order_id,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            quantity=intent.quantity,
            remaining_quantity=intent.quantity,
            price=intent.price,
            stop_price=intent.stop_price,
            time_in_force=intent.time_in_force,
            position_side=intent.position_side,
            reduce_only=intent.reduce_only,
            strategy_id=intent.strategy_id,
            exchange_id=self._adapter.exchange_id,
        )
    
    def _create_result_from_order(
        self,
        order: OrderRecord,
        result_code: ExecutionResultCode = None,
        error_message: str = None,
    ) -> ExecutionResult:
        """Create execution result from order."""
        # Determine result code if not provided
        if result_code is None:
            if order.state == OrderState.COMPLETED:
                result_code = ExecutionResultCode.SUCCESS
            elif order.state == OrderState.FILLED:
                result_code = ExecutionResultCode.SUCCESS
            elif order.state == OrderState.PARTIALLY_FILLED:
                result_code = ExecutionResultCode.PARTIAL_SUCCESS
            elif order.state == OrderState.SUBMITTED:
                result_code = ExecutionResultCode.SUCCESS
            elif order.state == OrderState.REJECTED:
                result_code = ExecutionResultCode.REJECTED_BY_EXCHANGE
            elif order.state == OrderState.CANCELED:
                result_code = ExecutionResultCode.SUCCESS
            elif order.state == OrderState.FAILED:
                result_code = ExecutionResultCode.FAILED_INTERNAL
            else:
                result_code = ExecutionResultCode.SUCCESS
        
        return ExecutionResult(
            intent_id=order.intent_id,
            order_id=order.order_id,
            exchange_order_id=order.exchange_order_id,
            client_order_id=order.client_order_id,
            result_code=result_code,
            order_state=order.state,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            requested_quantity=order.quantity,
            filled_quantity=order.filled_quantity,
            average_fill_price=order.average_fill_price,
            commission=order.commission,
            commission_asset=order.commission_asset,
            submitted_at=order.submitted_at,
            filled_at=order.filled_at,
            completed_at=order.completed_at,
            error_message=error_message or order.last_error,
            error_code=order.exchange_error_code,
            retry_count=order.retry_count,
        )
    
    def _map_validation_error(self, code: str) -> ExecutionResultCode:
        """Map validation error code to result code."""
        mapping = {
            "VAL_HALT_STATE": ExecutionResultCode.BLOCKED_HALT_STATE,
            "VAL_INVALID_APPROVAL": ExecutionResultCode.BLOCKED_NO_APPROVAL,
            "VAL_EXPIRED_APPROVAL": ExecutionResultCode.BLOCKED_EXPIRED_APPROVAL,
            "VAL_INSUFFICIENT_BALANCE": ExecutionResultCode.REJECTED_INSUFFICIENT_BALANCE,
            "VAL_INVALID_SYMBOL": ExecutionResultCode.REJECTED_INVALID_SYMBOL,
            "VAL_INVALID_QUANTITY": ExecutionResultCode.REJECTED_INVALID_QUANTITY,
            "VAL_INVALID_PRICE": ExecutionResultCode.REJECTED_INVALID_PRICE,
            "VAL_BELOW_MIN_NOTIONAL": ExecutionResultCode.REJECTED_INVALID_QUANTITY,
        }
        return mapping.get(code, ExecutionResultCode.FAILED_VALIDATION)
    
    def _map_exchange_error(self, code: str) -> ExecutionResultCode:
        """Map exchange error code to result code."""
        if "INSUFFICIENT" in code.upper():
            return ExecutionResultCode.REJECTED_INSUFFICIENT_BALANCE
        elif "RATE" in code.upper():
            return ExecutionResultCode.REJECTED_RATE_LIMITED
        elif "TIMEOUT" in code.upper() or "TMO" in code.upper():
            return ExecutionResultCode.FAILED_TIMEOUT
        elif "NET" in code.upper():
            return ExecutionResultCode.FAILED_NETWORK
        elif "AUT" in code.upper():
            return ExecutionResultCode.FAILED_AUTHENTICATION
        elif "POSITION" in code.upper():
            return ExecutionResultCode.REJECTED_POSITION_LIMIT
        elif "MARKET" in code.upper() and "CLOSED" in code.upper():
            return ExecutionResultCode.REJECTED_MARKET_CLOSED
        else:
            return ExecutionResultCode.REJECTED_BY_EXCHANGE
