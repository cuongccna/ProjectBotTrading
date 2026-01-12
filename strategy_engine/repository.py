"""
Strategy Engine - Repository.

============================================================
PURPOSE
============================================================
Repository pattern implementation for strategy engine persistence.

Provides clean interface for:
- Saving trade intents
- Recording NO_TRADE decisions
- Querying historical evaluations
- Updating intent status

============================================================
"""

from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, desc, and_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import TradeIntentRecord, NoTradeRecord, StrategyEvaluation
from .types import (
    StrategyEngineOutput,
    TradeIntent,
    NoTradeResult,
    IntentStatus,
)


class StrategyEngineRepository:
    """
    Repository for strategy engine persistence operations.
    
    ============================================================
    METHODS
    ============================================================
    - save_evaluation: Persist complete evaluation
    - save_intent: Persist trade intent
    - save_no_trade: Persist NO_TRADE decision
    - update_intent_status: Update intent lifecycle
    - get_latest_intent: Get most recent intent
    - get_intents_by_symbol: Historical query
    
    ============================================================
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.
        
        Args:
            session: SQLAlchemy async session
        """
        self._session = session
    
    # --------------------------------------------------------
    # WRITE OPERATIONS
    # --------------------------------------------------------
    
    async def save_evaluation(
        self,
        output: StrategyEngineOutput,
    ) -> StrategyEvaluation:
        """
        Save a complete strategy evaluation.
        
        Creates:
        - StrategyEvaluation record
        - Optionally TradeIntentRecord if has_intent
        
        Args:
            output: The StrategyEngineOutput to persist
        
        Returns:
            Created StrategyEvaluation
        """
        # Determine timestamp
        if output.has_intent:
            timestamp = output.trade_intent.timestamp
            symbol = output.trade_intent.symbol
            exchange = output.trade_intent.exchange
            timeframe = output.trade_intent.timeframe
        else:
            timestamp = output.no_trade.timestamp
            symbol = output.no_trade.symbol
            exchange = output.no_trade.exchange
            timeframe = output.no_trade.timeframe
        
        evaluation = StrategyEvaluation(
            evaluation_id=output.evaluation_id,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            has_intent=output.has_intent,
            direction=output.trade_intent.direction.value if output.has_intent else None,
            confidence_level=output.trade_intent.confidence.name if output.has_intent else None,
            reason_code=output.trade_intent.reason_code.value if output.has_intent else None,
            no_trade_reason=output.no_trade.reason.value if not output.has_intent else None,
            no_trade_explanation=output.no_trade.explanation if not output.has_intent else None,
            output_json=output.to_dict(),
            evaluation_duration_ms=output.evaluation_duration_ms,
            evaluation_timestamp=timestamp,
            engine_version=output.engine_version,
        )
        
        self._session.add(evaluation)
        await self._session.flush()
        
        return evaluation
    
    async def save_intent(
        self,
        intent: TradeIntent,
        evaluation_id: Optional[str] = None,
    ) -> TradeIntentRecord:
        """
        Save a trade intent.
        
        Args:
            intent: The TradeIntent to persist
            evaluation_id: Optional evaluation ID for tracing
        
        Returns:
            Created TradeIntentRecord
        """
        record = TradeIntentRecord(
            symbol=intent.symbol,
            exchange=intent.exchange,
            timeframe=intent.timeframe,
            direction=intent.direction.value,
            confidence_level=intent.confidence.name,
            confidence_value=intent.confidence.value,
            reason_code=intent.reason_code.value,
            market_structure_direction=intent.market_structure_signal.direction.value,
            market_structure_strength=intent.market_structure_signal.strength.name,
            market_structure_reason=intent.market_structure_signal.reason,
            volume_flow_direction=intent.volume_flow_signal.direction.value,
            volume_flow_strength=intent.volume_flow_signal.strength.name,
            volume_flow_reason=intent.volume_flow_signal.reason,
            sentiment_effect=intent.sentiment_modifier.effect,
            sentiment_magnitude=intent.sentiment_modifier.magnitude,
            price_at_intent=intent.market_context.price,
            market_regime=intent.market_context.market_regime,
            volatility_regime=intent.market_context.volatility_regime,
            risk_level=intent.market_context.risk_level,
            risk_score=intent.market_context.risk_score,
            market_context_json=intent.market_context.to_dict(),
            signal_metrics_json={
                "market_structure": intent.market_structure_signal.metrics,
                "volume_flow": intent.volume_flow_signal.metrics,
                "sentiment": intent.sentiment_modifier.metrics,
            },
            status=intent.status.value,
            intent_timestamp=intent.timestamp,
            expires_at=intent.expires_at,
            evaluation_id=evaluation_id,
        )
        
        self._session.add(record)
        await self._session.flush()
        
        return record
    
    async def save_no_trade(
        self,
        no_trade: NoTradeResult,
        evaluation_id: Optional[str] = None,
    ) -> NoTradeRecord:
        """
        Save a NO_TRADE decision.
        
        Args:
            no_trade: The NoTradeResult to persist
            evaluation_id: Optional evaluation ID for tracing
        
        Returns:
            Created NoTradeRecord
        """
        record = NoTradeRecord(
            symbol=no_trade.symbol,
            exchange=no_trade.exchange,
            timeframe=no_trade.timeframe,
            reason=no_trade.reason.value,
            explanation=no_trade.explanation,
            market_structure_direction=(
                no_trade.market_structure_signal.direction.value 
                if no_trade.market_structure_signal else None
            ),
            market_structure_strength=(
                no_trade.market_structure_signal.strength.name
                if no_trade.market_structure_signal else None
            ),
            volume_flow_direction=(
                no_trade.volume_flow_signal.direction.value
                if no_trade.volume_flow_signal else None
            ),
            volume_flow_strength=(
                no_trade.volume_flow_signal.strength.name
                if no_trade.volume_flow_signal else None
            ),
            price_at_evaluation=(
                no_trade.market_context.price
                if no_trade.market_context else None
            ),
            risk_level=(
                no_trade.market_context.risk_level
                if no_trade.market_context else None
            ),
            market_context_json=(
                no_trade.market_context.to_dict()
                if no_trade.market_context else None
            ),
            evaluation_timestamp=no_trade.timestamp,
            evaluation_id=evaluation_id,
        )
        
        self._session.add(record)
        await self._session.flush()
        
        return record
    
    async def update_intent_status(
        self,
        intent_id: UUID,
        new_status: IntentStatus,
        consumed_by: Optional[str] = None,
    ) -> None:
        """
        Update the status of a trade intent.
        
        Args:
            intent_id: ID of the intent
            new_status: New status value
            consumed_by: Component that consumed (if applicable)
        """
        stmt = (
            update(TradeIntentRecord)
            .where(TradeIntentRecord.id == intent_id)
            .values(
                status=new_status.value,
                consumed_at=datetime.utcnow() if new_status == IntentStatus.CONSUMED else None,
                consumed_by=consumed_by,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
    
    async def expire_old_intents(self) -> int:
        """
        Mark expired intents as EXPIRED.
        
        Returns:
            Number of intents expired
        """
        now = datetime.utcnow()
        
        stmt = (
            update(TradeIntentRecord)
            .where(
                and_(
                    TradeIntentRecord.status == IntentStatus.GENERATED.value,
                    TradeIntentRecord.expires_at < now,
                )
            )
            .values(status=IntentStatus.EXPIRED.value)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        
        return result.rowcount
    
    # --------------------------------------------------------
    # READ OPERATIONS
    # --------------------------------------------------------
    
    async def get_latest_intent(
        self,
        symbol: Optional[str] = None,
    ) -> Optional[TradeIntentRecord]:
        """
        Get the most recent trade intent.
        
        Args:
            symbol: Optional symbol filter
        
        Returns:
            Latest TradeIntentRecord or None
        """
        conditions = []
        if symbol:
            conditions.append(TradeIntentRecord.symbol == symbol)
        
        stmt = (
            select(TradeIntentRecord)
            .where(and_(*conditions) if conditions else True)
            .order_by(desc(TradeIntentRecord.intent_timestamp))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_pending_intents(
        self,
        symbol: Optional[str] = None,
    ) -> List[TradeIntentRecord]:
        """
        Get all GENERATED intents that haven't expired.
        
        Args:
            symbol: Optional symbol filter
        
        Returns:
            List of pending TradeIntentRecord
        """
        now = datetime.utcnow()
        
        conditions = [
            TradeIntentRecord.status == IntentStatus.GENERATED.value,
            TradeIntentRecord.expires_at > now,
        ]
        
        if symbol:
            conditions.append(TradeIntentRecord.symbol == symbol)
        
        stmt = (
            select(TradeIntentRecord)
            .where(and_(*conditions))
            .order_by(desc(TradeIntentRecord.intent_timestamp))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_intents_in_range(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        symbol: Optional[str] = None,
        limit: int = 1000,
    ) -> List[TradeIntentRecord]:
        """
        Get intents within a time range.
        
        Args:
            start_time: Start of range
            end_time: End of range (defaults to now)
            symbol: Optional symbol filter
            limit: Maximum results
        
        Returns:
            List of TradeIntentRecord
        """
        end_time = end_time or datetime.utcnow()
        
        conditions = [
            TradeIntentRecord.intent_timestamp >= start_time,
            TradeIntentRecord.intent_timestamp <= end_time,
        ]
        
        if symbol:
            conditions.append(TradeIntentRecord.symbol == symbol)
        
        stmt = (
            select(TradeIntentRecord)
            .where(and_(*conditions))
            .order_by(desc(TradeIntentRecord.intent_timestamp))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_no_trades_in_range(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        symbol: Optional[str] = None,
        reason: Optional[str] = None,
        limit: int = 1000,
    ) -> List[NoTradeRecord]:
        """
        Get NO_TRADE records within a time range.
        
        Args:
            start_time: Start of range
            end_time: End of range (defaults to now)
            symbol: Optional symbol filter
            reason: Optional reason filter
            limit: Maximum results
        
        Returns:
            List of NoTradeRecord
        """
        end_time = end_time or datetime.utcnow()
        
        conditions = [
            NoTradeRecord.evaluation_timestamp >= start_time,
            NoTradeRecord.evaluation_timestamp <= end_time,
        ]
        
        if symbol:
            conditions.append(NoTradeRecord.symbol == symbol)
        
        if reason:
            conditions.append(NoTradeRecord.reason == reason)
        
        stmt = (
            select(NoTradeRecord)
            .where(and_(*conditions))
            .order_by(desc(NoTradeRecord.evaluation_timestamp))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_evaluation_by_id(
        self,
        evaluation_id: str,
    ) -> Optional[StrategyEvaluation]:
        """
        Get an evaluation by its ID.
        
        Args:
            evaluation_id: The evaluation ID string
        
        Returns:
            StrategyEvaluation or None
        """
        stmt = select(StrategyEvaluation).where(
            StrategyEvaluation.evaluation_id == evaluation_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    
    # --------------------------------------------------------
    # ANALYTICS
    # --------------------------------------------------------
    
    async def get_intent_count(
        self,
        hours: int = 24,
        symbol: Optional[str] = None,
    ) -> int:
        """
        Get count of intents in a time period.
        
        Args:
            hours: Hours to look back
            symbol: Optional symbol filter
        
        Returns:
            Count of intents
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        
        conditions = [TradeIntentRecord.intent_timestamp >= since]
        if symbol:
            conditions.append(TradeIntentRecord.symbol == symbol)
        
        stmt = select(func.count(TradeIntentRecord.id)).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return result.scalar() or 0
    
    async def get_no_trade_distribution(
        self,
        hours: int = 24,
        symbol: Optional[str] = None,
    ) -> dict[str, int]:
        """
        Get distribution of NO_TRADE reasons.
        
        Args:
            hours: Hours to look back
            symbol: Optional symbol filter
        
        Returns:
            Dict mapping reason to count
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        
        conditions = [NoTradeRecord.evaluation_timestamp >= since]
        if symbol:
            conditions.append(NoTradeRecord.symbol == symbol)
        
        stmt = (
            select(NoTradeRecord.reason, func.count(NoTradeRecord.id))
            .where(and_(*conditions))
            .group_by(NoTradeRecord.reason)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
    
    async def get_direction_distribution(
        self,
        hours: int = 24,
        symbol: Optional[str] = None,
    ) -> dict[str, int]:
        """
        Get distribution of intent directions.
        
        Args:
            hours: Hours to look back
            symbol: Optional symbol filter
        
        Returns:
            Dict mapping direction to count
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        
        conditions = [TradeIntentRecord.intent_timestamp >= since]
        if symbol:
            conditions.append(TradeIntentRecord.symbol == symbol)
        
        stmt = (
            select(TradeIntentRecord.direction, func.count(TradeIntentRecord.id))
            .where(and_(*conditions))
            .group_by(TradeIntentRecord.direction)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
    
    async def get_confidence_distribution(
        self,
        hours: int = 24,
        symbol: Optional[str] = None,
    ) -> dict[str, int]:
        """
        Get distribution of confidence levels.
        
        Args:
            hours: Hours to look back
            symbol: Optional symbol filter
        
        Returns:
            Dict mapping confidence level to count
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        
        conditions = [TradeIntentRecord.intent_timestamp >= since]
        if symbol:
            conditions.append(TradeIntentRecord.symbol == symbol)
        
        stmt = (
            select(TradeIntentRecord.confidence_level, func.count(TradeIntentRecord.id))
            .where(and_(*conditions))
            .group_by(TradeIntentRecord.confidence_level)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
