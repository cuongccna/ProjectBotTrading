"""
Data Processing Pipeline - Cleaners.

============================================================
PURPOSE
============================================================
Stage processors for RAW → CLEANED transition.

Handles:
- News data cleaning
- Market data cleaning
- On-chain data cleaning

============================================================
STAGE TRANSITION
============================================================
FROM: RAW
TO: CLEANED

============================================================
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from data_processing.pipeline.base import BaseStageProcessor
from data_processing.pipeline.types import (
    DataDomain,
    ProcessingStage,
    QualityFlag,
    CleaningConfig,
    CleanedNewsItem,
    CleanedMarketItem,
    CleanedOnChainItem,
    CleaningError,
    compute_content_hash,
    compute_payload_hash,
)
from data_processing.cleaning.text_cleaner import TextCleaner, TextCleanerConfig
from data_processing.cleaning.deduplicator import Deduplicator, DeduplicatorConfig

from storage.models.raw_data import RawNewsData, RawMarketData, RawOnChainData
from storage.models.processed_data import ProcessedNewsData, CleanedTextData


# ============================================================
# NEWS DATA CLEANER
# ============================================================


class NewsCleaningProcessor(BaseStageProcessor[RawNewsData, CleanedNewsItem]):
    """
    Processor for cleaning raw news data.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    - Extract fields from raw payload
    - Clean text content (HTML, encoding, whitespace)
    - Detect and mark duplicates
    - Validate required fields
    - Compute quality flags
    
    ============================================================
    """
    
    def __init__(
        self,
        session: Session,
        config: Optional[CleaningConfig] = None,
        version: str = "1.0.0",
    ) -> None:
        super().__init__(session, DataDomain.NEWS, version)
        
        self._config = config or CleaningConfig()
        
        # Initialize cleaning components
        self._text_cleaner = TextCleaner(TextCleanerConfig(
            remove_html=self._config.remove_html,
            remove_urls=self._config.remove_urls,
            extract_urls=self._config.extract_urls,
            normalize_unicode=self._config.normalize_unicode,
            version=version,
        ))
        
        self._deduplicator = Deduplicator(DeduplicatorConfig(
            exact_match_enabled=self._config.enable_deduplication,
            near_duplicate_enabled=self._config.enable_deduplication,
            similarity_threshold=self._config.similarity_threshold,
            version=version,
        ))
    
    @property
    def from_stage(self) -> ProcessingStage:
        return ProcessingStage.RAW
    
    @property
    def to_stage(self) -> ProcessingStage:
        return ProcessingStage.CLEANED
    
    def load_pending_records(self, limit: int = 100) -> List[RawNewsData]:
        """Load raw news records pending cleaning."""
        stmt = (
            select(RawNewsData)
            .where(RawNewsData.processing_stage == "raw")
            .order_by(RawNewsData.collected_at)
            .limit(limit)
        )
        result = self._session.execute(stmt)
        return list(result.scalars().all())
    
    def get_record_id(self, record: RawNewsData) -> UUID:
        return record.raw_news_id
    
    def process_record(self, record: RawNewsData) -> CleanedNewsItem:
        """Clean a single news record."""
        payload = record.raw_payload or {}
        
        # Extract title
        raw_title = (
            payload.get("title") or
            payload.get("headline") or
            ""
        )
        
        # Extract content
        raw_content = (
            payload.get("content") or
            payload.get("body") or
            payload.get("text") or
            payload.get("description") or
            None
        )
        
        # Extract other fields
        raw_summary = payload.get("summary") or payload.get("excerpt")
        raw_url = payload.get("url") or payload.get("link")
        raw_author = payload.get("author") or payload.get("source", {}).get("name")
        
        # Clean title
        if raw_title:
            cleaned_title_result = self._text_cleaner.clean(raw_title)
            title = self._text_cleaner.clean_title(cleaned_title_result.cleaned)
        else:
            title = ""
            cleaned_title_result = None
        
        # Clean content
        extracted_urls: List[str] = []
        cleaning_operations: List[str] = []
        characters_removed = 0
        
        if raw_content:
            cleaned_content_result = self._text_cleaner.clean(raw_content)
            content = cleaned_content_result.cleaned
            extracted_urls.extend(cleaned_content_result.extracted_urls)
            cleaning_operations.extend(cleaned_content_result.cleaning_operations)
            characters_removed += cleaned_content_result.characters_removed
        else:
            content = None
        
        # Clean summary
        if raw_summary:
            cleaned_summary = self._text_cleaner.clean(raw_summary).cleaned
        else:
            cleaned_summary = None
        
        # Compute word count
        word_count = len((content or "").split()) if content else 0
        
        # Compute content hash for deduplication
        hash_content = f"{title} {content or ''}"
        content_hash = compute_content_hash(
            self._text_cleaner.clean_for_hash(hash_content)
        )
        
        # Check for duplicates
        dedup_result = self._deduplicator.check_duplicate(
            record.raw_news_id,
            hash_content,
            record.source,
            record.collected_at,
        )
        
        # Determine quality flag
        quality_flag = self._assess_quality(
            title=title,
            content=content,
            word_count=word_count,
            is_duplicate=dedup_result.is_duplicate,
        )
        
        return CleanedNewsItem(
            raw_news_id=record.raw_news_id,
            source=record.source,
            collected_at=record.collected_at,
            published_at=record.source_published_at,
            original_payload=payload,
            title=title,
            content=content,
            summary=cleaned_summary,
            url=raw_url,
            author=raw_author,
            content_hash=content_hash,
            is_duplicate=dedup_result.is_duplicate,
            duplicate_of_id=dedup_result.original_id,
            extracted_urls=extracted_urls,
            cleaning_operations=cleaning_operations,
            characters_removed=characters_removed,
            quality_flag=quality_flag,
            word_count=word_count,
            version=self._version,
        )
    
    def persist_result(self, result: CleanedNewsItem, source_id: UUID) -> UUID:
        """Persist cleaned news data."""
        # Create ProcessedNewsData entity
        entity = ProcessedNewsData(
            raw_news_id=result.raw_news_id,
            source=result.source,
            original_id=str(source_id),
            title=result.title,
            content=result.content,
            summary=result.summary,
            url=result.url,
            author=result.author,
            published_at=result.published_at or datetime.utcnow(),
            collected_at=result.collected_at,
            processed_at=result.cleaned_at,
            content_hash=result.content_hash,
            is_duplicate=result.is_duplicate,
            duplicate_of_id=result.duplicate_of_id,
            word_count=result.word_count,
            version=result.version,
            processing_stage="cleaned",
            confidence_score=Decimal("1.0"),
        )
        
        self._session.add(entity)
        self._session.flush()
        
        # Also create CleanedTextData entry
        if result.content:
            cleaned_text = CleanedTextData(
                processed_news_id=entity.processed_news_id,
                original_text=result.original_payload.get("content", ""),
                cleaned_text=result.content,
                extracted_urls=result.extracted_urls,
                cleaning_operations=result.cleaning_operations,
                characters_removed=result.characters_removed,
                version=result.version,
                processing_stage="cleaned",
            )
            self._session.add(cleaned_text)
        
        return entity.processed_news_id
    
    def update_source_stage(self, source_id: UUID) -> None:
        """Update raw news processing stage to cleaned."""
        stmt = (
            select(RawNewsData)
            .where(RawNewsData.raw_news_id == source_id)
        )
        result = self._session.execute(stmt)
        record = result.scalar_one_or_none()
        
        if record:
            record.processing_stage = "cleaned"
    
    def _assess_quality(
        self,
        title: str,
        content: Optional[str],
        word_count: int,
        is_duplicate: bool,
    ) -> QualityFlag:
        """Assess data quality and return appropriate flag."""
        if is_duplicate:
            return QualityFlag.DUPLICATE
        
        if not title:
            return QualityFlag.MISSING_FIELDS
        
        if not content:
            return QualityFlag.INCOMPLETE
        
        if word_count < self._config.min_content_length:
            return QualityFlag.LOW_QUALITY
        
        return QualityFlag.HIGH_QUALITY


# ============================================================
# MARKET DATA CLEANER
# ============================================================


class MarketCleaningProcessor(BaseStageProcessor[RawMarketData, CleanedMarketItem]):
    """
    Processor for cleaning raw market data.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    - Validate required fields (symbol, timestamp, price/volume)
    - Detect duplicate data points
    - Validate numeric ranges
    - Flag data quality issues
    
    ============================================================
    """
    
    def __init__(
        self,
        session: Session,
        config: Optional[CleaningConfig] = None,
        version: str = "1.0.0",
    ) -> None:
        super().__init__(session, DataDomain.MARKET, version)
        
        self._config = config or CleaningConfig()
        self._deduplicator = Deduplicator(DeduplicatorConfig(
            exact_match_enabled=True,
            near_duplicate_enabled=False,  # Exact match only for market data
            version=version,
        ))
    
    @property
    def from_stage(self) -> ProcessingStage:
        return ProcessingStage.RAW
    
    @property
    def to_stage(self) -> ProcessingStage:
        return ProcessingStage.CLEANED
    
    def load_pending_records(self, limit: int = 100) -> List[RawMarketData]:
        """Load raw market data records pending cleaning."""
        stmt = (
            select(RawMarketData)
            .where(RawMarketData.processing_stage == "raw")
            .order_by(RawMarketData.collected_at)
            .limit(limit)
        )
        result = self._session.execute(stmt)
        return list(result.scalars().all())
    
    def get_record_id(self, record: RawMarketData) -> UUID:
        return record.raw_market_id
    
    def process_record(self, record: RawMarketData) -> CleanedMarketItem:
        """Clean a single market data record."""
        payload = record.raw_payload or {}
        
        # Validate required fields
        fields_validated: List[str] = []
        fields_missing: List[str] = []
        
        # Check symbol
        symbol = record.symbol
        if symbol:
            fields_validated.append("symbol")
        else:
            fields_missing.append("symbol")
        
        # Check timestamp
        source_timestamp = record.source_timestamp if hasattr(record, 'source_timestamp') else None
        if source_timestamp:
            fields_validated.append("timestamp")
        else:
            fields_missing.append("timestamp")
        
        # Validate payload fields
        cleaned_payload = self._clean_payload(payload)
        
        # Check for required numeric fields based on data type
        if record.data_type == "ticker":
            for field in ["price", "current_price", "last_price"]:
                if field in payload and payload[field] is not None:
                    fields_validated.append("price")
                    break
            else:
                fields_missing.append("price")
        
        # Compute payload hash
        payload_hash = record.payload_hash or compute_payload_hash(payload)
        
        # Check for duplicates
        dedup_result = self._deduplicator.check_duplicate(
            record.raw_market_id,
            str(payload),  # Use payload as content for hash
            record.source,
            record.collected_at,
        )
        
        # Determine quality flag
        quality_flag = self._assess_quality(
            fields_validated=fields_validated,
            fields_missing=fields_missing,
            is_duplicate=dedup_result.is_duplicate,
        )
        
        return CleanedMarketItem(
            raw_market_id=record.raw_market_id,
            source=record.source,
            symbol=symbol,
            data_type=record.data_type,
            collected_at=record.collected_at,
            source_timestamp=source_timestamp,
            cleaned_payload=cleaned_payload,
            payload_hash=payload_hash,
            is_duplicate=dedup_result.is_duplicate,
            fields_validated=fields_validated,
            fields_missing=fields_missing,
            quality_flag=quality_flag,
            version=self._version,
        )
    
    def persist_result(self, result: CleanedMarketItem, source_id: UUID) -> UUID:
        """Persist cleaned market data."""
        # For market data, we update the raw record's stage
        # and store cleaned data in a separate table if needed
        # For now, just return the source_id as we're updating in place
        return source_id
    
    def update_source_stage(self, source_id: UUID) -> None:
        """Update raw market data processing stage to cleaned."""
        stmt = (
            select(RawMarketData)
            .where(RawMarketData.raw_market_id == source_id)
        )
        result = self._session.execute(stmt)
        record = result.scalar_one_or_none()
        
        if record:
            record.processing_stage = "cleaned"
    
    def _clean_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and validate payload fields."""
        cleaned = {}
        
        # Copy and clean numeric fields
        numeric_fields = [
            "price", "current_price", "last_price",
            "volume", "volume_24h", "total_volume",
            "market_cap", "market_cap_change_24h",
            "price_change_24h", "price_change_percentage_24h",
            "high_24h", "low_24h",
        ]
        
        for field in numeric_fields:
            if field in payload:
                value = payload[field]
                if value is not None:
                    try:
                        cleaned[field] = float(value)
                    except (ValueError, TypeError):
                        pass
        
        # Copy string fields
        string_fields = ["id", "symbol", "name"]
        for field in string_fields:
            if field in payload and payload[field]:
                cleaned[field] = str(payload[field])
        
        return cleaned
    
    def _assess_quality(
        self,
        fields_validated: List[str],
        fields_missing: List[str],
        is_duplicate: bool,
    ) -> QualityFlag:
        """Assess data quality."""
        if is_duplicate:
            return QualityFlag.DUPLICATE
        
        if fields_missing:
            return QualityFlag.MISSING_FIELDS
        
        if len(fields_validated) < 2:
            return QualityFlag.LOW_QUALITY
        
        return QualityFlag.HIGH_QUALITY


# ============================================================
# ON-CHAIN DATA CLEANER
# ============================================================


class OnChainCleaningProcessor(BaseStageProcessor[RawOnChainData, CleanedOnChainItem]):
    """
    Processor for cleaning raw on-chain data.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    - Validate blockchain identifiers (addresses, tx hashes)
    - Validate block numbers and timestamps
    - Detect duplicate transactions
    - Flag data quality issues
    
    ============================================================
    """
    
    def __init__(
        self,
        session: Session,
        config: Optional[CleaningConfig] = None,
        version: str = "1.0.0",
    ) -> None:
        super().__init__(session, DataDomain.ONCHAIN, version)
        
        self._config = config or CleaningConfig()
        self._deduplicator = Deduplicator(DeduplicatorConfig(
            exact_match_enabled=True,
            near_duplicate_enabled=False,
            version=version,
        ))
    
    @property
    def from_stage(self) -> ProcessingStage:
        return ProcessingStage.RAW
    
    @property
    def to_stage(self) -> ProcessingStage:
        return ProcessingStage.CLEANED
    
    def load_pending_records(self, limit: int = 100) -> List[RawOnChainData]:
        """Load raw on-chain data records pending cleaning."""
        stmt = (
            select(RawOnChainData)
            .where(RawOnChainData.processing_stage == "raw")
            .order_by(RawOnChainData.collected_at)
            .limit(limit)
        )
        result = self._session.execute(stmt)
        return list(result.scalars().all())
    
    def get_record_id(self, record: RawOnChainData) -> UUID:
        return record.raw_onchain_id
    
    def process_record(self, record: RawOnChainData) -> CleanedOnChainItem:
        """Clean a single on-chain data record."""
        payload = record.raw_payload or {}
        
        # Validate fields
        fields_validated: List[str] = []
        fields_missing: List[str] = []
        
        # Validate chain
        chain = record.chain
        if chain:
            fields_validated.append("chain")
        else:
            fields_missing.append("chain")
        
        # Validate block number
        block_number = record.block_number
        if block_number is not None:
            fields_validated.append("block_number")
        else:
            fields_missing.append("block_number")
        
        # Validate block timestamp
        block_timestamp = record.block_timestamp
        if block_timestamp:
            fields_validated.append("block_timestamp")
        else:
            fields_missing.append("block_timestamp")
        
        # Validate transaction hash (if applicable)
        tx_hash = record.transaction_hash
        if tx_hash:
            if self._is_valid_tx_hash(tx_hash, chain):
                fields_validated.append("transaction_hash")
            else:
                fields_missing.append("transaction_hash")
        
        # Clean payload
        cleaned_payload = self._clean_payload(payload)
        
        # Compute payload hash
        payload_hash = record.payload_hash or compute_payload_hash(payload)
        
        # Check for duplicates (by tx hash if available)
        dedup_content = tx_hash if tx_hash else str(payload)
        dedup_result = self._deduplicator.check_duplicate(
            record.raw_onchain_id,
            dedup_content,
            chain,
            record.collected_at,
        )
        
        # Determine quality flag
        quality_flag = self._assess_quality(
            fields_validated=fields_validated,
            fields_missing=fields_missing,
            is_duplicate=dedup_result.is_duplicate,
        )
        
        return CleanedOnChainItem(
            raw_onchain_id=record.raw_onchain_id,
            chain=chain,
            data_type=record.data_type,
            collected_at=record.collected_at,
            block_number=block_number,
            block_timestamp=block_timestamp,
            transaction_hash=tx_hash,
            cleaned_payload=cleaned_payload,
            payload_hash=payload_hash,
            is_duplicate=dedup_result.is_duplicate,
            fields_validated=fields_validated,
            fields_missing=fields_missing,
            quality_flag=quality_flag,
            version=self._version,
        )
    
    def persist_result(self, result: CleanedOnChainItem, source_id: UUID) -> UUID:
        """Persist cleaned on-chain data."""
        # For on-chain data, we update stage in place
        return source_id
    
    def update_source_stage(self, source_id: UUID) -> None:
        """Update raw on-chain data processing stage to cleaned."""
        stmt = (
            select(RawOnChainData)
            .where(RawOnChainData.raw_onchain_id == source_id)
        )
        result = self._session.execute(stmt)
        record = result.scalar_one_or_none()
        
        if record:
            record.processing_stage = "cleaned"
    
    def _is_valid_tx_hash(self, tx_hash: str, chain: str) -> bool:
        """Validate transaction hash format."""
        import re
        
        # Ethereum-like chains: 0x followed by 64 hex characters
        if chain.lower() in ["ethereum", "polygon", "bsc", "arbitrum", "optimism"]:
            return bool(re.match(r"^0x[a-fA-F0-9]{64}$", tx_hash))
        
        # Bitcoin: 64 hex characters (no 0x prefix)
        if chain.lower() == "bitcoin":
            return bool(re.match(r"^[a-fA-F0-9]{64}$", tx_hash))
        
        # Default: accept any non-empty string
        return bool(tx_hash)
    
    def _clean_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and validate payload fields."""
        cleaned = {}
        
        # Copy and validate numeric fields
        numeric_fields = [
            "value", "gas", "gasPrice", "gasUsed",
            "nonce", "blockNumber", "transactionIndex",
        ]
        
        for field in numeric_fields:
            if field in payload:
                value = payload[field]
                if value is not None:
                    try:
                        # Handle hex values
                        if isinstance(value, str) and value.startswith("0x"):
                            cleaned[field] = int(value, 16)
                        else:
                            cleaned[field] = int(value)
                    except (ValueError, TypeError):
                        pass
        
        # Copy string fields (addresses, hashes)
        string_fields = ["from", "to", "hash", "input", "contractAddress"]
        for field in string_fields:
            if field in payload and payload[field]:
                cleaned[field] = str(payload[field]).lower()
        
        return cleaned
    
    def _assess_quality(
        self,
        fields_validated: List[str],
        fields_missing: List[str],
        is_duplicate: bool,
    ) -> QualityFlag:
        """Assess data quality."""
        if is_duplicate:
            return QualityFlag.DUPLICATE
        
        if "chain" in fields_missing or "block_number" in fields_missing:
            return QualityFlag.MISSING_FIELDS
        
        if len(fields_missing) > 2:
            return QualityFlag.LOW_QUALITY
        
        return QualityFlag.HIGH_QUALITY
