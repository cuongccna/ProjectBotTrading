"""
API Fault Injectors.

============================================================
PURPOSE
============================================================
Inject faults in API/external dependencies:
- Timeouts
- Rate limits
- Invalid responses
- Authentication failures
- Connection errors

============================================================
"""

import asyncio
import logging
import random
from typing import Dict, Any, Callable

from ..models import (
    FaultCategory,
    ApiFaultType,
    FaultDefinition,
    ActiveFault,
)
from .base import (
    BaseFaultInjector,
    TimeoutFaultException,
    ConnectionFaultException,
    InjectedFaultException,
)


logger = logging.getLogger(__name__)


# ============================================================
# API FAULT INJECTOR
# ============================================================

class ApiFaultInjector(BaseFaultInjector):
    """
    Injects API/external dependency faults.
    """
    
    def __init__(self):
        """Initialize API fault injector."""
        super().__init__(FaultCategory.API)
    
    async def inject(self, fault_def: FaultDefinition) -> ActiveFault:
        """Inject an API fault."""
        if fault_def.category != FaultCategory.API:
            raise ValueError(f"Invalid fault category: {fault_def.category}")
        
        active = await self.create_active_fault(fault_def)
        
        logger.warning(
            f"CHAOS: Injected API fault {fault_def.fault_type} "
            f"at {fault_def.injection_point}"
        )
        
        return active
    
    async def remove(self, injection_id: str) -> bool:
        """Remove an API fault."""
        fault = await self.registry.unregister(injection_id)
        return fault is not None


# ============================================================
# FAULT EXECUTION FUNCTIONS
# ============================================================

async def execute_timeout(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute timeout fault."""
    timeout_seconds = params.get("timeout_seconds", 30)
    logger.warning(f"CHAOS: Injecting TIMEOUT fault ({timeout_seconds}s)")
    
    # Simulate hanging then timeout
    await asyncio.sleep(timeout_seconds)
    raise TimeoutFaultException(f"Operation timed out after {timeout_seconds}s (injected)")


async def execute_rate_limit(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute rate limit fault."""
    logger.warning("CHAOS: Injecting RATE_LIMIT fault")
    
    retry_after = params.get("retry_after", 60)
    
    raise InjectedFaultException(
        "RATE_LIMIT",
        f"Rate limit exceeded. Retry after {retry_after} seconds"
    )


async def execute_invalid_response(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute invalid response fault."""
    logger.warning("CHAOS: Injecting INVALID_RESPONSE fault")
    
    response_type = params.get("response_type", "garbage")
    
    if response_type == "empty":
        return {}
    elif response_type == "null":
        return None
    elif response_type == "wrong_type":
        return "unexpected_string_instead_of_dict"
    else:  # garbage
        return {
            "__chaos__": True,
            "error": "invalid",
            "gibberish": random.randbytes(32).hex(),
        }


async def execute_auth_failure(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute authentication failure fault."""
    logger.warning("CHAOS: Injecting AUTH_FAILURE fault")
    
    error_type = params.get("error_type", "invalid_key")
    
    messages = {
        "invalid_key": "Invalid API key",
        "expired": "API key has expired",
        "revoked": "API key has been revoked",
        "ip_blocked": "IP address not whitelisted",
        "permission_denied": "Insufficient permissions",
    }
    
    raise InjectedFaultException(
        "AUTH_FAILURE",
        messages.get(error_type, "Authentication failed")
    )


async def execute_connection_refused(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute connection refused fault."""
    logger.warning("CHAOS: Injecting CONNECTION_REFUSED fault")
    raise ConnectionFaultException("Connection refused (injected)")


async def execute_ssl_error(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute SSL error fault."""
    logger.warning("CHAOS: Injecting SSL_ERROR fault")
    
    error_type = params.get("error_type", "certificate_verify_failed")
    
    messages = {
        "certificate_verify_failed": "SSL certificate verification failed",
        "certificate_expired": "SSL certificate has expired",
        "hostname_mismatch": "SSL hostname mismatch",
        "handshake_failed": "SSL handshake failed",
    }
    
    raise ConnectionFaultException(
        messages.get(error_type, "SSL error occurred")
    )


async def execute_dns_failure(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute DNS failure fault."""
    logger.warning("CHAOS: Injecting DNS_FAILURE fault")
    raise ConnectionFaultException("DNS resolution failed (injected)")


async def execute_http_500(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute HTTP 500 fault."""
    logger.warning("CHAOS: Injecting HTTP_500 fault")
    
    raise InjectedFaultException(
        "HTTP_500",
        "Internal Server Error (injected)"
    )


async def execute_http_503(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute HTTP 503 fault."""
    logger.warning("CHAOS: Injecting HTTP_503 fault")
    
    raise InjectedFaultException(
        "HTTP_503",
        "Service Unavailable (injected)"
    )


async def execute_malformed_json(
    params: Dict[str, Any],
    original_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute malformed JSON fault."""
    logger.warning("CHAOS: Injecting MALFORMED_JSON fault")
    
    # Return something that looks like corrupted JSON
    raise InjectedFaultException(
        "MALFORMED_JSON",
        "Failed to parse JSON response: Unexpected token at position 42"
    )
