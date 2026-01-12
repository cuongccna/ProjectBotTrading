"""
Data Retention Models.

============================================================
PURPOSE
============================================================
Core data models for the Data Retention and Monetization layer.

This module defines:
1. Data categories with strict separation
2. Retention policies per category
3. Data lineage structures
4. Storage tier definitions
5. Access control models

CRITICAL: This module does NOT trade, does NOT influence decisions.
Data is treated as a first-class strategic asset.

============================================================
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set


# ============================================================
# DATA CATEGORIES (STRICT SEPARATION)
# ============================================================

class DataCategory(Enum):
    """
    Strict data categories.
    
    Each category has different:
    - Retention requirements
    - Storage strategy
    - Monetization potential
    - Compliance requirements
    """
    RAW_DATA = "raw_data"
    PROCESSED_DATA = "processed_data"
    DERIVED_SCORES = "derived_scores"
    DECISION_LOGS = "decision_logs"
    EXECUTION_RECORDS = "execution_records"
    SYSTEM_METADATA = "system_metadata"


class DataSubCategory(Enum):
    """Subcategories for finer classification."""
    # Raw Data
    NEWS_HEADLINES = "news_headlines"
    MARKET_OHLCV = "market_ohlcv"
    ONCHAIN_FLOW_EVENTS = "onchain_flow_events"
    EXCHANGE_RESPONSES = "exchange_responses"
    ORDERBOOK_SNAPSHOTS = "orderbook_snapshots"
    FUNDING_RATES = "funding_rates"
    
    # Processed Data
    CLEANED_NEWS = "cleaned_news"
    NORMALIZED_MARKET_DATA = "normalized_market_data"
    FLOW_METRICS = "flow_metrics"
    MARKET_CONDITION_STATES = "market_condition_states"
    AGGREGATED_ORDERBOOK = "aggregated_orderbook"
    
    # Derived Scores
    SENTIMENT_SCORES = "sentiment_scores"
    FLOW_RISK_SCORES = "flow_risk_scores"
    AGGREGATED_RISK_STATES = "aggregated_risk_states"
    VOLATILITY_INDICES = "volatility_indices"
    REGIME_CLASSIFICATIONS = "regime_classifications"
    
    # Decision Logs
    RISK_DECISIONS = "risk_decisions"
    STRATEGY_DECISIONS = "strategy_decisions"
    TRADE_GUARD_DECISIONS = "trade_guard_decisions"
    POSITION_SIZING_DECISIONS = "position_sizing_decisions"
    
    # Execution Records
    ORDERS_SUBMITTED = "orders_submitted"
    ORDERS_FILLED = "orders_filled"
    PARTIAL_FILLS = "partial_fills"
    SLIPPAGE_METRICS = "slippage_metrics"
    FEE_RECORDS = "fee_records"
    
    # System Metadata
    MODULE_HEALTH = "module_health"
    ERRORS = "errors"
    LATENCY_METRICS = "latency_metrics"
    ANOMALIES = "anomalies"
    RESOURCE_USAGE = "resource_usage"


# ============================================================
# RETENTION PERIODS
# ============================================================

class RetentionPeriod(Enum):
    """Retention period classifications."""
    SHORT_TERM = "short_term"       # 7-30 days
    MEDIUM_TERM = "medium_term"     # 30-180 days
    LONG_TERM = "long_term"         # 180 days - 2 years
    INDEFINITE = "indefinite"       # Never delete


@dataclass(frozen=True)
class RetentionDuration:
    """Concrete retention duration."""
    days: Optional[int] = None
    indefinite: bool = False
    
    def __post_init__(self):
        if not self.indefinite and self.days is None:
            raise ValueError("Must specify days or set indefinite=True")
        if self.indefinite and self.days is not None:
            raise ValueError("Cannot specify days when indefinite=True")
    
    @classmethod
    def short_term(cls, days: int = 30) -> "RetentionDuration":
        return cls(days=days)
    
    @classmethod
    def medium_term(cls, days: int = 180) -> "RetentionDuration":
        return cls(days=days)
    
    @classmethod
    def long_term(cls, days: int = 730) -> "RetentionDuration":
        return cls(days=days)
    
    @classmethod
    def forever(cls) -> "RetentionDuration":
        return cls(indefinite=True)
    
    def is_expired(self, created_at: datetime) -> bool:
        """Check if data has exceeded retention period."""
        if self.indefinite:
            return False
        return datetime.utcnow() > created_at + timedelta(days=self.days)
    
    def expiration_date(self, created_at: datetime) -> Optional[datetime]:
        """Get expiration date."""
        if self.indefinite:
            return None
        return created_at + timedelta(days=self.days)


# ============================================================
# STORAGE TIERS
# ============================================================

class StorageTier(Enum):
    """
    Storage tier for cost optimization.
    
    HOT: Frequently accessed, fast retrieval, highest cost
    WARM: Occasionally accessed, moderate latency
    COLD: Rarely accessed, high latency, lowest cost
    ARCHIVE: Long-term preservation, very high latency
    """
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    ARCHIVE = "archive"


@dataclass
class StorageTierConfig:
    """Configuration for a storage tier."""
    tier: StorageTier
    max_age_days: Optional[int]  # Data older than this moves to next tier
    retrieval_latency_ms: int
    cost_per_gb_month: Decimal
    compression_enabled: bool = True
    encryption_required: bool = True
    
    @classmethod
    def hot_tier(cls) -> "StorageTierConfig":
        return cls(
            tier=StorageTier.HOT,
            max_age_days=7,
            retrieval_latency_ms=10,
            cost_per_gb_month=Decimal("0.10"),
            compression_enabled=False,
            encryption_required=True,
        )
    
    @classmethod
    def warm_tier(cls) -> "StorageTierConfig":
        return cls(
            tier=StorageTier.WARM,
            max_age_days=30,
            retrieval_latency_ms=100,
            cost_per_gb_month=Decimal("0.05"),
            compression_enabled=True,
            encryption_required=True,
        )
    
    @classmethod
    def cold_tier(cls) -> "StorageTierConfig":
        return cls(
            tier=StorageTier.COLD,
            max_age_days=180,
            retrieval_latency_ms=5000,
            cost_per_gb_month=Decimal("0.01"),
            compression_enabled=True,
            encryption_required=True,
        )
    
    @classmethod
    def archive_tier(cls) -> "StorageTierConfig":
        return cls(
            tier=StorageTier.ARCHIVE,
            max_age_days=None,  # No further migration
            retrieval_latency_ms=43200000,  # 12 hours
            cost_per_gb_month=Decimal("0.004"),
            compression_enabled=True,
            encryption_required=True,
        )


# ============================================================
# ACCESS CONTROL
# ============================================================

class AccessLevel(Enum):
    """Access level for data."""
    INTERNAL_FULL = "internal_full"       # Read + Write
    INTERNAL_READ = "internal_read"       # Read only
    EXTERNAL_READ = "external_read"       # External read (logged)
    EXPORT = "export"                     # Export permission
    NONE = "none"                         # No access


class DataSensitivity(Enum):
    """Data sensitivity classification."""
    PUBLIC = "public"               # Can be shared externally
    INTERNAL = "internal"           # Internal use only
    CONFIDENTIAL = "confidential"   # Limited internal access
    RESTRICTED = "restricted"       # Highly sensitive, audit required
    PROHIBITED = "prohibited"       # Cannot be exported or shared


# ============================================================
# DATA LINEAGE
# ============================================================

@dataclass
class DataSource:
    """Source of data."""
    source_id: str
    source_type: str  # e.g., "exchange_api", "news_feed", "internal_module"
    source_name: str  # e.g., "binance", "cryptopanic", "sentiment_analyzer"
    source_version: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessingStep:
    """A step in data processing pipeline."""
    step_id: str
    step_name: str
    module_name: str
    module_version: str
    timestamp: datetime
    input_record_ids: List[str]
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_name": self.step_name,
            "module_name": self.module_name,
            "module_version": self.module_version,
            "timestamp": self.timestamp.isoformat(),
            "input_record_ids": self.input_record_ids,
            "parameters": self.parameters,
        }


@dataclass
class DataLineage:
    """
    Complete lineage for a data record.
    
    Every derived data point must be traceable back to raw inputs.
    """
    lineage_id: str
    record_id: str
    source: DataSource
    processing_steps: List[ProcessingStep] = field(default_factory=list)
    parent_record_ids: List[str] = field(default_factory=list)
    correlation_id: Optional[str] = None  # Links related records
    
    def add_processing_step(self, step: ProcessingStep) -> None:
        """Add a processing step."""
        self.processing_steps.append(step)
    
    def get_root_sources(self) -> List[str]:
        """Get IDs of root source records."""
        if not self.processing_steps:
            return [self.record_id]
        return self.processing_steps[0].input_record_ids
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "lineage_id": self.lineage_id,
            "record_id": self.record_id,
            "source": {
                "source_id": self.source.source_id,
                "source_type": self.source.source_type,
                "source_name": self.source.source_name,
                "source_version": self.source.source_version,
            },
            "processing_steps": [s.to_dict() for s in self.processing_steps],
            "parent_record_ids": self.parent_record_ids,
            "correlation_id": self.correlation_id,
        }


# ============================================================
# RETENTION POLICY
# ============================================================

@dataclass
class RetentionPolicy:
    """
    Retention policy for a data category.
    
    All policies must be explicit and logged.
    """
    policy_id: str
    category: DataCategory
    subcategory: Optional[DataSubCategory] = None
    retention_duration: RetentionDuration = field(default_factory=RetentionDuration.forever)
    sensitivity: DataSensitivity = DataSensitivity.INTERNAL
    storage_tiers: List[StorageTier] = field(default_factory=lambda: [StorageTier.HOT])
    monetization_eligible: bool = False
    requires_anonymization: bool = True
    compliance_tags: List[str] = field(default_factory=list)
    description: str = ""
    
    @classmethod
    def for_raw_data(cls) -> "RetentionPolicy":
        """Policy for raw data: long-term retention."""
        return cls(
            policy_id="policy_raw_data",
            category=DataCategory.RAW_DATA,
            retention_duration=RetentionDuration.long_term(days=730),
            sensitivity=DataSensitivity.INTERNAL,
            storage_tiers=[StorageTier.HOT, StorageTier.WARM, StorageTier.COLD],
            monetization_eligible=True,
            requires_anonymization=True,
            description="Raw data: long-term retention for historical analysis and products",
        )
    
    @classmethod
    def for_processed_data(cls) -> "RetentionPolicy":
        """Policy for processed data: medium to long-term."""
        return cls(
            policy_id="policy_processed_data",
            category=DataCategory.PROCESSED_DATA,
            retention_duration=RetentionDuration.long_term(days=365),
            sensitivity=DataSensitivity.INTERNAL,
            storage_tiers=[StorageTier.HOT, StorageTier.WARM],
            monetization_eligible=True,
            requires_anonymization=True,
            description="Processed data: medium-long term for analysis and feature evolution",
        )
    
    @classmethod
    def for_derived_scores(cls) -> "RetentionPolicy":
        """Policy for derived scores: long-term (intellectual assets)."""
        return cls(
            policy_id="policy_derived_scores",
            category=DataCategory.DERIVED_SCORES,
            retention_duration=RetentionDuration.forever(),
            sensitivity=DataSensitivity.CONFIDENTIAL,
            storage_tiers=[StorageTier.HOT, StorageTier.WARM, StorageTier.ARCHIVE],
            monetization_eligible=True,
            requires_anonymization=True,
            compliance_tags=["intellectual_property"],
            description="Derived scores: indefinite retention, core intellectual assets",
        )
    
    @classmethod
    def for_decision_logs(cls) -> "RetentionPolicy":
        """Policy for decision logs: indefinite (audit required)."""
        return cls(
            policy_id="policy_decision_logs",
            category=DataCategory.DECISION_LOGS,
            retention_duration=RetentionDuration.forever(),
            sensitivity=DataSensitivity.RESTRICTED,
            storage_tiers=[StorageTier.HOT, StorageTier.WARM, StorageTier.ARCHIVE],
            monetization_eligible=False,  # Never monetize decision logs
            requires_anonymization=True,
            compliance_tags=["audit_required", "compliance"],
            description="Decision logs: indefinite retention for audit and trust",
        )
    
    @classmethod
    def for_execution_records(cls) -> "RetentionPolicy":
        """Policy for execution records: indefinite (compliance)."""
        return cls(
            policy_id="policy_execution_records",
            category=DataCategory.EXECUTION_RECORDS,
            retention_duration=RetentionDuration.forever(),
            sensitivity=DataSensitivity.RESTRICTED,
            storage_tiers=[StorageTier.HOT, StorageTier.WARM, StorageTier.ARCHIVE],
            monetization_eligible=False,  # Never monetize execution records
            requires_anonymization=True,
            compliance_tags=["compliance", "financial_records"],
            description="Execution records: indefinite for compliance and performance evaluation",
        )
    
    @classmethod
    def for_system_metadata(cls) -> "RetentionPolicy":
        """Policy for system metadata: short to medium-term."""
        return cls(
            policy_id="policy_system_metadata",
            category=DataCategory.SYSTEM_METADATA,
            retention_duration=RetentionDuration.medium_term(days=90),
            sensitivity=DataSensitivity.INTERNAL,
            storage_tiers=[StorageTier.HOT, StorageTier.WARM],
            monetization_eligible=False,
            requires_anonymization=False,
            description="System metadata: short-medium term for reliability improvement",
        )


# ============================================================
# DATA RECORD
# ============================================================

@dataclass
class DataRecord:
    """
    A stored data record with full metadata.
    """
    record_id: str
    category: DataCategory
    subcategory: Optional[DataSubCategory]
    created_at: datetime
    data_hash: str  # SHA-256 of content
    size_bytes: int
    storage_tier: StorageTier
    lineage: DataLineage
    policy: RetentionPolicy
    correlation_id: Optional[str] = None
    symbol: Optional[str] = None
    exchange: Optional[str] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deletion_reason: Optional[str] = None
    last_accessed: Optional[datetime] = None
    access_count: int = 0
    
    def mark_deleted(self, reason: str) -> None:
        """Mark record as deleted (soft delete)."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.deletion_reason = reason
    
    def is_expired(self) -> bool:
        """Check if record has exceeded retention period."""
        return self.policy.retention_duration.is_expired(self.created_at)
    
    def get_expiration_date(self) -> Optional[datetime]:
        """Get expiration date."""
        return self.policy.retention_duration.expiration_date(self.created_at)


# ============================================================
# AUDIT RECORDS
# ============================================================

class AuditAction(Enum):
    """Auditable actions."""
    CREATE = "create"
    READ = "read"
    EXPORT = "export"
    TIER_MIGRATE = "tier_migrate"
    MARK_DELETED = "mark_deleted"
    HARD_DELETE = "hard_delete"
    ACCESS_DENIED = "access_denied"
    POLICY_CHANGE = "policy_change"


@dataclass
class AuditRecord:
    """
    Audit record for data access and modifications.
    
    All retention and deletion actions must be logged.
    """
    audit_id: str
    record_id: str
    action: AuditAction
    timestamp: datetime
    actor: str  # Module or user
    actor_type: str  # "system", "user", "export"
    details: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "record_id": self.record_id,
            "action": self.action.value,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "actor_type": self.actor_type,
            "details": self.details,
            "success": self.success,
            "error_message": self.error_message,
        }


# ============================================================
# MONETIZATION PREPARATION
# ============================================================

class MonetizationStatus(Enum):
    """Status of monetization preparation."""
    NOT_ELIGIBLE = "not_eligible"
    PENDING_ANONYMIZATION = "pending_anonymization"
    ANONYMIZED = "anonymized"
    AGGREGATED = "aggregated"
    READY_FOR_PRODUCT = "ready_for_product"


@dataclass
class MonetizationMetadata:
    """
    Metadata for monetization-ready data.
    
    Requirements:
    - No user-identifiable information
    - No exchange API keys
    - No account balances
    - No execution secrets
    """
    record_id: str
    original_record_id: str
    status: MonetizationStatus
    anonymization_applied: bool = False
    aggregation_level: Optional[str] = None  # "hourly", "daily", "weekly"
    pii_removed: bool = False
    secrets_removed: bool = False
    product_category: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def is_safe_for_export(self) -> bool:
        """Check if data is safe for external use."""
        return (
            self.anonymization_applied and
            self.pii_removed and
            self.secrets_removed and
            self.status in [
                MonetizationStatus.ANONYMIZED,
                MonetizationStatus.AGGREGATED,
                MonetizationStatus.READY_FOR_PRODUCT,
            ]
        )


# ============================================================
# DATA PRODUCT DEFINITIONS
# ============================================================

class DataProductType(Enum):
    """Types of potential data products."""
    SENTIMENT_INDEX = "sentiment_index"
    RISK_REGIME_DATASET = "risk_regime_dataset"
    FLOW_PRESSURE_INDICATOR = "flow_pressure_indicator"
    MARKET_CONDITION_TIMELINE = "market_condition_timeline"
    VOLATILITY_DASHBOARD = "volatility_dashboard"
    HISTORICAL_RISK_EVENTS = "historical_risk_events"


@dataclass
class DataProductDefinition:
    """
    Definition of a potential data product.
    
    These are informational products, not trading advice.
    """
    product_id: str
    product_type: DataProductType
    name: str
    description: str
    source_categories: List[DataCategory]
    aggregation_level: str
    update_frequency: str
    anonymization_required: bool = True
    is_enabled: bool = False  # Not selling yet
    disclaimer: str = "For informational purposes only. Not trading advice."


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_default_retention_policies() -> Dict[DataCategory, RetentionPolicy]:
    """Create default retention policies for all categories."""
    return {
        DataCategory.RAW_DATA: RetentionPolicy.for_raw_data(),
        DataCategory.PROCESSED_DATA: RetentionPolicy.for_processed_data(),
        DataCategory.DERIVED_SCORES: RetentionPolicy.for_derived_scores(),
        DataCategory.DECISION_LOGS: RetentionPolicy.for_decision_logs(),
        DataCategory.EXECUTION_RECORDS: RetentionPolicy.for_execution_records(),
        DataCategory.SYSTEM_METADATA: RetentionPolicy.for_system_metadata(),
    }


def create_storage_tier_configs() -> Dict[StorageTier, StorageTierConfig]:
    """Create default storage tier configurations."""
    return {
        StorageTier.HOT: StorageTierConfig.hot_tier(),
        StorageTier.WARM: StorageTierConfig.warm_tier(),
        StorageTier.COLD: StorageTierConfig.cold_tier(),
        StorageTier.ARCHIVE: StorageTierConfig.archive_tier(),
    }


def compute_data_hash(data: bytes) -> str:
    """Compute SHA-256 hash of data."""
    return hashlib.sha256(data).hexdigest()


def generate_record_id() -> str:
    """Generate a unique record ID."""
    return f"rec_{uuid.uuid4().hex}"


def generate_correlation_id() -> str:
    """Generate a correlation ID for linking related records."""
    return f"corr_{uuid.uuid4().hex}"
