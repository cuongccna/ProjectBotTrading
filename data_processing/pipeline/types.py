"""
Data Processing Pipeline - Type Definitions.

============================================================
PURPOSE
============================================================
Shared types for the data processing pipeline.

- Processing stages and transitions
- Result and metrics types
- Configuration dataclasses
- Error types

============================================================
PROCESSING STAGES
============================================================
1. RAW - Unprocessed ingested data
2. CLEANED - Deduplicated, validated, sanitized
3. NORMALIZED - Standardized formats (UTC, symbols, precision)
4. LABELED - Descriptive labels (topic, type, quality)
5. FEATURE_READY - Features extracted, ready for analysis

============================================================
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4


# ============================================================
# ENUMS
# ============================================================


class ProcessingStage(str, Enum):
    """Processing stage for data lifecycle."""
    
    RAW = "raw"
    CLEANED = "cleaned"
    NORMALIZED = "normalized"
    LABELED = "labeled"
    FEATURE_READY = "feature_ready"
    
    @classmethod
    def next_stage(cls, current: "ProcessingStage") -> Optional["ProcessingStage"]:
        """Get the next stage in the pipeline."""
        order = [cls.RAW, cls.CLEANED, cls.NORMALIZED, cls.LABELED, cls.FEATURE_READY]
        try:
            idx = order.index(current)
            return order[idx + 1] if idx < len(order) - 1 else None
        except ValueError:
            return None
    
    @classmethod
    def is_valid_transition(cls, from_stage: "ProcessingStage", to_stage: "ProcessingStage") -> bool:
        """Check if a stage transition is valid."""
        order = [cls.RAW, cls.CLEANED, cls.NORMALIZED, cls.LABELED, cls.FEATURE_READY]
        try:
            from_idx = order.index(from_stage)
            to_idx = order.index(to_stage)
            return to_idx == from_idx + 1
        except ValueError:
            return False


class ProcessingStatus(str, Enum):
    """Status of a processing operation."""
    
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class DataDomain(str, Enum):
    """Data domain types."""
    
    NEWS = "news"
    MARKET = "market"
    ONCHAIN = "onchain"


class QualityFlag(str, Enum):
    """Data quality flags (non-predictive)."""
    
    HIGH_QUALITY = "high_quality"
    LOW_QUALITY = "low_quality"
    MISSING_FIELDS = "missing_fields"
    DUPLICATE = "duplicate"
    STALE = "stale"
    VALID = "valid"
    INCOMPLETE = "incomplete"


# ============================================================
# CONFIGURATION DATACLASSES
# ============================================================


@dataclass
class CleaningConfig:
    """Configuration for data cleaning stage."""
    
    # Deduplication
    enable_deduplication: bool = True
    similarity_threshold: float = 0.85
    
    # Text cleaning
    remove_html: bool = True
    remove_urls: bool = False
    extract_urls: bool = True
    normalize_unicode: bool = True
    min_content_length: int = 10
    
    # Validation
    require_timestamp: bool = True
    require_source: bool = True
    max_age_hours: int = 168  # 7 days
    
    # Version
    version: str = "1.0.0"


@dataclass
class NormalizationConfig:
    """Configuration for data normalization stage."""
    
    # Timestamp normalization
    target_timezone: str = "UTC"
    
    # Symbol normalization
    symbol_mapping_file: Optional[str] = None
    normalize_to_uppercase: bool = True
    
    # Numeric precision
    price_decimal_places: int = 8
    volume_decimal_places: int = 4
    percentage_decimal_places: int = 4
    
    # Text normalization
    target_encoding: str = "utf-8"
    
    # Version
    version: str = "1.0.0"


@dataclass
class LabelingConfig:
    """Configuration for data labeling stage."""
    
    # Topic classification
    enabled_topics: List[str] = field(default_factory=lambda: [
        "regulation",
        "technology",
        "market",
        "adoption",
        "security",
        "macro",
        "defi",
        "nft",
        "other",
    ])
    min_topic_confidence: float = 0.5
    max_topics_per_item: int = 3
    
    # Risk keyword detection
    enable_risk_detection: bool = True
    risk_categories: List[str] = field(default_factory=lambda: [
        "regulatory_risk",
        "security_risk",
        "liquidity_risk",
        "market_risk",
        "operational_risk",
    ])
    
    # Version
    version: str = "1.0.0"


@dataclass
class FeatureConfig:
    """Configuration for feature extraction stage."""
    
    # Time windows (in seconds)
    time_windows: List[int] = field(default_factory=lambda: [
        300,     # 5 minutes
        900,     # 15 minutes
        3600,    # 1 hour
        14400,   # 4 hours
        86400,   # 24 hours
    ])
    
    # Feature categories
    enabled_feature_categories: List[str] = field(default_factory=lambda: [
        "volume",
        "frequency",
        "volatility",
        "activity",
    ])
    
    # Version
    version: str = "1.0.0"


@dataclass
class PipelineConfig:
    """Configuration for the entire processing pipeline."""
    
    cleaning: CleaningConfig = field(default_factory=CleaningConfig)
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)
    labeling: LabelingConfig = field(default_factory=LabelingConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    
    # Batch processing
    batch_size: int = 100
    parallel_processing: bool = True
    max_workers: int = 4
    
    # Error handling
    continue_on_error: bool = True
    max_errors_per_batch: int = 10


# ============================================================
# RESULT DATACLASSES
# ============================================================


@dataclass
class StageTransition:
    """Record of a stage transition."""
    
    record_id: UUID
    domain: DataDomain
    from_stage: ProcessingStage
    to_stage: ProcessingStage
    transitioned_at: datetime = field(default_factory=datetime.utcnow)
    processor_version: str = "1.0.0"


@dataclass
class ProcessingResult:
    """Result of processing a single record."""
    
    record_id: UUID
    domain: DataDomain
    status: ProcessingStatus
    from_stage: ProcessingStage
    to_stage: ProcessingStage
    processed_at: datetime = field(default_factory=datetime.utcnow)
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StageMetrics:
    """Metrics for a single processing stage."""
    
    stage: ProcessingStage
    records_processed: int = 0
    records_succeeded: int = 0
    records_failed: int = 0
    records_skipped: int = 0
    total_duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.records_processed == 0:
            return 0.0
        return self.records_succeeded / self.records_processed
    
    @property
    def average_duration_ms(self) -> float:
        """Calculate average duration per record in milliseconds."""
        if self.records_processed == 0:
            return 0.0
        return (self.total_duration_seconds * 1000) / self.records_processed


@dataclass
class PipelineRunResult:
    """Result of a complete pipeline run."""
    
    run_id: UUID = field(default_factory=uuid4)
    status: ProcessingStatus = ProcessingStatus.SUCCESS
    domain: Optional[DataDomain] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    stage_metrics: Dict[ProcessingStage, StageMetrics] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
    @property
    def total_records_processed(self) -> int:
        """Total records processed across all stages."""
        return sum(m.records_processed for m in self.stage_metrics.values())
    
    @property
    def total_duration_seconds(self) -> float:
        """Total duration in seconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0


# ============================================================
# PROCESSING ITEM TYPES
# ============================================================


@dataclass
class CleanedNewsItem:
    """News item after cleaning stage."""
    
    raw_news_id: UUID
    source: str
    collected_at: datetime
    published_at: Optional[datetime]
    original_payload: Dict[str, Any]
    
    # Cleaned content
    title: str
    content: Optional[str]
    summary: Optional[str]
    url: Optional[str]
    author: Optional[str]
    
    # Cleaning metadata
    content_hash: str
    is_duplicate: bool
    duplicate_of_id: Optional[UUID]
    extracted_urls: List[str]
    cleaning_operations: List[str]
    characters_removed: int
    
    # Quality
    quality_flag: QualityFlag
    word_count: int
    
    # Versioning
    cleaned_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


@dataclass
class NormalizedNewsItem:
    """News item after normalization stage."""
    
    raw_news_id: UUID
    source: str
    
    # Normalized timestamps (UTC)
    collected_at_utc: datetime
    published_at_utc: Optional[datetime]
    
    # Normalized content
    title: str
    content: Optional[str]
    summary: Optional[str]
    url: Optional[str]
    author: Optional[str]
    
    # Normalized metadata
    assets_mentioned: List[str]
    language_detected: str
    word_count: int
    content_hash: str
    
    # Quality
    quality_flag: QualityFlag
    
    # Versioning
    normalized_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


@dataclass
class LabeledNewsItem:
    """News item after labeling stage."""
    
    raw_news_id: UUID
    source: str
    
    # Normalized data
    collected_at_utc: datetime
    published_at_utc: Optional[datetime]
    title: str
    content: Optional[str]
    
    # Labels (descriptive, non-predictive)
    news_category: str  # regulation, technology, market, etc.
    event_type: Optional[str]  # announcement, update, incident, etc.
    primary_topics: List[str]
    topic_confidences: Dict[str, float]
    
    # Risk keywords (descriptive)
    detected_keywords: List[str]
    keyword_categories: Dict[str, List[str]]  # category -> keywords
    
    # Quality
    quality_flag: QualityFlag
    data_quality_score: Decimal
    
    # Versioning
    labeled_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


@dataclass
class FeatureReadyNewsItem:
    """News item after feature extraction stage."""
    
    raw_news_id: UUID
    source: str
    collected_at_utc: datetime
    
    # Reference to labels
    news_category: str
    primary_topics: List[str]
    
    # Extracted features (stateless, deterministic)
    features: Dict[str, float]
    feature_version: str
    
    # Quality
    quality_flag: QualityFlag
    
    # Versioning
    feature_extracted_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


# ============================================================
# MARKET DATA PROCESSING ITEMS
# ============================================================


@dataclass
class CleanedMarketItem:
    """Market data item after cleaning stage."""
    
    raw_market_id: UUID
    source: str
    symbol: str
    data_type: str
    collected_at: datetime
    source_timestamp: Optional[datetime]
    
    # Cleaned payload
    cleaned_payload: Dict[str, Any]
    
    # Cleaning metadata
    payload_hash: str
    is_duplicate: bool
    fields_validated: List[str]
    fields_missing: List[str]
    
    # Quality
    quality_flag: QualityFlag
    
    # Versioning
    cleaned_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


@dataclass
class NormalizedMarketItem:
    """Market data item after normalization stage."""
    
    raw_market_id: UUID
    source: str
    symbol_normalized: str  # e.g., BTC/USD
    data_type: str
    
    # Normalized timestamps (UTC)
    collected_at_utc: datetime
    source_timestamp_utc: Optional[datetime]
    
    # Normalized values
    price: Optional[Decimal]
    volume_24h: Optional[Decimal]
    market_cap: Optional[Decimal]
    change_24h_pct: Optional[Decimal]
    
    # Additional normalized fields
    normalized_payload: Dict[str, Any]
    
    # Quality
    quality_flag: QualityFlag
    
    # Versioning
    normalized_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


@dataclass
class LabeledMarketItem:
    """Market data item after labeling stage."""
    
    raw_market_id: UUID
    source: str
    symbol_normalized: str
    
    # Labels (descriptive, non-predictive)
    activity_type: str  # normal, high_volume, low_volume
    data_freshness: str  # fresh, stale, delayed
    
    # Quality
    quality_flag: QualityFlag
    data_quality_score: Decimal
    
    # Versioning
    labeled_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


@dataclass
class FeatureReadyMarketItem:
    """Market data item after feature extraction stage."""
    
    raw_market_id: UUID
    source: str
    symbol_normalized: str
    collected_at_utc: datetime
    
    # Extracted features
    features: Dict[str, float]
    feature_version: str
    
    # Quality
    quality_flag: QualityFlag
    
    # Versioning
    feature_extracted_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


# ============================================================
# ON-CHAIN DATA PROCESSING ITEMS
# ============================================================


@dataclass
class CleanedOnChainItem:
    """On-chain data item after cleaning stage."""
    
    raw_onchain_id: UUID
    chain: str
    data_type: str
    collected_at: datetime
    block_number: Optional[int]
    block_timestamp: Optional[datetime]
    transaction_hash: Optional[str]
    
    # Cleaned payload
    cleaned_payload: Dict[str, Any]
    
    # Cleaning metadata
    payload_hash: str
    is_duplicate: bool
    fields_validated: List[str]
    fields_missing: List[str]
    
    # Quality
    quality_flag: QualityFlag
    
    # Versioning
    cleaned_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


@dataclass
class NormalizedOnChainItem:
    """On-chain data item after normalization stage."""
    
    raw_onchain_id: UUID
    chain_normalized: str  # e.g., ETHEREUM, BITCOIN
    data_type: str
    
    # Normalized timestamps (UTC)
    collected_at_utc: datetime
    block_timestamp_utc: Optional[datetime]
    
    # Normalized identifiers
    block_number: Optional[int]
    transaction_hash_normalized: Optional[str]
    address_normalized: Optional[str]
    
    # Normalized values
    value_native: Optional[Decimal]
    value_usd: Optional[Decimal]
    gas_used: Optional[int]
    
    # Additional normalized fields
    normalized_payload: Dict[str, Any]
    
    # Quality
    quality_flag: QualityFlag
    
    # Versioning
    normalized_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


@dataclass
class LabeledOnChainItem:
    """On-chain data item after labeling stage."""
    
    raw_onchain_id: UUID
    chain_normalized: str
    
    # Labels (descriptive, non-predictive)
    activity_type: str  # transfer, swap, stake, bridge, etc.
    transaction_size_category: str  # small, medium, large, whale
    
    # Quality
    quality_flag: QualityFlag
    data_quality_score: Decimal
    
    # Versioning
    labeled_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


@dataclass
class FeatureReadyOnChainItem:
    """On-chain data item after feature extraction stage."""
    
    raw_onchain_id: UUID
    chain_normalized: str
    collected_at_utc: datetime
    
    # Extracted features
    features: Dict[str, float]
    feature_version: str
    
    # Quality
    quality_flag: QualityFlag
    
    # Versioning
    feature_extracted_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


# ============================================================
# ERROR TYPES
# ============================================================


class ProcessingError(Exception):
    """Base exception for processing errors."""
    
    def __init__(
        self,
        message: str,
        stage: ProcessingStage,
        record_id: Optional[UUID] = None,
        recoverable: bool = True,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.record_id = record_id
        self.recoverable = recoverable


class CleaningError(ProcessingError):
    """Error during data cleaning."""
    
    def __init__(
        self,
        message: str,
        record_id: Optional[UUID] = None,
        recoverable: bool = True,
    ) -> None:
        super().__init__(message, ProcessingStage.CLEANED, record_id, recoverable)


class NormalizationError(ProcessingError):
    """Error during data normalization."""
    
    def __init__(
        self,
        message: str,
        record_id: Optional[UUID] = None,
        recoverable: bool = True,
    ) -> None:
        super().__init__(message, ProcessingStage.NORMALIZED, record_id, recoverable)


class LabelingError(ProcessingError):
    """Error during data labeling."""
    
    def __init__(
        self,
        message: str,
        record_id: Optional[UUID] = None,
        recoverable: bool = True,
    ) -> None:
        super().__init__(message, ProcessingStage.LABELED, record_id, recoverable)


class FeatureExtractionError(ProcessingError):
    """Error during feature extraction."""
    
    def __init__(
        self,
        message: str,
        record_id: Optional[UUID] = None,
        recoverable: bool = True,
    ) -> None:
        super().__init__(message, ProcessingStage.FEATURE_READY, record_id, recoverable)


# ============================================================
# UTILITY FUNCTIONS
# ============================================================


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    """Compute SHA-256 hash of JSON payload."""
    payload_str = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
