"""
Data Processing Pipeline - Normalizers.

============================================================
PURPOSE
============================================================
Stage processors for CLEANED → NORMALIZED transition.

Handles:
- Timestamp normalization to UTC
- Symbol normalization to standard format
- Numeric precision normalization
- Text encoding normalization

============================================================
STAGE TRANSITION
============================================================
FROM: CLEANED
TO: NORMALIZED

============================================================
"""

import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_processing.pipeline.base import BaseStageProcessor
from data_processing.pipeline.types import (
    DataDomain,
    ProcessingStage,
    QualityFlag,
    NormalizationConfig,
    NormalizedNewsItem,
    NormalizedMarketItem,
    NormalizedOnChainItem,
    NormalizationError,
)
from storage.models.processed_data import ProcessedNewsData


# ============================================================
# SYMBOL NORMALIZER
# ============================================================


class SymbolNormalizer:
    """
    Normalizes cryptocurrency symbols to standard format.
    
    Examples:
        btc -> BTC
        bitcoin -> BTC
        eth-usd -> ETH/USD
        BTCUSDT -> BTC/USDT
    """
    
    # Common symbol mappings
    SYMBOL_MAP: Dict[str, str] = {
        "bitcoin": "BTC",
        "ethereum": "ETH",
        "ripple": "XRP",
        "litecoin": "LTC",
        "cardano": "ADA",
        "polkadot": "DOT",
        "solana": "SOL",
        "dogecoin": "DOGE",
        "avalanche": "AVAX",
        "chainlink": "LINK",
        "polygon": "MATIC",
        "uniswap": "UNI",
        "tether": "USDT",
        "usd-coin": "USDC",
        "binancecoin": "BNB",
        "stellar": "XLM",
        "cosmos": "ATOM",
        "near": "NEAR",
        "algorand": "ALGO",
        "fantom": "FTM",
        "arbitrum": "ARB",
        "optimism": "OP",
    }
    
    # Quote currencies
    QUOTE_CURRENCIES = {"USD", "USDT", "USDC", "BTC", "ETH", "EUR", "GBP", "JPY"}
    
    def __init__(self, normalize_to_uppercase: bool = True) -> None:
        self._normalize_to_uppercase = normalize_to_uppercase
    
    def normalize(self, symbol: str) -> str:
        """
        Normalize a symbol to standard format.
        
        Args:
            symbol: Raw symbol string
            
        Returns:
            Normalized symbol
        """
        if not symbol:
            return ""
        
        # Clean and lowercase for lookup
        clean_symbol = symbol.strip().lower()
        
        # Check direct mapping
        if clean_symbol in self.SYMBOL_MAP:
            return self.SYMBOL_MAP[clean_symbol]
        
        # Handle pairs (e.g., BTCUSD, BTC-USD, BTC/USD)
        normalized = self._normalize_pair(clean_symbol)
        
        if self._normalize_to_uppercase:
            normalized = normalized.upper()
        
        return normalized
    
    def _normalize_pair(self, symbol: str) -> str:
        """Normalize trading pair format."""
        # Remove common separators
        clean = re.sub(r"[-_]", "", symbol.upper())
        
        # Try to split into base/quote
        for quote in self.QUOTE_CURRENCIES:
            if clean.endswith(quote):
                base = clean[:-len(quote)]
                if base:
                    return f"{base}/{quote}"
        
        return symbol.upper()
    
    def extract_assets_from_text(self, text: str) -> List[str]:
        """
        Extract mentioned assets from text.
        
        Args:
            text: Text content
            
        Returns:
            List of normalized asset symbols
        """
        assets = set()
        text_lower = text.lower()
        
        # Check for full names
        for name, symbol in self.SYMBOL_MAP.items():
            if name in text_lower:
                assets.add(symbol)
        
        # Check for symbol patterns (e.g., $BTC, BTC)
        symbol_pattern = r"\b(?:\$)?([A-Z]{2,5})\b"
        matches = re.findall(symbol_pattern, text.upper())
        
        for match in matches:
            if match in self.SYMBOL_MAP.values() or match in self.QUOTE_CURRENCIES:
                assets.add(match)
        
        return sorted(assets)


# ============================================================
# TIMESTAMP NORMALIZER
# ============================================================


class TimestampNormalizer:
    """Normalizes timestamps to UTC."""
    
    def normalize_to_utc(self, dt: Optional[datetime]) -> Optional[datetime]:
        """
        Normalize datetime to UTC.
        
        Args:
            dt: Input datetime (may be naive or aware)
            
        Returns:
            UTC datetime or None
        """
        if dt is None:
            return None
        
        # If naive, assume UTC
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        
        # Convert to UTC
        return dt.astimezone(timezone.utc)
    
    def parse_timestamp(self, value: Any) -> Optional[datetime]:
        """
        Parse various timestamp formats.
        
        Args:
            value: Timestamp value (string, int, datetime)
            
        Returns:
            Parsed datetime or None
        """
        if value is None:
            return None
        
        if isinstance(value, datetime):
            return self.normalize_to_utc(value)
        
        if isinstance(value, (int, float)):
            # Unix timestamp (seconds or milliseconds)
            if value > 1e12:
                value = value / 1000  # Convert ms to seconds
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except (ValueError, OSError):
                return None
        
        if isinstance(value, str):
            return self._parse_string_timestamp(value)
        
        return None
    
    def _parse_string_timestamp(self, value: str) -> Optional[datetime]:
        """Parse string timestamp."""
        # Common formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(value, fmt)
                return self.normalize_to_utc(dt)
            except ValueError:
                continue
        
        return None


# ============================================================
# NUMERIC NORMALIZER
# ============================================================


class NumericNormalizer:
    """Normalizes numeric values to standard precision."""
    
    def __init__(
        self,
        price_decimals: int = 8,
        volume_decimals: int = 4,
        percentage_decimals: int = 4,
    ) -> None:
        self._price_decimals = price_decimals
        self._volume_decimals = volume_decimals
        self._percentage_decimals = percentage_decimals
    
    def normalize_price(self, value: Any) -> Optional[Decimal]:
        """Normalize price value."""
        return self._normalize(value, self._price_decimals)
    
    def normalize_volume(self, value: Any) -> Optional[Decimal]:
        """Normalize volume value."""
        return self._normalize(value, self._volume_decimals)
    
    def normalize_percentage(self, value: Any) -> Optional[Decimal]:
        """Normalize percentage value."""
        return self._normalize(value, self._percentage_decimals)
    
    def _normalize(self, value: Any, decimals: int) -> Optional[Decimal]:
        """Normalize value to specified decimal places."""
        if value is None:
            return None
        
        try:
            d = Decimal(str(value))
            
            # Check for invalid values
            if d.is_nan() or d.is_infinite():
                return None
            
            # Round to specified precision
            quantize_str = "0." + "0" * decimals
            return d.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)
            
        except Exception:
            return None


# ============================================================
# NEWS NORMALIZER
# ============================================================


class NewsNormalizationProcessor(BaseStageProcessor[ProcessedNewsData, NormalizedNewsItem]):
    """
    Processor for normalizing cleaned news data.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    - Normalize timestamps to UTC
    - Extract and normalize mentioned assets
    - Detect language
    - Standardize text encoding
    
    ============================================================
    """
    
    def __init__(
        self,
        session: Session,
        config: Optional[NormalizationConfig] = None,
        version: str = "1.0.0",
    ) -> None:
        super().__init__(session, DataDomain.NEWS, version)
        
        self._config = config or NormalizationConfig()
        self._symbol_normalizer = SymbolNormalizer(
            normalize_to_uppercase=self._config.normalize_to_uppercase
        )
        self._timestamp_normalizer = TimestampNormalizer()
    
    @property
    def from_stage(self) -> ProcessingStage:
        return ProcessingStage.CLEANED
    
    @property
    def to_stage(self) -> ProcessingStage:
        return ProcessingStage.NORMALIZED
    
    def load_pending_records(self, limit: int = 100) -> List[ProcessedNewsData]:
        """Load cleaned news records pending normalization."""
        stmt = (
            select(ProcessedNewsData)
            .where(ProcessedNewsData.processing_stage == "cleaned")
            .order_by(ProcessedNewsData.processed_at)
            .limit(limit)
        )
        result = self._session.execute(stmt)
        return list(result.scalars().all())
    
    def get_record_id(self, record: ProcessedNewsData) -> UUID:
        return record.processed_news_id
    
    def process_record(self, record: ProcessedNewsData) -> NormalizedNewsItem:
        """Normalize a single news record."""
        # Normalize timestamps
        collected_at_utc = self._timestamp_normalizer.normalize_to_utc(record.collected_at)
        published_at_utc = self._timestamp_normalizer.normalize_to_utc(record.published_at)
        
        if collected_at_utc is None:
            collected_at_utc = datetime.now(timezone.utc)
        
        # Extract mentioned assets
        text_content = f"{record.title} {record.content or ''}"
        assets_mentioned = self._symbol_normalizer.extract_assets_from_text(text_content)
        
        # Detect language (simple heuristic)
        language_detected = self._detect_language(record.content or record.title)
        
        # Normalize text encoding
        title = self._normalize_encoding(record.title)
        content = self._normalize_encoding(record.content) if record.content else None
        summary = self._normalize_encoding(record.summary) if record.summary else None
        
        # Determine quality flag
        quality_flag = self._assess_quality(record)
        
        return NormalizedNewsItem(
            raw_news_id=record.raw_news_id,
            source=record.source,
            collected_at_utc=collected_at_utc,
            published_at_utc=published_at_utc,
            title=title,
            content=content,
            summary=summary,
            url=record.url,
            author=record.author,
            assets_mentioned=assets_mentioned,
            language_detected=language_detected,
            word_count=record.word_count or 0,
            content_hash=record.content_hash,
            quality_flag=quality_flag,
            version=self._version,
        )
    
    def persist_result(self, result: NormalizedNewsItem, source_id: UUID) -> UUID:
        """Persist normalized news data."""
        # Update the existing ProcessedNewsData record
        stmt = select(ProcessedNewsData).where(
            ProcessedNewsData.processed_news_id == source_id
        )
        record = self._session.execute(stmt).scalar_one_or_none()
        
        if record:
            record.assets_mentioned = result.assets_mentioned
            record.language_detected = result.language_detected
            record.processing_stage = "normalized"
        
        return source_id
    
    def update_source_stage(self, source_id: UUID) -> None:
        """Update is done in persist_result."""
        pass
    
    def _detect_language(self, text: str) -> str:
        """
        Simple language detection heuristic.
        
        Returns 'en' for English, 'unknown' otherwise.
        """
        if not text:
            return "unknown"
        
        # Simple heuristic: check for common English words
        english_words = {
            "the", "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "do", "does", "did",
            "and", "or", "but", "for", "with", "at", "by",
            "from", "to", "in", "on", "of", "a", "an",
        }
        
        words = text.lower().split()
        english_count = sum(1 for w in words if w in english_words)
        
        if len(words) > 0 and english_count / len(words) > 0.1:
            return "en"
        
        return "unknown"
    
    def _normalize_encoding(self, text: str) -> str:
        """Ensure text is properly encoded."""
        if not text:
            return ""
        
        try:
            # Encode and decode to ensure valid UTF-8
            return text.encode(self._config.target_encoding, errors="replace").decode(
                self._config.target_encoding
            )
        except Exception:
            return text
    
    def _assess_quality(self, record: ProcessedNewsData) -> QualityFlag:
        """Assess quality after normalization."""
        if record.is_duplicate:
            return QualityFlag.DUPLICATE
        
        if not record.title:
            return QualityFlag.MISSING_FIELDS
        
        if (record.word_count or 0) < 10:
            return QualityFlag.LOW_QUALITY
        
        return QualityFlag.HIGH_QUALITY


# ============================================================
# MARKET DATA NORMALIZER
# ============================================================


class MarketNormalizationProcessor(BaseStageProcessor[dict, NormalizedMarketItem]):
    """
    Processor for normalizing cleaned market data.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    - Normalize timestamps to UTC
    - Normalize symbol format
    - Normalize numeric precision
    - Handle different source formats
    
    ============================================================
    """
    
    def __init__(
        self,
        session: Session,
        config: Optional[NormalizationConfig] = None,
        version: str = "1.0.0",
    ) -> None:
        super().__init__(session, DataDomain.MARKET, version)
        
        self._config = config or NormalizationConfig()
        self._symbol_normalizer = SymbolNormalizer(
            normalize_to_uppercase=self._config.normalize_to_uppercase
        )
        self._timestamp_normalizer = TimestampNormalizer()
        self._numeric_normalizer = NumericNormalizer(
            price_decimals=self._config.price_decimal_places,
            volume_decimals=self._config.volume_decimal_places,
            percentage_decimals=self._config.percentage_decimal_places,
        )
    
    @property
    def from_stage(self) -> ProcessingStage:
        return ProcessingStage.CLEANED
    
    @property
    def to_stage(self) -> ProcessingStage:
        return ProcessingStage.NORMALIZED
    
    def load_pending_records(self, limit: int = 100) -> List[dict]:
        """Load cleaned market data records pending normalization."""
        from storage.models.raw_data import RawMarketData
        
        stmt = (
            select(RawMarketData)
            .where(RawMarketData.processing_stage == "cleaned")
            .order_by(RawMarketData.collected_at)
            .limit(limit)
        )
        result = self._session.execute(stmt)
        
        # Convert to dicts with needed fields
        records = []
        for r in result.scalars().all():
            records.append({
                "raw_market_id": r.raw_market_id,
                "source": r.source,
                "symbol": r.symbol,
                "data_type": r.data_type,
                "collected_at": r.collected_at,
                "source_timestamp": getattr(r, 'source_timestamp', None),
                "payload": r.raw_payload,
            })
        
        return records
    
    def get_record_id(self, record: dict) -> UUID:
        return record["raw_market_id"]
    
    def process_record(self, record: dict) -> NormalizedMarketItem:
        """Normalize a single market data record."""
        # Normalize symbol
        symbol_normalized = self._symbol_normalizer.normalize(record["symbol"])
        
        # Normalize timestamps
        collected_at_utc = self._timestamp_normalizer.normalize_to_utc(record["collected_at"])
        source_timestamp_utc = self._timestamp_normalizer.parse_timestamp(
            record.get("source_timestamp")
        )
        
        if collected_at_utc is None:
            collected_at_utc = datetime.now(timezone.utc)
        
        payload = record.get("payload", {})
        
        # Extract and normalize numeric values
        price = self._numeric_normalizer.normalize_price(
            payload.get("current_price") or payload.get("price")
        )
        volume_24h = self._numeric_normalizer.normalize_volume(
            payload.get("total_volume") or payload.get("volume_24h")
        )
        market_cap = self._numeric_normalizer.normalize_price(
            payload.get("market_cap")
        )
        change_24h_pct = self._numeric_normalizer.normalize_percentage(
            payload.get("price_change_percentage_24h")
        )
        
        # Build normalized payload
        normalized_payload = {
            k: v for k, v in {
                "price": str(price) if price else None,
                "volume_24h": str(volume_24h) if volume_24h else None,
                "market_cap": str(market_cap) if market_cap else None,
                "change_24h_pct": str(change_24h_pct) if change_24h_pct else None,
                "high_24h": str(self._numeric_normalizer.normalize_price(payload.get("high_24h"))) if payload.get("high_24h") else None,
                "low_24h": str(self._numeric_normalizer.normalize_price(payload.get("low_24h"))) if payload.get("low_24h") else None,
            }.items() if v is not None
        }
        
        # Determine quality flag
        quality_flag = QualityFlag.HIGH_QUALITY
        if price is None and volume_24h is None:
            quality_flag = QualityFlag.MISSING_FIELDS
        
        return NormalizedMarketItem(
            raw_market_id=record["raw_market_id"],
            source=record["source"],
            symbol_normalized=symbol_normalized,
            data_type=record["data_type"],
            collected_at_utc=collected_at_utc,
            source_timestamp_utc=source_timestamp_utc,
            price=price,
            volume_24h=volume_24h,
            market_cap=market_cap,
            change_24h_pct=change_24h_pct,
            normalized_payload=normalized_payload,
            quality_flag=quality_flag,
            version=self._version,
        )
    
    def persist_result(self, result: NormalizedMarketItem, source_id: UUID) -> UUID:
        """Persist normalized market data."""
        from storage.models.raw_data import RawMarketData
        
        stmt = select(RawMarketData).where(RawMarketData.raw_market_id == source_id)
        record = self._session.execute(stmt).scalar_one_or_none()
        
        if record:
            record.processing_stage = "normalized"
        
        return source_id
    
    def update_source_stage(self, source_id: UUID) -> None:
        """Update is done in persist_result."""
        pass


# ============================================================
# ON-CHAIN DATA NORMALIZER
# ============================================================


class OnChainNormalizationProcessor(BaseStageProcessor[dict, NormalizedOnChainItem]):
    """
    Processor for normalizing cleaned on-chain data.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    - Normalize chain identifiers
    - Normalize addresses (checksums)
    - Normalize timestamps to UTC
    - Normalize values to standard precision
    
    ============================================================
    """
    
    # Chain name mapping
    CHAIN_MAP: Dict[str, str] = {
        "eth": "ETHEREUM",
        "ethereum": "ETHEREUM",
        "btc": "BITCOIN",
        "bitcoin": "BITCOIN",
        "bnb": "BSC",
        "bsc": "BSC",
        "polygon": "POLYGON",
        "matic": "POLYGON",
        "arbitrum": "ARBITRUM",
        "arb": "ARBITRUM",
        "optimism": "OPTIMISM",
        "op": "OPTIMISM",
        "avalanche": "AVALANCHE",
        "avax": "AVALANCHE",
        "solana": "SOLANA",
        "sol": "SOLANA",
    }
    
    def __init__(
        self,
        session: Session,
        config: Optional[NormalizationConfig] = None,
        version: str = "1.0.0",
    ) -> None:
        super().__init__(session, DataDomain.ONCHAIN, version)
        
        self._config = config or NormalizationConfig()
        self._timestamp_normalizer = TimestampNormalizer()
        self._numeric_normalizer = NumericNormalizer()
    
    @property
    def from_stage(self) -> ProcessingStage:
        return ProcessingStage.CLEANED
    
    @property
    def to_stage(self) -> ProcessingStage:
        return ProcessingStage.NORMALIZED
    
    def load_pending_records(self, limit: int = 100) -> List[dict]:
        """Load cleaned on-chain data records pending normalization."""
        from storage.models.raw_data import RawOnChainData
        
        stmt = (
            select(RawOnChainData)
            .where(RawOnChainData.processing_stage == "cleaned")
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
                "collected_at": r.collected_at,
                "block_number": r.block_number,
                "block_timestamp": r.block_timestamp,
                "transaction_hash": r.transaction_hash,
                "address": r.address,
                "payload": r.raw_payload,
            })
        
        return records
    
    def get_record_id(self, record: dict) -> UUID:
        return record["raw_onchain_id"]
    
    def process_record(self, record: dict) -> NormalizedOnChainItem:
        """Normalize a single on-chain data record."""
        # Normalize chain
        chain_normalized = self._normalize_chain(record["chain"])
        
        # Normalize timestamps
        collected_at_utc = self._timestamp_normalizer.normalize_to_utc(record["collected_at"])
        block_timestamp_utc = self._timestamp_normalizer.parse_timestamp(
            record.get("block_timestamp")
        )
        
        if collected_at_utc is None:
            collected_at_utc = datetime.now(timezone.utc)
        
        # Normalize transaction hash
        tx_hash = record.get("transaction_hash")
        tx_hash_normalized = tx_hash.lower() if tx_hash else None
        
        # Normalize address
        address = record.get("address")
        address_normalized = self._normalize_address(address, chain_normalized) if address else None
        
        payload = record.get("payload", {})
        
        # Normalize values
        value_native = self._numeric_normalizer.normalize_price(
            payload.get("value")
        )
        value_usd = self._numeric_normalizer.normalize_price(
            payload.get("valueUsd") or payload.get("value_usd")
        )
        gas_used = payload.get("gasUsed")
        if gas_used is not None:
            try:
                gas_used = int(gas_used)
            except (ValueError, TypeError):
                gas_used = None
        
        # Build normalized payload
        normalized_payload = {
            k: v for k, v in {
                "from": payload.get("from", "").lower() if payload.get("from") else None,
                "to": payload.get("to", "").lower() if payload.get("to") else None,
                "value": str(value_native) if value_native else None,
                "gas_used": gas_used,
            }.items() if v is not None
        }
        
        # Determine quality flag
        quality_flag = QualityFlag.HIGH_QUALITY
        if not tx_hash_normalized and not record.get("block_number"):
            quality_flag = QualityFlag.MISSING_FIELDS
        
        return NormalizedOnChainItem(
            raw_onchain_id=record["raw_onchain_id"],
            chain_normalized=chain_normalized,
            data_type=record["data_type"],
            collected_at_utc=collected_at_utc,
            block_timestamp_utc=block_timestamp_utc,
            block_number=record.get("block_number"),
            transaction_hash_normalized=tx_hash_normalized,
            address_normalized=address_normalized,
            value_native=value_native,
            value_usd=value_usd,
            gas_used=gas_used,
            normalized_payload=normalized_payload,
            quality_flag=quality_flag,
            version=self._version,
        )
    
    def persist_result(self, result: NormalizedOnChainItem, source_id: UUID) -> UUID:
        """Persist normalized on-chain data."""
        from storage.models.raw_data import RawOnChainData
        
        stmt = select(RawOnChainData).where(RawOnChainData.raw_onchain_id == source_id)
        record = self._session.execute(stmt).scalar_one_or_none()
        
        if record:
            record.processing_stage = "normalized"
        
        return source_id
    
    def update_source_stage(self, source_id: UUID) -> None:
        """Update is done in persist_result."""
        pass
    
    def _normalize_chain(self, chain: str) -> str:
        """Normalize chain identifier."""
        if not chain:
            return "UNKNOWN"
        
        clean = chain.lower().strip()
        return self.CHAIN_MAP.get(clean, chain.upper())
    
    def _normalize_address(self, address: str, chain: str) -> str:
        """Normalize blockchain address."""
        if not address:
            return ""
        
        # For EVM chains, lowercase
        if chain in ["ETHEREUM", "BSC", "POLYGON", "ARBITRUM", "OPTIMISM", "AVALANCHE"]:
            return address.lower()
        
        return address
