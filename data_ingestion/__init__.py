"""
Data Ingestion Package.

This package handles all data collection and normalization.
No business logic - only data acquisition.

Sub-packages:
- collectors: Data collection from external sources
- normalizers: Data normalization to standard formats (future phase)

Main service:
- ingestion_service: Orchestrates all ingestion activities
"""

from data_ingestion.ingestion_service import IngestionService, IngestionServiceConfig
from data_ingestion.collectors import (
    BaseCollector,
    CryptoNewsApiCollector,
    CoinGeckoCollector,
    OnChainCollector,
    MarketDataWebSocketCollector,
)
from data_ingestion.types import (
    IngestionSource,
    IngestionStatus,
    DataType,
    CollectorConfig,
    NewsApiConfig,
    CoinGeckoConfig,
    OnChainConfig,
    WebSocketConfig,
    IngestionResult,
    IngestionMetrics,
    RawNewsItem,
    RawMarketItem,
    RawOnChainItem,
    IngestionError,
    FetchError,
    ParseError,
    StorageError,
)


__all__ = [
    # Service
    "IngestionService",
    "IngestionServiceConfig",
    # Collectors
    "BaseCollector",
    "CryptoNewsApiCollector",
    "CoinGeckoCollector",
    "OnChainCollector",
    "MarketDataWebSocketCollector",
    # Types - Enums
    "IngestionSource",
    "IngestionStatus",
    "DataType",
    # Types - Configs
    "CollectorConfig",
    "NewsApiConfig",
    "CoinGeckoConfig",
    "OnChainConfig",
    "WebSocketConfig",
    # Types - Results
    "IngestionResult",
    "IngestionMetrics",
    # Types - Items
    "RawNewsItem",
    "RawMarketItem",
    "RawOnChainItem",
    # Types - Errors
    "IngestionError",
    "FetchError",
    "ParseError",
    "StorageError",
]
