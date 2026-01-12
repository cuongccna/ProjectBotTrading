"""
Data Ingestion - Collectors Package.

This package contains all data collection modules.
Each collector is responsible for a specific data source.

Collectors:
- crypto_news_api: News data from crypto news providers
- coingecko: Market data from CoinGecko
- onchain_free_sources: On-chain data from free sources
- market_data_ws: Real-time market data via WebSocket
"""

from data_ingestion.collectors.base import BaseCollector
from data_ingestion.collectors.crypto_news_api import CryptoNewsApiCollector
from data_ingestion.collectors.coingecko import CoinGeckoCollector
from data_ingestion.collectors.onchain_free_sources import OnChainCollector
from data_ingestion.collectors.market_data_ws import MarketDataWebSocketCollector


__all__ = [
    "BaseCollector",
    "CryptoNewsApiCollector",
    "CoinGeckoCollector",
    "OnChainCollector",
    "MarketDataWebSocketCollector",
]
