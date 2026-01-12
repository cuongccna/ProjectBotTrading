"""
Database ORM Models - All Tables.

============================================================
INSTITUTIONAL-GRADE DATABASE SCHEMA
============================================================

Defines all 12 required tables with:
- Primary keys
- Timestamps (UTC)
- Source/module identifiers
- Correlation IDs
- Proper indexes

============================================================
"""

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Float, Boolean,
    DateTime, JSON, ForeignKey, Index, Enum as SQLEnum,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from .engine import Base


# =============================================================
# HELPER FUNCTIONS
# =============================================================

def generate_uuid():
    """Generate a new UUID."""
    return str(uuid.uuid4())


def utc_now():
    """Get current UTC timestamp."""
    return datetime.utcnow()


# =============================================================
# 1. RAW NEWS TABLE
# =============================================================

class RawNews(Base):
    """
    Raw news articles before processing.
    
    Source: data_ingestion.collectors
    Update Frequency: Per collection cycle
    Retention: 90 days
    """
    __tablename__ = "raw_news"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id = Column(String(36), nullable=False, default=generate_uuid, index=True)
    
    # Content
    external_id = Column(String(255), nullable=True)  # ID from source
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    
    # Source metadata
    source_name = Column(String(100), nullable=False, index=True)  # e.g., "crypto_news_api"
    source_module = Column(String(100), nullable=False, default="data_ingestion")
    author = Column(String(255), nullable=True)
    
    # Classification
    categories = Column(JSONB, nullable=True)  # List of categories
    tokens = Column(JSONB, nullable=True)  # Mentioned tokens
    
    # Timestamps
    published_at = Column(DateTime, nullable=True, index=True)
    fetched_at = Column(DateTime, nullable=False, default=utc_now)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    
    # Processing status
    processed = Column(Boolean, default=False, index=True)
    processing_error = Column(Text, nullable=True)
    
    __table_args__ = (
        Index("idx_raw_news_source_date", "source_name", "created_at"),
        Index("idx_raw_news_unprocessed", "processed", "created_at"),
    )


# =============================================================
# 2. CLEANED NEWS TABLE
# =============================================================

class CleanedNews(Base):
    """
    Cleaned/processed news articles.
    
    Source: data_processing.news_cleaner
    Update Frequency: After raw news processing
    Retention: 90 days
    """
    __tablename__ = "cleaned_news"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id = Column(String(36), nullable=False, index=True)
    raw_news_id = Column(BigInteger, ForeignKey("raw_news.id"), nullable=True, index=True)
    
    # Cleaned content
    cleaned_title = Column(Text, nullable=False)
    cleaned_content = Column(Text, nullable=True)
    cleaned_summary = Column(Text, nullable=True)
    
    # Extracted features
    tokens_mentioned = Column(JSONB, nullable=True)  # Normalized token list
    entities = Column(JSONB, nullable=True)  # Named entities
    keywords = Column(JSONB, nullable=True)  # Extracted keywords
    
    # Quality metrics
    content_quality_score = Column(Float, nullable=True)
    relevance_score = Column(Float, nullable=True)
    
    # Source tracking
    source_module = Column(String(100), nullable=False, default="data_processing")
    
    # Timestamps
    processed_at = Column(DateTime, nullable=False, default=utc_now)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    
    # Processing status
    sentiment_processed = Column(Boolean, default=False, index=True)
    
    __table_args__ = (
        Index("idx_cleaned_news_correlation", "correlation_id"),
        Index("idx_cleaned_news_pending_sentiment", "sentiment_processed", "created_at"),
    )


# =============================================================
# 3. SENTIMENT SCORES TABLE
# =============================================================

class SentimentScore(Base):
    """
    Sentiment analysis results.
    
    Source: sentiment_analysis module
    Update Frequency: After cleaned news processing
    Retention: 90 days
    """
    __tablename__ = "sentiment_scores"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id = Column(String(36), nullable=False, index=True)
    cleaned_news_id = Column(BigInteger, ForeignKey("cleaned_news.id"), nullable=True, index=True)
    
    # Target
    token = Column(String(20), nullable=False, index=True)  # BTC, ETH, etc.
    
    # Sentiment values
    sentiment_score = Column(Float, nullable=False)  # -1.0 to 1.0
    sentiment_label = Column(String(20), nullable=False)  # positive, negative, neutral
    confidence = Column(Float, nullable=False)  # 0.0 to 1.0
    
    # Model info
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(50), nullable=True)
    
    # Component scores (if applicable)
    title_sentiment = Column(Float, nullable=True)
    content_sentiment = Column(Float, nullable=True)
    
    # Source tracking
    source_module = Column(String(100), nullable=False, default="sentiment_analysis")
    source_type = Column(String(50), nullable=False, default="news")  # news, social, etc.
    
    # Timestamps
    analyzed_at = Column(DateTime, nullable=False, default=utc_now)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    
    __table_args__ = (
        Index("idx_sentiment_token_date", "token", "created_at"),
        Index("idx_sentiment_source_type", "source_type", "created_at"),
    )


# =============================================================
# 4. MARKET DATA TABLE
# =============================================================

class MarketData(Base):
    """
    Market price and volume data.
    
    Source: data_ingestion.market_data
    Update Frequency: Per candle interval
    Retention: 1 year for hourly, indefinite for daily
    """
    __tablename__ = "market_data"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id = Column(String(36), nullable=False, index=True)
    
    # Asset info
    symbol = Column(String(20), nullable=False, index=True)  # BTC, ETH
    pair = Column(String(20), nullable=False)  # BTCUSDT
    exchange = Column(String(50), nullable=False, index=True)
    
    # OHLCV
    open_price = Column(Float, nullable=False)
    high_price = Column(Float, nullable=False)
    low_price = Column(Float, nullable=False)
    close_price = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    quote_volume = Column(Float, nullable=True)
    
    # Derived
    vwap = Column(Float, nullable=True)
    trade_count = Column(Integer, nullable=True)
    
    # Timeframe
    interval = Column(String(10), nullable=False)  # 1m, 5m, 1h, 1d
    candle_open_time = Column(DateTime, nullable=False, index=True)
    candle_close_time = Column(DateTime, nullable=False)
    
    # Source tracking
    source_module = Column(String(100), nullable=False, default="market_data_collector")
    
    # Timestamps
    fetched_at = Column(DateTime, nullable=False, default=utc_now)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    
    __table_args__ = (
        UniqueConstraint("symbol", "exchange", "interval", "candle_open_time", name="uq_market_data"),
        Index("idx_market_data_symbol_time", "symbol", "interval", "candle_open_time"),
    )


# =============================================================
# 5. ON-CHAIN FLOW RAW TABLE
# =============================================================

class OnchainFlowRaw(Base):
    """
    Raw on-chain flow data.
    
    Source: data_ingestion.onchain
    Update Frequency: Per collection cycle
    Retention: 90 days
    """
    __tablename__ = "onchain_flow_raw"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id = Column(String(36), nullable=False, default=generate_uuid, index=True)
    
    # Flow data
    token = Column(String(20), nullable=False, index=True)
    chain = Column(String(50), nullable=False)  # ethereum, bitcoin
    flow_type = Column(String(50), nullable=False)  # exchange_inflow, exchange_outflow, whale_transfer
    
    # Values
    amount = Column(Float, nullable=False)
    amount_usd = Column(Float, nullable=True)
    
    # Addresses
    from_address = Column(String(100), nullable=True)
    to_address = Column(String(100), nullable=True)
    from_entity = Column(String(100), nullable=True)  # exchange name, whale label
    to_entity = Column(String(100), nullable=True)
    
    # Transaction
    tx_hash = Column(String(100), nullable=True, index=True)
    block_number = Column(BigInteger, nullable=True)
    
    # Source tracking
    source_name = Column(String(100), nullable=False)  # coinglass, glassnode
    source_module = Column(String(100), nullable=False, default="onchain_collector")
    
    # Timestamps
    event_time = Column(DateTime, nullable=False, index=True)
    fetched_at = Column(DateTime, nullable=False, default=utc_now)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    
    # Processing
    processed = Column(Boolean, default=False, index=True)
    
    __table_args__ = (
        Index("idx_onchain_token_time", "token", "event_time"),
        Index("idx_onchain_flow_type", "flow_type", "event_time"),
    )


# =============================================================
# 6. FLOW SCORES TABLE
# =============================================================

class FlowScore(Base):
    """
    Aggregated flow scores.
    
    Source: flow_scoring module
    Update Frequency: Per scoring cycle
    Retention: 90 days
    """
    __tablename__ = "flow_scores"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id = Column(String(36), nullable=False, index=True)
    
    # Target
    token = Column(String(20), nullable=False, index=True)
    
    # Score components
    exchange_flow_score = Column(Float, nullable=False)  # -100 to 100
    whale_activity_score = Column(Float, nullable=False)
    smart_money_score = Column(Float, nullable=False)
    
    # Aggregated
    composite_flow_score = Column(Float, nullable=False)  # -100 to 100
    flow_signal = Column(String(20), nullable=False)  # bullish, bearish, neutral
    confidence = Column(Float, nullable=False)
    
    # Underlying data
    data_points_count = Column(Integer, nullable=False)
    time_window_hours = Column(Integer, nullable=False)
    
    # Weights used
    weights = Column(JSONB, nullable=True)
    
    # Source tracking
    source_module = Column(String(100), nullable=False, default="flow_scoring")
    
    # Timestamps
    calculated_at = Column(DateTime, nullable=False, default=utc_now)
    data_start_time = Column(DateTime, nullable=False)
    data_end_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    
    __table_args__ = (
        Index("idx_flow_scores_token_time", "token", "created_at"),
    )


# =============================================================
# 7. MARKET STATE TABLE
# =============================================================

class MarketState(Base):
    """
    Current market condition assessment.
    
    Source: market_analyzer module
    Update Frequency: Per analysis cycle
    Retention: 90 days
    """
    __tablename__ = "market_state"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id = Column(String(36), nullable=False, index=True)
    
    # Target
    token = Column(String(20), nullable=False, index=True)
    
    # Market regime
    regime = Column(String(30), nullable=False)  # trending_up, trending_down, ranging, volatile
    regime_confidence = Column(Float, nullable=False)
    
    # Trend
    trend_direction = Column(String(10), nullable=False)  # up, down, neutral
    trend_strength = Column(Float, nullable=False)  # 0 to 1
    
    # Volatility
    volatility_percentile = Column(Float, nullable=False)  # 0 to 100
    volatility_expanding = Column(Boolean, nullable=False)
    atr_value = Column(Float, nullable=True)
    
    # Support/Resistance
    near_support = Column(Boolean, nullable=False)
    near_resistance = Column(Boolean, nullable=False)
    support_level = Column(Float, nullable=True)
    resistance_level = Column(Float, nullable=True)
    
    # Current price
    current_price = Column(Float, nullable=False)
    price_change_24h = Column(Float, nullable=True)
    
    # Source tracking
    source_module = Column(String(100), nullable=False, default="market_analyzer")
    
    # Timestamps
    analyzed_at = Column(DateTime, nullable=False, default=utc_now)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    
    __table_args__ = (
        Index("idx_market_state_token_time", "token", "created_at"),
    )


# =============================================================
# 8. RISK STATE TABLE
# =============================================================

class RiskState(Base):
    """
    Global risk assessment.
    
    Source: risk_scoring module
    Update Frequency: Per risk cycle
    Retention: 1 year
    """
    __tablename__ = "risk_state"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id = Column(String(36), nullable=False, index=True)
    
    # Target (optional, null for global)
    token = Column(String(20), nullable=True, index=True)
    
    # Global risk
    global_risk_score = Column(Float, nullable=False)  # 0 to 100
    risk_level = Column(String(20), nullable=False)  # low, medium, high, extreme
    
    # Component scores (raw)
    sentiment_risk_raw = Column(Float, nullable=False)
    flow_risk_raw = Column(Float, nullable=False)
    smart_money_risk_raw = Column(Float, nullable=False)
    market_condition_risk_raw = Column(Float, nullable=False)
    volatility_risk_raw = Column(Float, nullable=True)
    
    # Component scores (normalized)
    sentiment_risk_normalized = Column(Float, nullable=False)
    flow_risk_normalized = Column(Float, nullable=False)
    smart_money_risk_normalized = Column(Float, nullable=False)
    market_condition_risk_normalized = Column(Float, nullable=False)
    
    # Weights used
    weights = Column(JSONB, nullable=False)
    
    # Trading status
    trading_allowed = Column(Boolean, nullable=False)
    trading_blocked_reason = Column(Text, nullable=True)
    
    # Source tracking
    source_module = Column(String(100), nullable=False, default="risk_scoring")
    
    # Timestamps
    calculated_at = Column(DateTime, nullable=False, default=utc_now)
    valid_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    
    __table_args__ = (
        Index("idx_risk_state_time", "created_at"),
        Index("idx_risk_state_token_time", "token", "created_at"),
    )


# =============================================================
# 9. ENTRY DECISION TABLE
# =============================================================

class EntryDecision(Base):
    """
    Trade entry decisions.
    
    Source: decision_engine module
    Update Frequency: Per decision
    Retention: Indefinite
    """
    __tablename__ = "entry_decision"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id = Column(String(36), nullable=False, index=True)
    
    # Target
    token = Column(String(20), nullable=False, index=True)
    pair = Column(String(20), nullable=False)
    
    # Decision
    decision = Column(String(20), nullable=False)  # ALLOW, BLOCK
    direction = Column(String(10), nullable=True)  # long, short
    
    # Reason
    reason_code = Column(String(50), nullable=False)
    reason_details = Column(Text, nullable=True)
    
    # Triggering factors
    triggering_risk_factors = Column(JSONB, nullable=False)
    risk_state_id = Column(BigInteger, ForeignKey("risk_state.id"), nullable=True)
    
    # Trade Guard
    trade_guard_intervention = Column(Boolean, default=False)
    trade_guard_rule_id = Column(String(50), nullable=True)
    trade_guard_reason = Column(Text, nullable=True)
    
    # Input scores at decision time
    sentiment_score = Column(Float, nullable=True)
    flow_score = Column(Float, nullable=True)
    smart_money_score = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=True)
    
    # Source tracking
    source_module = Column(String(100), nullable=False, default="decision_engine")
    
    # Timestamps
    decided_at = Column(DateTime, nullable=False, default=utc_now)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    
    __table_args__ = (
        Index("idx_entry_decision_token_time", "token", "decided_at"),
        Index("idx_entry_decision_type", "decision", "decided_at"),
    )


# =============================================================
# 10. POSITION SIZING TABLE
# =============================================================

class PositionSizing(Base):
    """
    Position sizing calculations.
    
    Source: position_sizing module
    Update Frequency: Per sizing calculation
    Retention: 1 year
    """
    __tablename__ = "position_sizing"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id = Column(String(36), nullable=False, index=True)
    entry_decision_id = Column(BigInteger, ForeignKey("entry_decision.id"), nullable=True)
    
    # Target
    token = Column(String(20), nullable=False, index=True)
    pair = Column(String(20), nullable=False)
    
    # Position size
    calculated_size = Column(Float, nullable=False)  # In base currency
    size_usd = Column(Float, nullable=False)
    size_percent_of_portfolio = Column(Float, nullable=False)
    
    # Risk parameters
    risk_per_trade = Column(Float, nullable=False)  # Risk amount in USD
    risk_percent = Column(Float, nullable=False)  # Risk as % of portfolio
    stop_loss_price = Column(Float, nullable=True)
    stop_loss_percent = Column(Float, nullable=True)
    
    # Portfolio context
    portfolio_value = Column(Float, nullable=False)
    available_balance = Column(Float, nullable=False)
    current_exposure = Column(Float, nullable=False)
    max_position_size = Column(Float, nullable=False)
    
    # Adjustments
    risk_adjusted = Column(Boolean, default=False)
    adjustment_factor = Column(Float, default=1.0)
    adjustment_reason = Column(Text, nullable=True)
    
    # Final size
    final_size = Column(Float, nullable=False)
    final_size_usd = Column(Float, nullable=False)
    
    # Source tracking
    source_module = Column(String(100), nullable=False, default="position_sizing")
    
    # Timestamps
    calculated_at = Column(DateTime, nullable=False, default=utc_now)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    
    __table_args__ = (
        Index("idx_position_sizing_token_time", "token", "created_at"),
    )


# =============================================================
# 11. EXECUTION RECORDS TABLE
# =============================================================

class ExecutionRecord(Base):
    """
    Trade execution records.
    
    Source: execution module
    Update Frequency: Per execution
    Retention: Indefinite
    """
    __tablename__ = "execution_records"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id = Column(String(36), nullable=False, index=True)
    entry_decision_id = Column(BigInteger, ForeignKey("entry_decision.id"), nullable=True)
    position_sizing_id = Column(BigInteger, ForeignKey("position_sizing.id"), nullable=True)
    
    # Order info
    order_id = Column(String(100), nullable=True, index=True)
    client_order_id = Column(String(100), nullable=True)
    
    # Target
    token = Column(String(20), nullable=False, index=True)
    pair = Column(String(20), nullable=False)
    exchange = Column(String(50), nullable=False)
    
    # Order details
    order_type = Column(String(20), nullable=False)  # market, limit
    side = Column(String(10), nullable=False)  # buy, sell
    requested_size = Column(Float, nullable=False)
    requested_price = Column(Float, nullable=True)
    
    # Execution result
    status = Column(String(20), nullable=False)  # pending, filled, partial, cancelled, failed
    executed_size = Column(Float, nullable=True)
    executed_price = Column(Float, nullable=True)
    avg_fill_price = Column(Float, nullable=True)
    
    # Costs
    commission = Column(Float, nullable=True)
    commission_asset = Column(String(20), nullable=True)
    slippage = Column(Float, nullable=True)
    slippage_percent = Column(Float, nullable=True)
    
    # Timing
    latency_ms = Column(Integer, nullable=True)
    
    # Errors
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Source tracking
    source_module = Column(String(100), nullable=False, default="execution")
    
    # Timestamps
    submitted_at = Column(DateTime, nullable=False, default=utc_now)
    executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    
    __table_args__ = (
        Index("idx_execution_token_time", "token", "created_at"),
        Index("idx_execution_status", "status", "created_at"),
    )


# =============================================================
# 12. SYSTEM MONITORING TABLE
# =============================================================

class SystemMonitoring(Base):
    """
    System monitoring and alerts.
    
    Source: monitoring module
    Update Frequency: Per event
    Retention: 90 days
    """
    __tablename__ = "system_monitoring"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id = Column(String(36), nullable=False, default=generate_uuid, index=True)
    
    # Event type
    event_type = Column(String(50), nullable=False, index=True)  # health_check, alert, metric
    severity = Column(String(20), nullable=False, index=True)  # info, warning, error, critical
    
    # Source
    module_name = Column(String(100), nullable=False, index=True)
    component = Column(String(100), nullable=True)
    
    # Event details
    message = Column(Text, nullable=False)
    details = Column(JSONB, nullable=True)
    
    # Metric (if applicable)
    metric_name = Column(String(100), nullable=True)
    metric_value = Column(Float, nullable=True)
    metric_unit = Column(String(20), nullable=True)
    
    # Alert handling
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    
    # Source tracking
    source_module = Column(String(100), nullable=False, default="monitoring")
    
    # Timestamps
    event_time = Column(DateTime, nullable=False, default=utc_now, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    
    __table_args__ = (
        Index("idx_monitoring_severity_time", "severity", "event_time"),
        Index("idx_monitoring_module_time", "module_name", "event_time"),
        Index("idx_monitoring_unresolved", "resolved", "severity", "event_time"),
    )


# =============================================================
# EXPORT ALL MODELS
# =============================================================

__all__ = [
    "RawNews",
    "CleanedNews",
    "SentimentScore",
    "MarketData",
    "OnchainFlowRaw",
    "FlowScore",
    "MarketState",
    "RiskState",
    "EntryDecision",
    "PositionSizing",
    "ExecutionRecord",
    "SystemMonitoring",
]
