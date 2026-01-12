"""
Database Persistence Functions.

============================================================
REAL, AUDITABLE PERSISTENCE OPERATIONS
============================================================

Every function:
- Performs REAL database writes
- Logs structured output: "Persist table_name: inserted=N"
- Raises hard exceptions on failure
- NO stubs, NO mocks, NO silent failures

============================================================
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .models import (
    RawNews,
    CleanedNews,
    SentimentScore,
    MarketData,
    OnchainFlowRaw,
    FlowScore,
    MarketState,
    RiskState,
    EntryDecision,
    PositionSizing,
    ExecutionRecord,
    SystemMonitoring,
)
from .engine import DatabasePersistenceError, PersistenceValidationError

logger = logging.getLogger(__name__)


# =============================================================
# HELPER FUNCTIONS
# =============================================================

def _validate_not_empty(data: List, table_name: str) -> None:
    """Validate data is not empty."""
    if not data:
        logger.warning(f"Persist {table_name}: inserted=0 (empty input)")


def _log_persistence(table_name: str, count: int, details: str = "") -> None:
    """Log persistence result in structured format."""
    if details:
        logger.info(f"Persist {table_name}: inserted={count} ({details})")
    else:
        logger.info(f"Persist {table_name}: inserted={count}")


def _log_zero_records(table_name: str, reason: str, stage: str) -> None:
    """Log when zero records are inserted."""
    logger.warning(
        f"Persist {table_name}: inserted=0 | reason={reason} | stage={stage}"
    )


# =============================================================
# 1. RAW NEWS PERSISTENCE
# =============================================================

def persist_raw_news(
    session: Session,
    news_items: List[Dict[str, Any]],
    correlation_id: str,
    source_name: str = "unknown",
) -> int:
    """
    Persist raw news articles to database.
    
    Args:
        session: Database session
        news_items: List of news item dictionaries
        correlation_id: Correlation ID for this batch
        source_name: Name of data source
        
    Returns:
        Number of records inserted
        
    Raises:
        DatabasePersistenceError on failure
    """
    if not news_items:
        _log_zero_records("raw_news", "empty input", "data_ingestion")
        return 0
    
    try:
        records = []
        for item in news_items:
            record = RawNews(
                correlation_id=correlation_id,
                external_id=item.get("id") or item.get("external_id"),
                title=item.get("title", ""),
                content=item.get("content") or item.get("text"),
                summary=item.get("summary") or item.get("description"),
                url=item.get("url") or item.get("link"),
                source_name=source_name,
                source_module="data_ingestion",
                author=item.get("author"),
                categories=item.get("categories"),
                tokens=item.get("tokens") or item.get("tickers"),
                published_at=item.get("published_at") or item.get("date"),
                fetched_at=datetime.utcnow(),
            )
            records.append(record)
        
        session.bulk_save_objects(records)
        session.flush()
        
        _log_persistence("raw_news", len(records), f"source={source_name}")
        return len(records)
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to persist raw_news: {e}")
        raise DatabasePersistenceError(f"raw_news persistence failed: {e}") from e


# =============================================================
# 2. CLEANED NEWS PERSISTENCE
# =============================================================

def persist_cleaned_news(
    session: Session,
    cleaned_items: List[Dict[str, Any]],
    correlation_id: str,
) -> int:
    """
    Persist cleaned news articles.
    
    Args:
        session: Database session
        cleaned_items: List of cleaned news dictionaries
        correlation_id: Correlation ID
        
    Returns:
        Number of records inserted
    """
    if not cleaned_items:
        _log_zero_records("cleaned_news", "empty input", "data_processing")
        return 0
    
    try:
        records = []
        for item in cleaned_items:
            record = CleanedNews(
                correlation_id=correlation_id,
                raw_news_id=item.get("raw_news_id"),
                cleaned_title=item.get("cleaned_title", item.get("title", "")),
                cleaned_content=item.get("cleaned_content"),
                cleaned_summary=item.get("cleaned_summary"),
                tokens_mentioned=item.get("tokens_mentioned"),
                entities=item.get("entities"),
                keywords=item.get("keywords"),
                content_quality_score=item.get("quality_score"),
                relevance_score=item.get("relevance_score"),
                source_module="data_processing",
            )
            records.append(record)
        
        session.bulk_save_objects(records)
        session.flush()
        
        _log_persistence("cleaned_news", len(records))
        return len(records)
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to persist cleaned_news: {e}")
        raise DatabasePersistenceError(f"cleaned_news persistence failed: {e}") from e


# =============================================================
# 3. SENTIMENT SCORES PERSISTENCE
# =============================================================

def persist_sentiment_scores(
    session: Session,
    scores: List[Dict[str, Any]],
    correlation_id: str,
) -> int:
    """
    Persist sentiment analysis results.
    
    Args:
        session: Database session
        scores: List of sentiment score dictionaries
        correlation_id: Correlation ID
        
    Returns:
        Number of records inserted
    """
    if not scores:
        _log_zero_records("sentiment_scores", "empty input", "sentiment_analysis")
        return 0
    
    try:
        records = []
        for item in scores:
            record = SentimentScore(
                correlation_id=correlation_id,
                cleaned_news_id=item.get("cleaned_news_id"),
                token=item.get("token", "UNKNOWN"),
                sentiment_score=item.get("score", 0.0),
                sentiment_label=item.get("label", "neutral"),
                confidence=item.get("confidence", 0.5),
                model_name=item.get("model", "unknown"),
                model_version=item.get("model_version"),
                title_sentiment=item.get("title_sentiment"),
                content_sentiment=item.get("content_sentiment"),
                source_module="sentiment_analysis",
                source_type=item.get("source_type", "news"),
            )
            records.append(record)
        
        session.bulk_save_objects(records)
        session.flush()
        
        _log_persistence("sentiment_scores", len(records))
        return len(records)
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to persist sentiment_scores: {e}")
        raise DatabasePersistenceError(f"sentiment_scores persistence failed: {e}") from e


# =============================================================
# 4. MARKET DATA PERSISTENCE
# =============================================================

def persist_market_data(
    session: Session,
    candles: List[Dict[str, Any]],
    correlation_id: str,
    symbol: str,
    exchange: str = "binance",
) -> int:
    """
    Persist market OHLCV data.
    
    Args:
        session: Database session
        candles: List of candle dictionaries
        correlation_id: Correlation ID
        symbol: Trading symbol
        exchange: Exchange name
        
    Returns:
        Number of records inserted
    """
    if not candles:
        _log_zero_records("market_data", "empty input", "market_data_collection")
        return 0
    
    try:
        records = []
        for candle in candles:
            record = MarketData(
                correlation_id=correlation_id,
                symbol=symbol,
                pair=candle.get("pair", f"{symbol}USDT"),
                exchange=exchange,
                open_price=candle.get("open"),
                high_price=candle.get("high"),
                low_price=candle.get("low"),
                close_price=candle.get("close"),
                volume=candle.get("volume", 0),
                quote_volume=candle.get("quote_volume"),
                vwap=candle.get("vwap"),
                trade_count=candle.get("trade_count"),
                interval=candle.get("interval", "1h"),
                candle_open_time=candle.get("open_time"),
                candle_close_time=candle.get("close_time"),
                source_module="market_data_collector",
            )
            records.append(record)
        
        session.bulk_save_objects(records)
        session.flush()
        
        _log_persistence("market_data", len(records), f"symbol={symbol}")
        return len(records)
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to persist market_data: {e}")
        raise DatabasePersistenceError(f"market_data persistence failed: {e}") from e


# =============================================================
# 5. ON-CHAIN FLOW RAW PERSISTENCE
# =============================================================

def persist_onchain_flow_raw(
    session: Session,
    flows: List[Dict[str, Any]],
    correlation_id: str,
    source_name: str = "unknown",
) -> int:
    """
    Persist raw on-chain flow data.
    
    Args:
        session: Database session
        flows: List of flow dictionaries
        correlation_id: Correlation ID
        source_name: Data source name
        
    Returns:
        Number of records inserted
    """
    if not flows:
        _log_zero_records("onchain_flow_raw", "empty input", "onchain_collection")
        return 0
    
    try:
        records = []
        for flow in flows:
            record = OnchainFlowRaw(
                correlation_id=correlation_id,
                token=flow.get("token", "UNKNOWN"),
                chain=flow.get("chain", "unknown"),
                flow_type=flow.get("type") or flow.get("flow_type", "unknown"),
                amount=flow.get("amount", 0),
                amount_usd=flow.get("amount_usd"),
                from_address=flow.get("from_address") or flow.get("from"),
                to_address=flow.get("to_address") or flow.get("to"),
                from_entity=flow.get("from_entity"),
                to_entity=flow.get("to_entity"),
                tx_hash=flow.get("tx_hash") or flow.get("hash"),
                block_number=flow.get("block_number") or flow.get("block"),
                source_name=source_name,
                source_module="onchain_collector",
                event_time=flow.get("timestamp") or flow.get("event_time") or datetime.utcnow(),
            )
            records.append(record)
        
        session.bulk_save_objects(records)
        session.flush()
        
        _log_persistence("onchain_flow_raw", len(records), f"source={source_name}")
        return len(records)
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to persist onchain_flow_raw: {e}")
        raise DatabasePersistenceError(f"onchain_flow_raw persistence failed: {e}") from e


# =============================================================
# 6. FLOW SCORES PERSISTENCE
# =============================================================

def persist_flow_scores(
    session: Session,
    scores: List[Dict[str, Any]],
    correlation_id: str,
) -> int:
    """
    Persist aggregated flow scores.
    
    Args:
        session: Database session
        scores: List of flow score dictionaries
        correlation_id: Correlation ID
        
    Returns:
        Number of records inserted
    """
    if not scores:
        _log_zero_records("flow_scores", "empty input", "flow_scoring")
        return 0
    
    try:
        records = []
        for item in scores:
            record = FlowScore(
                correlation_id=correlation_id,
                token=item.get("token", "UNKNOWN"),
                exchange_flow_score=item.get("exchange_flow_score", 0),
                whale_activity_score=item.get("whale_activity_score", 0),
                smart_money_score=item.get("smart_money_score", 0),
                composite_flow_score=item.get("composite_score", 0),
                flow_signal=item.get("signal", "neutral"),
                confidence=item.get("confidence", 0.5),
                data_points_count=item.get("data_points", 0),
                time_window_hours=item.get("time_window_hours", 24),
                weights=item.get("weights"),
                source_module="flow_scoring",
                data_start_time=item.get("data_start_time", datetime.utcnow()),
                data_end_time=item.get("data_end_time", datetime.utcnow()),
            )
            records.append(record)
        
        session.bulk_save_objects(records)
        session.flush()
        
        _log_persistence("flow_scores", len(records))
        return len(records)
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to persist flow_scores: {e}")
        raise DatabasePersistenceError(f"flow_scores persistence failed: {e}") from e


# =============================================================
# 7. MARKET STATE PERSISTENCE
# =============================================================

def persist_market_state(
    session: Session,
    state: Dict[str, Any],
    correlation_id: str,
) -> int:
    """
    Persist market state assessment.
    
    Args:
        session: Database session
        state: Market state dictionary
        correlation_id: Correlation ID
        
    Returns:
        Number of records inserted (1 or 0)
    """
    if not state:
        _log_zero_records("market_state", "empty input", "market_analysis")
        return 0
    
    try:
        record = MarketState(
            correlation_id=correlation_id,
            token=state.get("token", "UNKNOWN"),
            regime=state.get("regime", "unknown"),
            regime_confidence=state.get("regime_confidence", 0.5),
            trend_direction=state.get("trend_direction", "neutral"),
            trend_strength=state.get("trend_strength", 0),
            volatility_percentile=state.get("volatility_percentile", 50),
            volatility_expanding=state.get("volatility_expanding", False),
            atr_value=state.get("atr"),
            near_support=state.get("near_support", False),
            near_resistance=state.get("near_resistance", False),
            support_level=state.get("support_level"),
            resistance_level=state.get("resistance_level"),
            current_price=state.get("current_price", 0),
            price_change_24h=state.get("price_change_24h"),
            source_module="market_analyzer",
        )
        
        session.add(record)
        session.flush()
        
        _log_persistence("market_state", 1, f"token={state.get('token')}")
        return 1
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to persist market_state: {e}")
        raise DatabasePersistenceError(f"market_state persistence failed: {e}") from e


# =============================================================
# 8. RISK STATE PERSISTENCE
# =============================================================

def persist_risk_state(
    session: Session,
    risk: Dict[str, Any],
    correlation_id: str,
) -> int:
    """
    Persist global risk assessment.
    
    Args:
        session: Database session
        risk: Risk state dictionary
        correlation_id: Correlation ID
        
    Returns:
        Number of records inserted (1 or 0)
    """
    if not risk:
        _log_zero_records("risk_state", "empty input", "risk_scoring")
        return 0
    
    try:
        record = RiskState(
            correlation_id=correlation_id,
            token=risk.get("token"),
            global_risk_score=risk.get("global_risk_score", 50),
            risk_level=risk.get("risk_level", "medium"),
            sentiment_risk_raw=risk.get("sentiment_risk_raw", 0),
            flow_risk_raw=risk.get("flow_risk_raw", 0),
            smart_money_risk_raw=risk.get("smart_money_risk_raw", 0),
            market_condition_risk_raw=risk.get("market_condition_risk_raw", 0),
            volatility_risk_raw=risk.get("volatility_risk_raw"),
            sentiment_risk_normalized=risk.get("sentiment_risk_normalized", 0),
            flow_risk_normalized=risk.get("flow_risk_normalized", 0),
            smart_money_risk_normalized=risk.get("smart_money_risk_normalized", 0),
            market_condition_risk_normalized=risk.get("market_condition_risk_normalized", 0),
            weights=risk.get("weights", {}),
            trading_allowed=risk.get("trading_allowed", True),
            trading_blocked_reason=risk.get("trading_blocked_reason"),
            source_module="risk_scoring",
            valid_until=risk.get("valid_until"),
        )
        
        session.add(record)
        session.flush()
        
        _log_persistence("risk_state", 1, f"level={risk.get('risk_level')}")
        return 1
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to persist risk_state: {e}")
        raise DatabasePersistenceError(f"risk_state persistence failed: {e}") from e


# =============================================================
# 9. ENTRY DECISION PERSISTENCE
# =============================================================

def persist_entry_decision(
    session: Session,
    decision: Dict[str, Any],
    correlation_id: str,
) -> int:
    """
    Persist trade entry decision.
    
    Args:
        session: Database session
        decision: Decision dictionary
        correlation_id: Correlation ID
        
    Returns:
        Number of records inserted (1 or 0)
    """
    if not decision:
        _log_zero_records("entry_decision", "empty input", "decision_engine")
        return 0
    
    try:
        record = EntryDecision(
            correlation_id=correlation_id,
            token=decision.get("token", "UNKNOWN"),
            pair=decision.get("pair", ""),
            decision=decision.get("decision", "BLOCK"),
            direction=decision.get("direction"),
            reason_code=decision.get("reason_code", "unknown"),
            reason_details=decision.get("reason_details"),
            triggering_risk_factors=decision.get("triggering_factors", {}),
            risk_state_id=decision.get("risk_state_id"),
            trade_guard_intervention=decision.get("trade_guard_intervention", False),
            trade_guard_rule_id=decision.get("trade_guard_rule_id"),
            trade_guard_reason=decision.get("trade_guard_reason"),
            sentiment_score=decision.get("sentiment_score"),
            flow_score=decision.get("flow_score"),
            smart_money_score=decision.get("smart_money_score"),
            risk_score=decision.get("risk_score"),
            source_module="decision_engine",
        )
        
        session.add(record)
        session.flush()
        
        _log_persistence(
            "entry_decision", 1,
            f"token={decision.get('token')} decision={decision.get('decision')}"
        )
        return 1
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to persist entry_decision: {e}")
        raise DatabasePersistenceError(f"entry_decision persistence failed: {e}") from e


# =============================================================
# 10. POSITION SIZING PERSISTENCE
# =============================================================

def persist_position_sizing(
    session: Session,
    sizing: Dict[str, Any],
    correlation_id: str,
) -> int:
    """
    Persist position sizing calculation.
    
    Args:
        session: Database session
        sizing: Position sizing dictionary
        correlation_id: Correlation ID
        
    Returns:
        Number of records inserted (1 or 0)
    """
    if not sizing:
        _log_zero_records("position_sizing", "empty input", "position_sizing")
        return 0
    
    try:
        record = PositionSizing(
            correlation_id=correlation_id,
            entry_decision_id=sizing.get("entry_decision_id"),
            token=sizing.get("token", "UNKNOWN"),
            pair=sizing.get("pair", ""),
            calculated_size=sizing.get("calculated_size", 0),
            size_usd=sizing.get("size_usd", 0),
            size_percent_of_portfolio=sizing.get("size_percent", 0),
            risk_per_trade=sizing.get("risk_per_trade", 0),
            risk_percent=sizing.get("risk_percent", 0),
            stop_loss_price=sizing.get("stop_loss_price"),
            stop_loss_percent=sizing.get("stop_loss_percent"),
            portfolio_value=sizing.get("portfolio_value", 0),
            available_balance=sizing.get("available_balance", 0),
            current_exposure=sizing.get("current_exposure", 0),
            max_position_size=sizing.get("max_position_size", 0),
            risk_adjusted=sizing.get("risk_adjusted", False),
            adjustment_factor=sizing.get("adjustment_factor", 1.0),
            adjustment_reason=sizing.get("adjustment_reason"),
            final_size=sizing.get("final_size", 0),
            final_size_usd=sizing.get("final_size_usd", 0),
            source_module="position_sizing",
        )
        
        session.add(record)
        session.flush()
        
        _log_persistence("position_sizing", 1, f"token={sizing.get('token')}")
        return 1
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to persist position_sizing: {e}")
        raise DatabasePersistenceError(f"position_sizing persistence failed: {e}") from e


# =============================================================
# 11. EXECUTION RECORDS PERSISTENCE
# =============================================================

def persist_execution_record(
    session: Session,
    execution: Dict[str, Any],
    correlation_id: str,
) -> int:
    """
    Persist trade execution record.
    
    Args:
        session: Database session
        execution: Execution dictionary
        correlation_id: Correlation ID
        
    Returns:
        Number of records inserted (1 or 0)
    """
    if not execution:
        _log_zero_records("execution_records", "empty input", "execution")
        return 0
    
    try:
        record = ExecutionRecord(
            correlation_id=correlation_id,
            entry_decision_id=execution.get("entry_decision_id"),
            position_sizing_id=execution.get("position_sizing_id"),
            order_id=execution.get("order_id"),
            client_order_id=execution.get("client_order_id"),
            token=execution.get("token", "UNKNOWN"),
            pair=execution.get("pair", ""),
            exchange=execution.get("exchange", "unknown"),
            order_type=execution.get("order_type", "market"),
            side=execution.get("side", "buy"),
            requested_size=execution.get("requested_size", 0),
            requested_price=execution.get("requested_price"),
            status=execution.get("status", "pending"),
            executed_size=execution.get("executed_size"),
            executed_price=execution.get("executed_price"),
            avg_fill_price=execution.get("avg_fill_price"),
            commission=execution.get("commission"),
            commission_asset=execution.get("commission_asset"),
            slippage=execution.get("slippage"),
            slippage_percent=execution.get("slippage_percent"),
            latency_ms=execution.get("latency_ms"),
            error_code=execution.get("error_code"),
            error_message=execution.get("error_message"),
            source_module="execution",
            executed_at=execution.get("executed_at"),
        )
        
        session.add(record)
        session.flush()
        
        _log_persistence(
            "execution_records", 1,
            f"token={execution.get('token')} status={execution.get('status')}"
        )
        return 1
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to persist execution_records: {e}")
        raise DatabasePersistenceError(f"execution_records persistence failed: {e}") from e


# =============================================================
# 12. SYSTEM MONITORING PERSISTENCE
# =============================================================

def persist_system_monitoring(
    session: Session,
    event: Dict[str, Any],
    correlation_id: Optional[str] = None,
) -> int:
    """
    Persist system monitoring event.
    
    Args:
        session: Database session
        event: Monitoring event dictionary
        correlation_id: Optional correlation ID
        
    Returns:
        Number of records inserted (1 or 0)
    """
    if not event:
        _log_zero_records("system_monitoring", "empty input", "monitoring")
        return 0
    
    try:
        record = SystemMonitoring(
            correlation_id=correlation_id,
            event_type=event.get("event_type", "unknown"),
            severity=event.get("severity", "info"),
            module_name=event.get("module_name", "unknown"),
            component=event.get("component"),
            message=event.get("message", ""),
            details=event.get("details"),
            metric_name=event.get("metric_name"),
            metric_value=event.get("metric_value"),
            metric_unit=event.get("metric_unit"),
            source_module="monitoring",
            event_time=event.get("event_time", datetime.utcnow()),
        )
        
        session.add(record)
        session.flush()
        
        _log_persistence(
            "system_monitoring", 1,
            f"type={event.get('event_type')} severity={event.get('severity')}"
        )
        return 1
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to persist system_monitoring: {e}")
        raise DatabasePersistenceError(f"system_monitoring persistence failed: {e}") from e


def persist_system_monitoring_batch(
    session: Session,
    events: List[Dict[str, Any]],
    correlation_id: Optional[str] = None,
) -> int:
    """
    Persist multiple system monitoring events.
    
    Args:
        session: Database session
        events: List of event dictionaries
        correlation_id: Optional correlation ID
        
    Returns:
        Number of records inserted
    """
    if not events:
        _log_zero_records("system_monitoring", "empty input", "monitoring")
        return 0
    
    try:
        records = []
        for event in events:
            record = SystemMonitoring(
                correlation_id=correlation_id,
                event_type=event.get("event_type", "unknown"),
                severity=event.get("severity", "info"),
                module_name=event.get("module_name", "unknown"),
                component=event.get("component"),
                message=event.get("message", ""),
                details=event.get("details"),
                metric_name=event.get("metric_name"),
                metric_value=event.get("metric_value"),
                metric_unit=event.get("metric_unit"),
                source_module="monitoring",
                event_time=event.get("event_time", datetime.utcnow()),
            )
            records.append(record)
        
        session.bulk_save_objects(records)
        session.flush()
        
        _log_persistence("system_monitoring", len(records))
        return len(records)
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to persist system_monitoring batch: {e}")
        raise DatabasePersistenceError(f"system_monitoring persistence failed: {e}") from e


# =============================================================
# EXPORTS
# =============================================================

__all__ = [
    "persist_raw_news",
    "persist_cleaned_news",
    "persist_sentiment_scores",
    "persist_market_data",
    "persist_onchain_flow_raw",
    "persist_flow_scores",
    "persist_market_state",
    "persist_risk_state",
    "persist_entry_decision",
    "persist_position_sizing",
    "persist_execution_record",
    "persist_system_monitoring",
    "persist_system_monitoring_batch",
]
