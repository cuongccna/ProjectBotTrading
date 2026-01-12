"""
Scoring Domain ORM Models.

============================================================
PURPOSE
============================================================
Models for storing all scoring outputs: sentiment analysis,
confidence calibrations, and composite risk/flow/sentiment scores.

============================================================
DATA LIFECYCLE ROLE
============================================================
- Stage: DERIVED
- Mutability: IMMUTABLE (append-only versioned)
- Source: Processed data tables
- Consumers: Decision engine, risk management

============================================================
MODELS
============================================================
- SentimentAnalysisResult: Sentiment scores from analysis
- ConfidenceCalibration: Calibration records for confidence
- RiskScore: Individual risk dimension scores
- FlowScore: Money flow indicator scores
- SentimentScore: Market sentiment scores
- CompositeScore: Combined weighted scores

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


class SentimentAnalysisResult(Base):
    """
    Sentiment analysis results for news content.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores sentiment analysis output including polarity,
    subjectivity, and model-specific scores.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (scored)
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: processed_news_data
    
    ============================================================
    TRACEABILITY
    ============================================================
    - processed_news_id: FK to processed news
    - model_name: Model used for analysis
    - version: Model version
    - confidence_score: Analysis confidence
    
    ============================================================
    """
    
    __tablename__ = "sentiment_analysis_results"
    
    # Primary Key
    sentiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for sentiment result"
    )
    
    # Foreign Key
    processed_news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processed_news_data.processed_news_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to processed news"
    )
    
    # Sentiment Scores
    polarity: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Sentiment polarity -1 to 1"
    )
    
    subjectivity: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Subjectivity score 0-1"
    )
    
    positive_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Positive sentiment probability"
    )
    
    negative_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Negative sentiment probability"
    )
    
    neutral_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Neutral sentiment probability"
    )
    
    sentiment_label: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Final label: positive, negative, neutral"
    )
    
    # Model Metadata
    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Model used for analysis"
    )
    
    model_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Model version"
    )
    
    # Confidence
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Analysis confidence"
    )
    
    # Raw Output
    raw_output: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Raw model output"
    )
    
    # Timestamps
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When analysis was performed"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Pipeline version"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="scored",
        comment="Processing stage"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_sent_proc_news", "processed_news_id"),
        Index("idx_sent_label", "sentiment_label"),
        Index("idx_sent_polarity", "polarity"),
        Index("idx_sent_analyzed_at", "analyzed_at"),
        Index("idx_sent_model", "model_name"),
    )


class ConfidenceCalibration(Base):
    """
    Confidence calibration records.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores calibration data for confidence score adjustments
    across different models and data sources.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (calibrated)
    - Mutability: IMMUTABLE
    - Retention: 5 years (audit)
    - Source: System calibration process
    
    ============================================================
    TRACEABILITY
    ============================================================
    - model_name: Model being calibrated
    - version: Calibration version
    
    ============================================================
    """
    
    __tablename__ = "confidence_calibrations"
    
    # Primary Key
    calibration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for calibration"
    )
    
    # Calibration Target
    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Model being calibrated"
    )
    
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Data source type"
    )
    
    # Calibration Parameters
    calibration_curve: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Calibration curve parameters"
    )
    
    adjustment_factor: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        comment="Global adjustment factor"
    )
    
    # Validation Metrics
    brier_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        comment="Brier score before calibration"
    )
    
    brier_score_calibrated: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        comment="Brier score after calibration"
    )
    
    sample_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of samples used"
    )
    
    # Validity Period
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Calibration validity start"
    )
    
    valid_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Calibration validity end"
    )
    
    # Timestamps
    calibrated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When calibration was performed"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Calibration version"
    )
    
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        comment="Whether calibration is active"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_conf_cal_model", "model_name"),
        Index("idx_conf_cal_source", "source_type"),
        Index("idx_conf_cal_valid", "valid_from", "valid_until"),
        Index("idx_conf_cal_active", "model_name", "is_active"),
    )


class RiskScore(Base):
    """
    Individual risk dimension scores.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores calculated risk scores for specific dimensions
    (market risk, liquidity risk, etc.) at point in time.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (scored)
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: Multiple processed data sources
    
    ============================================================
    TRACEABILITY
    ============================================================
    - input_data_refs: References to input data
    - version: Scoring model version
    - confidence_score: Score confidence
    
    ============================================================
    """
    
    __tablename__ = "risk_scores"
    
    # Primary Key
    risk_score_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for risk score"
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
    
    # Score Details
    risk_dimension: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Risk dimension: market, liquidity, regulatory, etc."
    )
    
    score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Risk score 0-1 (higher = more risk)"
    )
    
    score_percentile: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Score percentile vs historical"
    )
    
    # Component Breakdown
    components: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Score component breakdown"
    )
    
    # Input Data References
    input_data_refs: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="References to input data used"
    )
    
    # Timestamps
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When score was calculated"
    )
    
    data_as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Data timestamp for score"
    )
    
    # Versioning & Traceability
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Scoring model version"
    )
    
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Score confidence"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="scored",
        comment="Processing stage"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_risk_score_symbol", "symbol", "exchange"),
        Index("idx_risk_score_dimension", "risk_dimension"),
        Index("idx_risk_score_scored_at", "scored_at"),
        Index("idx_risk_score_data_as_of", "data_as_of"),
    )


class FlowScore(Base):
    """
    Money flow indicator scores.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores calculated money flow scores derived from
    on-chain data, exchange flows, and market data.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (scored)
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: On-chain and market data
    
    ============================================================
    TRACEABILITY
    ============================================================
    - input_data_refs: References to input data
    - version: Scoring model version
    - confidence_score: Score confidence
    
    ============================================================
    """
    
    __tablename__ = "flow_scores"
    
    # Primary Key
    flow_score_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for flow score"
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
    
    # Score Details
    flow_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Flow type: exchange_inflow, exchange_outflow, whale_movement"
    )
    
    score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Flow score 0-1"
    )
    
    direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Flow direction: inflow, outflow, neutral"
    )
    
    magnitude: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="Flow magnitude in base currency"
    )
    
    # Component Breakdown
    components: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Score component breakdown"
    )
    
    # Input Data References
    input_data_refs: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="References to input data used"
    )
    
    # Timestamps
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When score was calculated"
    )
    
    data_as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Data timestamp for score"
    )
    
    # Versioning & Traceability
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Scoring model version"
    )
    
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Score confidence"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="scored",
        comment="Processing stage"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_flow_score_symbol", "symbol", "exchange"),
        Index("idx_flow_score_type", "flow_type"),
        Index("idx_flow_score_direction", "direction"),
        Index("idx_flow_score_scored_at", "scored_at"),
    )


class SentimentScore(Base):
    """
    Aggregated market sentiment scores.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores aggregated sentiment scores combining multiple
    sentiment analysis results for a symbol at a point in time.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (aggregated)
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: sentiment_analysis_results
    
    ============================================================
    TRACEABILITY
    ============================================================
    - source_sentiment_ids: IDs of source sentiments
    - version: Aggregation version
    - confidence_score: Aggregation confidence
    
    ============================================================
    """
    
    __tablename__ = "sentiment_scores"
    
    # Primary Key
    sentiment_score_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for sentiment score"
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
    
    # Aggregated Scores
    overall_sentiment: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Overall sentiment -1 to 1"
    )
    
    bullish_ratio: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Ratio of bullish signals"
    )
    
    bearish_ratio: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Ratio of bearish signals"
    )
    
    sentiment_strength: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Strength of sentiment signal"
    )
    
    # Source Statistics
    source_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of sources aggregated"
    )
    
    source_sentiment_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        comment="Source sentiment IDs"
    )
    
    # Time Window
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Aggregation window start"
    )
    
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Aggregation window end"
    )
    
    # Timestamps
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When score was calculated"
    )
    
    # Versioning & Traceability
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Aggregation version"
    )
    
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Aggregation confidence"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="aggregated",
        comment="Processing stage"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_sent_score_symbol", "symbol", "exchange"),
        Index("idx_sent_score_scored_at", "scored_at"),
        Index("idx_sent_score_window", "window_start", "window_end"),
    )


class CompositeScore(Base):
    """
    Combined weighted composite scores.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores the final composite score combining risk, flow,
    and sentiment scores with configurable weights.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: DERIVED (final)
    - Mutability: IMMUTABLE
    - Retention: 2 years
    - Source: risk_scores, flow_scores, sentiment_scores
    
    ============================================================
    TRACEABILITY
    ============================================================
    - component_score_ids: References to component scores
    - version: Composition version
    - confidence_score: Composite confidence
    
    ============================================================
    """
    
    __tablename__ = "composite_scores"
    
    # Primary Key
    composite_score_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for composite score"
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
    
    # Composite Score
    composite_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Final composite score 0-1"
    )
    
    signal_direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Signal direction: long, short, neutral"
    )
    
    signal_strength: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Signal strength 0-1"
    )
    
    # Component Scores
    risk_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="Risk component score"
    )
    
    flow_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="Flow component score"
    )
    
    sentiment_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="Sentiment component score"
    )
    
    # Weights Used
    weights: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Weights used for composition"
    )
    
    # Component References
    component_score_ids: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="References to component scores"
    )
    
    # Timestamps
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When score was calculated"
    )
    
    data_as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Data timestamp for score"
    )
    
    # Versioning & Traceability
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Composition version"
    )
    
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Composite confidence"
    )
    
    processing_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="final",
        comment="Processing stage"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_comp_score_symbol", "symbol", "exchange"),
        Index("idx_comp_score_scored_at", "scored_at"),
        Index("idx_comp_score_direction", "signal_direction"),
        Index("idx_comp_score_data_as_of", "data_as_of"),
    )
