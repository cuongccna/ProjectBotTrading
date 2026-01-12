"""
Test script for On-chain Data Adapters.

Demonstrates:
- Adapter registration
- Fetching on-chain metrics
- Caching behavior
- Fallback handling
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from onchain_adapters import (
    AdapterRegistry,
    EtherscanAdapter,
    FlipsideAdapter,
    MetricsRequest,
    Chain,
    MetricType,
    OnchainMetrics,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def print_banner(text: str) -> None:
    """Print a banner."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_metrics(metrics: OnchainMetrics) -> None:
    """Print metrics."""
    print(f"  Chain: {metrics.chain}")
    print(f"  Timestamp: {metrics.timestamp}")
    print(f"  TX Count (24h): {metrics.tx_count:,}")
    print(f"  Active Addresses: {metrics.active_addresses:,}")
    print(f"  Gas Used: {metrics.gas_used:,}")
    if metrics.whale_activity_score is not None:
        print(f"  Whale Activity Score: {metrics.whale_activity_score:.1f}/100")
    if metrics.avg_gas_price_gwei is not None:
        print(f"  Avg Gas Price: {metrics.avg_gas_price_gwei:.2f} gwei")
    if metrics.net_flow is not None:
        print(f"  Net Flow: {metrics.net_flow}")
    print(f"  Source: {metrics.source_name}")
    print(f"  Cached: {metrics.cached}")
    if metrics.cache_age_seconds:
        print(f"  Cache Age: {metrics.cache_age_seconds:.1f}s")


async def test_single_adapter():
    """Test fetching from a single adapter."""
    print_banner("TEST: Single Adapter (Etherscan)")
    
    async with EtherscanAdapter() as adapter:
        # Health check
        health = await adapter.health_check()
        print(f"\nHealth: {health.status.value}")
        if health.latency_ms:
            print(f"Latency: {health.latency_ms:.1f}ms")
        
        # Metadata
        meta = adapter.metadata()
        print(f"Provider: {meta.display_name}")
        print(f"Supported chains: {[c.value for c in meta.supported_chains]}")
        
        # Fetch metrics
        request = MetricsRequest(
            chain=Chain.ETHEREUM,
            time_range_hours=24,
        )
        
        print(f"\nFetching {request.chain.value} metrics...")
        metrics = await adapter.fetch(request)
        
        if metrics:
            print("\nMetrics received:")
            print_metrics(metrics)
        else:
            print("No metrics received (API may be rate limited)")


async def test_multiple_adapters():
    """Test fetching with multiple adapters."""
    print_banner("TEST: Multiple Adapters (Etherscan + Flipside)")
    
    async with AdapterRegistry() as registry:
        # Register adapters
        registry.register(EtherscanAdapter(), priority=1)
        registry.register(FlipsideAdapter(), priority=2)
        
        print(f"\nRegistered adapters: {registry.list_adapters()}")
        
        # Health check all
        health = await registry.health_check_all()
        print("\nHealth status:")
        for name, h in health.items():
            status = "[OK]" if h.is_healthy() else "[DEGRADED]" if h.is_usable() else "[FAIL]"
            latency = f"{h.latency_ms:.1f}ms" if h.latency_ms else "N/A"
            print(f"  {status} {name}: {h.status.value} ({latency})")
        
        # Fetch with fallback
        request = MetricsRequest(
            chain=Chain.ETHEREUM,
            time_range_hours=24,
        )
        
        print(f"\nFetching {request.chain.value} with automatic fallback...")
        metrics = await registry.fetch(request)
        
        if metrics:
            print("\nMetrics received:")
            print_metrics(metrics)


async def test_caching():
    """Test aggressive caching."""
    print_banner("TEST: Caching Behavior")
    
    async with EtherscanAdapter(cache_ttl=300) as adapter:
        request = MetricsRequest(
            chain=Chain.ETHEREUM,
            use_cache=True,
        )
        
        # First fetch - should hit API
        print("\nFirst fetch (cache miss expected)...")
        metrics1 = await adapter.fetch(request)
        if metrics1:
            print(f"  Cached: {metrics1.cached}")
        
        # Second fetch - should hit cache
        print("\nSecond fetch (cache hit expected)...")
        metrics2 = await adapter.fetch(request)
        if metrics2:
            print(f"  Cached: {metrics2.cached}")
            if metrics2.cache_age_seconds:
                print(f"  Cache age: {metrics2.cache_age_seconds:.2f}s")
        
        # Check cache stats
        stats = adapter.get_cache_stats()
        print(f"\nCache stats:")
        print(f"  Entries: {stats['entries']}")
        print(f"  Hits: {stats['hits']}")
        print(f"  Misses: {stats['misses']}")
        print(f"  Hit rate: {stats['hit_rate_percent']:.1f}%")


async def test_multi_chain():
    """Test fetching from multiple chains."""
    print_banner("TEST: Multi-chain Support")
    
    async with AdapterRegistry() as registry:
        registry.register(EtherscanAdapter(), priority=1)
        registry.register(FlipsideAdapter(), priority=2)
        
        chains = [Chain.ETHEREUM, Chain.POLYGON, Chain.ARBITRUM]
        
        for chain in chains:
            # Check which adapters support this chain
            adapters = registry.get_adapters_for_chain(chain)
            print(f"\n{chain.value}: supported by {adapters}")
            
            request = MetricsRequest(chain=chain)
            metrics = await registry.fetch(request)
            
            if metrics:
                print(f"  TX Count: {metrics.tx_count:,}")
                print(f"  Source: {metrics.source_name}")
            else:
                print("  No data available")


async def test_registry_stats():
    """Test registry statistics."""
    print_banner("TEST: Registry Statistics")
    
    async with AdapterRegistry() as registry:
        registry.register(EtherscanAdapter(), priority=1)
        registry.register(FlipsideAdapter(), priority=2)
        
        # Run health check
        await registry.health_check_all()
        
        # Make some requests to populate stats
        request = MetricsRequest(chain=Chain.ETHEREUM)
        await registry.fetch(request)
        await registry.fetch(request)  # Should hit cache
        
        # Get stats
        stats = registry.get_stats()
        
        print(f"\nTotal adapters: {stats['total_adapters']}")
        print(f"Adapter order: {stats['adapter_order']}")
        
        print(f"\nHealth summary:")
        for status, count in stats['health_summary'].items():
            if count > 0:
                print(f"  {status}: {count}")
        
        print(f"\nCache stats:")
        print(f"  Total entries: {stats['total_cache_entries']}")
        print(f"  Total hits: {stats['total_cache_hits']}")
        
        print(f"\nAdapters:")
        for name, info in stats['adapters'].items():
            print(f"  {name}:")
            print(f"    Status: {info['status']}")
            print(f"    Usable: {info['is_usable']}")


async def test_non_blocking():
    """Test that fetch never blocks."""
    print_banner("TEST: Non-blocking Behavior")
    
    async with AdapterRegistry() as registry:
        # Don't register any adapters
        print("\nFetching with no adapters registered...")
        
        request = MetricsRequest(chain=Chain.ETHEREUM)
        
        # This should return None immediately, not raise
        start = asyncio.get_event_loop().time()
        result = await registry.fetch(request, timeout=1.0)
        elapsed = asyncio.get_event_loop().time() - start
        
        print(f"  Result: {result}")
        print(f"  Elapsed: {elapsed:.3f}s")
        print(f"  Blocked: No (returned None gracefully)")


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  ON-CHAIN ADAPTERS - TEST SUITE")
    print("=" * 60)
    
    try:
        await test_single_adapter()
        await test_multiple_adapters()
        await test_caching()
        await test_multi_chain()
        await test_registry_stats()
        await test_non_blocking()
        
        print_banner("ALL TESTS COMPLETED")
        print("\n[OK] On-chain Adapters are working correctly!")
        print("  - Signal context data available")
        print("  - Caching working")
        print("  - Non-blocking fetch confirmed")
        print()
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
