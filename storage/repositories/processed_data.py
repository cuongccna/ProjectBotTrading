"""
Processed Data Repositories.

============================================================
PURPOSE
============================================================
Repositories for processed data. These handle cleaned,
normalized, and labeled data ready for analysis.

============================================================
DATA LIFECYCLE
============================================================
- Stage: PROCESSED
- Mutability: IMMUTABLE (processed results are preserved)
- Linked to raw data via foreign keys

============================================================
REPOSITORIES
============================================================
- ProcessedTextRepository: Cleaned/normalized text data
- LabeledDataRepository: Topic/risk labels and classifications

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

from storage.models.processed_data import (
    ProcessedNewsData,
    CleanedTextData,
    TopicClassification,
    RiskKeywordDetection,
)
from storage.repositories.base import BaseRepository
from storage.repositories.exceptions import (
    RecordNotFoundError,
    RepositoryException,
)


class ProcessedTextRepository(BaseRepository[ProcessedNewsData]):
    """
    Repository for processed text data.
    
    ============================================================
    SCOPE
    ============================================================
    Manages ProcessedNewsData and CleanedTextData records.
    Processed text is cleaned, normalized, and prepared for
    NLP analysis.
    
    ============================================================
    MODELS MANAGED
    ============================================================
    - ProcessedNewsData: Processed news articles
    - CleanedTextData: Cleaned/normalized text content
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, ProcessedNewsData, "ProcessedTextRepository")
    
    # =========================================================
    # PROCESSED NEWS OPERATIONS
    # =========================================================
    
    def create_processed_news(
        self,
        raw_news_id: UUID,
        processed_at: datetime,
        title: Optional[str],
        content: str,
        language: str,
        word_count: int,
        processor_version: str,
        quality_score: Decimal = Decimal("1.0"),
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProcessedNewsData:
        """
        Create a processed news record.
        
        Args:
            raw_news_id: Reference to raw news data
            processed_at: Processing timestamp
            title: Cleaned title
            content: Cleaned content
            language: Detected language
            word_count: Word count
            processor_version: Processor version
            quality_score: Quality score
            metadata: Additional metadata
            
        Returns:
            Created ProcessedNewsData record
        """
        entity = ProcessedNewsData(
            raw_news_id=raw_news_id,
            processed_at=processed_at,
            title=title,
            content=content,
            language=language,
            word_count=word_count,
            processor_version=processor_version,
            quality_score=quality_score,
            metadata=metadata or {},
        )
        return self._add(entity)
    
    def get_processed_news_by_id(
        self,
        processed_news_id: UUID
    ) -> Optional[ProcessedNewsData]:
        """Get processed news by ID."""
        return self._get_by_id(processed_news_id)
    
    def get_processed_news_by_raw_id(
        self,
        raw_news_id: UUID
    ) -> Optional[ProcessedNewsData]:
        """
        Get processed news by raw news ID.
        
        Args:
            raw_news_id: The raw news UUID
            
        Returns:
            ProcessedNewsData or None
        """
        stmt = select(ProcessedNewsData).where(
            ProcessedNewsData.raw_news_id == raw_news_id
        )
        return self._execute_scalar(stmt)
    
    def list_processed_news_by_language(
        self,
        language: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[ProcessedNewsData]:
        """
        List processed news by language.
        
        Args:
            language: Language code
            limit: Maximum records to return
            offset: Number of records to skip
            
        Returns:
            List of ProcessedNewsData
        """
        stmt = (
            select(ProcessedNewsData)
            .where(ProcessedNewsData.language == language)
            .order_by(desc(ProcessedNewsData.processed_at))
            .limit(limit)
            .offset(offset)
        )
        return self._execute_query(stmt)
    
    def list_processed_news_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        min_quality_score: Optional[Decimal] = None,
        limit: int = 1000
    ) -> List[ProcessedNewsData]:
        """
        List processed news within a time range.
        
        Args:
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            min_quality_score: Minimum quality score filter
            limit: Maximum records to return
            
        Returns:
            List of ProcessedNewsData
        """
        conditions = [
            ProcessedNewsData.processed_at >= start_time,
            ProcessedNewsData.processed_at < end_time,
        ]
        if min_quality_score is not None:
            conditions.append(ProcessedNewsData.quality_score >= min_quality_score)
        
        stmt = (
            select(ProcessedNewsData)
            .where(and_(*conditions))
            .order_by(ProcessedNewsData.processed_at)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    # =========================================================
    # CLEANED TEXT OPERATIONS
    # =========================================================
    
    def create_cleaned_text(
        self,
        processed_news_id: UUID,
        cleaned_at: datetime,
        cleaned_text: str,
        cleaning_method: str,
        processor_version: str,
        tokens: Optional[List[str]] = None,
        normalized_tokens: Optional[List[str]] = None,
    ) -> CleanedTextData:
        """
        Create a cleaned text record.
        
        Args:
            processed_news_id: Reference to processed news
            cleaned_at: Cleaning timestamp
            cleaned_text: Final cleaned text
            cleaning_method: Method used for cleaning
            processor_version: Processor version
            tokens: Optional tokenized text
            normalized_tokens: Optional normalized tokens
            
        Returns:
            Created CleanedTextData record
        """
        entity = CleanedTextData(
            processed_news_id=processed_news_id,
            cleaned_at=cleaned_at,
            cleaned_text=cleaned_text,
            cleaning_method=cleaning_method,
            processor_version=processor_version,
            tokens=tokens or [],
            normalized_tokens=normalized_tokens or [],
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.debug(f"Created cleaned text for processed_news_id={processed_news_id}")
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "create_cleaned_text", {
                "processed_news_id": str(processed_news_id)
            })
            raise
    
    def get_cleaned_text_by_id(
        self,
        cleaned_text_id: UUID
    ) -> Optional[CleanedTextData]:
        """Get cleaned text by ID."""
        stmt = select(CleanedTextData).where(
            CleanedTextData.id == cleaned_text_id
        )
        return self._execute_scalar(stmt)
    
    def get_cleaned_text_by_processed_news_id(
        self,
        processed_news_id: UUID
    ) -> Optional[CleanedTextData]:
        """
        Get cleaned text by processed news ID.
        
        Args:
            processed_news_id: The processed news UUID
            
        Returns:
            CleanedTextData or None
        """
        stmt = select(CleanedTextData).where(
            CleanedTextData.processed_news_id == processed_news_id
        )
        return self._execute_scalar(stmt)
    
    def list_cleaned_text_by_method(
        self,
        cleaning_method: str,
        limit: int = 100
    ) -> List[CleanedTextData]:
        """
        List cleaned text by cleaning method.
        
        Args:
            cleaning_method: Cleaning method identifier
            limit: Maximum records to return
            
        Returns:
            List of CleanedTextData
        """
        stmt = (
            select(CleanedTextData)
            .where(CleanedTextData.cleaning_method == cleaning_method)
            .order_by(desc(CleanedTextData.cleaned_at))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_cleaned_text_by_method", {
                "method": cleaning_method
            })
            raise


class LabeledDataRepository(BaseRepository[TopicClassification]):
    """
    Repository for labeled data.
    
    ============================================================
    SCOPE
    ============================================================
    Manages TopicClassification and RiskKeywordDetection records.
    Labeled data includes topic assignments, risk keywords, and
    other classification results.
    
    ============================================================
    MODELS MANAGED
    ============================================================
    - TopicClassification: Topic labels and confidence scores
    - RiskKeywordDetection: Risk keywords and severity levels
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, TopicClassification, "LabeledDataRepository")
    
    # =========================================================
    # TOPIC CLASSIFICATION OPERATIONS
    # =========================================================
    
    def create_topic_classification(
        self,
        processed_news_id: UUID,
        classified_at: datetime,
        topic: str,
        confidence: Decimal,
        classifier_version: str,
        subtopics: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TopicClassification:
        """
        Create a topic classification record.
        
        Args:
            processed_news_id: Reference to processed news
            classified_at: Classification timestamp
            topic: Primary topic
            confidence: Classification confidence
            classifier_version: Classifier version
            subtopics: Optional subtopics
            metadata: Additional metadata
            
        Returns:
            Created TopicClassification record
        """
        entity = TopicClassification(
            processed_news_id=processed_news_id,
            classified_at=classified_at,
            topic=topic,
            confidence=confidence,
            classifier_version=classifier_version,
            subtopics=subtopics or [],
            metadata=metadata or {},
        )
        return self._add(entity)
    
    def get_topic_classification_by_id(
        self,
        classification_id: UUID
    ) -> Optional[TopicClassification]:
        """Get topic classification by ID."""
        return self._get_by_id(classification_id)
    
    def list_topic_classifications_by_news(
        self,
        processed_news_id: UUID
    ) -> List[TopicClassification]:
        """
        List all topic classifications for a news item.
        
        Args:
            processed_news_id: The processed news UUID
            
        Returns:
            List of TopicClassification
        """
        stmt = (
            select(TopicClassification)
            .where(TopicClassification.processed_news_id == processed_news_id)
            .order_by(desc(TopicClassification.confidence))
        )
        return self._execute_query(stmt)
    
    def list_by_topic(
        self,
        topic: str,
        min_confidence: Optional[Decimal] = None,
        limit: int = 100
    ) -> List[TopicClassification]:
        """
        List classifications by topic.
        
        Args:
            topic: Topic to filter by
            min_confidence: Minimum confidence threshold
            limit: Maximum records to return
            
        Returns:
            List of TopicClassification
        """
        conditions = [TopicClassification.topic == topic]
        if min_confidence is not None:
            conditions.append(TopicClassification.confidence >= min_confidence)
        
        stmt = (
            select(TopicClassification)
            .where(and_(*conditions))
            .order_by(desc(TopicClassification.confidence))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_topic_classifications_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        topic: Optional[str] = None,
        limit: int = 1000
    ) -> List[TopicClassification]:
        """
        List topic classifications within a time range.
        
        Args:
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            topic: Optional topic filter
            limit: Maximum records to return
            
        Returns:
            List of TopicClassification
        """
        conditions = [
            TopicClassification.classified_at >= start_time,
            TopicClassification.classified_at < end_time,
        ]
        if topic:
            conditions.append(TopicClassification.topic == topic)
        
        stmt = (
            select(TopicClassification)
            .where(and_(*conditions))
            .order_by(TopicClassification.classified_at)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    # =========================================================
    # RISK KEYWORD DETECTION OPERATIONS
    # =========================================================
    
    def create_risk_keyword_detection(
        self,
        processed_news_id: UUID,
        detected_at: datetime,
        keyword: str,
        severity: str,
        context: str,
        detector_version: str,
        confidence: Decimal = Decimal("1.0"),
        category: Optional[str] = None,
    ) -> RiskKeywordDetection:
        """
        Create a risk keyword detection record.
        
        Args:
            processed_news_id: Reference to processed news
            detected_at: Detection timestamp
            keyword: Detected keyword
            severity: Severity level (low, medium, high, critical)
            context: Context around keyword
            detector_version: Detector version
            confidence: Detection confidence
            category: Optional keyword category
            
        Returns:
            Created RiskKeywordDetection record
        """
        entity = RiskKeywordDetection(
            processed_news_id=processed_news_id,
            detected_at=detected_at,
            keyword=keyword,
            severity=severity,
            context=context,
            detector_version=detector_version,
            confidence=confidence,
            category=category,
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.debug(f"Created risk keyword detection: {keyword}")
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "create_risk_keyword_detection", {
                "keyword": keyword
            })
            raise
    
    def get_risk_keyword_by_id(
        self,
        detection_id: UUID
    ) -> Optional[RiskKeywordDetection]:
        """Get risk keyword detection by ID."""
        stmt = select(RiskKeywordDetection).where(
            RiskKeywordDetection.id == detection_id
        )
        return self._execute_scalar(stmt)
    
    def list_risk_keywords_by_news(
        self,
        processed_news_id: UUID
    ) -> List[RiskKeywordDetection]:
        """
        List all risk keyword detections for a news item.
        
        Args:
            processed_news_id: The processed news UUID
            
        Returns:
            List of RiskKeywordDetection
        """
        stmt = (
            select(RiskKeywordDetection)
            .where(RiskKeywordDetection.processed_news_id == processed_news_id)
            .order_by(desc(RiskKeywordDetection.confidence))
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_risk_keywords_by_news", {
                "processed_news_id": str(processed_news_id)
            })
            raise
    
    def list_by_severity(
        self,
        severity: str,
        limit: int = 100
    ) -> List[RiskKeywordDetection]:
        """
        List risk keyword detections by severity.
        
        Args:
            severity: Severity level to filter by
            limit: Maximum records to return
            
        Returns:
            List of RiskKeywordDetection
        """
        stmt = (
            select(RiskKeywordDetection)
            .where(RiskKeywordDetection.severity == severity)
            .order_by(desc(RiskKeywordDetection.detected_at))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_by_severity", {"severity": severity})
            raise
    
    def list_risk_keywords_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        min_severity: Optional[str] = None,
        limit: int = 1000
    ) -> List[RiskKeywordDetection]:
        """
        List risk keyword detections within a time range.
        
        Args:
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            min_severity: Optional minimum severity filter
            limit: Maximum records to return
            
        Returns:
            List of RiskKeywordDetection
        """
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        
        conditions = [
            RiskKeywordDetection.detected_at >= start_time,
            RiskKeywordDetection.detected_at < end_time,
        ]
        
        stmt = (
            select(RiskKeywordDetection)
            .where(and_(*conditions))
            .order_by(RiskKeywordDetection.detected_at)
            .limit(limit)
        )
        
        try:
            result = self._session.execute(stmt)
            detections = list(result.scalars().all())
            
            # Filter by minimum severity in Python (complex SQL ordering avoided)
            if min_severity and min_severity in severity_order:
                min_level = severity_order[min_severity]
                detections = [
                    d for d in detections
                    if severity_order.get(d.severity, 0) >= min_level
                ]
            
            return detections
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_risk_keywords_by_time_range", {
                "start": str(start_time),
                "end": str(end_time)
            })
            raise
    
    def count_by_severity(self, severity: str) -> int:
        """
        Count risk keyword detections by severity.
        
        Args:
            severity: Severity level
            
        Returns:
            Count of detections
        """
        from sqlalchemy import func
        stmt = (
            select(func.count())
            .select_from(RiskKeywordDetection)
            .where(RiskKeywordDetection.severity == severity)
        )
        try:
            result = self._session.execute(stmt)
            return result.scalar() or 0
        except SQLAlchemyError as e:
            self._handle_db_error(e, "count_by_severity", {"severity": severity})
            raise
