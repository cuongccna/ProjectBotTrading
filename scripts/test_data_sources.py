"""
Test script for Market Data Sources.

Demonstrates:
- Source registration
- Fetching from multiple providers
- Automatic fallback
- Health monitoring
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_sources import (
    BinanceMarketSource,
    OKXMarketSource,
    SourceRegistry,
    FetchRequest,
    Interval,
    DataType,
    NormalizedMarketData,
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


def print_candle(candle: NormalizedMarketData) -> None:
    """Print a candle."""
    print(
        f"  {candle.timestamp.strftime('%Y-%m-%d %H:%M')} | "
        f"O: {candle.open:>10} | H: {candle.high:>10} | "
        f"L: {candle.low:>10} | C: {candle.close:>10} | "
        f"V: {candle.volume:>12} | Source: {candle.source_name}"
    )


async def test_single_source():
    """Test fetching from a single source."""
    print_banner("TEST: Single Source (Binance)")
    
    async with BinanceMarketSource(use_futures=True) as source:
        # Health check
        health = await source.health_check()
        print(f"\nHealth: {health.status.value} (latency: {health.latency_ms:.1f}ms)")
        
        # Metadata
        meta = source.metadata()
        print(f"Provider: {meta.display_name}")
        print(f"Rate limit: {meta.rate_limit_per_minute}/min")
        
        # Fetch klines
        request = FetchRequest(
            symbol="BTCUSDT",
            interval=Interval.H1,
            data_type=DataType.KLINE,
            limit=5,
        )
        
        print(f"\nFetching {request.symbol} {request.interval.value} klines...")
        data = await source.fetch(request)
        
        if data:
            print(f"Received {len(data)} candles:")
            for candle in data:
                print_candle(candle)
        else:
            print("No data received")


async def test_multiple_sources():
    """Test fetching from multiple sources."""
    print_banner("TEST: Multiple Sources (Binance + OKX)")
    
    async with SourceRegistry() as registry:
        # Register sources
        registry.register(BinanceMarketSource(use_futures=True), priority=1)
        registry.register(OKXMarketSource(inst_type="SWAP"), priority=2)
        
        print(f"\nRegistered sources: {registry.list_sources()}")
        
        # Health check all
        health = await registry.health_check_all()
        print("\nHealth status:")
        for name, h in health.items():
            status = "✓" if h.is_healthy() else "✗"
            latency = f"{h.latency_ms:.1f}ms" if h.latency_ms else "N/A"
            print(f"  {status} {name}: {h.status.value} ({latency})")
        
        # Fetch with fallback
        request = FetchRequest(
            symbol="BTCUSDT",
            interval=Interval.H1,
            data_type=DataType.KLINE,
            limit=3,
        )
        
        print(f"\nFetching {request.symbol} with automatic fallback...")
        data = await registry.fetch(request)
        
        if data:
            print(f"Received {len(data)} candles from {data[0].source_name}:")
            for candle in data:
                print_candle(candle)


async def test_fetch_from_all():
    """Test fetching from all sources for comparison."""
    print_banner("TEST: Fetch From All Sources")
    
    async with SourceRegistry() as registry:
        registry.register(BinanceMarketSource(use_futures=True), priority=1)
        registry.register(OKXMarketSource(inst_type="SWAP"), priority=2)
        
        request = FetchRequest(
            symbol="BTCUSDT",
            interval=Interval.H1,
            data_type=DataType.KLINE,
            limit=1,
        )
        
        print(f"\nFetching {request.symbol} from ALL sources...")
        results = await registry.fetch_from_all(request)
        
        print("\nResults by source:")
        for source_name, data in results.items():
            if data:
                candle = data[0]
                print(f"\n  {source_name}:")
                print(f"    Close: {candle.close}")
                print(f"    Volume: {candle.volume}")
                print(f"    Timestamp: {candle.timestamp}")
            else:
                print(f"\n  {source_name}: No data")


async def test_funding_rate():
    """Test fetching funding rate."""
    print_banner("TEST: Funding Rate")
    
    async with BinanceMarketSource(use_futures=True) as source:
        request = FetchRequest(
            symbol="BTCUSDT",
            data_type=DataType.FUNDING_RATE,
            limit=5,
        )
        
        print(f"\nFetching {request.symbol} funding rates...")
        data = await source.fetch(request)
        
        if data:
            print(f"Received {len(data)} funding rates:")
            for fr in data:
                print(
                    f"  {fr.timestamp.strftime('%Y-%m-%d %H:%M')} | "
                    f"Rate: {fr.funding_rate}"
                )
        else:
            print("No data received")


async def test_open_interest():
    """Test fetching open interest."""
    print_banner("TEST: Open Interest")
    
    async with BinanceMarketSource(use_futures=True) as source:
        request = FetchRequest(
            symbol="BTCUSDT",
            data_type=DataType.OPEN_INTEREST,
            limit=1,
        )
        
        print(f"\nFetching {request.symbol} open interest...")
        data = await source.fetch(request)
        
        if data:
            for oi in data:
                print(f"  Open Interest: {oi.open_interest}")
        else:
            print("No data received")


async def test_registry_stats():
    """Test registry statistics."""
    print_banner("TEST: Registry Statistics")
    
    async with SourceRegistry() as registry:
        registry.register(BinanceMarketSource(use_futures=True), priority=1)
        registry.register(OKXMarketSource(inst_type="SWAP"), priority=2)
        
        # Run health check
        await registry.health_check_all()
        
        # Get stats
        stats = registry.get_stats()
        
        print(f"\nTotal sources: {stats['total_sources']}")
        print(f"Source order: {stats['source_order']}")
        print(f"\nHealth summary:")
        for status, count in stats['health_summary'].items():
            print(f"  {status}: {count}")
        
        print(f"\nSources:")
        for name, info in stats['sources'].items():
            print(f"  {name}:")
            print(f"    Status: {info['status']}")
            print(f"    Usable: {info['is_usable']}")
            print(f"    Priority: {info['priority']}")


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  MARKET DATA SOURCES - TEST SUITE")
    print("=" * 60)
    
    try:
        await test_single_source()
        await test_multiple_sources()
        await test_fetch_from_all()
        await test_funding_rate()
        await test_open_interest()
        await test_registry_stats()
        
        print_banner("ALL TESTS COMPLETED")
        print("\n✓ Market Data Sources are working correctly!\n")
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
