"""
Scoring Repositories.

============================================================
PURPOSE
============================================================
Repositories for scoring data. These handle sentiment scores,
flow scores, and composite risk/signal scores.

============================================================
DATA LIFECYCLE
============================================================
- Stage: SCORING
- Mutability: IMMUTABLE (scores are versioned, not updated)
- Linked to processed data and analysis results

============================================================
REPOSITORIES
============================================================
- SentimentScoreRepository: Sentiment analysis results
- FlowScoreRepository: Fund flow and volume scores
- CompositeScoreRepository: Combined scores and risk metrics

============================================================
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import UUID

from sqlalchemy import select, and_, desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from storage.models.scoring import (
    SentimentAnalysisResult,
    SentimentScore,
    FlowScore,
    CompositeScore,
    RiskScore,
)
from storage.repositories.base import BaseRepository
from storage.repositories.exceptions import (
    RecordNotFoundError,
    RepositoryException,
)


class SentimentScoreRepository(BaseRepository[SentimentScore]):
    """
    Repository for sentiment scores.
    
    ============================================================
    SCOPE
    ============================================================
    Manages SentimentAnalysisResult and SentimentScore records.
    Sentiment data captures market sentiment from news, social
    media, and other text sources.
    
    ============================================================
    MODELS MANAGED
    ============================================================
    - SentimentAnalysisResult: Raw sentiment analysis output
    - SentimentScore: Aggregated sentiment scores
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, SentimentScore, "SentimentScoreRepository")
    
    # =========================================================
    # SENTIMENT ANALYSIS RESULT OPERATIONS
    # =========================================================
    
    def create_sentiment_analysis_result(
        self,
        processed_news_id: UUID,
        analyzed_at: datetime,
        model_name: str,
        model_version: str,
        sentiment_label: str,
        sentiment_score: Decimal,
        confidence: Decimal,
        raw_output: Optional[Dict[str, Any]] = None,
    ) -> SentimentAnalysisResult:
        """
        Create a sentiment analysis result.
        
        Args:
            processed_news_id: Reference to processed news
            analyzed_at: Analysis timestamp
            model_name: Model name
            model_version: Model version
            sentiment_label: Sentiment label (positive, negative, neutral)
            sentiment_score: Numerical sentiment score
            confidence: Model confidence
            raw_output: Raw model output
            
        Returns:
            Created SentimentAnalysisResult record
        """
        entity = SentimentAnalysisResult(
            processed_news_id=processed_news_id,
            analyzed_at=analyzed_at,
            model_name=model_name,
            model_version=model_version,
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            confidence=confidence,
            raw_output=raw_output or {},
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.debug(f"Created sentiment analysis result: {sentiment_label}")
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "create_sentiment_analysis_result", {
                "processed_news_id": str(processed_news_id)
            })
            raise
    
    def get_sentiment_analysis_by_id(
        self,
        result_id: UUID
    ) -> Optional[SentimentAnalysisResult]:
        """Get sentiment analysis result by ID."""
        stmt = select(SentimentAnalysisResult).where(
            SentimentAnalysisResult.id == result_id
        )
        return self._execute_scalar(stmt)
    
    def list_sentiment_analysis_by_news(
        self,
        processed_news_id: UUID
    ) -> List[SentimentAnalysisResult]:
        """
        List all sentiment analysis results for a news item.
        
        Args:
            processed_news_id: The processed news UUID
            
        Returns:
            List of SentimentAnalysisResult
        """
        stmt = (
            select(SentimentAnalysisResult)
            .where(SentimentAnalysisResult.processed_news_id == processed_news_id)
            .order_by(desc(SentimentAnalysisResult.analyzed_at))
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_sentiment_analysis_by_news", {
                "processed_news_id": str(processed_news_id)
            })
            raise
    
    def list_sentiment_analysis_by_model(
        self,
        model_name: str,
        model_version: Optional[str] = None,
        limit: int = 100
    ) -> List[SentimentAnalysisResult]:
        """
        List sentiment analysis results by model.
        
        Args:
            model_name: Model name
            model_version: Optional model version
            limit: Maximum records to return
            
        Returns:
            List of SentimentAnalysisResult
        """
        conditions = [SentimentAnalysisResult.model_name == model_name]
        if model_version:
            conditions.append(SentimentAnalysisResult.model_version == model_version)
        
        stmt = (
            select(SentimentAnalysisResult)
            .where(and_(*conditions))
            .order_by(desc(SentimentAnalysisResult.analyzed_at))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_sentiment_analysis_by_model", {
                "model_name": model_name
            })
            raise
    
    # =========================================================
    # SENTIMENT SCORE OPERATIONS
    # =========================================================
    
    def create_sentiment_score(
        self,
        symbol: str,
        score_timestamp: datetime,
        calculated_at: datetime,
        score_value: Decimal,
        score_type: str,
        aggregator_version: str,
        source_count: int,
        confidence: Decimal,
        time_window_minutes: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SentimentScore:
        """
        Create a sentiment score.
        
        Args:
            symbol: Trading symbol
            score_timestamp: Score reference timestamp
            calculated_at: Calculation timestamp
            score_value: Score value
            score_type: Score type (realtime, hourly, daily)
            aggregator_version: Aggregator version
            source_count: Number of sources
            confidence: Aggregated confidence
            time_window_minutes: Time window in minutes
            metadata: Additional metadata
            
        Returns:
            Created SentimentScore record
        """
        entity = SentimentScore(
            symbol=symbol,
            score_timestamp=score_timestamp,
            calculated_at=calculated_at,
            score_value=score_value,
            score_type=score_type,
            aggregator_version=aggregator_version,
            source_count=source_count,
            confidence=confidence,
            time_window_minutes=time_window_minutes,
            metadata=metadata or {},
        )
        return self._add(entity)
    
    def get_sentiment_score_by_id(
        self,
        score_id: UUID
    ) -> Optional[SentimentScore]:
        """Get sentiment score by ID."""
        return self._get_by_id(score_id)
    
    def get_latest_sentiment_score(
        self,
        symbol: str,
        score_type: Optional[str] = None
    ) -> Optional[SentimentScore]:
        """
        Get the most recent sentiment score for a symbol.
        
        Args:
            symbol: Trading symbol
            score_type: Optional score type filter
            
        Returns:
            Most recent SentimentScore or None
        """
        conditions = [SentimentScore.symbol == symbol]
        if score_type:
            conditions.append(SentimentScore.score_type == score_type)
        
        stmt = (
            select(SentimentScore)
            .where(and_(*conditions))
            .order_by(desc(SentimentScore.score_timestamp))
            .limit(1)
        )
        return self._execute_scalar(stmt)
    
    def list_sentiment_scores_by_symbol(
        self,
        symbol: str,
        score_type: Optional[str] = None,
        limit: int = 100
    ) -> List[SentimentScore]:
        """
        List sentiment scores by symbol.
        
        Args:
            symbol: Trading symbol
            score_type: Optional score type filter
            limit: Maximum records to return
            
        Returns:
            List of SentimentScore
        """
        conditions = [SentimentScore.symbol == symbol]
        if score_type:
            conditions.append(SentimentScore.score_type == score_type)
        
        stmt = (
            select(SentimentScore)
            .where(and_(*conditions))
            .order_by(desc(SentimentScore.score_timestamp))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_sentiment_scores_by_time_range(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        score_type: Optional[str] = None,
        limit: int = 1000
    ) -> List[SentimentScore]:
        """
        List sentiment scores within a time range.
        
        Args:
            symbol: Trading symbol
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            score_type: Optional score type filter
            limit: Maximum records to return
            
        Returns:
            List of SentimentScore
        """
        conditions = [
            SentimentScore.symbol == symbol,
            SentimentScore.score_timestamp >= start_time,
            SentimentScore.score_timestamp < end_time,
        ]
        if score_type:
            conditions.append(SentimentScore.score_type == score_type)
        
        stmt = (
            select(SentimentScore)
            .where(and_(*conditions))
            .order_by(SentimentScore.score_timestamp)
            .limit(limit)
        )
        return self._execute_query(stmt)


class FlowScoreRepository(BaseRepository[FlowScore]):
    """
    Repository for flow scores.
    
    ============================================================
    SCOPE
    ============================================================
    Manages FlowScore records. Flow scores capture fund flows,
    volume patterns, and liquidity metrics.
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, FlowScore, "FlowScoreRepository")
    
    # =========================================================
    # CREATE OPERATIONS
    # =========================================================
    
    def create_flow_score(
        self,
        symbol: str,
        exchange: str,
        score_timestamp: datetime,
        calculated_at: datetime,
        flow_value: Decimal,
        flow_type: str,
        calculator_version: str,
        volume: Decimal,
        net_flow: Decimal,
        time_window_minutes: int,
        confidence: Decimal = Decimal("1.0"),
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FlowScore:
        """
        Create a flow score.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange identifier
            score_timestamp: Score reference timestamp
            calculated_at: Calculation timestamp
            flow_value: Flow score value
            flow_type: Flow type (inflow, outflow, net)
            calculator_version: Calculator version
            volume: Trading volume
            net_flow: Net fund flow
            time_window_minutes: Time window in minutes
            confidence: Score confidence
            metadata: Additional metadata
            
        Returns:
            Created FlowScore record
        """
        entity = FlowScore(
            symbol=symbol,
            exchange=exchange,
            score_timestamp=score_timestamp,
            calculated_at=calculated_at,
            flow_value=flow_value,
            flow_type=flow_type,
            calculator_version=calculator_version,
            volume=volume,
            net_flow=net_flow,
            time_window_minutes=time_window_minutes,
            confidence=confidence,
            metadata=metadata or {},
        )
        return self._add(entity)
    
    # =========================================================
    # READ OPERATIONS
    # =========================================================
    
    def get_by_id(self, flow_score_id: UUID) -> Optional[FlowScore]:
        """Get flow score by ID."""
        return self._get_by_id(flow_score_id)
    
    def get_latest_flow_score(
        self,
        symbol: str,
        exchange: str,
        flow_type: Optional[str] = None
    ) -> Optional[FlowScore]:
        """
        Get the most recent flow score for a symbol/exchange.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange identifier
            flow_type: Optional flow type filter
            
        Returns:
            Most recent FlowScore or None
        """
        conditions = [
            FlowScore.symbol == symbol,
            FlowScore.exchange == exchange,
        ]
        if flow_type:
            conditions.append(FlowScore.flow_type == flow_type)
        
        stmt = (
            select(FlowScore)
            .where(and_(*conditions))
            .order_by(desc(FlowScore.score_timestamp))
            .limit(1)
        )
        return self._execute_scalar(stmt)
    
    def list_by_symbol(
        self,
        symbol: str,
        exchange: Optional[str] = None,
        flow_type: Optional[str] = None,
        limit: int = 100
    ) -> List[FlowScore]:
        """
        List flow scores by symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Optional exchange filter
            flow_type: Optional flow type filter
            limit: Maximum records to return
            
        Returns:
            List of FlowScore
        """
        conditions = [FlowScore.symbol == symbol]
        if exchange:
            conditions.append(FlowScore.exchange == exchange)
        if flow_type:
            conditions.append(FlowScore.flow_type == flow_type)
        
        stmt = (
            select(FlowScore)
            .where(and_(*conditions))
            .order_by(desc(FlowScore.score_timestamp))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_by_time_range(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        exchange: Optional[str] = None,
        limit: int = 1000
    ) -> List[FlowScore]:
        """
        List flow scores within a time range.
        
        Args:
            symbol: Trading symbol
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            exchange: Optional exchange filter
            limit: Maximum records to return
            
        Returns:
            List of FlowScore
        """
        conditions = [
            FlowScore.symbol == symbol,
            FlowScore.score_timestamp >= start_time,
            FlowScore.score_timestamp < end_time,
        ]
        if exchange:
            conditions.append(FlowScore.exchange == exchange)
        
        stmt = (
            select(FlowScore)
            .where(and_(*conditions))
            .order_by(FlowScore.score_timestamp)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_by_exchange(
        self,
        exchange: str,
        limit: int = 100
    ) -> List[FlowScore]:
        """
        List flow scores by exchange.
        
        Args:
            exchange: Exchange identifier
            limit: Maximum records to return
            
        Returns:
            List of FlowScore
        """
        stmt = (
            select(FlowScore)
            .where(FlowScore.exchange == exchange)
            .order_by(desc(FlowScore.score_timestamp))
            .limit(limit)
        )
        return self._execute_query(stmt)


class CompositeScoreRepository(BaseRepository[CompositeScore]):
    """
    Repository for composite and risk scores.
    
    ============================================================
    SCOPE
    ============================================================
    Manages CompositeScore and RiskScore records. Composite
    scores combine multiple signal sources into unified metrics.
    Risk scores quantify overall risk levels.
    
    ============================================================
    MODELS MANAGED
    ============================================================
    - CompositeScore: Combined signal scores
    - RiskScore: Risk level assessments
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, CompositeScore, "CompositeScoreRepository")
    
    # =========================================================
    # COMPOSITE SCORE OPERATIONS
    # =========================================================
    
    def create_composite_score(
        self,
        symbol: str,
        score_timestamp: datetime,
        calculated_at: datetime,
        composite_value: Decimal,
        score_type: str,
        aggregator_version: str,
        components: Dict[str, Decimal],
        weights: Dict[str, Decimal],
        confidence: Decimal,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CompositeScore:
        """
        Create a composite score.
        
        Args:
            symbol: Trading symbol
            score_timestamp: Score reference timestamp
            calculated_at: Calculation timestamp
            composite_value: Final composite value
            score_type: Score type
            aggregator_version: Aggregator version
            components: Component scores
            weights: Component weights
            confidence: Score confidence
            metadata: Additional metadata
            
        Returns:
            Created CompositeScore record
        """
        entity = CompositeScore(
            symbol=symbol,
            score_timestamp=score_timestamp,
            calculated_at=calculated_at,
            composite_value=composite_value,
            score_type=score_type,
            aggregator_version=aggregator_version,
            components=components,
            weights=weights,
            confidence=confidence,
            metadata=metadata or {},
        )
        return self._add(entity)
    
    def get_composite_score_by_id(
        self,
        score_id: UUID
    ) -> Optional[CompositeScore]:
        """Get composite score by ID."""
        return self._get_by_id(score_id)
    
    def get_latest_composite_score(
        self,
        symbol: str,
        score_type: Optional[str] = None
    ) -> Optional[CompositeScore]:
        """
        Get the most recent composite score for a symbol.
        
        Args:
            symbol: Trading symbol
            score_type: Optional score type filter
            
        Returns:
            Most recent CompositeScore or None
        """
        conditions = [CompositeScore.symbol == symbol]
        if score_type:
            conditions.append(CompositeScore.score_type == score_type)
        
        stmt = (
            select(CompositeScore)
            .where(and_(*conditions))
            .order_by(desc(CompositeScore.score_timestamp))
            .limit(1)
        )
        return self._execute_scalar(stmt)
    
    def list_composite_scores_by_symbol(
        self,
        symbol: str,
        score_type: Optional[str] = None,
        limit: int = 100
    ) -> List[CompositeScore]:
        """
        List composite scores by symbol.
        
        Args:
            symbol: Trading symbol
            score_type: Optional score type filter
            limit: Maximum records to return
            
        Returns:
            List of CompositeScore
        """
        conditions = [CompositeScore.symbol == symbol]
        if score_type:
            conditions.append(CompositeScore.score_type == score_type)
        
        stmt = (
            select(CompositeScore)
            .where(and_(*conditions))
            .order_by(desc(CompositeScore.score_timestamp))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_composite_scores_by_time_range(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        score_type: Optional[str] = None,
        limit: int = 1000
    ) -> List[CompositeScore]:
        """
        List composite scores within a time range.
        
        Args:
            symbol: Trading symbol
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            score_type: Optional score type filter
            limit: Maximum records to return
            
        Returns:
            List of CompositeScore
        """
        conditions = [
            CompositeScore.symbol == symbol,
            CompositeScore.score_timestamp >= start_time,
            CompositeScore.score_timestamp < end_time,
        ]
        if score_type:
            conditions.append(CompositeScore.score_type == score_type)
        
        stmt = (
            select(CompositeScore)
            .where(and_(*conditions))
            .order_by(CompositeScore.score_timestamp)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    # =========================================================
    # RISK SCORE OPERATIONS
    # =========================================================
    
    def create_risk_score(
        self,
        symbol: str,
        score_timestamp: datetime,
        calculated_at: datetime,
        risk_value: Decimal,
        risk_level: str,
        calculator_version: str,
        risk_factors: Dict[str, Decimal],
        confidence: Decimal,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RiskScore:
        """
        Create a risk score.
        
        Args:
            symbol: Trading symbol
            score_timestamp: Score reference timestamp
            calculated_at: Calculation timestamp
            risk_value: Numerical risk value
            risk_level: Risk level (low, medium, high, critical)
            calculator_version: Calculator version
            risk_factors: Individual risk factors
            confidence: Score confidence
            metadata: Additional metadata
            
        Returns:
            Created RiskScore record
        """
        entity = RiskScore(
            symbol=symbol,
            score_timestamp=score_timestamp,
            calculated_at=calculated_at,
            risk_value=risk_value,
            risk_level=risk_level,
            calculator_version=calculator_version,
            risk_factors=risk_factors,
            confidence=confidence,
            metadata=metadata or {},
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.debug(f"Created risk score for {symbol}: {risk_level}")
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "create_risk_score", {"symbol": symbol})
            raise
    
    def get_risk_score_by_id(
        self,
        score_id: UUID
    ) -> Optional[RiskScore]:
        """Get risk score by ID."""
        stmt = select(RiskScore).where(RiskScore.id == score_id)
        return self._execute_scalar(stmt)
    
    def get_latest_risk_score(
        self,
        symbol: str
    ) -> Optional[RiskScore]:
        """
        Get the most recent risk score for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Most recent RiskScore or None
        """
        stmt = (
            select(RiskScore)
            .where(RiskScore.symbol == symbol)
            .order_by(desc(RiskScore.score_timestamp))
            .limit(1)
        )
        try:
            result = self._session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            self._handle_db_error(e, "get_latest_risk_score", {"symbol": symbol})
            raise
    
    def list_risk_scores_by_symbol(
        self,
        symbol: str,
        limit: int = 100
    ) -> List[RiskScore]:
        """
        List risk scores by symbol.
        
        Args:
            symbol: Trading symbol
            limit: Maximum records to return
            
        Returns:
            List of RiskScore
        """
        stmt = (
            select(RiskScore)
            .where(RiskScore.symbol == symbol)
            .order_by(desc(RiskScore.score_timestamp))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_risk_scores_by_symbol", {"symbol": symbol})
            raise
    
    def list_risk_scores_by_level(
        self,
        risk_level: str,
        limit: int = 100
    ) -> List[RiskScore]:
        """
        List risk scores by risk level.
        
        Args:
            risk_level: Risk level to filter by
            limit: Maximum records to return
            
        Returns:
            List of RiskScore
        """
        stmt = (
            select(RiskScore)
            .where(RiskScore.risk_level == risk_level)
            .order_by(desc(RiskScore.score_timestamp))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_risk_scores_by_level", {
                "risk_level": risk_level
            })
            raise
    
    def list_risk_scores_by_time_range(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000
    ) -> List[RiskScore]:
        """
        List risk scores within a time range.
        
        Args:
            symbol: Trading symbol
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            limit: Maximum records to return
            
        Returns:
            List of RiskScore
        """
        stmt = (
            select(RiskScore)
            .where(and_(
                RiskScore.symbol == symbol,
                RiskScore.score_timestamp >= start_time,
                RiskScore.score_timestamp < end_time,
            ))
            .order_by(RiskScore.score_timestamp)
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_risk_scores_by_time_range", {
                "symbol": symbol,
                "start": str(start_time),
                "end": str(end_time)
            })
            raise
