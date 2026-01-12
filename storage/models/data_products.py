"""
Data Products Domain ORM Models.

============================================================
PURPOSE
============================================================
Models for data product management: definitions, schemas,
aggregations, anonymization, exports, and quality metrics.

============================================================
DATA LIFECYCLE ROLE
============================================================
- Stage: DERIVED (products)
- Mutability: IMMUTABLE
- Source: Processed data, aggregation jobs
- Consumers: External systems, research, compliance

============================================================
MODELS
============================================================
- DataProductDefinition: Product definitions
- SchemaVersion: Schema versioning
- AggregatedSentimentData: Aggregated sentiment
- AggregatedFlowData: Aggregated flow metrics
- AggregatedMarketData: Aggregated market data
- AnonymizationRun: Anonymization job runs
- AnonymizedDataBatch: Anonymized data batches
- ExportConfiguration: Export configurations
- ExportRun: Export job runs
- ExportDeliveryLog: Export delivery logs
- AccessLog: Data access audit logs
- Subscription: Data subscriptions
- QualityMetric: Data quality metrics

============================================================
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.models.base import Base


class DataProductDefinition(Base):
    """
    Data product definitions.
    
    ============================================================
    PURPOSE
    ============================================================
    Defines available data products with their specifications,
    schemas, and access requirements.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: CONFIGURATION
    - Mutability: VERSIONED
    - Retention: Permanent
    - Source: Product management
    
    ============================================================
    TRACEABILITY
    ============================================================
    - product_id: Unique product identifier
    - version: Product version
    - schema_version_id: FK to schema
    
    ============================================================
    """
    
    __tablename__ = "data_product_definitions"
    
    # Primary Key
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for product"
    )
    
    # Product Identification
    product_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="Product name"
    )
    
    product_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="Product code for API"
    )
    
    # Description
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Product description"
    )
    
    # Category
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Product category"
    )
    
    subcategory: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Product subcategory"
    )
    
    # Data Specification
    source_tables: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        comment="Source tables for product"
    )
    
    aggregation_rules: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Aggregation rules"
    )
    
    refresh_frequency: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Refresh frequency: real-time, hourly, daily"
    )
    
    latency_sla_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Latency SLA in seconds"
    )
    
    # Schema
    current_schema_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Current schema version"
    )
    
    schema_definition: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Schema definition (JSON Schema)"
    )
    
    # Access Control
    access_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Access level: public, internal, restricted"
    )
    
    requires_anonymization: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether anonymization required"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        comment="Status: draft, active, deprecated, retired"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When product was created"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When product was last updated"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Product definition version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_dp_def_name", "product_name"),
        Index("idx_dp_def_code", "product_code"),
        Index("idx_dp_def_category", "category"),
        Index("idx_dp_def_status", "status"),
    )


class SchemaVersion(Base):
    """
    Schema version records.
    
    ============================================================
    PURPOSE
    ============================================================
    Tracks schema versions for data products to support
    backward compatibility and migration.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: CONFIGURATION
    - Mutability: IMMUTABLE
    - Retention: Permanent
    - Source: Schema management
    
    ============================================================
    TRACEABILITY
    ============================================================
    - product_id: FK to product
    - Full schema history
    
    ============================================================
    """
    
    __tablename__ = "schema_versions"
    
    # Primary Key
    schema_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for schema version"
    )
    
    # Foreign Key
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_product_definitions.product_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to product"
    )
    
    # Version Details
    version_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Version number (semver)"
    )
    
    version_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Version type: major, minor, patch"
    )
    
    # Schema
    schema_definition: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Schema definition"
    )
    
    # Migration
    migration_script: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Migration script from previous"
    )
    
    breaking_changes: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether has breaking changes"
    )
    
    # Changelog
    changelog: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Version changelog"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="Status: active, deprecated, retired"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When version was created"
    )
    
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When version was deprecated"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_schema_product", "product_id"),
        Index("idx_schema_version", "version_number"),
        Index("idx_schema_status", "status"),
    )


class AggregatedSentimentData(Base):
    """
    Aggregated sentiment data.
    
    ============================================================
    PURPOSE
    ============================================================
    Pre-aggregated sentiment data for efficient consumption
    by downstream systems and analytics.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (aggregated)
    - Mutability: IMMUTABLE
    - Retention: 1 year
    - Source: Aggregation job
    
    ============================================================
    TRACEABILITY
    ============================================================
    - aggregation_period: Time period
    - source_count: Number of sources
    
    ============================================================
    """
    
    __tablename__ = "aggregated_sentiment_data"
    
    # Primary Key
    aggregation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for aggregation"
    )
    
    # Scope
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Trading symbol"
    )
    
    exchange: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Exchange (null for cross-exchange)"
    )
    
    # Aggregation Period
    period_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Period type: 5min, hourly, daily"
    )
    
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Period start"
    )
    
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Period end"
    )
    
    # Aggregated Metrics
    avg_sentiment: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Average sentiment"
    )
    
    min_sentiment: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Minimum sentiment"
    )
    
    max_sentiment: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Maximum sentiment"
    )
    
    std_sentiment: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Sentiment standard deviation"
    )
    
    bullish_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Bullish signal count"
    )
    
    bearish_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Bearish signal count"
    )
    
    neutral_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Neutral signal count"
    )
    
    # Source Statistics
    source_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of sources"
    )
    
    article_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of articles"
    )
    
    # Quality
    confidence_avg: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Average confidence"
    )
    
    # Timestamps
    aggregated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When aggregation was performed"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Aggregation version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_agg_sent_symbol", "symbol"),
        Index("idx_agg_sent_period", "period_type", "period_start"),
        Index("idx_agg_sent_aggregated_at", "aggregated_at"),
    )


class AggregatedFlowData(Base):
    """
    Aggregated flow data.
    
    ============================================================
    PURPOSE
    ============================================================
    Pre-aggregated money flow data for efficient consumption.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (aggregated)
    - Mutability: IMMUTABLE
    - Retention: 1 year
    - Source: Aggregation job
    
    ============================================================
    """
    
    __tablename__ = "aggregated_flow_data"
    
    # Primary Key
    aggregation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for aggregation"
    )
    
    # Scope
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Trading symbol"
    )
    
    exchange: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Exchange"
    )
    
    # Aggregation Period
    period_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Period type"
    )
    
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Period start"
    )
    
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Period end"
    )
    
    # Flow Metrics
    net_flow: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Net flow (inflow - outflow)"
    )
    
    total_inflow: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Total inflow"
    )
    
    total_outflow: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Total outflow"
    )
    
    avg_flow_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Average flow score"
    )
    
    # Whale Activity
    whale_transaction_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Large transaction count"
    )
    
    whale_volume: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Whale transaction volume"
    )
    
    # Quality
    data_completeness: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Data completeness score"
    )
    
    # Timestamps
    aggregated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When aggregation was performed"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Aggregation version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_agg_flow_symbol", "symbol", "exchange"),
        Index("idx_agg_flow_period", "period_type", "period_start"),
        Index("idx_agg_flow_aggregated_at", "aggregated_at"),
    )


class AggregatedMarketData(Base):
    """
    Aggregated market data.
    
    ============================================================
    PURPOSE
    ============================================================
    Pre-aggregated market data (OHLCV + metrics) for analytics.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (aggregated)
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: Aggregation job
    
    ============================================================
    """
    
    __tablename__ = "aggregated_market_data"
    
    # Primary Key
    aggregation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for aggregation"
    )
    
    # Scope
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Trading symbol"
    )
    
    exchange: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Exchange"
    )
    
    # Aggregation Period
    period_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Period type"
    )
    
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Period start"
    )
    
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Period end"
    )
    
    # OHLCV
    open_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Open price"
    )
    
    high_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="High price"
    )
    
    low_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Low price"
    )
    
    close_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Close price"
    )
    
    volume: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Volume"
    )
    
    quote_volume: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Quote volume"
    )
    
    # Derived Metrics
    vwap: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Volume weighted average price"
    )
    
    trade_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of trades"
    )
    
    volatility: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        comment="Price volatility"
    )
    
    # Quality
    data_completeness: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Data completeness score"
    )
    
    # Timestamps
    aggregated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When aggregation was performed"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Aggregation version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_agg_market_symbol", "symbol", "exchange"),
        Index("idx_agg_market_period", "period_type", "period_start"),
        Index("idx_agg_market_aggregated_at", "aggregated_at"),
    )


class AnonymizationRun(Base):
    """
    Anonymization job runs.
    
    ============================================================
    PURPOSE
    ============================================================
    Tracks anonymization job runs for data privacy compliance.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: APPEND-ONLY
    - Retention: 5 years (compliance)
    - Source: Anonymization service
    
    ============================================================
    """
    
    __tablename__ = "anonymization_runs"
    
    # Primary Key
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for run"
    )
    
    # Product Reference
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_product_definitions.product_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Reference to product"
    )
    
    # Run Details
    run_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Run type: scheduled, manual, triggered"
    )
    
    # Scope
    source_table: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Source table"
    )
    
    record_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of records processed"
    )
    
    # Anonymization Config
    anonymization_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Anonymization configuration"
    )
    
    techniques_applied: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        comment="Techniques applied"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="running",
        comment="Status: running, completed, failed"
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if failed"
    )
    
    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Run start time"
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Run completion time"
    )
    
    duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Run duration in seconds"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Anonymization version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_anon_run_product", "product_id"),
        Index("idx_anon_run_status", "status"),
        Index("idx_anon_run_started_at", "started_at"),
    )


class AnonymizedDataBatch(Base):
    """
    Anonymized data batches.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores metadata for anonymized data batches produced
    by anonymization runs.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (anonymized)
    - Mutability: IMMUTABLE
    - Retention: Per product policy
    - Source: Anonymization service
    
    ============================================================
    """
    
    __tablename__ = "anonymized_data_batches"
    
    # Primary Key
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for batch"
    )
    
    # Foreign Key
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("anonymization_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to run"
    )
    
    # Batch Details
    batch_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Batch sequence number"
    )
    
    record_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Records in batch"
    )
    
    # Storage Location
    storage_location: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Storage location"
    )
    
    file_format: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="File format"
    )
    
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="File size in bytes"
    )
    
    # Data Range
    data_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Data range start"
    )
    
    data_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Data range end"
    )
    
    # Checksums
    checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="File checksum"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When batch was created"
    )
    
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When batch expires"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_anon_batch_run", "run_id"),
        Index("idx_anon_batch_created_at", "created_at"),
    )


class ExportConfiguration(Base):
    """
    Export configurations.
    
    ============================================================
    PURPOSE
    ============================================================
    Defines export configurations for data products including
    format, destination, and scheduling.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: CONFIGURATION
    - Mutability: VERSIONED
    - Retention: Permanent
    - Source: Export management
    
    ============================================================
    """
    
    __tablename__ = "export_configurations"
    
    # Primary Key
    config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for config"
    )
    
    # Foreign Key
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_product_definitions.product_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to product"
    )
    
    # Configuration Name
    config_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Configuration name"
    )
    
    # Export Format
    export_format: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Format: json, csv, parquet, avro"
    )
    
    compression: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Compression: gzip, snappy, none"
    )
    
    # Destination
    destination_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Destination type: s3, gcs, sftp, api"
    )
    
    destination_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Destination configuration"
    )
    
    # Scheduling
    schedule_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Schedule type: manual, cron, event"
    )
    
    schedule_config: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Schedule configuration"
    )
    
    # Filters
    filter_config: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Data filters"
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        comment="Whether config is active"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When config was created"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When config was last updated"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Config version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_export_config_product", "product_id"),
        Index("idx_export_config_active", "is_active"),
    )


class ExportRun(Base):
    """
    Export job runs.
    
    ============================================================
    PURPOSE
    ============================================================
    Tracks export job executions with status and metrics.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: APPEND-ONLY
    - Retention: 90 days
    - Source: Export service
    
    ============================================================
    """
    
    __tablename__ = "export_runs"
    
    # Primary Key
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for run"
    )
    
    # Foreign Key
    config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("export_configurations.config_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Reference to config"
    )
    
    # Run Details
    trigger_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Trigger: scheduled, manual, event"
    )
    
    # Data Range
    data_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Data range start"
    )
    
    data_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Data range end"
    )
    
    # Metrics
    record_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Records exported"
    )
    
    file_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Files created"
    )
    
    total_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Total size in bytes"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="running",
        comment="Status: running, completed, failed"
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if failed"
    )
    
    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Run start time"
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Run completion time"
    )
    
    duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Run duration in seconds"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Export service version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_export_run_config", "config_id"),
        Index("idx_export_run_status", "status"),
        Index("idx_export_run_started_at", "started_at"),
    )


class ExportDeliveryLog(Base):
    """
    Export delivery logs.
    
    ============================================================
    PURPOSE
    ============================================================
    Logs delivery of exported data to destinations.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: IMMUTABLE
    - Retention: 90 days
    - Source: Export service
    
    ============================================================
    """
    
    __tablename__ = "export_delivery_log"
    
    # Primary Key
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for delivery"
    )
    
    # Foreign Key
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("export_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to run"
    )
    
    # File Details
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="File name"
    )
    
    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Full file path"
    )
    
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="File size"
    )
    
    # Delivery Details
    destination: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Destination"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Status: delivered, failed"
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error if failed"
    )
    
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Retry attempts"
    )
    
    # Timestamps
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Delivery time"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_del_log_run", "run_id"),
        Index("idx_del_log_status", "status"),
        Index("idx_del_log_delivered_at", "delivered_at"),
    )


class AccessLog(Base):
    """
    Data access audit logs.
    
    ============================================================
    PURPOSE
    ============================================================
    Audit trail for all data product accesses for compliance
    and usage tracking.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: AUDIT
    - Mutability: IMMUTABLE
    - Retention: 7 years (regulatory)
    - Source: Access control system
    
    ============================================================
    """
    
    __tablename__ = "access_log"
    
    # Primary Key
    access_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for access"
    )
    
    # Product Reference
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_product_definitions.product_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Reference to product"
    )
    
    # Accessor Details
    accessor_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Accessor identifier"
    )
    
    accessor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Accessor type: user, service, api_key"
    )
    
    # Access Details
    access_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Access type: read, export, stream"
    )
    
    access_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Access method: api, direct, export"
    )
    
    # Request Details
    request_parameters: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Request parameters"
    )
    
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Client IP address"
    )
    
    # Response Metrics
    record_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Records accessed"
    )
    
    response_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Response size"
    )
    
    response_time_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Response time in ms"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Status: success, denied, error"
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if failed"
    )
    
    # Timestamps
    accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Access time"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_access_log_product", "product_id"),
        Index("idx_access_log_accessor", "accessor_id"),
        Index("idx_access_log_type", "access_type"),
        Index("idx_access_log_accessed_at", "accessed_at"),
        Index("idx_access_log_status", "status"),
    )


class Subscription(Base):
    """
    Data product subscriptions.
    
    ============================================================
    PURPOSE
    ============================================================
    Manages subscriptions to data products for automated
    delivery and access control.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: CONFIGURATION
    - Mutability: UPDATABLE
    - Retention: Active + 1 year
    - Source: Subscription management
    
    ============================================================
    """
    
    __tablename__ = "subscriptions"
    
    # Primary Key
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for subscription"
    )
    
    # Product Reference
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_product_definitions.product_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Reference to product"
    )
    
    # Subscriber Details
    subscriber_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Subscriber identifier"
    )
    
    subscriber_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Subscriber name"
    )
    
    # Subscription Details
    subscription_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type: streaming, batch, on_demand"
    )
    
    delivery_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Delivery configuration"
    )
    
    # Access Level
    access_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Access level granted"
    )
    
    # Validity
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Subscription start"
    )
    
    valid_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Subscription end"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="Status: active, suspended, cancelled, expired"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When subscription was created"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When subscription was last updated"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Subscription version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_sub_product", "product_id"),
        Index("idx_sub_subscriber", "subscriber_id"),
        Index("idx_sub_status", "status"),
        Index("idx_sub_valid", "valid_from", "valid_until"),
    )


class QualityMetric(Base):
    """
    Data quality metrics.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores data quality metrics for monitoring product health.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: IMMUTABLE
    - Retention: 1 year
    - Source: Quality monitoring
    
    ============================================================
    """
    
    __tablename__ = "quality_metrics"
    
    # Primary Key
    metric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for metric"
    )
    
    # Product Reference
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_product_definitions.product_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to product"
    )
    
    # Metric Details
    metric_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Metric name"
    )
    
    metric_category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Category: completeness, accuracy, timeliness, consistency"
    )
    
    metric_value: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        comment="Metric value"
    )
    
    threshold_value: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        comment="Threshold for alerting"
    )
    
    is_passing: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Whether metric passes threshold"
    )
    
    # Measurement Details
    measurement_period: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Measurement period: hourly, daily"
    )
    
    sample_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Sample size for measurement"
    )
    
    # Context
    measurement_details: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Measurement details"
    )
    
    # Timestamps
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When metric was measured"
    )
    
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Measurement period start"
    )
    
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Measurement period end"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Measurement version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_quality_product", "product_id"),
        Index("idx_quality_metric", "metric_name"),
        Index("idx_quality_category", "metric_category"),
        Index("idx_quality_passing", "is_passing"),
        Index("idx_quality_measured_at", "measured_at"),
    )
