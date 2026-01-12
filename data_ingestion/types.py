"""
Data Ingestion - Type Definitions.

============================================================
PURPOSE
============================================================
Shared types for the data ingestion layer.

- Configuration dataclasses
- Ingestion result types
- Metric tracking types
- Error types

============================================================
DESIGN PRINCIPLES
============================================================
- Immutable data structures where possible
- Clear typing for all fields
- No business logic
- Serializable for monitoring

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


# =============================================================
# ENUMS
# =============================================================

class IngestionSource(str, Enum):
    """Identifiers for ingestion sources."""
    CRYPTO_NEWS_API = "crypto_news_api"
    COINGECKO = "coingecko"
    ONCHAIN_FREE = "onchain_free"
    MARKET_DATA_WS = "market_data_ws"


class IngestionStatus(str, Enum):
    """Status of an ingestion operation."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class DataType(str, Enum):
    """Types of data being ingested."""
    NEWS = "news"
    MARKET = "market"
    ONCHAIN = "onchain"


# =============================================================
# CONFIGURATION TYPES
# =============================================================

@dataclass(frozen=True)
class CollectorConfig:
    """Base configuration for all collectors."""
    source_name: str
    enabled: bool = True
    polling_interval_seconds: int = 60
    rate_limit_per_minute: int = 30
    max_retries: int = 3
    timeout_seconds: int = 30
    version: str = "1.0.0"


@dataclass(frozen=True)
class NewsApiConfig(CollectorConfig):
    """Configuration for crypto news API collector."""
    api_key: str = ""
    base_url: str = "https://cryptonews-api.com/api/v1"
    batch_size: int = 100


@dataclass(frozen=True)
class CoinGeckoConfig(CollectorConfig):
    """Configuration for CoinGecko collector."""
    api_key: Optional[str] = None
    base_url: str = "https://api.coingecko.com/api/v3"
    tracked_assets: tuple = ("bitcoin", "ethereum")
    include_market_cap: bool = True


@dataclass(frozen=True)
class OnChainConfig(CollectorConfig):
    """Configuration for on-chain data collector."""
    supported_chains: tuple = ("ethereum", "bitcoin")
    data_types: tuple = ("whale_movement", "large_transaction")


@dataclass(frozen=True)
class WebSocketConfig(CollectorConfig):
    """Configuration for WebSocket collector."""
    ws_url: str = ""
    exchange_name: str = ""
    subscriptions: tuple = ()
    heartbeat_interval_seconds: int = 30
    reconnect_attempts: int = 5


# =============================================================
# INGESTION RESULT TYPES
# =============================================================

@dataclass
class IngestionResult:
    """Result of a single ingestion operation."""
    batch_id: UUID = field(default_factory=uuid4)
    source: str = ""
    data_type: DataType = DataType.NEWS
    status: IngestionStatus = IngestionStatus.SUCCESS
    
    # Counts
    records_fetched: int = 0
    records_stored: int = 0
    records_skipped: int = 0
    records_failed: int = 0
    
    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    # Errors
    errors: List[str] = field(default_factory=list)
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def mark_complete(self, completed_at: datetime) -> None:
        """Mark the ingestion as complete and calculate duration."""
        self.completed_at = completed_at
        if self.started_at:
            delta = completed_at - self.started_at
            self.duration_seconds = delta.total_seconds()
    
    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)
        if self.status == IngestionStatus.SUCCESS:
            self.status = IngestionStatus.PARTIAL
    
    def mark_failed(self, error: str) -> None:
        """Mark the ingestion as failed."""
        self.status = IngestionStatus.FAILED
        self.add_error(error)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/monitoring."""
        return {
            "batch_id": str(self.batch_id),
            "source": self.source,
            "data_type": self.data_type.value,
            "status": self.status.value,
            "records_fetched": self.records_fetched,
            "records_stored": self.records_stored,
            "records_skipped": self.records_skipped,
            "records_failed": self.records_failed,
            "duration_seconds": self.duration_seconds,
            "error_count": len(self.errors),
            "errors": self.errors[:5],  # Limit for logging
        }


@dataclass
class IngestionMetrics:
    """Aggregated metrics for ingestion service."""
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    
    total_records_fetched: int = 0
    total_records_stored: int = 0
    total_records_failed: int = 0
    
    last_run_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    
    # Per-source metrics
    source_metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def record_result(self, result: IngestionResult) -> None:
        """Record an ingestion result."""
        self.total_runs += 1
        self.last_run_at = result.completed_at
        
        self.total_records_fetched += result.records_fetched
        self.total_records_stored += result.records_stored
        self.total_records_failed += result.records_failed
        
        if result.status == IngestionStatus.SUCCESS:
            self.successful_runs += 1
            self.last_success_at = result.completed_at
        elif result.status == IngestionStatus.FAILED:
            self.failed_runs += 1
            self.last_failure_at = result.completed_at
        
        # Update source-specific metrics
        if result.source not in self.source_metrics:
            self.source_metrics[result.source] = {
                "runs": 0,
                "records_stored": 0,
                "last_run": None,
            }
        
        self.source_metrics[result.source]["runs"] += 1
        self.source_metrics[result.source]["records_stored"] += result.records_stored
        self.source_metrics[result.source]["last_run"] = result.completed_at


# =============================================================
# RAW DATA ITEM TYPES
# =============================================================

@dataclass
class RawNewsItem:
    """Raw news item ready for storage."""
    source: str
    collected_at: datetime
    raw_payload: Dict[str, Any]
    payload_hash: str
    version: str
    
    source_article_id: Optional[str] = None
    source_published_at: Optional[datetime] = None
    confidence_score: Decimal = Decimal("1.0")
    collection_batch_id: Optional[UUID] = None
    collector_instance: Optional[str] = None


@dataclass
class RawMarketItem:
    """Raw market data item ready for storage."""
    source: str
    symbol: str
    data_type: str
    collected_at: datetime
    raw_payload: Dict[str, Any]
    payload_hash: str
    version: str
    
    source_timestamp: Optional[datetime] = None
    sequence_number: Optional[int] = None
    confidence_score: Decimal = Decimal("1.0")
    collection_batch_id: Optional[UUID] = None


@dataclass
class RawOnChainItem:
    """Raw on-chain data item ready for storage."""
    source: str
    chain: str
    data_type: str
    collected_at: datetime
    raw_payload: Dict[str, Any]
    payload_hash: str
    version: str
    
    block_timestamp: Optional[datetime] = None
    block_number: Optional[int] = None
    tx_hash: Optional[str] = None
    confidence_score: Decimal = Decimal("1.0")
    collection_batch_id: Optional[UUID] = None


# =============================================================
# ERROR TYPES
# =============================================================

class IngestionError(Exception):
    """Base exception for ingestion errors."""
    
    def __init__(
        self,
        message: str,
        source: str,
        recoverable: bool = True,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.source = source
        self.recoverable = recoverable
        self.details = details or {}


class FetchError(IngestionError):
    """Error fetching data from external source."""
    pass


class ParseError(IngestionError):
    """Error parsing data from external source."""
    pass


class StorageError(IngestionError):
    """Error storing data to repository."""
    pass
