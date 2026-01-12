"""
Data Processing Pipeline - Labelers.

============================================================
PURPOSE
============================================================
Stage processors for NORMALIZED → LABELED transition.

Handles:
- Topic classification (descriptive)
- Event type labeling
- Risk keyword detection
- Data quality flagging

============================================================
STAGE TRANSITION
============================================================
FROM: NORMALIZED
TO: LABELED

============================================================
IMPORTANT
============================================================
All labels are DESCRIPTIVE, not PREDICTIVE.

NO bullish/bearish labels.
NO sentiment scoring.
NO price prediction indicators.

============================================================
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_processing.pipeline.base import BaseStageProcessor
from data_processing.pipeline.types import (
    DataDomain,
    ProcessingStage,
    QualityFlag,
    LabelingConfig,
    LabeledNewsItem,
    LabeledMarketItem,
    LabeledOnChainItem,
    LabelingError,
)
from data_processing.labeling.topic_classifier import TopicClassifier, TopicClassifierConfig
from data_processing.labeling.risk_keyword_detector import RiskKeywordDetector, RiskKeywordConfig

from storage.models.processed_data import (
    ProcessedNewsData,
    TopicClassification,
    RiskKeywordDetection,
)


# ============================================================
# NEWS LABELER
# ============================================================


class NewsLabelingProcessor(BaseStageProcessor[ProcessedNewsData, LabeledNewsItem]):
    """
    Processor for labeling normalized news data.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    - Classify news by topic (descriptive)
    - Detect event type
    - Detect risk keywords
    - Assess data quality
    
    ============================================================
    NON-PREDICTIVE LABELS ONLY
    ============================================================
    Topics: regulation, technology, market, adoption, security, etc.
    Event types: announcement, update, incident, analysis, etc.
    
    NO sentiment labels.
    NO bullish/bearish indicators.
    
    ============================================================
    """
    
    def __init__(
        self,
        session: Session,
        config: Optional[LabelingConfig] = None,
        version: str = "1.0.0",
    ) -> None:
        super().__init__(session, DataDomain.NEWS, version)
        
        self._config = config or LabelingConfig()
        
        # Initialize classifiers
        self._topic_classifier = TopicClassifier(TopicClassifierConfig(
            topics=self._config.enabled_topics,
            min_confidence=self._config.min_topic_confidence,
            max_labels=self._config.max_topics_per_item,
            version=version,
        ))
        
        self._risk_detector = RiskKeywordDetector(RiskKeywordConfig(
            categories=self._config.risk_categories,
            version=version,
        ))
    
    @property
    def from_stage(self) -> ProcessingStage:
        return ProcessingStage.NORMALIZED
    
    @property
    def to_stage(self) -> ProcessingStage:
        return ProcessingStage.LABELED
    
    def load_pending_records(self, limit: int = 100) -> List[ProcessedNewsData]:
        """Load normalized news records pending labeling."""
        stmt = (
            select(ProcessedNewsData)
            .where(ProcessedNewsData.processing_stage == "normalized")
            .order_by(ProcessedNewsData.processed_at)
            .limit(limit)
        )
        result = self._session.execute(stmt)
        return list(result.scalars().all())
    
    def get_record_id(self, record: ProcessedNewsData) -> UUID:
        return record.processed_news_id
    
    def process_record(self, record: ProcessedNewsData) -> LabeledNewsItem:
        """Label a single news record."""
        # Classify topics
        topic_result = self._topic_classifier.classify(
            record.title,
            record.content,
        )
        
        # Detect risk keywords
        text_content = f"{record.title} {record.content or ''}"
        risk_result = self._risk_detector.detect(text_content)
        
        # Determine event type (descriptive)
        event_type = self._detect_event_type(record.title, record.content)
        
        # Assess data quality
        quality_flag = self._assess_quality(record, topic_result, risk_result)
        quality_score = self._calculate_quality_score(record)
        
        return LabeledNewsItem(
            raw_news_id=record.raw_news_id,
            source=record.source,
            collected_at_utc=record.collected_at,
            published_at_utc=record.published_at,
            title=record.title,
            content=record.content,
            news_category=topic_result.primary_topic,
            event_type=event_type,
            primary_topics=topic_result.topic_list,
            topic_confidences=topic_result.confidence_dict,
            detected_keywords=[d.keyword for d in risk_result.detections],
            keyword_categories=risk_result.get_keywords_by_category(),
            quality_flag=quality_flag,
            data_quality_score=Decimal(str(quality_score)),
            version=self._version,
        )
    
    def persist_result(self, result: LabeledNewsItem, source_id: UUID) -> UUID:
        """Persist labeled news data."""
        # Update processing stage
        stmt = select(ProcessedNewsData).where(
            ProcessedNewsData.processed_news_id == source_id
        )
        record = self._session.execute(stmt).scalar_one_or_none()
        
        if record:
            record.processing_stage = "labeled"
        
        # Store topic classifications
        for topic in result.primary_topics:
            confidence = result.topic_confidences.get(topic, 0.5)
            is_primary = (topic == result.news_category)
            
            classification = TopicClassification(
                processed_news_id=source_id,
                topic=topic,
                confidence_score=Decimal(str(confidence)),
                is_primary_topic=is_primary,
                classification_method="rule_based",
                version=self._version,
                processing_stage="labeled",
            )
            self._session.add(classification)
        
        # Store risk keyword detections
        for keyword, keywords_list in result.keyword_categories.items():
            for kw in keywords_list:
                detection = RiskKeywordDetection(
                    processed_news_id=source_id,
                    keyword=kw,
                    category=keyword,
                    severity=Decimal("0.5"),  # Default severity
                    confidence_score=Decimal("1.0"),
                    detection_method="pattern",
                    version=self._version,
                    processing_stage="labeled",
                )
                self._session.add(detection)
        
        return source_id
    
    def update_source_stage(self, source_id: UUID) -> None:
        """Update is done in persist_result."""
        pass
    
    def _detect_event_type(
        self,
        title: str,
        content: Optional[str],
    ) -> Optional[str]:
        """
        Detect event type (descriptive classification).
        
        Event types:
        - announcement: New product, partnership, launch
        - update: Protocol update, version release
        - incident: Hack, exploit, outage
        - analysis: Market analysis, research report
        - regulatory: Legal, compliance news
        - opinion: Editorial, commentary
        """
        text = f"{title} {content or ''}".lower()
        
        # Check for event type indicators
        if any(w in text for w in ["announce", "announces", "announced", "launch", "launches"]):
            return "announcement"
        
        if any(w in text for w in ["update", "upgrade", "release", "version", "v2", "v3"]):
            return "update"
        
        if any(w in text for w in ["hack", "exploit", "breach", "attack", "outage", "down"]):
            return "incident"
        
        if any(w in text for w in ["sec", "cftc", "lawsuit", "regulation", "regulatory", "legal"]):
            return "regulatory"
        
        if any(w in text for w in ["analysis", "report", "research", "study", "survey"]):
            return "analysis"
        
        if any(w in text for w in ["opinion", "editorial", "commentary", "think", "believe"]):
            return "opinion"
        
        return None
    
    def _assess_quality(
        self,
        record: ProcessedNewsData,
        topic_result,
        risk_result,
    ) -> QualityFlag:
        """Assess data quality after labeling."""
        if record.is_duplicate:
            return QualityFlag.DUPLICATE
        
        if not record.title:
            return QualityFlag.MISSING_FIELDS
        
        # Check for low-quality signals
        if (record.word_count or 0) < 20:
            return QualityFlag.LOW_QUALITY
        
        # If we couldn't classify into any topic
        if topic_result.primary_topic == "other" and len(topic_result.labels) == 1:
            return QualityFlag.LOW_QUALITY
        
        return QualityFlag.HIGH_QUALITY
    
    def _calculate_quality_score(self, record: ProcessedNewsData) -> float:
        """Calculate a data quality score."""
        score = 0.5  # Base score
        
        # Boost for having content
        if record.content:
            score += 0.2
        
        # Boost for word count
        word_count = record.word_count or 0
        if word_count > 50:
            score += 0.1
        if word_count > 200:
            score += 0.1
        
        # Penalty for duplicates
        if record.is_duplicate:
            score -= 0.3
        
        return max(0.0, min(1.0, score))


# ============================================================
# MARKET DATA LABELER
# ============================================================


class MarketLabelingProcessor(BaseStageProcessor[dict, LabeledMarketItem]):
    """
    Processor for labeling normalized market data.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    - Label activity type (descriptive)
    - Assess data freshness
    - Flag data quality
    
    ============================================================
    LABELS (DESCRIPTIVE ONLY)
    ============================================================
    Activity types: normal, high_volume, low_volume
    Freshness: fresh, stale, delayed
    
    NO price direction labels.
    NO trend indicators.
    
    ============================================================
    """
    
    def __init__(
        self,
        session: Session,
        config: Optional[LabelingConfig] = None,
        version: str = "1.0.0",
    ) -> None:
        super().__init__(session, DataDomain.MARKET, version)
        
        self._config = config or LabelingConfig()
    
    @property
    def from_stage(self) -> ProcessingStage:
        return ProcessingStage.NORMALIZED
    
    @property
    def to_stage(self) -> ProcessingStage:
        return ProcessingStage.LABELED
    
    def load_pending_records(self, limit: int = 100) -> List[dict]:
        """Load normalized market data records pending labeling."""
        from storage.models.raw_data import RawMarketData
        
        stmt = (
            select(RawMarketData)
            .where(RawMarketData.processing_stage == "normalized")
            .order_by(RawMarketData.collected_at)
            .limit(limit)
        )
        result = self._session.execute(stmt)
        
        records = []
        for r in result.scalars().all():
            records.append({
                "raw_market_id": r.raw_market_id,
                "source": r.source,
                "symbol": r.symbol,
                "collected_at": r.collected_at,
                "payload": r.raw_payload,
            })
        
        return records
    
    def get_record_id(self, record: dict) -> UUID:
        return record["raw_market_id"]
    
    def process_record(self, record: dict) -> LabeledMarketItem:
        """Label a single market data record."""
        payload = record.get("payload", {})
        
        # Determine activity type (descriptive)
        activity_type = self._determine_activity_type(payload)
        
        # Assess data freshness
        data_freshness = self._assess_freshness(record["collected_at"])
        
        # Assess quality
        quality_flag = QualityFlag.HIGH_QUALITY
        if data_freshness == "stale":
            quality_flag = QualityFlag.STALE
        
        quality_score = 1.0 if quality_flag == QualityFlag.HIGH_QUALITY else 0.5
        
        return LabeledMarketItem(
            raw_market_id=record["raw_market_id"],
            source=record["source"],
            symbol_normalized=record["symbol"],
            activity_type=activity_type,
            data_freshness=data_freshness,
            quality_flag=quality_flag,
            data_quality_score=Decimal(str(quality_score)),
            version=self._version,
        )
    
    def persist_result(self, result: LabeledMarketItem, source_id: UUID) -> UUID:
        """Persist labeled market data."""
        from storage.models.raw_data import RawMarketData
        
        stmt = select(RawMarketData).where(RawMarketData.raw_market_id == source_id)
        record = self._session.execute(stmt).scalar_one_or_none()
        
        if record:
            record.processing_stage = "labeled"
        
        return source_id
    
    def update_source_stage(self, source_id: UUID) -> None:
        """Update is done in persist_result."""
        pass
    
    def _determine_activity_type(self, payload: Dict[str, Any]) -> str:
        """
        Determine activity type (descriptive only).
        
        NOT a prediction - just describes current state.
        """
        # Check volume if available
        volume = payload.get("total_volume") or payload.get("volume_24h")
        
        if volume is None:
            return "unknown"
        
        # This would normally compare to historical baseline
        # For now, just return "normal"
        return "normal"
    
    def _assess_freshness(self, collected_at: datetime) -> str:
        """Assess data freshness."""
        from datetime import timezone
        
        now = datetime.now(timezone.utc)
        
        # Make collected_at timezone aware if it isn't
        if collected_at.tzinfo is None:
            collected_at = collected_at.replace(tzinfo=timezone.utc)
        
        age_seconds = (now - collected_at).total_seconds()
        
        if age_seconds < 60:
            return "fresh"
        elif age_seconds < 300:
            return "recent"
        elif age_seconds < 3600:
            return "delayed"
        else:
            return "stale"


# ============================================================
# ON-CHAIN DATA LABELER
# ============================================================


class OnChainLabelingProcessor(BaseStageProcessor[dict, LabeledOnChainItem]):
    """
    Processor for labeling normalized on-chain data.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    - Label activity type (descriptive)
    - Categorize transaction size
    - Assess data quality
    
    ============================================================
    LABELS (DESCRIPTIVE ONLY)
    ============================================================
    Activity types: transfer, swap, stake, bridge, contract_call
    Size categories: small, medium, large, whale
    
    NO directional labels.
    NO accumulation/distribution signals.
    
    ============================================================
    """
    
    # Transaction size thresholds (in USD equivalent)
    SIZE_THRESHOLDS = {
        "small": 1000,
        "medium": 10000,
        "large": 100000,
        "whale": 1000000,
    }
    
    def __init__(
        self,
        session: Session,
        config: Optional[LabelingConfig] = None,
        version: str = "1.0.0",
    ) -> None:
        super().__init__(session, DataDomain.ONCHAIN, version)
        
        self._config = config or LabelingConfig()
    
    @property
    def from_stage(self) -> ProcessingStage:
        return ProcessingStage.NORMALIZED
    
    @property
    def to_stage(self) -> ProcessingStage:
        return ProcessingStage.LABELED
    
    def load_pending_records(self, limit: int = 100) -> List[dict]:
        """Load normalized on-chain data records pending labeling."""
        from storage.models.raw_data import RawOnChainData
        
        stmt = (
            select(RawOnChainData)
            .where(RawOnChainData.processing_stage == "normalized")
            .order_by(RawOnChainData.collected_at)
            .limit(limit)
        )
        result = self._session.execute(stmt)
        
        records = []
        for r in result.scalars().all():
            records.append({
                "raw_onchain_id": r.raw_onchain_id,
                "chain": r.chain,
                "data_type": r.data_type,
                "payload": r.raw_payload,
            })
        
        return records
    
    def get_record_id(self, record: dict) -> UUID:
        return record["raw_onchain_id"]
    
    def process_record(self, record: dict) -> LabeledOnChainItem:
        """Label a single on-chain data record."""
        payload = record.get("payload", {})
        
        # Determine activity type
        activity_type = self._determine_activity_type(record["data_type"], payload)
        
        # Categorize transaction size
        size_category = self._categorize_size(payload)
        
        # Assess quality
        quality_flag = QualityFlag.HIGH_QUALITY
        quality_score = Decimal("1.0")
        
        return LabeledOnChainItem(
            raw_onchain_id=record["raw_onchain_id"],
            chain_normalized=record["chain"],
            activity_type=activity_type,
            transaction_size_category=size_category,
            quality_flag=quality_flag,
            data_quality_score=quality_score,
            version=self._version,
        )
    
    def persist_result(self, result: LabeledOnChainItem, source_id: UUID) -> UUID:
        """Persist labeled on-chain data."""
        from storage.models.raw_data import RawOnChainData
        
        stmt = select(RawOnChainData).where(RawOnChainData.raw_onchain_id == source_id)
        record = self._session.execute(stmt).scalar_one_or_none()
        
        if record:
            record.processing_stage = "labeled"
        
        return source_id
    
    def update_source_stage(self, source_id: UUID) -> None:
        """Update is done in persist_result."""
        pass
    
    def _determine_activity_type(
        self,
        data_type: str,
        payload: Dict[str, Any],
    ) -> str:
        """
        Determine activity type (descriptive).
        
        Types: transfer, swap, stake, bridge, contract_call, mint, burn
        """
        # Check input data for common patterns
        input_data = payload.get("input", "")
        
        if not input_data or input_data == "0x":
            return "transfer"
        
        # Check for common function signatures
        if input_data.startswith("0xa9059cbb"):  # ERC20 transfer
            return "transfer"
        
        if input_data.startswith("0x38ed1739") or input_data.startswith("0x7ff36ab5"):
            return "swap"  # Uniswap-like swaps
        
        if input_data.startswith("0xa694fc3a"):  # stake
            return "stake"
        
        # Default to contract_call for complex transactions
        if len(input_data) > 10:
            return "contract_call"
        
        return "transfer"
    
    def _categorize_size(self, payload: Dict[str, Any]) -> str:
        """
        Categorize transaction size (descriptive).
        
        Categories: small, medium, large, whale
        """
        # Try to get USD value
        value_usd = payload.get("valueUsd") or payload.get("value_usd")
        
        if value_usd is None:
            return "unknown"
        
        try:
            value = float(value_usd)
        except (ValueError, TypeError):
            return "unknown"
        
        if value < self.SIZE_THRESHOLDS["small"]:
            return "small"
        elif value < self.SIZE_THRESHOLDS["medium"]:
            return "medium"
        elif value < self.SIZE_THRESHOLDS["large"]:
            return "large"
        else:
            return "whale"
