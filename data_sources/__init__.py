"""
Data Sources Package - Modular market data source layer.

Provides pluggable, fail-safe market data sources for the institutional trading system.

Features:
- Isolated, replaceable data providers
- Normalized output format across all sources
- Automatic fallback on provider failure
- Health monitoring with incident logging
- No downstream dependency on specific providers

Quick Start:
    from data_sources import (
        SourceRegistry,
        BinanceMarketSource,
        OKXMarketSource,
        FetchRequest,
        Interval,
        DataType,
    )
    
    # Setup registry with sources
    async def setup():
        registry = SourceRegistry()
        registry.register(BinanceMarketSource())
        registry.register(OKXMarketSource())
        
        # Fetch with automatic fallback
        request = FetchRequest(
            symbol="BTCUSDT",
            interval=Interval.H1,
            limit=100,
        )
        data = await registry.fetch(request)
        
        for candle in data:
            print(f"{candle.timestamp}: O={candle.open} H={candle.high} L={candle.low} C={candle.close}")

Adding New Providers:
    1. Create class extending BaseMarketDataSource
    2. Implement: fetch_raw(), normalize(), health_check(), metadata()
    3. Register with SourceRegistry
    4. No changes needed to strategy, risk, or execution logic
"""

from data_sources.base import BaseMarketDataSource
from data_sources.exceptions import (
    ConfigurationError,
    DataSourceError,
    FetchError,
    HealthCheckError,
    NoAvailableSourceError,
    NormalizationError,
    RateLimitError,
    SourceUnavailableError,
)
from data_sources.models import (
    DataType,
    FetchRequest,
    Interval,
    NormalizedMarketData,
    SourceHealth,
    SourceIncident,
    SourceMetadata,
    SourceStatus,
)
from data_sources.providers import BinanceMarketSource, OKXMarketSource
from data_sources.registry import (
    SourceRegistry,
    get_default_registry,
    setup_default_sources,
)


__version__ = "1.0.0"

__all__ = [
    # Base
    "BaseMarketDataSource",
    
    # Models
    "NormalizedMarketData",
    "SourceHealth",
    "SourceMetadata",
    "SourceIncident",
    "SourceStatus",
    "DataType",
    "Interval",
    "FetchRequest",
    
    # Exceptions
    "DataSourceError",
    "FetchError",
    "NormalizationError",
    "HealthCheckError",
    "RateLimitError",
    "SourceUnavailableError",
    "NoAvailableSourceError",
    "ConfigurationError",
    
    # Providers
    "BinanceMarketSource",
    "OKXMarketSource",
    
    # Registry
    "SourceRegistry",
    "get_default_registry",
    "setup_default_sources",
]
