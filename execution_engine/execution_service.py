"""
Execution Engine - Execution Service.

============================================================
PURPOSE
============================================================
Main orchestrator for order execution.

This is the primary entry point for the Execution Engine.
It receives approved intents from Trade Guard Absolute
and coordinates the complete execution workflow.

============================================================
DESIGN PRINCIPLES
============================================================
- REACTIVE: Only executes explicitly approved decisions
- DEFENSIVE: Extremely defensive about inputs
- IDEMPOTENT: Safe to retry operations
- AUDITABLE: Complete audit trail
- SUBORDINATE: Never overrides upstream decisions

============================================================
EXECUTION WORKFLOW
============================================================
1. Receive approved OrderIntent from Trade Guard
2. Validate System Risk Controller state (not HALTED)
3. Fetch current account state and symbol rules
4. Submit order via OrderManager
5. Monitor for completion
6. Persist execution event
7. Send alerts on failures
8. Return ExecutionResult

============================================================
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable, Awaitable, Any
from decimal import Decimal
from dataclasses import dataclass, field

from .types import (
    OrderIntent,
    OrderRecord,
    OrderState,
    ExecutionResult,
    ExecutionResultCode,
    AccountState,
    SymbolRules,
    ExchangeError,
    HaltStateError,
    ApprovalError,
)
from .config import ExecutionEngineConfig
from .order_manager import OrderManager
from .state_machine import StateTransitionEvent
from .adapters import ExchangeAdapter


logger = logging.getLogger(__name__)


# ============================================================
# EXECUTION SERVICE
# ============================================================

class ExecutionService:
    """
    Main execution service.
    
    Orchestrates order execution workflow.
    
    AUTHORITY BOUNDARIES:
    - CAN: Submit orders, cancel orders, query status
    - MUST NOT: Override Trade Guard decisions
    - MUST NOT: Bypass System Risk Controller HALT
    - MUST NOT: Resize trades or modify quantities
    """
    
    _is_placeholder: bool = False  # Real implementation
    
    def __init__(
        self,
        config: Optional[ExecutionEngineConfig] = None,
        adapter: Optional[ExchangeAdapter] = None,
        is_system_halted: Callable[[], bool] = None,
        on_execution_complete: Callable[[ExecutionResult], Awaitable[None]] = None,
        on_state_change: Callable[[StateTransitionEvent], Awaitable[None]] = None,
        on_alert: Callable[[str, str, Dict[str, Any]], Awaitable[None]] = None,
        **kwargs,  # For orchestrator compatibility
    ):
        """
        Initialize execution service.
        
        Args:
            config: Execution configuration
            adapter: Exchange adapter
            is_system_halted: Callable to check halt state
            on_execution_complete: Callback for execution completion
            on_state_change: Callback for order state changes
            on_alert: Callback for alerts (severity, message, details)
        """
        # Handle orchestrator dict config
        if config is None or isinstance(config, dict):
            config = ExecutionEngineConfig()
        self._config = config
        self._adapter = adapter
        self._is_system_halted = is_system_halted or (lambda: False)
        self._on_execution_complete = on_execution_complete
        self._on_state_change = on_state_change
        self._on_alert = on_alert
        
        # Create order manager (only if adapter provided)
        self._order_manager = None
        if adapter is not None:
            self._order_manager = OrderManager(
                adapter=adapter,
                config=config,
                is_system_halted=is_system_halted,
                on_state_change=self._handle_state_change,
            )
        
        # Execution tracking
        self._pending_executions: Dict[str, OrderIntent] = {}
        self._execution_history: Dict[str, ExecutionResult] = {}
        
        # Reconciliation task
        self._reconciliation_task: Optional[asyncio.Task] = None
        
        # Service state
        self._running = False
        self._lock = asyncio.Lock()
        
        # Statistics
        self._stats = {
            "total_executions": 0,
            "successful": 0,
            "failed": 0,
            "blocked": 0,
            "rejected": 0,
        }
    
    # --------------------------------------------------------
    # LIFECYCLE
    # --------------------------------------------------------
    
    async def start(self) -> None:
        """Start the execution service."""
        if self._running:
            return
        
        logger.info("Starting Execution Service...")
        
        # Connect adapter (only if configured)
        if self._adapter is not None:
            await self._adapter.connect()
        else:
            logger.warning("Execution Service started without adapter - execute disabled")
        
        # Start reconciliation loop if enabled
        if self._config.reconciliation.enabled and self._adapter is not None:
            self._reconciliation_task = asyncio.create_task(
                self._reconciliation_loop()
            )
        
        self._running = True
        logger.info("Execution Service started")
    
    async def stop(self) -> None:
        """Stop the execution service."""
        if not self._running:
            return
        
        logger.info("Stopping Execution Service...")
        
        self._running = False
        
        # Cancel reconciliation task
        if self._reconciliation_task:
            self._reconciliation_task.cancel()
            try:
                await self._reconciliation_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect adapter (only if configured)
        if self._adapter is not None:
            await self._adapter.disconnect()
        
        logger.info("Execution Service stopped")
    
    # --------------------------------------------------------
    # EXECUTION
    # --------------------------------------------------------
    
    async def execute(self, intent: OrderIntent) -> ExecutionResult:
        """
        Execute an approved order intent.
        
        This is the main entry point for order execution.
        The intent MUST have been approved by Trade Guard Absolute.
        
        Args:
            intent: Approved order intent
            
        Returns:
            ExecutionResult with outcome
        """
        self._stats["total_executions"] += 1
        
        # 1. Check service is running
        if not self._running:
            logger.error("Execute called but service not running")
            return self._create_blocked_result(
                intent,
                ExecutionResultCode.FAILED_INTERNAL,
                "Execution service not running",
            )
        
        # 2. Check system halt state
        if self._is_system_halted():
            logger.warning(
                f"Execution blocked for {intent.intent_id}: System HALTED"
            )
            self._stats["blocked"] += 1
            await self._send_alert(
                "CRITICAL",
                "Execution blocked by HALT state",
                {"intent_id": intent.intent_id, "symbol": intent.symbol},
            )
            return self._create_blocked_result(
                intent,
                ExecutionResultCode.BLOCKED_HALT_STATE,
                "System is in HALT state",
            )
        
        # 3. Validate approval
        if not intent.is_approval_valid():
            logger.warning(
                f"Execution blocked for {intent.intent_id}: Invalid/expired approval"
            )
            self._stats["blocked"] += 1
            return self._create_blocked_result(
                intent,
                ExecutionResultCode.BLOCKED_EXPIRED_APPROVAL
                if intent.approval_token else ExecutionResultCode.BLOCKED_NO_APPROVAL,
                "Trade Guard approval is invalid or expired",
            )
        
        # 4. Track as pending
        self._pending_executions[intent.intent_id] = intent
        
        try:
            # 5. Get account state and symbol rules
            account_state = await self._get_account_state()
            symbol_rules = await self._get_symbol_rules(intent.symbol)
            
            if not symbol_rules:
                logger.error(f"Could not get symbol rules for {intent.symbol}")
                self._stats["rejected"] += 1
                return self._create_blocked_result(
                    intent,
                    ExecutionResultCode.REJECTED_INVALID_SYMBOL,
                    f"Could not get trading rules for {intent.symbol}",
                )
            
            # 6. Submit order
            logger.info(
                f"Executing order: {intent.side.value} {intent.quantity} "
                f"{intent.symbol} @ {intent.order_type.value}"
            )
            
            result = await self._order_manager.submit_order(
                intent, account_state, symbol_rules
            )
            
            # 7. Update statistics
            if result.result_code.is_success():
                self._stats["successful"] += 1
            elif result.result_code in {
                ExecutionResultCode.BLOCKED_HALT_STATE,
                ExecutionResultCode.BLOCKED_NO_APPROVAL,
                ExecutionResultCode.BLOCKED_EXPIRED_APPROVAL,
            }:
                self._stats["blocked"] += 1
            elif result.result_code.name.startswith("REJECTED"):
                self._stats["rejected"] += 1
            else:
                self._stats["failed"] += 1
            
            # 8. Store result
            self._execution_history[intent.intent_id] = result
            
            # 9. Notify completion
            if self._on_execution_complete:
                await self._on_execution_complete(result)
            
            # 10. Send alert if failed
            if not result.result_code.is_success():
                await self._send_alert(
                    "ERROR" if result.result_code.name.startswith("REJECTED") else "CRITICAL",
                    f"Order execution failed: {result.result_code.value}",
                    {
                        "intent_id": intent.intent_id,
                        "order_id": result.order_id,
                        "symbol": intent.symbol,
                        "error": result.error_message,
                    },
                )
            
            logger.info(
                f"Execution complete: {intent.intent_id} -> "
                f"{result.result_code.value} (order: {result.order_id})"
            )
            
            return result
            
        finally:
            # Remove from pending
            self._pending_executions.pop(intent.intent_id, None)
    
    async def cancel(
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
        return await self._order_manager.cancel_order(order_id, reason)
    
    async def cancel_all(
        self,
        symbol: Optional[str] = None,
        reason: str = "Cancel all",
    ) -> int:
        """
        Cancel all open orders.
        
        Args:
            symbol: Specific symbol or None for all
            reason: Cancellation reason
            
        Returns:
            Number of orders canceled
        """
        count = await self._order_manager.cancel_all_orders(symbol, reason)
        
        if count > 0:
            await self._send_alert(
                "WARNING",
                f"Canceled {count} orders",
                {"symbol": symbol or "all", "reason": reason},
            )
        
        return count
    
    # --------------------------------------------------------
    # QUERIES
    # --------------------------------------------------------
    
    def get_order(self, order_id: str) -> Optional[OrderRecord]:
        """Get order by ID."""
        return self._order_manager.get_order(order_id)
    
    def get_active_orders(self) -> List[OrderRecord]:
        """Get all active orders."""
        return self._order_manager.get_active_orders()
    
    def get_orders_by_symbol(self, symbol: str) -> List[OrderRecord]:
        """Get orders for a symbol."""
        return self._order_manager.get_orders_by_symbol(symbol)
    
    def get_execution_result(self, intent_id: str) -> Optional[ExecutionResult]:
        """Get execution result by intent ID."""
        return self._execution_history.get(intent_id)
    
    def get_pending_count(self) -> int:
        """Get count of pending executions."""
        return len(self._pending_executions)
    
    def get_statistics(self) -> Dict[str, int]:
        """Get execution statistics."""
        return dict(self._stats)
    
    # --------------------------------------------------------
    # ACCOUNT & SYMBOL INFO
    # --------------------------------------------------------
    
    async def _get_account_state(self) -> AccountState:
        """Get current account state."""
        try:
            return await self._adapter.get_account_state()
        except ExchangeError as e:
            logger.error(f"Failed to get account state: {e}")
            # Return minimal state
            return AccountState(
                exchange_id=self._adapter.exchange_id,
                timestamp=datetime.utcnow(),
            )
    
    async def _get_symbol_rules(self, symbol: str) -> Optional[SymbolRules]:
        """Get symbol trading rules."""
        try:
            return await self._adapter.get_symbol_rules(symbol)
        except ExchangeError as e:
            logger.error(f"Failed to get symbol rules for {symbol}: {e}")
            return None
    
    # --------------------------------------------------------
    # RECONCILIATION
    # --------------------------------------------------------
    
    async def _reconciliation_loop(self) -> None:
        """Background reconciliation loop."""
        interval = self._config.reconciliation.interval_seconds
        
        while self._running:
            try:
                await asyncio.sleep(interval)
                
                if not self._running:
                    break
                
                # Sync all active orders
                active_count = await self._order_manager.sync_all_active_orders()
                
                if active_count > 0:
                    logger.debug(f"Reconciled {active_count} active orders")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reconciliation error: {e}")
                await self._send_alert(
                    "ERROR",
                    "Reconciliation error",
                    {"error": str(e)},
                )
    
    # --------------------------------------------------------
    # STATE CHANGE HANDLING
    # --------------------------------------------------------
    
    async def _handle_state_change(self, event: StateTransitionEvent) -> None:
        """Handle order state change event."""
        # Forward to external callback
        if self._on_state_change:
            await self._on_state_change(event)
        
        # Log important transitions
        if event.to_state.is_terminal():
            logger.info(
                f"Order {event.order_id} reached terminal state: "
                f"{event.to_state.value} ({event.reason})"
            )
            
            # Alert on failures
            if event.to_state in {OrderState.FAILED, OrderState.REJECTED}:
                await self._send_alert(
                    "ERROR",
                    f"Order {event.to_state.value.lower()}: {event.reason}",
                    {
                        "order_id": event.order_id,
                        "from_state": event.from_state.value,
                        "to_state": event.to_state.value,
                        "details": event.details,
                    },
                )
    
    # --------------------------------------------------------
    # HELPERS
    # --------------------------------------------------------
    
    def _create_blocked_result(
        self,
        intent: OrderIntent,
        result_code: ExecutionResultCode,
        error_message: str,
    ) -> ExecutionResult:
        """Create a blocked execution result."""
        return ExecutionResult(
            intent_id=intent.intent_id,
            result_code=result_code,
            order_state=OrderState.REJECTED,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            error_message=error_message,
        )
    
    async def _send_alert(
        self,
        severity: str,
        message: str,
        details: Dict[str, Any],
    ) -> None:
        """Send an alert."""
        if self._on_alert:
            try:
                await self._on_alert(severity, message, details)
            except Exception as e:
                logger.error(f"Failed to send alert: {e}")
        
        # Always log
        log_func = {
            "CRITICAL": logger.critical,
            "ERROR": logger.error,
            "WARNING": logger.warning,
            "INFO": logger.info,
        }.get(severity, logger.info)
        
        log_func(f"ALERT [{severity}]: {message} - {details}")


# ============================================================
# EXECUTION ENGINE (Convenience Alias)
# ============================================================

# Alias for backward compatibility
ExecutionEngine = ExecutionService
