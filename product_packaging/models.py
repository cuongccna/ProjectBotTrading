"""
Product Data Packaging - Core Models.

============================================================
PURPOSE
============================================================
Define core data models for the Product Data Packaging layer:
- Data product definitions
- Product schemas and versions
- Delivery configurations
- Export metadata

============================================================
CRITICAL CONSTRAINTS
============================================================
- This module does NOT trade
- This module does NOT affect internal decisions
- This module ONLY prepares data for external consumption
- All products must be NON-ACTIONABLE

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple
import hashlib
import json


# ============================================================
# PRODUCT TYPES
# ============================================================

class ProductType(Enum):
    """
    Enumeration of sellable data product types.
    
    Each product type represents a distinct commercial offering.
    """
    SENTIMENT_INDEX = "sentiment_index"
    FLOW_PRESSURE = "flow_pressure"
    MARKET_CONDITION_TIMELINE = "market_condition_timeline"
    RISK_REGIME_DATASET = "risk_regime_dataset"
    SYSTEM_HEALTH_METRICS = "system_health_metrics"


class ProductTier(Enum):
    """Product tier for commercial offerings."""
    BASIC = "basic"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class TimeBucket(Enum):
    """Time bucket for aggregation."""
    MINUTES_15 = "15m"
    HOUR_1 = "1h"
    HOURS_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"
    
    @property
    def seconds(self) -> int:
        """Get bucket duration in seconds."""
        mapping = {
            "15m": 900,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
            "1w": 604800,
            "1M": 2592000,
        }
        return mapping[self.value]
    
    @property
    def display_name(self) -> str:
        """Human-readable name."""
        mapping = {
            "15m": "15 Minutes",
            "1h": "1 Hour",
            "4h": "4 Hours",
            "1d": "1 Day",
            "1w": "1 Week",
            "1M": "1 Month",
        }
        return mapping[self.value]


class OutputFormat(Enum):
    """Supported output formats."""
    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"


class DeliveryMethod(Enum):
    """Data delivery methods."""
    FILE_DOWNLOAD = "file_download"
    REST_API = "rest_api"
    WEBHOOK = "webhook"
    S3_BUCKET = "s3_bucket"


# ============================================================
# DATA SOURCE PERMISSIONS
# ============================================================

class AllowedDataSource(Enum):
    """
    Data sources that CAN be read for product packaging.
    
    CRITICAL: Only these sources are permitted.
    """
    RAW_DATA = "raw_data"
    PROCESSED_DATA = "processed_data"
    DERIVED_SCORES = "derived_scores"
    MARKET_CONDITION_STATES = "market_condition_states"


class ProhibitedDataSource(Enum):
    """
    Data sources that must NEVER be read.
    
    CRITICAL: Access to these sources is strictly forbidden.
    """
    EXECUTION_LOGIC = "execution_logic"
    STRATEGY_LOGIC = "strategy_logic"
    RISK_THRESHOLDS = "risk_thresholds"
    ACCOUNT_TRADE_HISTORY = "account_trade_history"
    POSITION_SIZING_LOGIC = "position_sizing_logic"
    API_KEYS = "api_keys"
    ACCOUNT_BALANCES = "account_balances"


# ============================================================
# SCHEMA VERSIONING
# ============================================================

@dataclass
class SchemaVersion:
    """
    Schema version for data products.
    
    Follows semantic versioning: MAJOR.MINOR.PATCH
    - MAJOR: Breaking changes
    - MINOR: Backward-compatible additions
    - PATCH: Bug fixes
    """
    major: int
    minor: int
    patch: int
    released_at: datetime = field(default_factory=datetime.utcnow)
    deprecated: bool = False
    sunset_date: Optional[datetime] = None
    
    @property
    def version_string(self) -> str:
        """Get version as string."""
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def is_compatible_with(self, other: "SchemaVersion") -> bool:
        """Check if compatible with another version."""
        # Same major version is compatible
        return self.major == other.major
    
    def is_newer_than(self, other: "SchemaVersion") -> bool:
        """Check if this version is newer."""
        if self.major != other.major:
            return self.major > other.major
        if self.minor != other.minor:
            return self.minor > other.minor
        return self.patch > other.patch
    
    def __str__(self) -> str:
        return self.version_string


@dataclass
class SchemaField:
    """Definition of a field in a product schema."""
    name: str
    data_type: str  # "string", "number", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    nullable: bool = False
    example: Any = None
    format: Optional[str] = None  # "date-time", "decimal", etc.
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    enum_values: Optional[List[str]] = None


@dataclass
class ProductSchema:
    """
    Schema definition for a data product.
    
    Every product must have a versioned schema.
    """
    product_type: ProductType
    version: SchemaVersion
    name: str
    description: str
    fields: List[SchemaField]
    update_frequency: str  # "hourly", "daily", etc.
    time_buckets: List[TimeBucket]
    known_limitations: List[str]
    data_delay_seconds: int  # Minimum delay before data is available
    min_aggregation_count: int  # Minimum samples for aggregation
    
    def to_json_schema(self) -> Dict[str, Any]:
        """Convert to JSON Schema format."""
        properties = {}
        required = []
        
        for field in self.fields:
            prop = {
                "type": field.data_type,
                "description": field.description,
            }
            if field.example is not None:
                prop["example"] = field.example
            if field.format:
                prop["format"] = field.format
            if field.min_value is not None:
                prop["minimum"] = field.min_value
            if field.max_value is not None:
                prop["maximum"] = field.max_value
            if field.enum_values:
                prop["enum"] = field.enum_values
            if field.nullable:
                prop["nullable"] = True
            
            properties[field.name] = prop
            
            if field.required:
                required.append(field.name)
        
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": self.name,
            "description": self.description,
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
    
    def get_checksum(self) -> str:
        """Get schema checksum for integrity verification."""
        content = json.dumps(self.to_json_schema(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# ============================================================
# DATA PRODUCT DEFINITIONS
# ============================================================

@dataclass
class AggregationConfig:
    """Configuration for data aggregation."""
    method: str  # "mean", "median", "min", "max", "count", "sum"
    time_bucket: TimeBucket
    min_samples: int = 3  # Minimum samples required
    rolling_window: bool = False
    window_size: int = 1  # Number of buckets for rolling window


@dataclass
class DelayConfig:
    """Configuration for time delay."""
    min_delay_seconds: int  # Minimum delay
    max_delay_seconds: int  # Maximum delay (for randomization)
    jitter_enabled: bool = False  # Add random jitter
    
    def get_delay(self) -> timedelta:
        """Get delay as timedelta."""
        return timedelta(seconds=self.min_delay_seconds)


@dataclass
class NormalizationConfig:
    """Configuration for data normalization."""
    method: str  # "z_score", "min_max", "percentile", "none"
    min_value: float = 0.0
    max_value: float = 1.0
    clip_outliers: bool = True
    outlier_threshold: float = 3.0  # Standard deviations


@dataclass
class ProductDefinition:
    """
    Complete definition of a data product.
    
    This defines how data is extracted, transformed, and packaged.
    """
    product_id: str
    product_type: ProductType
    name: str
    description: str
    schema: ProductSchema
    tier: ProductTier
    
    # Data source
    allowed_sources: List[AllowedDataSource]
    
    # Transformation config
    aggregation: AggregationConfig
    delay: DelayConfig
    normalization: NormalizationConfig
    
    # Output config
    supported_formats: List[OutputFormat]
    supported_delivery: List[DeliveryMethod]
    
    # Safety config
    require_anonymization: bool = True
    require_non_actionable_check: bool = True
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    def get_product_key(self) -> str:
        """Get unique product key."""
        return f"{self.product_type.value}_{self.product_id}_v{self.schema.version}"


# ============================================================
# EXPORT METADATA
# ============================================================

@dataclass
class ExportMetadata:
    """
    Metadata included with every data export.
    
    All exports must include this information.
    """
    export_id: str
    product_id: str
    product_type: ProductType
    schema_version: str
    
    # Data range
    data_start_time: datetime
    data_end_time: datetime
    time_bucket: TimeBucket
    
    # Aggregation info
    record_count: int
    aggregation_method: str
    
    # Quality info
    data_freshness_seconds: int
    completeness_ratio: float  # 0.0 to 1.0
    
    # Export info
    exported_at: datetime
    format: OutputFormat
    checksum: str
    
    # Schema info
    schema_checksum: str
    known_limitations: List[str]
    update_frequency: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "export_id": self.export_id,
            "product_id": self.product_id,
            "product_type": self.product_type.value,
            "schema_version": self.schema_version,
            "data_range": {
                "start": self.data_start_time.isoformat(),
                "end": self.data_end_time.isoformat(),
                "time_bucket": self.time_bucket.value,
            },
            "aggregation": {
                "record_count": self.record_count,
                "method": self.aggregation_method,
            },
            "quality": {
                "data_freshness_seconds": self.data_freshness_seconds,
                "completeness_ratio": self.completeness_ratio,
            },
            "export": {
                "exported_at": self.exported_at.isoformat(),
                "format": self.format.value,
                "checksum": self.checksum,
            },
            "schema": {
                "checksum": self.schema_checksum,
                "known_limitations": self.known_limitations,
                "update_frequency": self.update_frequency,
            },
        }


# ============================================================
# EXPORT REQUEST / RESPONSE
# ============================================================

class ExportStatus(Enum):
    """Status of an export request."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ExportRequest:
    """Request for a data export."""
    request_id: str
    product_id: str
    product_type: ProductType
    
    # Time range
    start_time: datetime
    end_time: datetime
    time_bucket: TimeBucket
    
    # Output preferences
    format: OutputFormat
    delivery_method: DeliveryMethod
    
    # Filters
    symbols: Optional[List[str]] = None
    
    # Requester info (anonymized)
    requester_id: str = ""  # Hashed identifier
    
    # Metadata
    requested_at: datetime = field(default_factory=datetime.utcnow)
    status: ExportStatus = ExportStatus.PENDING


@dataclass
class ExportResponse:
    """Response for a data export."""
    request_id: str
    status: ExportStatus
    
    # Result
    data: Optional[Any] = None
    metadata: Optional[ExportMetadata] = None
    
    # Delivery
    download_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    
    # Error
    error_message: Optional[str] = None
    
    # Timing
    completed_at: Optional[datetime] = None
    processing_time_ms: Optional[int] = None


# ============================================================
# NON-ACTIONABLE VALIDATION
# ============================================================

class ActionableSignalType(Enum):
    """Types of actionable signals that are PROHIBITED."""
    BUY_SIGNAL = "buy_signal"
    SELL_SIGNAL = "sell_signal"
    LONG_SIGNAL = "long_signal"
    SHORT_SIGNAL = "short_signal"
    ENTRY_SIGNAL = "entry_signal"
    EXIT_SIGNAL = "exit_signal"
    DIRECTIONAL_BIAS = "directional_bias"
    PRICE_TARGET = "price_target"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


@dataclass
class NonActionableCheck:
    """Result of non-actionable validation."""
    is_valid: bool
    violations: List[str]
    signal_types_found: List[ActionableSignalType]
    recommendations: List[str]
    checked_at: datetime = field(default_factory=datetime.utcnow)


# ============================================================
# ACCESS CONTROL
# ============================================================

@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    max_data_points_per_request: int = 10000
    max_time_range_days: int = 365


@dataclass
class AccessLog:
    """Log entry for data access."""
    log_id: str
    requester_id: str  # Hashed
    product_id: str
    product_type: ProductType
    action: str  # "export", "query", "schema_fetch"
    
    # Request details
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None
    record_count: Optional[int] = None
    
    # Result
    success: bool = True
    error_message: Optional[str] = None
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ip_address_hash: Optional[str] = None
    processing_time_ms: Optional[int] = None


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_schema_version(major: int = 1, minor: int = 0, patch: int = 0) -> SchemaVersion:
    """Create a schema version."""
    return SchemaVersion(major=major, minor=minor, patch=patch)


def create_default_delay_config() -> DelayConfig:
    """Create default delay config (15 minute delay)."""
    return DelayConfig(
        min_delay_seconds=900,  # 15 minutes
        max_delay_seconds=900,
        jitter_enabled=False,
    )


def create_default_aggregation_config(
    time_bucket: TimeBucket = TimeBucket.HOUR_1
) -> AggregationConfig:
    """Create default aggregation config."""
    return AggregationConfig(
        method="mean",
        time_bucket=time_bucket,
        min_samples=3,
        rolling_window=False,
    )


def create_default_normalization_config() -> NormalizationConfig:
    """Create default normalization config."""
    return NormalizationConfig(
        method="min_max",
        min_value=0.0,
        max_value=1.0,
        clip_outliers=True,
        outlier_threshold=3.0,
    )


def create_default_rate_limit() -> RateLimitConfig:
    """Create default rate limit config."""
    return RateLimitConfig(
        requests_per_minute=60,
        requests_per_hour=1000,
        requests_per_day=10000,
    )
