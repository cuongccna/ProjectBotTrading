"""
Signal Outcome Tracker.

============================================================
PURPOSE
============================================================
Evaluates signal outcomes after expiration for directional correctness.

============================================================
WHAT THIS DOES
============================================================
- Find signals that have expired but not yet evaluated
- Fetch price at signal generation and at expiration
- Determine if signal direction was CORRECT, WRONG, or UNKNOWN
- Store outcome for analysis

============================================================
WHAT THIS DOES NOT DO
============================================================
- Calculate PnL or profitability
- Simulate trades or positions
- Make any trading decisions

============================================================
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from database.models import StrategySignalRecord, MarketData
from strategy_engine.types import SignalOutcome, TradeDirection


logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass(frozen=True)
class OutcomeEvaluationConfig:
    """Configuration for outcome evaluation."""
    
    # Minimum price move (%) to determine outcome
    # Below this threshold, outcome is UNKNOWN
    min_move_pct: float = 0.0
    
    # Grace period after expiration before evaluation (minutes)
    # Allows for price data to be ingested
    evaluation_delay_minutes: int = 5
    
    # Maximum signals to evaluate per batch
    batch_size: int = 100
    
    # Whether to evaluate non-actionable signals
    evaluate_non_actionable: bool = False


DEFAULT_CONFIG = OutcomeEvaluationConfig()


# ============================================================
# OUTCOME EVALUATION
# ============================================================

def get_pending_signals(
    session: Session,
    config: OutcomeEvaluationConfig = DEFAULT_CONFIG,
) -> List[StrategySignalRecord]:
    """
    Get signals that need outcome evaluation.
    
    Criteria:
    - expires_at is set and in the past
    - outcome is NULL (not yet evaluated)
    - Past the evaluation delay period
    
    Args:
        session: Database session
        config: Evaluation configuration
        
    Returns:
        List of signals pending evaluation
    """
    cutoff_time = datetime.utcnow() - timedelta(minutes=config.evaluation_delay_minutes)
    
    query = session.query(StrategySignalRecord).filter(
        and_(
            StrategySignalRecord.expires_at.isnot(None),
            StrategySignalRecord.expires_at < cutoff_time,
            StrategySignalRecord.outcome.is_(None),
        )
    )
    
    # Optionally filter to actionable only
    if not config.evaluate_non_actionable:
        query = query.filter(StrategySignalRecord.is_actionable == True)
    
    return query.order_by(StrategySignalRecord.expires_at.asc()).limit(config.batch_size).all()


def get_price_at_time(
    session: Session,
    symbol: str,
    target_time: datetime,
    interval: str = "1h",
    exchange: str = "binance",
) -> Optional[float]:
    """
    Get price closest to the target time.
    
    Args:
        session: Database session
        symbol: Trading symbol (e.g., "BTC")
        target_time: Time to find price for
        interval: Candle interval
        exchange: Exchange name
        
    Returns:
        Close price or None if not found
    """
    # Look for candle containing or nearest to target time
    # First try to find candle that contains the target time
    candle = session.query(MarketData).filter(
        and_(
            MarketData.symbol == symbol,
            MarketData.exchange == exchange,
            MarketData.interval == interval,
            MarketData.candle_open_time <= target_time,
            MarketData.candle_close_time >= target_time,
        )
    ).first()
    
    if candle:
        return candle.close_price
    
    # Fall back to nearest candle before target time
    candle = session.query(MarketData).filter(
        and_(
            MarketData.symbol == symbol,
            MarketData.exchange == exchange,
            MarketData.interval == interval,
            MarketData.candle_close_time <= target_time,
        )
    ).order_by(MarketData.candle_close_time.desc()).first()
    
    if candle:
        return candle.close_price
    
    return None


def evaluate_signal_outcome(
    session: Session,
    signal: StrategySignalRecord,
    config: OutcomeEvaluationConfig = DEFAULT_CONFIG,
) -> Tuple[SignalOutcome, Optional[float], Optional[float], Optional[float]]:
    """
    Evaluate a single signal's outcome.
    
    Args:
        session: Database session
        signal: Signal record to evaluate
        config: Evaluation configuration
        
    Returns:
        Tuple of (outcome, price_at_signal, price_at_expiry, price_move_pct)
    """
    # Get price at signal generation
    price_at_signal = get_price_at_time(
        session,
        symbol=signal.symbol,
        target_time=signal.generated_at,
        interval=signal.timeframe,
        exchange=signal.exchange,
    )
    
    if price_at_signal is None:
        logger.warning(
            f"No price data for signal {signal.signal_id} at generation time"
        )
        return SignalOutcome.UNKNOWN, None, None, None
    
    # Get price at expiration
    price_at_expiry = get_price_at_time(
        session,
        symbol=signal.symbol,
        target_time=signal.expires_at,
        interval=signal.timeframe,
        exchange=signal.exchange,
    )
    
    if price_at_expiry is None:
        logger.warning(
            f"No price data for signal {signal.signal_id} at expiration time"
        )
        return SignalOutcome.UNKNOWN, price_at_signal, None, None
    
    # Calculate price move
    price_move_pct = ((price_at_expiry - price_at_signal) / price_at_signal) * 100
    
    # Parse direction
    try:
        direction = TradeDirection(signal.direction)
    except ValueError:
        logger.error(f"Invalid direction '{signal.direction}' for signal {signal.signal_id}")
        return SignalOutcome.UNKNOWN, price_at_signal, price_at_expiry, price_move_pct
    
    # Evaluate outcome
    outcome = SignalOutcome.evaluate(
        direction=direction,
        price_at_signal=price_at_signal,
        price_at_expiry=price_at_expiry,
        min_move_pct=config.min_move_pct,
    )
    
    return outcome, price_at_signal, price_at_expiry, price_move_pct


def update_signal_outcome(
    session: Session,
    signal: StrategySignalRecord,
    outcome: SignalOutcome,
    price_at_signal: Optional[float],
    price_at_expiry: Optional[float],
    price_move_pct: Optional[float],
) -> None:
    """
    Update signal record with outcome.
    
    Args:
        session: Database session
        signal: Signal record to update
        outcome: Evaluated outcome
        price_at_signal: Price at generation
        price_at_expiry: Price at expiration
        price_move_pct: Percentage price move
    """
    signal.outcome = outcome.value
    signal.outcome_evaluated_at = datetime.utcnow()
    signal.price_at_signal = price_at_signal
    signal.price_at_expiry = price_at_expiry
    signal.price_move_pct = price_move_pct
    
    session.flush()


def evaluate_pending_signals(
    session: Session,
    config: OutcomeEvaluationConfig = DEFAULT_CONFIG,
) -> dict:
    """
    Evaluate all pending signals and update their outcomes.
    
    Args:
        session: Database session
        config: Evaluation configuration
        
    Returns:
        Summary dict with counts per outcome
    """
    pending = get_pending_signals(session, config)
    
    if not pending:
        logger.debug("No pending signals to evaluate")
        return {"total": 0, "correct": 0, "wrong": 0, "unknown": 0}
    
    logger.info(f"Evaluating outcomes for {len(pending)} pending signals")
    
    counts = {"total": 0, "correct": 0, "wrong": 0, "unknown": 0}
    
    for signal in pending:
        outcome, price_at_signal, price_at_expiry, price_move_pct = evaluate_signal_outcome(
            session, signal, config
        )
        
        update_signal_outcome(
            session, signal, outcome, price_at_signal, price_at_expiry, price_move_pct
        )
        
        counts["total"] += 1
        counts[outcome.value] += 1
        
        logger.debug(
            f"Signal {signal.signal_id} [{signal.direction}]: {outcome.value} "
            f"(move: {price_move_pct:.2f}% if price_move_pct else 'N/A')"
        )
    
    logger.info(
        f"Outcome evaluation complete: {counts['correct']} correct, "
        f"{counts['wrong']} wrong, {counts['unknown']} unknown"
    )
    
    return counts


# ============================================================
# QUERY FUNCTIONS
# ============================================================

def get_outcome_stats(
    session: Session,
    symbol: Optional[str] = None,
    tier: Optional[str] = None,
    hours: int = 24,
) -> dict:
    """
    Get outcome statistics for signals.
    
    Args:
        session: Database session
        symbol: Optional symbol filter
        tier: Optional tier filter
        hours: Look-back period in hours
        
    Returns:
        Dict with outcome counts and accuracy rate
    """
    from sqlalchemy import func
    
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    query = session.query(
        StrategySignalRecord.outcome,
        func.count(StrategySignalRecord.id).label("count")
    ).filter(
        and_(
            StrategySignalRecord.outcome.isnot(None),
            StrategySignalRecord.generated_at >= cutoff,
        )
    )
    
    if symbol:
        query = query.filter(StrategySignalRecord.symbol == symbol)
    if tier:
        query = query.filter(StrategySignalRecord.tier == tier)
    
    query = query.group_by(StrategySignalRecord.outcome)
    
    results = query.all()
    
    stats = {"correct": 0, "wrong": 0, "unknown": 0}
    for outcome, count in results:
        if outcome in stats:
            stats[outcome] = count
    
    # Calculate accuracy (excluding unknown)
    evaluated = stats["correct"] + stats["wrong"]
    stats["total_evaluated"] = evaluated
    stats["accuracy_pct"] = (
        (stats["correct"] / evaluated * 100) if evaluated > 0 else None
    )
    
    return stats


def get_signals_by_outcome(
    session: Session,
    outcome: SignalOutcome,
    symbol: Optional[str] = None,
    limit: int = 100,
) -> List[StrategySignalRecord]:
    """
    Get signals by outcome.
    
    Args:
        session: Database session
        outcome: Outcome to filter by
        symbol: Optional symbol filter
        limit: Max results
        
    Returns:
        List of signal records
    """
    query = session.query(StrategySignalRecord).filter(
        StrategySignalRecord.outcome == outcome.value
    )
    
    if symbol:
        query = query.filter(StrategySignalRecord.symbol == symbol)
    
    return query.order_by(StrategySignalRecord.generated_at.desc()).limit(limit).all()


def get_accuracy_by_tier(
    session: Session,
    hours: int = 168,  # 1 week
) -> dict:
    """
    Get accuracy breakdown by signal tier.
    
    Args:
        session: Database session
        hours: Look-back period
        
    Returns:
        Dict with accuracy per tier
    """
    from sqlalchemy import func, case
    
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    results = session.query(
        StrategySignalRecord.tier,
        func.count(case((StrategySignalRecord.outcome == "correct", 1))).label("correct"),
        func.count(case((StrategySignalRecord.outcome == "wrong", 1))).label("wrong"),
        func.count(case((StrategySignalRecord.outcome == "unknown", 1))).label("unknown"),
    ).filter(
        and_(
            StrategySignalRecord.outcome.isnot(None),
            StrategySignalRecord.generated_at >= cutoff,
        )
    ).group_by(StrategySignalRecord.tier).all()
    
    tier_stats = {}
    for tier, correct, wrong, unknown in results:
        evaluated = correct + wrong
        tier_stats[tier] = {
            "correct": correct,
            "wrong": wrong,
            "unknown": unknown,
            "total_evaluated": evaluated,
            "accuracy_pct": (correct / evaluated * 100) if evaluated > 0 else None,
        }
    
    return tier_stats


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    # Configuration
    "OutcomeEvaluationConfig",
    "DEFAULT_CONFIG",
    
    # Core functions
    "get_pending_signals",
    "evaluate_signal_outcome",
    "update_signal_outcome",
    "evaluate_pending_signals",
    
    # Query functions
    "get_outcome_stats",
    "get_signals_by_outcome",
    "get_accuracy_by_tier",
]
