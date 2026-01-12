"""
On-chain Adapters Package - Pluggable on-chain data layer.

Provides on-chain metrics for SIGNAL CONTEXT and VALIDATION ONLY.
NOT used for execution decisions.

Features:
- Isolated, replaceable adapters
- Normalized output format
- Aggressive caching
- Graceful rate limit handling
- Non-blocking operations

Quick Start:
    from onchain_adapters import (
        AdapterRegistry,
        EtherscanAdapter,
        FlipsideAdapter,
        MetricsRequest,
        Chain,
    )
    
    async def get_chain_metrics():
        registry = AdapterRegistry()
        registry.register(EtherscanAdapter())
        registry.register(FlipsideAdapter())
        
        request = MetricsRequest(
            chain=Chain.ETHEREUM,
            time_range_hours=24,
        )
        
        # Never blocks - returns None if unavailable
        metrics = await registry.fetch(request)
        
        if metrics:
            print(f"TX Count: {metrics.tx_count}")
            print(f"Active Addresses: {metrics.active_addresses}")
            print(f"Gas Used: {metrics.gas_used}")
            print(f"Whale Score: {metrics.whale_activity_score}")

Normalized Metrics:
- tx_count: Transaction count
- active_addresses: Unique active addresses
- gas_used: Total gas consumed
- net_flow: Net token flow (optional)
- whale_activity_score: Approximate whale activity (0-100)

Adding New Adapters:
    class NewAdapter(BaseOnchainAdapter):
        @property
        def name(self) -> str:
            return "new_adapter"
        
        async def fetch_raw(self, request): ...
        def normalize(self, raw_data, request): ...
        async def health_check(self): ...
        def metadata(self): ...
    
    registry.register(NewAdapter())
"""

from onchain_adapters.base import BaseOnchainAdapter
from onchain_adapters.exceptions import (
    CacheError,
    ChainNotSupportedError,
    ConfigurationError,
    FetchError,
    NoAvailableAdapterError,
    NormalizationError,
    OnchainAdapterError,
    RateLimitError,
)
from onchain_adapters.models import (
    AdapterHealth,
    AdapterIncident,
    AdapterMetadata,
    AdapterStatus,
    CacheEntry,
    Chain,
    MetricType,
    MetricsRequest,
    OnchainMetrics,
)
from onchain_adapters.providers import EtherscanAdapter, FlipsideAdapter
from onchain_adapters.registry import (
    AdapterRegistry,
    get_default_registry,
    setup_default_adapters,
)


__version__ = "1.0.0"

__all__ = [
    # Base
    "BaseOnchainAdapter",
    
    # Models
    "OnchainMetrics",
    "AdapterHealth",
    "AdapterMetadata",
    "AdapterIncident",
    "AdapterStatus",
    "Chain",
    "MetricType",
    "MetricsRequest",
    "CacheEntry",
    
    # Exceptions
    "OnchainAdapterError",
    "FetchError",
    "NormalizationError",
    "RateLimitError",
    "CacheError",
    "ChainNotSupportedError",
    "NoAvailableAdapterError",
    "ConfigurationError",
    
    # Providers
    "EtherscanAdapter",
    "FlipsideAdapter",
    
    # Registry
    "AdapterRegistry",
    "get_default_registry",
    "setup_default_adapters",
]
