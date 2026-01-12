"""
Sentiment Ingestion Layer - Pluggable sentiment data sources.

SAFETY WARNING: Sentiment is NEVER a standalone trade trigger.
All sentiment data should be used ONLY as a context modifier.

This package provides:
- CryptoPanic: Free tier crypto news aggregator
- Twitter: Keyword-based social sentiment scraping
- Normalization pipeline for unified output
- Registry for multi-source aggregation

Usage:
    from sentiment import SentimentRegistry, CryptoPanicSource, TwitterScraperSource
    
    # Create registry
    registry = SentimentRegistry()
    
    # Register sources
    registry.register(CryptoPanicSource(api_key="optional"))
    registry.register(TwitterScraperSource())
    
    # Get aggregated sentiment
    result = await registry.get_sentiment(
        symbols=["BTC", "ETH"],
        time_range_hours=24,
    )
    
    print(f"Overall sentiment: {result.overall_score}")
    print(f"Confidence: {result.confidence}")
    print(f"Category: {result.category.value}")

Output Schema:
- sentiment_score: -1.0 (very bearish) to +1.0 (very bullish)
- event_type: hack, listing, regulation, partnership, etc.
- source_reliability_weight: 0.0 to 1.0
- timestamp: When the data was published

Source Reliability Weights:
- CryptoPanic: 0.6 (community curated)
- Twitter: 0.35 (unverified social content)
"""

from .base import BaseSentimentSource
from .exceptions import (
    AuthenticationError,
    CacheError,
    FetchError,
    NormalizationError,
    ParseError,
    QuotaExhaustedError,
    RateLimitError,
    SentimentSourceError,
    SourceUnavailableError,
    ValidationError,
)
from .models import (
    AggregatedSentiment,
    EVENT_SENTIMENT_IMPACT,
    EventType,
    SentimentCategory,
    SentimentData,
    SentimentRequest,
    SourceHealth,
    SourceIncident,
    SourceMetadata,
    SourceStatus,
)
from .pipeline import SentimentPipeline
from .providers import CryptoPanicSource, TwitterScraperSource
from .registry import SentimentRegistry, get_registry, get_sentiment


__all__ = [
    # Base
    "BaseSentimentSource",
    
    # Providers
    "CryptoPanicSource",
    "TwitterScraperSource",
    
    # Pipeline & Registry
    "SentimentPipeline",
    "SentimentRegistry",
    "get_registry",
    "get_sentiment",
    
    # Models
    "SentimentData",
    "AggregatedSentiment",
    "SentimentRequest",
    "EventType",
    "SentimentCategory",
    "SourceHealth",
    "SourceMetadata",
    "SourceStatus",
    "SourceIncident",
    "EVENT_SENTIMENT_IMPACT",
    
    # Exceptions
    "SentimentSourceError",
    "RateLimitError",
    "FetchError",
    "ParseError",
    "AuthenticationError",
    "ValidationError",
    "CacheError",
    "NormalizationError",
    "SourceUnavailableError",
    "QuotaExhaustedError",
]


# Version
__version__ = "1.0.0"
