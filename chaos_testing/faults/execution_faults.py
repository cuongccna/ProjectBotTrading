"""
Execution Fault Injectors.

============================================================
PURPOSE
============================================================
Inject faults in order execution:
- Order rejection
- Partial fills stuck
- Duplicate execution
- Network disconnect during execution
- Fill timeouts

============================================================
"""

import asyncio
import logging
import random
from decimal import Decimal
from typing import Dict, Any, Callable

from ..models import (
    FaultCategory,
    ExecutionFaultType,
    FaultDefinition,
    ActiveFault,
)
from .base import (
    BaseFaultInjector,
    ExecutionFaultException,
    InjectedFaultException,
)


logger = logging.getLogger(__name__)


# ============================================================
# EXECUTION FAULT INJECTOR
# ============================================================

class ExecutionFaultInjector(BaseFaultInjector):
    """
    Injects execution layer faults.
    """
    
    def __init__(self):
        """Initialize execution fault injector."""
        super().__init__(FaultCategory.EXECUTION)
    
    async def inject(self, fault_def: FaultDefinition) -> ActiveFault:
        """Inject an execution fault."""
        if fault_def.category != FaultCategory.EXECUTION:
            raise ValueError(f"Invalid fault category: {fault_def.category}")
        
        active = await self.create_active_fault(fault_def)
        
        logger.warning(
            f"CHAOS: Injected execution fault {fault_def.fault_type} "
            f"at {fault_def.injection_point}"
        )
        
        return active
    
    async def remove(self, injection_id: str) -> bool:
        """Remove an execution fault."""
        fault = await self.registry.unregister(injection_id)
        return fault is not None


# ============================================================
# FAULT EXECUTION FUNCTIONS
# ============================================================

async def execute_order_rejected(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute order rejection fault."""
    logger.warning("CHAOS: Injecting ORDER_REJECTED fault")
    
    rejection_reason = params.get("reason", "insufficient_balance")
    
    reasons = {
        "insufficient_balance": "Insufficient balance for order",
        "insufficient_margin": "Insufficient margin",
        "invalid_price": "Order price is invalid",
        "invalid_quantity": "Order quantity is invalid",
        "min_notional": "Order value below minimum notional",
        "max_position": "Maximum position size exceeded",
        "market_closed": "Market is closed",
        "self_trade": "Self-trade prevention triggered",
        "risk_limit": "Risk limit exceeded",
    }
    
    raise ExecutionFaultException(
        f"Order rejected: {reasons.get(rejection_reason, 'Unknown reason')} (injected)"
    )


async def execute_partial_fill_stuck(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute partial fill stuck fault."""
    logger.warning("CHAOS: Injecting PARTIAL_FILL_STUCK fault")
    
    fill_percentage = params.get("fill_percentage", 50)
    
    # Simulate a partial fill that never completes
    result = await original_func(*args, **kwargs)
    
    if result and isinstance(result, dict):
        original_qty = result.get("quantity", Decimal("1"))
        result["filled_quantity"] = original_qty * Decimal(str(fill_percentage)) / Decimal("100")
        result["status"] = "PARTIALLY_FILLED"
        result["remaining_quantity"] = original_qty - result["filled_quantity"]
        result["__chaos_stuck__"] = True
    
    return result


async def execute_duplicate_execution(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute duplicate execution fault."""
    logger.warning("CHAOS: Injecting DUPLICATE_EXECUTION fault")
    
    raise ExecutionFaultException(
        "Duplicate order execution detected (injected)"
    )


async def execute_network_disconnect(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute network disconnect during execution fault."""
    logger.warning("CHAOS: Injecting NETWORK_DISCONNECT fault")
    
    disconnect_point = params.get("disconnect_point", "during")
    
    if disconnect_point == "before":
        raise ExecutionFaultException(
            "Network disconnected before order submission (injected)"
        )
    
    elif disconnect_point == "during":
        # Simulate starting execution then disconnecting
        await asyncio.sleep(0.5)  # Start processing
        raise ExecutionFaultException(
            "Network disconnected during order execution - order status UNKNOWN (injected)"
        )
    
    else:  # after
        # Execute but then fail to get confirmation
        result = await original_func(*args, **kwargs)
        raise ExecutionFaultException(
            "Network disconnected after order submission - confirmation lost (injected)"
        )


async def execute_fill_timeout(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute fill timeout fault."""
    timeout = params.get("timeout_seconds", 30)
    logger.warning(f"CHAOS: Injecting FILL_TIMEOUT fault ({timeout}s)")
    
    # Simulate waiting for fill that never comes
    await asyncio.sleep(timeout)
    
    raise ExecutionFaultException(
        f"Order fill timed out after {timeout}s (injected)"
    )


async def execute_price_slippage(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute price slippage fault."""
    slippage_pct = params.get("slippage_percentage", 5)
    logger.warning(f"CHAOS: Injecting PRICE_SLIPPAGE fault ({slippage_pct}%)")
    
    result = await original_func(*args, **kwargs)
    
    if result and isinstance(result, dict):
        # Apply slippage to fill price
        fill_price = result.get("fill_price") or result.get("price")
        if fill_price:
            slippage_factor = 1 + (slippage_pct / 100)
            side = result.get("side", "buy")
            
            if side.lower() == "buy":
                # Worse for buyer = higher price
                result["fill_price"] = fill_price * Decimal(str(slippage_factor))
            else:
                # Worse for seller = lower price
                result["fill_price"] = fill_price / Decimal(str(slippage_factor))
            
            result["__chaos_slippage__"] = slippage_pct
    
    return result


async def execute_insufficient_margin(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute insufficient margin fault."""
    logger.warning("CHAOS: Injecting INSUFFICIENT_MARGIN fault")
    
    required = params.get("required_margin", "10000")
    available = params.get("available_margin", "5000")
    
    raise ExecutionFaultException(
        f"Insufficient margin: required {required}, available {available} (injected)"
    )


async def execute_position_mismatch(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute position mismatch fault."""
    logger.warning("CHAOS: Injecting POSITION_MISMATCH fault")
    
    raise ExecutionFaultException(
        "Position mismatch detected between local and exchange state (injected)"
    )


async def execute_exchange_maintenance(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute exchange maintenance fault."""
    logger.warning("CHAOS: Injecting EXCHANGE_MAINTENANCE fault")
    
    estimated_duration = params.get("duration_minutes", 30)
    
    raise ExecutionFaultException(
        f"Exchange under maintenance. Estimated duration: {estimated_duration} minutes (injected)"
    )
