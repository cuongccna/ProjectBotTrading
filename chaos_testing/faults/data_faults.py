"""
Data Layer Fault Injectors.

============================================================
PURPOSE
============================================================
Inject faults in the data layer:
- Missing data
- Delayed data
- Corrupted data
- Partial updates
- Duplicate records

============================================================
"""

import asyncio
import logging
import random
import copy
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, Callable

from ..models import (
    FaultCategory,
    DataFaultType,
    FaultDefinition,
    ActiveFault,
)
from .base import (
    BaseFaultInjector,
    DataFaultException,
    get_fault_registry,
)


logger = logging.getLogger(__name__)


# ============================================================
# DATA FAULT INJECTOR
# ============================================================

class DataFaultInjector(BaseFaultInjector):
    """
    Injects data layer faults.
    """
    
    def __init__(self):
        """Initialize data fault injector."""
        super().__init__(FaultCategory.DATA)
        self._register_handlers()
    
    def _register_handlers(self):
        """Register fault type handlers."""
        self.register_handler(DataFaultType.MISSING_DATA.value, self._handle_missing)
        self.register_handler(DataFaultType.DELAYED_DATA.value, self._handle_delayed)
        self.register_handler(DataFaultType.CORRUPTED_DATA.value, self._handle_corrupted)
        self.register_handler(DataFaultType.PARTIAL_UPDATE.value, self._handle_partial)
        self.register_handler(DataFaultType.DUPLICATE_RECORDS.value, self._handle_duplicate)
        self.register_handler(DataFaultType.STALE_DATA.value, self._handle_stale)
        self.register_handler(DataFaultType.INVALID_FORMAT.value, self._handle_invalid_format)
        self.register_handler(DataFaultType.OUT_OF_RANGE.value, self._handle_out_of_range)
        self.register_handler(DataFaultType.NULL_VALUES.value, self._handle_null_values)
    
    async def inject(self, fault_def: FaultDefinition) -> ActiveFault:
        """Inject a data fault."""
        if fault_def.category != FaultCategory.DATA:
            raise ValueError(f"Invalid fault category: {fault_def.category}")
        
        active = await self.create_active_fault(fault_def)
        
        logger.warning(
            f"CHAOS: Injected data fault {fault_def.fault_type} "
            f"at {fault_def.injection_point}"
        )
        
        return active
    
    async def remove(self, injection_id: str) -> bool:
        """Remove a data fault."""
        fault = await self.registry.unregister(injection_id)
        return fault is not None
    
    # Handlers
    async def _handle_missing(self, fault: ActiveFault) -> Any:
        """Handle missing data fault."""
        raise DataFaultException("Data is missing")
    
    async def _handle_delayed(self, fault: ActiveFault) -> Any:
        """Handle delayed data fault."""
        delay = fault.fault_definition.parameters.get("delay_seconds", 5)
        await asyncio.sleep(delay)
        return None  # Continue after delay
    
    async def _handle_corrupted(self, fault: ActiveFault) -> Any:
        """Handle corrupted data fault."""
        raise DataFaultException("Data is corrupted")
    
    async def _handle_partial(self, fault: ActiveFault) -> Any:
        """Handle partial update fault."""
        raise DataFaultException("Partial data update received")
    
    async def _handle_duplicate(self, fault: ActiveFault) -> Any:
        """Handle duplicate records fault."""
        raise DataFaultException("Duplicate records detected")
    
    async def _handle_stale(self, fault: ActiveFault) -> Any:
        """Handle stale data fault."""
        raise DataFaultException("Data is stale")
    
    async def _handle_invalid_format(self, fault: ActiveFault) -> Any:
        """Handle invalid format fault."""
        raise DataFaultException("Invalid data format")
    
    async def _handle_out_of_range(self, fault: ActiveFault) -> Any:
        """Handle out of range fault."""
        raise DataFaultException("Data value out of valid range")
    
    async def _handle_null_values(self, fault: ActiveFault) -> Any:
        """Handle null values fault."""
        raise DataFaultException("Unexpected null values in data")


# ============================================================
# FAULT EXECUTION FUNCTIONS
# ============================================================

async def execute_missing_data(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute missing data fault."""
    logger.warning("CHAOS: Injecting MISSING_DATA fault")
    raise DataFaultException("Data is missing (injected)")


async def execute_delayed_data(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute delayed data fault."""
    delay = params.get("delay_seconds", 5)
    logger.warning(f"CHAOS: Injecting DELAYED_DATA fault ({delay}s delay)")
    await asyncio.sleep(delay)
    # Continue with original function after delay
    return await original_func(*args, **kwargs)


async def execute_corrupted_data(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute corrupted data fault."""
    logger.warning("CHAOS: Injecting CORRUPTED_DATA fault")
    
    # Get original result and corrupt it
    result = await original_func(*args, **kwargs)
    
    if result is None:
        return None
    
    return _corrupt_data(result, params)


async def execute_partial_update(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute partial update fault."""
    logger.warning("CHAOS: Injecting PARTIAL_UPDATE fault")
    
    result = await original_func(*args, **kwargs)
    
    if result is None:
        return None
    
    return _partial_data(result, params)


async def execute_duplicate_records(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute duplicate records fault."""
    logger.warning("CHAOS: Injecting DUPLICATE_RECORDS fault")
    
    result = await original_func(*args, **kwargs)
    
    if isinstance(result, list):
        # Duplicate random items
        duplicates = params.get("duplicate_count", 2)
        for _ in range(duplicates):
            if result:
                result.append(copy.deepcopy(random.choice(result)))
    
    return result


async def execute_stale_data(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute stale data fault."""
    logger.warning("CHAOS: Injecting STALE_DATA fault")
    
    result = await original_func(*args, **kwargs)
    
    if result is None:
        return None
    
    # Modify timestamp to make data appear stale
    stale_seconds = params.get("stale_seconds", 300)
    return _make_stale(result, stale_seconds)


async def execute_invalid_format(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute invalid format fault."""
    logger.warning("CHAOS: Injecting INVALID_FORMAT fault")
    
    # Return garbage data
    return {"__chaos_invalid__": True, "data": "corrupted"}


async def execute_out_of_range(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute out of range fault."""
    logger.warning("CHAOS: Injecting OUT_OF_RANGE fault")
    
    result = await original_func(*args, **kwargs)
    
    if result is None:
        return None
    
    return _make_out_of_range(result, params)


async def execute_null_values(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute null values fault."""
    logger.warning("CHAOS: Injecting NULL_VALUES fault")
    
    result = await original_func(*args, **kwargs)
    
    if result is None:
        return None
    
    return _inject_nulls(result, params)


# ============================================================
# DATA CORRUPTION HELPERS
# ============================================================

def _corrupt_data(data: Any, params: Dict[str, Any]) -> Any:
    """Corrupt data in various ways."""
    corruption_type = params.get("corruption_type", "random")
    
    if isinstance(data, dict):
        corrupted = copy.deepcopy(data)
        
        if corruption_type == "flip_sign":
            # Flip signs of numeric values
            for key, value in corrupted.items():
                if isinstance(value, (int, float, Decimal)):
                    corrupted[key] = -value
        
        elif corruption_type == "multiply":
            # Multiply numeric values by random factor
            factor = random.uniform(0.1, 10.0)
            for key, value in corrupted.items():
                if isinstance(value, (int, float)):
                    corrupted[key] = value * factor
                elif isinstance(value, Decimal):
                    corrupted[key] = value * Decimal(str(factor))
        
        elif corruption_type == "swap":
            # Swap values between keys
            keys = list(corrupted.keys())
            if len(keys) >= 2:
                k1, k2 = random.sample(keys, 2)
                corrupted[k1], corrupted[k2] = corrupted[k2], corrupted[k1]
        
        else:  # random
            # Random corruption
            for key in random.sample(list(corrupted.keys()), min(2, len(corrupted))):
                value = corrupted[key]
                if isinstance(value, (int, float, Decimal)):
                    corrupted[key] = value * random.uniform(-10, 10)
                elif isinstance(value, str):
                    corrupted[key] = "CORRUPTED_" + value
        
        return corrupted
    
    return data


def _partial_data(data: Any, params: Dict[str, Any]) -> Any:
    """Return partial data."""
    if isinstance(data, dict):
        # Remove random keys
        partial = copy.deepcopy(data)
        keys_to_remove = params.get("remove_keys", [])
        
        if not keys_to_remove:
            # Remove random 30% of keys
            keys_to_remove = random.sample(
                list(partial.keys()),
                max(1, len(partial) // 3)
            )
        
        for key in keys_to_remove:
            partial.pop(key, None)
        
        return partial
    
    elif isinstance(data, list):
        # Return partial list
        ratio = params.get("partial_ratio", 0.5)
        return data[:int(len(data) * ratio)]
    
    return data


def _make_stale(data: Any, stale_seconds: int) -> Any:
    """Make data appear stale."""
    if isinstance(data, dict):
        stale = copy.deepcopy(data)
        
        # Look for timestamp fields
        timestamp_keys = ["timestamp", "updated_at", "time", "datetime", "created_at"]
        stale_time = datetime.utcnow() - timedelta(seconds=stale_seconds)
        
        for key in timestamp_keys:
            if key in stale:
                if isinstance(stale[key], datetime):
                    stale[key] = stale_time
                elif isinstance(stale[key], (int, float)):
                    stale[key] = stale_time.timestamp()
                elif isinstance(stale[key], str):
                    stale[key] = stale_time.isoformat()
        
        return stale
    
    return data


def _make_out_of_range(data: Any, params: Dict[str, Any]) -> Any:
    """Make data values out of valid range."""
    if isinstance(data, dict):
        out_of_range = copy.deepcopy(data)
        
        # Target specific fields or all numeric fields
        target_fields = params.get("target_fields", [])
        
        for key, value in out_of_range.items():
            if target_fields and key not in target_fields:
                continue
            
            if isinstance(value, (int, float)):
                # Make extremely large or negative
                out_of_range[key] = value * 1000000 if random.random() > 0.5 else -abs(value) * 1000
            elif isinstance(value, Decimal):
                out_of_range[key] = value * Decimal("1000000")
        
        return out_of_range
    
    return data


def _inject_nulls(data: Any, params: Dict[str, Any]) -> Any:
    """Inject null values into data."""
    if isinstance(data, dict):
        nulled = copy.deepcopy(data)
        
        # Target specific fields or random fields
        target_fields = params.get("null_fields", [])
        
        if not target_fields:
            # Null random 30% of fields
            target_fields = random.sample(
                list(nulled.keys()),
                max(1, len(nulled) // 3)
            )
        
        for key in target_fields:
            if key in nulled:
                nulled[key] = None
        
        return nulled
    
    return data
