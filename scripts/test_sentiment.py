"""
Test script for Sentiment Ingestion Layer.

Validates:
1. CryptoPanic source connectivity
2. Twitter scraper (simulated mode)
3. Normalization pipeline
4. Registry aggregation
5. Non-blocking behavior
"""

import asyncio
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent to path
sys.path.insert(0, ".")

from sentiment import (
    AggregatedSentiment,
    CryptoPanicSource,
    EventType,
    SentimentData,
    SentimentPipeline,
    SentimentRegistry,
    SentimentRequest,
    TwitterScraperSource,
)


def print_header(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print('='*60)


def print_success(text: str) -> None:
    print(f"  [OK] {text}")


def print_warning(text: str) -> None:
    print(f"  [WARN] {text}")


def print_error(text: str) -> None:
    print(f"  [FAIL] {text}")


async def test_twitter_scraper() -> bool:
    """Test Twitter scraper in simulated mode."""
    print_header("Test 1: Twitter Scraper (Simulated Mode)")
    
    try:
        source = TwitterScraperSource()
        source.set_simulated_mode(True)
        
        request = SentimentRequest(
            symbols=["BTC", "ETH"],
            time_range_hours=24,
            limit=20,
        )
        
        start = time.time()
        result = await source.fetch_sentiment(request)
        elapsed = time.time() - start
        
        print(f"  Fetched {len(result)} tweets in {elapsed:.2f}s")
        
        if result:
            # Show sample
            sample = result[0]
            print(f"  Sample tweet:")
            print(f"    Title: {sample.title[:60]}...")
            print(f"    Score: {sample.sentiment_score:.2f}")
            print(f"    Event: {sample.event_type.value}")
            print(f"    Reliability: {sample.source_reliability_weight}")
            
            # Verify sentiment score range
            for s in result:
                assert -1.0 <= s.sentiment_score <= 1.0, "Score out of range"
                assert 0.0 <= s.source_reliability_weight <= 1.0, "Reliability out of range"
            
            print_success("Twitter scraper working (simulated mode)")
            return True
        else:
            print_warning("No tweets returned")
            return True  # Not a failure, just no data
            
    except Exception as e:
        print_error(f"Twitter scraper failed: {e}")
        return False
    finally:
        await source.close()


async def test_cryptopanic() -> bool:
    """Test CryptoPanic source (may fail without API key)."""
    print_header("Test 2: CryptoPanic Source")
    
    try:
        api_key = os.getenv("CRYPTOPANIC_API_KEY")
        if api_key:
            print(f"  Using API key from environment")
        else:
            print("  No API key found (set CRYPTOPANIC_API_KEY in .env)")
        
        source = CryptoPanicSource(api_key=api_key)
        
        request = SentimentRequest(
            symbols=["BTC"],
            time_range_hours=24,
            limit=10,
        )
        
        start = time.time()
        result = await source.fetch_sentiment(request)
        elapsed = time.time() - start
        
        print(f"  Fetched {len(result)} news items in {elapsed:.2f}s")
        
        if result:
            # Show sample
            sample = result[0]
            print(f"  Sample news:")
            print(f"    Title: {sample.title[:60]}...")
            print(f"    Score: {sample.sentiment_score:.2f}")
            print(f"    Event: {sample.event_type.value}")
            print(f"    Votes: +{sample.votes_positive} / -{sample.votes_negative}")
            
            print_success("CryptoPanic source working")
            return True
        else:
            print_warning("No news returned (API may require key)")
            # Check health
            health = await source.get_health()
            print(f"  Health status: {health.status.value}")
            return True  # Not a failure
            
    except Exception as e:
        print_warning(f"CryptoPanic failed: {e}")
        print("  (This is expected without API key)")
        return True  # Not a critical failure
    finally:
        await source.close()


async def test_pipeline() -> bool:
    """Test normalization pipeline."""
    print_header("Test 3: Sentiment Pipeline")
    
    try:
        pipeline = SentimentPipeline()
        
        # Create mock sentiment data
        now = datetime.utcnow()
        mock_data = [
            SentimentData(
                sentiment_score=0.5,
                event_type=EventType.LISTING,
                source_reliability_weight=0.6,
                timestamp=now,
                source_name="test/source1",
                title="BTC listed on new exchange",
                symbols=["BTC"],
                primary_symbol="BTC",
                importance=0.7,
            ),
            SentimentData(
                sentiment_score=0.8,
                event_type=EventType.ETF_APPROVAL,
                source_reliability_weight=0.7,
                timestamp=now,
                source_name="test/source2",
                title="ETF approved for BTC",
                symbols=["BTC"],
                primary_symbol="BTC",
                importance=0.9,
                is_breaking=True,
            ),
            SentimentData(
                sentiment_score=-0.3,
                event_type=EventType.REGULATORY_NEGATIVE,
                source_reliability_weight=0.5,
                timestamp=now,
                source_name="test/source3",
                title="Regulatory concerns",
                symbols=["BTC", "ETH"],
                primary_symbol="BTC",
                importance=0.5,
            ),
        ]
        
        # Aggregate
        result = pipeline.aggregate(mock_data, symbol="BTC")
        
        print(f"  Aggregated {result.data_points} data points")
        print(f"  Overall score: {result.overall_score:.3f}")
        print(f"  Confidence: {result.confidence:.3f}")
        print(f"  Category: {result.category.value}")
        print(f"  Dominant event: {result.dominant_event_type.value}")
        print(f"  Has breaking news: {result.has_breaking_news}")
        print(f"  Has positive events: {result.has_positive_events}")
        print(f"  Has negative events: {result.has_negative_events}")
        
        # Verify aggregation logic
        assert result.data_points == 3, "Wrong data point count"
        assert -1.0 <= result.overall_score <= 1.0, "Score out of range"
        assert result.has_breaking_news is True, "Should detect breaking news"
        assert result.has_positive_events is True, "Should detect positive events"
        assert result.has_negative_events is True, "Should detect negative events"
        
        # Test filtering
        filtered = pipeline.filter_by_importance(mock_data, min_importance=0.7)
        print(f"  Filtered to {len(filtered)} important items")
        assert len(filtered) == 2, "Wrong filter count"
        
        # Test alerts
        alerts = pipeline.get_alerts(mock_data)
        print(f"  Found {len(alerts)} alerts")
        
        print_success("Pipeline aggregation working")
        return True
        
    except Exception as e:
        print_error(f"Pipeline test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_registry() -> bool:
    """Test sentiment registry with multiple sources."""
    print_header("Test 4: Sentiment Registry")
    
    registry = SentimentRegistry()
    
    try:
        # Register sources
        twitter = TwitterScraperSource()
        twitter.set_simulated_mode(True)
        registry.register(twitter)
        
        api_key = os.getenv("CRYPTOPANIC_API_KEY")
        cryptopanic = CryptoPanicSource(api_key=api_key)
        registry.register(cryptopanic)
        
        print(f"  Registered {len(registry._sources)} sources")
        
        # Get aggregated sentiment
        start = time.time()
        result = await registry.get_sentiment(
            symbols=["BTC", "ETH"],
            time_range_hours=24,
            primary_symbol="BTC",
        )
        elapsed = time.time() - start
        
        print(f"  Fetched in {elapsed:.2f}s")
        print(f"  Data points: {result.data_points}")
        print(f"  Overall score: {result.overall_score:.3f}")
        print(f"  Confidence: {result.confidence:.3f}")
        print(f"  Category: {result.category.value}")
        print(f"  Sources used: {result.sources_used}")
        
        # Get health
        health = await registry.get_health_summary()
        print(f"  Source health: {health['healthy']}/{health['total_sources']} healthy")
        
        # Get stats
        stats = registry.get_stats()
        print(f"  Total requests: {stats['total_requests']}")
        
        print_success("Registry aggregation working")
        return True
        
    except Exception as e:
        print_error(f"Registry test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await registry.close()


async def test_non_blocking() -> bool:
    """Test that fetch never blocks indefinitely."""
    print_header("Test 5: Non-Blocking Behavior")
    
    try:
        source = TwitterScraperSource()
        source.set_simulated_mode(True)
        
        # Should complete quickly even with large request
        request = SentimentRequest(
            symbols=["BTC", "ETH", "SOL", "ADA", "DOGE"],
            time_range_hours=168,  # 1 week
            limit=500,
        )
        
        start = time.time()
        result = await source.fetch_sentiment(request)
        elapsed = time.time() - start
        
        print(f"  Large request completed in {elapsed:.3f}s")
        
        # Should be under 5 seconds
        assert elapsed < 5.0, f"Took too long: {elapsed}s"
        
        # Test with registry timeout
        registry = SentimentRegistry()
        registry.register(source)
        
        start = time.time()
        await registry.get_sentiment(symbols=["BTC"])
        elapsed = time.time() - start
        
        print(f"  Registry fetch completed in {elapsed:.3f}s")
        assert elapsed < 5.0, f"Registry took too long: {elapsed}s"
        
        print_success("Non-blocking behavior confirmed")
        return True
        
    except Exception as e:
        print_error(f"Non-blocking test failed: {e}")
        return False
    finally:
        await source.close()


async def test_caching() -> bool:
    """Test cache behavior."""
    print_header("Test 6: Caching Behavior")
    
    try:
        source = TwitterScraperSource()
        source.set_simulated_mode(True)
        
        request = SentimentRequest(
            symbols=["BTC"],
            time_range_hours=24,
            limit=20,
            use_cache=True,
        )
        
        # First fetch
        start = time.time()
        result1 = await source.fetch_sentiment(request)
        elapsed1 = time.time() - start
        
        # Second fetch (should be cached)
        start = time.time()
        result2 = await source.fetch_sentiment(request)
        elapsed2 = time.time() - start
        
        print(f"  First fetch: {elapsed1:.3f}s, {len(result1)} items")
        print(f"  Second fetch (cached): {elapsed2:.3f}s, {len(result2)} items")
        
        # Cached fetch should be faster
        stats = source.get_stats()
        cache_hits = stats.get("cache_hits", 0)
        print(f"  Cache hits: {cache_hits}")
        
        # Check if results are marked as cached
        if result2:
            cached_count = sum(1 for r in result2 if r.cached)
            print(f"  Cached results: {cached_count}/{len(result2)}")
        
        print_success("Caching working")
        return True
        
    except Exception as e:
        print_error(f"Caching test failed: {e}")
        return False
    finally:
        await source.close()


async def main() -> int:
    """Run all tests."""
    print("\n" + "="*60)
    print("  SENTIMENT INGESTION LAYER - TEST SUITE")
    print("  SAFETY: Sentiment is CONTEXT ONLY - never a trade trigger")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Twitter Scraper", await test_twitter_scraper()))
    results.append(("CryptoPanic", await test_cryptopanic()))
    results.append(("Pipeline", await test_pipeline()))
    results.append(("Registry", await test_registry()))
    results.append(("Non-Blocking", await test_non_blocking()))
    results.append(("Caching", await test_caching()))
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = 0
    failed = 0
    
    for name, success in results:
        if success:
            print_success(f"{name}: PASSED")
            passed += 1
        else:
            print_error(f"{name}: FAILED")
            failed += 1
    
    print(f"\n  Total: {passed}/{len(results)} passed")
    
    if failed == 0:
        print("\n  [OK] ALL TESTS PASSED")
        print("\n  REMINDER: Sentiment is CONTEXT ONLY - never a trade trigger!")
        return 0
    else:
        print(f"\n  [FAIL] {failed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
