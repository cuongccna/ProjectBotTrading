"""
Dashboard Database Models - Data Pipeline.

============================================================
DATA PIPELINE TABLES
============================================================

Tables for tracking data ingestion, processing, and integrity.

Source: Data ingestion modules, sentiment processors
Update Frequency: Every minute
Retention: 30 days

============================================================
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from dataclasses import dataclass, field


class PipelineStage(str, Enum):
    """Pipeline processing stages."""
    INGESTION = "ingestion"
    CLEANING = "cleaning"
    ENRICHMENT = "enrichment"
    SENTIMENT = "sentiment"
    STORAGE = "storage"


class BatchStatus(str, Enum):
    """Batch processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class PipelineMetrics:
    """
    Real-time pipeline metrics per source.
    
    Table: pipeline_metrics
    Primary Key: (source_name, stage)
    """
    source_name: str
    stage: PipelineStage
    records_in_1h: int
    records_out_1h: int
    records_in_24h: int
    records_out_24h: int
    drop_rate_1h: float  # (in - out) / in
    avg_processing_time_ms: float
    last_record_time: Optional[datetime]
    error_count_1h: int
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "pipeline_monitor"
    update_frequency_seconds: int = 60
    
    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "stage": self.stage.value,
            "records_in_1h": self.records_in_1h,
            "records_out_1h": self.records_out_1h,
            "records_in_24h": self.records_in_24h,
            "records_out_24h": self.records_out_24h,
            "drop_rate_1h": round(self.drop_rate_1h, 4),
            "avg_processing_time_ms": round(self.avg_processing_time_ms, 2),
            "last_record_time": self.last_record_time.isoformat() if self.last_record_time else None,
            "error_count_1h": self.error_count_1h,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class IngestionCount:
    """
    Data ingestion count per source type.
    
    Table: ingestion_counts
    Primary Key: (source_type, time_bucket)
    """
    source_type: str  # news, onchain, smart_money, market_data
    time_bucket: datetime  # Hourly bucket
    raw_count: int
    cleaned_count: int
    enriched_count: int
    error_count: int
    
    # Source breakdown
    source_breakdown: dict = field(default_factory=dict)  # {source: count}
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "ingestion_monitor"
    update_frequency_seconds: int = 300  # 5 minutes
    
    def to_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "time_bucket": self.time_bucket.isoformat(),
            "raw_count": self.raw_count,
            "cleaned_count": self.cleaned_count,
            "enriched_count": self.enriched_count,
            "error_count": self.error_count,
            "source_breakdown": self.source_breakdown,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class SentimentBatchStatus:
    """
    Sentiment processing batch status.
    
    Table: sentiment_batch_status
    Primary Key: batch_id
    """
    batch_id: str
    status: BatchStatus
    source_type: str
    records_total: int
    records_processed: int
    records_failed: int
    started_at: datetime
    completed_at: Optional[datetime]
    processing_time_seconds: Optional[float]
    error_message: Optional[str]
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "sentiment_processor"
    retention_days: int = 7
    
    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "status": self.status.value,
            "source_type": self.source_type,
            "records_total": self.records_total,
            "records_processed": self.records_processed,
            "records_failed": self.records_failed,
            "progress_pct": round(self.records_processed / max(1, self.records_total) * 100, 1),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "processing_time_seconds": self.processing_time_seconds,
            "error_message": self.error_message,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class DataQualityMetrics:
    """
    Data quality metrics per source.
    
    Table: data_quality_metrics
    Primary Key: (source_name, metric_type)
    """
    source_name: str
    metric_type: str  # completeness, accuracy, consistency, timeliness
    score: float  # 0-100
    samples_evaluated: int
    threshold: float
    is_passing: bool
    details: Optional[str]
    
    measured_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "data_quality_monitor"
    update_frequency_seconds: int = 300
    
    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "metric_type": self.metric_type,
            "score": round(self.score, 2),
            "samples_evaluated": self.samples_evaluated,
            "threshold": self.threshold,
            "is_passing": self.is_passing,
            "details": self.details,
            "measured_at": self.measured_at.isoformat(),
        }


@dataclass
class OnChainEventCount:
    """
    On-chain event counts.
    
    Table: onchain_event_counts
    Primary Key: (chain, event_type, time_bucket)
    """
    chain: str  # ethereum, bitcoin, solana
    event_type: str  # whale_transfer, exchange_flow, etc.
    time_bucket: datetime
    event_count: int
    total_value_usd: float
    unique_addresses: int
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "onchain_monitor"
    update_frequency_seconds: int = 60


@dataclass
class SmartMoneyEventCount:
    """
    Smart money event counts.
    
    Table: smart_money_event_counts
    Primary Key: (entity_type, time_bucket)
    """
    entity_type: str  # fund, whale, market_maker
    time_bucket: datetime
    event_count: int
    buy_count: int
    sell_count: int
    total_volume_usd: float
    unique_wallets: int
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "smart_money_tracker"
    update_frequency_seconds: int = 60


# =============================================================
# SQL TABLE DEFINITIONS
# =============================================================

PIPELINE_METRICS_TABLE = """
CREATE TABLE IF NOT EXISTS pipeline_metrics (
    source_name VARCHAR(100) NOT NULL,
    stage VARCHAR(50) NOT NULL,
    records_in_1h INTEGER DEFAULT 0,
    records_out_1h INTEGER DEFAULT 0,
    records_in_24h INTEGER DEFAULT 0,
    records_out_24h INTEGER DEFAULT 0,
    drop_rate_1h FLOAT DEFAULT 0,
    avg_processing_time_ms FLOAT DEFAULT 0,
    last_record_time TIMESTAMP,
    error_count_1h INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'pipeline_monitor',
    update_frequency_seconds INTEGER DEFAULT 60,
    PRIMARY KEY (source_name, stage)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_source ON pipeline_metrics(source_name);
CREATE INDEX IF NOT EXISTS idx_pipeline_stage ON pipeline_metrics(stage);
"""

INGESTION_COUNTS_TABLE = """
CREATE TABLE IF NOT EXISTS ingestion_counts (
    source_type VARCHAR(50) NOT NULL,
    time_bucket TIMESTAMP NOT NULL,
    raw_count INTEGER DEFAULT 0,
    cleaned_count INTEGER DEFAULT 0,
    enriched_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    source_breakdown JSONB,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'ingestion_monitor',
    PRIMARY KEY (source_type, time_bucket)
);

CREATE INDEX IF NOT EXISTS idx_ingestion_type ON ingestion_counts(source_type);
CREATE INDEX IF NOT EXISTS idx_ingestion_time ON ingestion_counts(time_bucket);
"""

SENTIMENT_BATCH_STATUS_TABLE = """
CREATE TABLE IF NOT EXISTS sentiment_batch_status (
    batch_id VARCHAR(100) PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    records_total INTEGER DEFAULT 0,
    records_processed INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    processing_time_seconds FLOAT,
    error_message TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'sentiment_processor'
);

CREATE INDEX IF NOT EXISTS idx_batch_status ON sentiment_batch_status(status);
CREATE INDEX IF NOT EXISTS idx_batch_started ON sentiment_batch_status(started_at);
"""

DATA_QUALITY_METRICS_TABLE = """
CREATE TABLE IF NOT EXISTS data_quality_metrics (
    source_name VARCHAR(100) NOT NULL,
    metric_type VARCHAR(50) NOT NULL,
    score FLOAT NOT NULL,
    samples_evaluated INTEGER DEFAULT 0,
    threshold FLOAT DEFAULT 0,
    is_passing BOOLEAN DEFAULT true,
    details TEXT,
    measured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'data_quality_monitor',
    PRIMARY KEY (source_name, metric_type)
);

CREATE INDEX IF NOT EXISTS idx_quality_source ON data_quality_metrics(source_name);
CREATE INDEX IF NOT EXISTS idx_quality_passing ON data_quality_metrics(is_passing);
"""

ONCHAIN_EVENT_COUNTS_TABLE = """
CREATE TABLE IF NOT EXISTS onchain_event_counts (
    chain VARCHAR(50) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    time_bucket TIMESTAMP NOT NULL,
    event_count INTEGER DEFAULT 0,
    total_value_usd FLOAT DEFAULT 0,
    unique_addresses INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'onchain_monitor',
    PRIMARY KEY (chain, event_type, time_bucket)
);

CREATE INDEX IF NOT EXISTS idx_onchain_chain ON onchain_event_counts(chain);
CREATE INDEX IF NOT EXISTS idx_onchain_time ON onchain_event_counts(time_bucket);
"""

SMART_MONEY_EVENT_COUNTS_TABLE = """
CREATE TABLE IF NOT EXISTS smart_money_event_counts (
    entity_type VARCHAR(50) NOT NULL,
    time_bucket TIMESTAMP NOT NULL,
    event_count INTEGER DEFAULT 0,
    buy_count INTEGER DEFAULT 0,
    sell_count INTEGER DEFAULT 0,
    total_volume_usd FLOAT DEFAULT 0,
    unique_wallets INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'smart_money_tracker',
    PRIMARY KEY (entity_type, time_bucket)
);

CREATE INDEX IF NOT EXISTS idx_smart_money_entity ON smart_money_event_counts(entity_type);
CREATE INDEX IF NOT EXISTS idx_smart_money_time ON smart_money_event_counts(time_bucket);
"""

ALL_PIPELINE_TABLES = [
    PIPELINE_METRICS_TABLE,
    INGESTION_COUNTS_TABLE,
    SENTIMENT_BATCH_STATUS_TABLE,
    DATA_QUALITY_METRICS_TABLE,
    ONCHAIN_EVENT_COUNTS_TABLE,
    SMART_MONEY_EVENT_COUNTS_TABLE,
]
