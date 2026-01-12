"""
Raw Data Domain ORM Models.

============================================================
PURPOSE
============================================================
Models for storing raw, immutable data from external sources.
This is the Data Ingestion Layer's persistence target.

============================================================
DATA LIFECYCLE ROLE
============================================================
- Stage: RAW
- Mutability: IMMUTABLE (append-only)
- Source: External APIs, WebSockets, blockchain explorers
- Consumers: Processing layer, audit, replay

============================================================
MODELS
============================================================
- RawNewsData: Raw news articles from news APIs
- RawMarketData: Raw market data from exchanges/aggregators
- RawOnChainData: Raw blockchain data from on-chain sources

============================================================
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from storage.models.base import Base


class RawNewsData(Base):
    """
    Raw news data from crypto news API providers.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores unmodified news articles exactly as received from
    external news APIs. This data is immutable and serves as
    the source of truth for all derived news processing.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: RAW
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: CryptoNewsAPI, other news providers
    
    ============================================================
    TRACEABILITY
    ============================================================
    - source: Identifies the API provider
    - version: API version used for collection
    - processing_stage: Always "raw" for this table
    - confidence_score: Always 1.0 for raw data
    
    ============================================================
    """
    
    __tablename__ = "raw_news_data"
    
    # Primary Key
    raw_news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for raw news record"
    )
    
    # Source Identification
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="News API provider name"
    )
    
    source_article_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Original article ID from source"
    )
    
    # Timestamps
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When data was collected by our system"
    )
    
    source_published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Original publication timestamp from source"
    )
    
    # Raw Payload
    raw_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Complete unmodified API response"
    )
    
    # Data Quality
    payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of raw_payload for deduplication"
    )
    
    # Versioning & Traceability
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="API version used for collection"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="raw",
        comment="Processing stage - always 'raw' for this table"
    )
    
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        default=Decimal("1.0"),
        comment="Data confidence - always 1.0 for raw data"
    )
    
    # Collection Metadata
    collection_batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Batch identifier for grouped collections"
    )
    
    collector_instance: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Collector instance that fetched this data"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_raw_news_collected_at", "collected_at"),
        Index("idx_raw_news_source", "source"),
        Index("idx_raw_news_source_published", "source_published_at"),
        Index("idx_raw_news_payload_hash", "payload_hash"),
        Index("idx_raw_news_source_article", "source", "source_article_id"),
    )


class RawMarketData(Base):
    """
    Raw market data from exchanges and aggregators.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores unmodified market data (prices, volumes, order book
    snapshots) exactly as received. This includes data from
    CoinGecko, exchange WebSockets, and other market sources.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: RAW
    - Mutability: IMMUTABLE
    - Retention: 1 year (high volume)
    - Source: CoinGecko, Exchange WebSockets
    
    ============================================================
    TRACEABILITY
    ============================================================
    - source: Exchange or aggregator name
    - version: API/WebSocket protocol version
    - processing_stage: Always "raw" for this table
    - confidence_score: Always 1.0 for raw data
    
    ============================================================
    """
    
    __tablename__ = "raw_market_data"
    
    # Primary Key
    raw_market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for raw market record"
    )
    
    # Source Identification
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Data source (exchange, aggregator)"
    )
    
    symbol: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Trading pair symbol as received"
    )
    
    data_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Type: ticker, trade, orderbook, ohlcv"
    )
    
    # Timestamps
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When data was collected by our system"
    )
    
    source_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Original timestamp from source"
    )
    
    # Raw Payload
    raw_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Complete unmodified data payload"
    )
    
    # Data Quality
    payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash for deduplication"
    )
    
    sequence_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Sequence number for WebSocket ordering"
    )
    
    # Versioning & Traceability
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="API/protocol version"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="raw",
        comment="Processing stage - always 'raw'"
    )
    
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        default=Decimal("1.0"),
        comment="Data confidence - always 1.0 for raw"
    )
    
    # Collection Metadata
    collection_batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Batch identifier for grouped collections"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_raw_market_collected_at", "collected_at"),
        Index("idx_raw_market_source_symbol", "source", "symbol"),
        Index("idx_raw_market_symbol_time", "symbol", "collected_at"),
        Index("idx_raw_market_data_type", "data_type"),
        Index("idx_raw_market_payload_hash", "payload_hash"),
    )


class RawOnChainData(Base):
    """
    Raw on-chain data from blockchain sources.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores unmodified blockchain data including transactions,
    whale movements, and smart contract events from free
    on-chain data sources.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: RAW
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: Blockchain explorers, free on-chain APIs
    
    ============================================================
    TRACEABILITY
    ============================================================
    - source: Blockchain data provider
    - version: API version
    - processing_stage: Always "raw" for this table
    - confidence_score: Always 1.0 for raw data
    
    ============================================================
    """
    
    __tablename__ = "raw_onchain_data"
    
    # Primary Key
    raw_onchain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for raw on-chain record"
    )
    
    # Source Identification
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="On-chain data provider"
    )
    
    chain: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Blockchain network name"
    )
    
    data_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type: transaction, whale_movement, contract_event"
    )
    
    # Timestamps
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When data was collected"
    )
    
    block_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Blockchain block timestamp"
    )
    
    # Block Reference
    block_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Block number"
    )
    
    tx_hash: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Transaction hash if applicable"
    )
    
    # Raw Payload
    raw_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Complete unmodified payload"
    )
    
    # Data Quality
    payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash for deduplication"
    )
    
    # Versioning & Traceability
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="API version"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="raw",
        comment="Processing stage - always 'raw'"
    )
    
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        default=Decimal("1.0"),
        comment="Data confidence - always 1.0 for raw"
    )
    
    # Collection Metadata
    collection_batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Batch identifier"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_raw_onchain_collected_at", "collected_at"),
        Index("idx_raw_onchain_chain", "chain"),
        Index("idx_raw_onchain_chain_type", "chain", "data_type"),
        Index("idx_raw_onchain_block", "chain", "block_number"),
        Index("idx_raw_onchain_tx_hash", "tx_hash"),
        Index("idx_raw_onchain_payload_hash", "payload_hash"),
    )
