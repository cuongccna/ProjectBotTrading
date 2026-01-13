"""
Strategy Engine - Persistence Layer.

============================================================
PURPOSE
============================================================
ORM models for persisting trade intents and evaluations.

Enables:
- Audit trail of all intents generated
- Analysis of strategy performance
- NO_TRADE logging for debugging
- Historical pattern analysis

============================================================
MODELS
============================================================
1. TradeIntentRecord: Persisted trade intents
2. NoTradeRecord: Persisted NO_TRADE decisions
3. StrategyEvaluation: Complete evaluation record

============================================================
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Index,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship, Mapped, mapped_column

from database.engine import Base


# ============================================================
# TRADE INTENT RECORD
# ============================================================


class TradeIntentRecord(Base):
    """
    Persisted trade intent from the Strategy Engine.
    
    ============================================================
    WHAT IT STORES
    ============================================================
    - Direction and confidence
    - Strategy reason code
    - Signal breakdown
    - Market context snapshot
    - Status tracking
    
    ============================================================
    """
    
    __tablename__ = "strategy_trade_intents"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    
    # Symbol context
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Trading symbol (e.g., BTC/USDT)",
    )
    
    exchange: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Exchange name",
    )
    
    timeframe: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="1H",
        comment="Primary timeframe",
    )
    
    # Direction and confidence
    direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="LONG or SHORT",
    )
    
    confidence_level: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="LOW, MEDIUM, HIGH",
    )
    
    confidence_value: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Numeric confidence: 1, 2, 3",
    )
    
    # Strategy identification
    reason_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Strategy reason code",
    )
    
    # Signal breakdown
    market_structure_direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Market structure signal direction",
    )
    
    market_structure_strength: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        comment="Market structure signal strength",
    )
    
    market_structure_reason: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="Market structure reason",
    )
    
    volume_flow_direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Volume flow signal direction",
    )
    
    volume_flow_strength: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        comment="Volume flow signal strength",
    )
    
    volume_flow_reason: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="Volume flow reason",
    )
    
    sentiment_effect: Mapped[str] = mapped_column(
        String(15),
        nullable=True,
        comment="Sentiment modifier effect",
    )
    
    sentiment_magnitude: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Sentiment modifier magnitude",
    )
    
    # Market context
    price_at_intent: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Price when intent was generated",
    )
    
    market_regime: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Market regime at intent time",
    )
    
    volatility_regime: Mapped[Optional[str]] = mapped_column(
        String(15),
        nullable=True,
        comment="Volatility regime at intent time",
    )
    
    risk_level: Mapped[Optional[str]] = mapped_column(
        String(15),
        nullable=True,
        comment="Risk level at intent time",
    )
    
    risk_score: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Risk score at intent time (0-8)",
    )
    
    # Full context as JSON
    market_context_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Full market context snapshot",
    )
    
    signal_metrics_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Signal metrics for debugging",
    )
    
    # Status tracking
    status: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        default="GENERATED",
        comment="GENERATED, CONSUMED, EXPIRED, REJECTED",
    )
    
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When intent was consumed by Risk Budget Manager",
    )
    
    consumed_by: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Component that consumed the intent",
    )
    
    # Timestamps
    intent_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the intent was generated",
    )
    
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the intent expires",
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    
    # Engine metadata
    engine_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
    )
    
    evaluation_id: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Evaluation ID for tracing",
    )
    
    # Signal tier classification
    tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="informational",
        comment="Signal tier: informational, actionable, premium",
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_trade_intents_symbol", "symbol"),
        Index("ix_trade_intents_timestamp", "intent_timestamp"),
        Index("ix_trade_intents_direction", "direction"),
        Index("ix_trade_intents_status", "status"),
        Index("ix_trade_intents_reason_code", "reason_code"),
        Index("ix_trade_intents_tier", "tier"),
        Index("ix_trade_intents_symbol_time_tier", "symbol", "intent_timestamp", "tier"),
    )
    
    def __repr__(self) -> str:
        return (
            f"TradeIntentRecord("
            f"symbol={self.symbol}, "
            f"direction={self.direction}, "
            f"confidence={self.confidence_level})"
        )


# ============================================================
# NO TRADE RECORD
# ============================================================


class NoTradeRecord(Base):
    """
    Persisted NO_TRADE decision from the Strategy Engine.
    
    ============================================================
    PURPOSE
    ============================================================
    - Audit trail for debugging
    - Analysis of why trades weren't generated
    - Pattern identification in missed opportunities
    
    ============================================================
    """
    
    __tablename__ = "strategy_no_trades"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    
    # Symbol context
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    
    exchange: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    
    timeframe: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="1H",
    )
    
    # Reason
    reason: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="NoTradeReason enum value",
    )
    
    explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable explanation",
    )
    
    # Signal state (if available)
    market_structure_direction: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
    )
    
    market_structure_strength: Mapped[Optional[str]] = mapped_column(
        String(15),
        nullable=True,
    )
    
    volume_flow_direction: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
    )
    
    volume_flow_strength: Mapped[Optional[str]] = mapped_column(
        String(15),
        nullable=True,
    )
    
    # Market context (if available)
    price_at_evaluation: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    risk_level: Mapped[Optional[str]] = mapped_column(
        String(15),
        nullable=True,
    )
    
    market_context_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    
    # Timestamps
    evaluation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    
    # Engine metadata
    engine_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
    )
    
    evaluation_id: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    
    # Signal tier classification (always INFORMATIONAL for no-trade)
    tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="informational",
        comment="Signal tier: always informational for NO_TRADE",
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_no_trades_symbol", "symbol"),
        Index("ix_no_trades_timestamp", "evaluation_timestamp"),
        Index("ix_no_trades_reason", "reason"),
        Index("ix_no_trades_tier", "tier"),
        Index("ix_no_trades_symbol_time_tier", "symbol", "evaluation_timestamp", "tier"),
    )
    
    def __repr__(self) -> str:
        return (
            f"NoTradeRecord("
            f"symbol={self.symbol}, "
            f"reason={self.reason})"
        )


# ============================================================
# STRATEGY EVALUATION RECORD
# ============================================================


class StrategyEvaluation(Base):
    """
    Complete evaluation record (both intent and no-trade).
    
    ============================================================
    PURPOSE
    ============================================================
    - Single table for all evaluations
    - Simplified querying
    - Complete audit trail
    
    ============================================================
    """
    
    __tablename__ = "strategy_evaluations"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    
    evaluation_id: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Unique evaluation identifier",
    )
    
    # Symbol context
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    
    exchange: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    
    timeframe: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="1H",
    )
    
    # Result type
    has_intent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    
    # Intent fields (if has_intent=True)
    direction: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
    )
    
    confidence_level: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
    )
    
    reason_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    
    # No-trade fields (if has_intent=False)
    no_trade_reason: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    
    no_trade_explanation: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    
    # Full output as JSON
    output_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="Complete StrategyEngineOutput as JSON",
    )
    
    # Performance
    evaluation_duration_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Timestamps
    evaluation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    
    # Engine metadata
    engine_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
    )
    
    # Signal tier classification
    tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="informational",
        comment="Signal tier: informational, actionable, premium",
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_evaluations_symbol", "symbol"),
        Index("ix_evaluations_timestamp", "evaluation_timestamp"),
        Index("ix_evaluations_has_intent", "has_intent"),
        Index("ix_evaluations_evaluation_id", "evaluation_id"),
        Index("ix_evaluations_tier", "tier"),
        Index("ix_evaluations_symbol_time_tier", "symbol", "evaluation_timestamp", "tier"),
    )
    
    def __repr__(self) -> str:
        result = "INTENT" if self.has_intent else "NO_TRADE"
        return (
            f"StrategyEvaluation("
            f"symbol={self.symbol}, "
            f"result={result})"
        )
