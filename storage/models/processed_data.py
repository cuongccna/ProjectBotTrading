"""
Processed Data Domain ORM Models.

============================================================
PURPOSE
============================================================
Models for storing processed, normalized, and labeled data.
This is the output of the Data Processing Layer.

============================================================
DATA LIFECYCLE ROLE
============================================================
- Stage: PROCESSED
- Mutability: IMMUTABLE (versioned)
- Source: Raw data tables
- Consumers: Scoring engine, decision engine

============================================================
MODELS
============================================================
- ProcessedNewsData: Normalized news with extracted metadata
- CleanedTextData: Cleaned and preprocessed text content
- TopicClassification: Topic labels assigned to content
- RiskKeywordDetection: Risk keywords detected in content

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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.models.base import Base


class ProcessedNewsData(Base):
    """
    Processed and normalized news data.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores news data after normalization, field extraction,
    and standardization. Links back to raw data for traceability.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: PROCESSED (normalized)
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: raw_news_data
    
    ============================================================
    TRACEABILITY
    ============================================================
    - raw_news_id: FK to source raw data
    - source: Original data source
    - version: Processing pipeline version
    - processing_stage: "normalized"
    - confidence_score: Inherited or adjusted
    
    ============================================================
    """
    
    __tablename__ = "processed_news_data"
    
    # Primary Key
    processed_news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for processed news"
    )
    
    # Foreign Key to Raw Data
    raw_news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_news_data.raw_news_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Reference to source raw news data"
    )
    
    # Source Tracking
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Original news source"
    )
    
    original_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Original article ID from source"
    )
    
    # Extracted Fields
    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Extracted article title"
    )
    
    content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Extracted article content"
    )
    
    summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Article summary if available"
    )
    
    url: Mapped[Optional[str]] = mapped_column(
        String(2000),
        nullable=True,
        comment="Original article URL"
    )
    
    author: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Article author"
    )
    
    # Timestamps
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Article publication time"
    )
    
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When raw data was collected"
    )
    
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When processing completed"
    )
    
    # Extracted Metadata
    assets_mentioned: Mapped[Optional[list]] = mapped_column(
        ARRAY(String(20)),
        nullable=True,
        comment="Crypto assets mentioned in article"
    )
    
    language_detected: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="Detected language code"
    )
    
    word_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Word count after extraction"
    )
    
    # Deduplication
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Hash of normalized content"
    )
    
    is_duplicate: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether this is a duplicate"
    )
    
    duplicate_of_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID of original if duplicate"
    )
    
    # Versioning & Traceability
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Processing pipeline version"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="normalized",
        comment="Processing stage"
    )
    
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Processing confidence score"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_proc_news_raw_id", "raw_news_id"),
        Index("idx_proc_news_published_at", "published_at"),
        Index("idx_proc_news_source", "source"),
        Index("idx_proc_news_content_hash", "content_hash"),
        Index("idx_proc_news_assets", "assets_mentioned", postgresql_using="gin"),
        Index("idx_proc_news_not_duplicate", "is_duplicate"),
    )


class CleanedTextData(Base):
    """
    Cleaned and preprocessed text content.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores text after cleaning operations including HTML removal,
    unicode normalization, URL extraction, and whitespace cleanup.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: PROCESSED (cleaned)
    - Mutability: IMMUTABLE
    - Retention: 1 year
    - Source: processed_news_data
    
    ============================================================
    TRACEABILITY
    ============================================================
    - processed_news_id: FK to processed news
    - version: Cleaning pipeline version
    - processing_stage: "cleaned"
    
    ============================================================
    """
    
    __tablename__ = "cleaned_text_data"
    
    # Primary Key
    cleaned_text_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for cleaned text"
    )
    
    # Foreign Key
    processed_news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processed_news_data.processed_news_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to processed news"
    )
    
    # Cleaned Content
    original_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Original text before cleaning"
    )
    
    cleaned_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Text after cleaning operations"
    )
    
    # Extracted During Cleaning
    extracted_urls: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="URLs extracted from text"
    )
    
    # Cleaning Metadata
    cleaning_operations: Mapped[list] = mapped_column(
        ARRAY(String(50)),
        nullable=False,
        comment="List of cleaning operations applied"
    )
    
    characters_removed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of characters removed"
    )
    
    # Timestamps
    cleaned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When cleaning was performed"
    )
    
    # Versioning & Traceability
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Cleaning pipeline version"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="cleaned",
        comment="Processing stage"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_cleaned_text_proc_news", "processed_news_id"),
        Index("idx_cleaned_text_cleaned_at", "cleaned_at"),
    )


class TopicClassification(Base):
    """
    Topic labels assigned to news content.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores topic classification results for news articles.
    Each article can have multiple topic labels with confidence.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: PROCESSED (labeled)
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: processed_news_data
    
    ============================================================
    TRACEABILITY
    ============================================================
    - processed_news_id: FK to processed news
    - version: Classifier model version
    - confidence_score: Classification confidence
    
    ============================================================
    """
    
    __tablename__ = "topic_classifications"
    
    # Primary Key
    classification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for classification"
    )
    
    # Foreign Key
    processed_news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processed_news_data.processed_news_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to processed news"
    )
    
    # Classification Results
    topic: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Topic label"
    )
    
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Classification confidence 0-1"
    )
    
    is_primary_topic: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether this is the primary topic"
    )
    
    # Classification Metadata
    classification_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Method: rule_based, ml_model, hybrid"
    )
    
    model_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="ML model name if applicable"
    )
    
    # Timestamps
    classified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When classification was performed"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Classifier version"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="labeled",
        comment="Processing stage"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_topic_class_proc_news", "processed_news_id"),
        Index("idx_topic_class_topic", "topic"),
        Index("idx_topic_class_primary", "processed_news_id", "is_primary_topic"),
        Index("idx_topic_class_confidence", "confidence_score"),
    )


class RiskKeywordDetection(Base):
    """
    Risk keywords detected in content.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores detected risk keywords and phrases found in news
    content. Each detection includes category and severity.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: PROCESSED (labeled)
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: processed_news_data
    
    ============================================================
    TRACEABILITY
    ============================================================
    - processed_news_id: FK to processed news
    - version: Detector version
    - confidence_score: Detection confidence
    
    ============================================================
    """
    
    __tablename__ = "risk_keyword_detections"
    
    # Primary Key
    detection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for detection"
    )
    
    # Foreign Key
    processed_news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processed_news_data.processed_news_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to processed news"
    )
    
    # Detection Results
    keyword: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Detected keyword or phrase"
    )
    
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Risk category"
    )
    
    severity: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Severity score 0-1"
    )
    
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Detection confidence 0-1"
    )
    
    # Context
    context_snippet: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Surrounding text context"
    )
    
    position_in_text: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Character position in text"
    )
    
    # Detection Metadata
    detection_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Method: exact_match, pattern, ml"
    )
    
    # Timestamps
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When detection was performed"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Detector version"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="labeled",
        comment="Processing stage"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_risk_kw_proc_news", "processed_news_id"),
        Index("idx_risk_kw_category", "category"),
        Index("idx_risk_kw_severity", "severity"),
        Index("idx_risk_kw_keyword", "keyword"),
    )


# ============================================================
# FEATURE VECTOR TABLES
# ============================================================


class NewsFeatureVector(Base):
    """Feature vectors extracted from labeled news data."""
    
    __tablename__ = "news_feature_vectors"
    
    feature_vector_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for news feature vector",
    )
    
    processed_news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processed_news_data.processed_news_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to processed news record",
    )
    
    raw_news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_news_data.raw_news_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to raw news record",
    )
    
    feature_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Feature extraction pipeline version",
    )
    
    feature_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Deterministic hash of feature payload",
    )
    
    features: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Extracted deterministic feature payload",
    )
    
    quality_flag: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="high_quality",
        comment="Data quality flag",
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="feature_ready",
        comment="Processing stage for feature vector",
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Feature extraction timestamp",
    )
    
    __table_args__ = (
        Index("idx_news_features_processed", "processed_news_id"),
        Index("idx_news_features_hash", "feature_hash"),
    )


class MarketFeatureVector(Base):
    """Feature vectors extracted from labeled market data."""
    
    __tablename__ = "market_feature_vectors"
    
    feature_vector_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for market feature vector",
    )
    
    raw_market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_market_data.raw_market_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to raw market data",
    )
    
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Data source name",
    )
    
    symbol_normalized: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Normalized trading symbol",
    )
    
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Collection timestamp in UTC",
    )
    
    feature_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Feature extraction pipeline version",
    )
    
    feature_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Deterministic hash of feature payload",
    )
    
    features: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Extracted deterministic feature payload",
    )
    
    quality_flag: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="high_quality",
        comment="Data quality flag",
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="feature_ready",
        comment="Processing stage for feature vector",
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Feature extraction timestamp",
    )
    
    __table_args__ = (
        Index("idx_market_features_raw", "raw_market_id"),
        Index("idx_market_features_symbol", "symbol_normalized"),
    )


class OnChainFeatureVector(Base):
    """Feature vectors extracted from labeled on-chain data."""
    
    __tablename__ = "onchain_feature_vectors"
    
    feature_vector_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for on-chain feature vector",
    )
    
    raw_onchain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_onchain_data.raw_onchain_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to raw on-chain data",
    )
    
    chain_normalized: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Normalized blockchain identifier",
    )
    
    data_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Data classification (transaction, whale_movement, etc.)",
    )
    
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Collection timestamp in UTC",
    )
    
    feature_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Feature extraction pipeline version",
    )
    
    feature_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Deterministic hash of feature payload",
    )
    
    features: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Extracted deterministic feature payload",
    )
    
    quality_flag: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="high_quality",
        comment="Data quality flag",
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="feature_ready",
        comment="Processing stage for feature vector",
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Feature extraction timestamp",
    )
    
    __table_args__ = (
        Index("idx_onchain_features_raw", "raw_onchain_id"),
        Index("idx_onchain_features_chain", "chain_normalized"),
    )
