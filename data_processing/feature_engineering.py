"""Feature extraction processors for LABELED → FEATURE_READY stage."""

import hashlib
import json
import logging
import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_processing.pipeline.base import BaseStageProcessor
from data_processing.pipeline.normalizers import SymbolNormalizer, TimestampNormalizer
from data_processing.pipeline.types import (
   DataDomain,
   FeatureConfig,
   FeatureExtractionError,
   FeatureReadyMarketItem,
   FeatureReadyNewsItem,
   FeatureReadyOnChainItem,
   ProcessingStage,
   QualityFlag,
)
from storage.models.processed_data import (
   ProcessedNewsData,
   TopicClassification,
   RiskKeywordDetection,
   NewsFeatureVector,
   MarketFeatureVector,
   OnChainFeatureVector,
)
from storage.models.raw_data import RawMarketData, RawOnChainData


# ============================================================
# HELPERS
# ============================================================


def _safe_float(value: Any) -> Optional[float]:
   """Convert arbitrary input to float when possible."""
   if value is None:
      return None
   try:
      return float(value)
   except (TypeError, ValueError):
      return None


def _log_value(value: Optional[float]) -> Optional[float]:
   """Return log-scaled value for wide-range metrics."""
   if value is None or value <= 0:
      return None
   return math.log1p(value)


def _ensure_utc(timestamp: Optional[datetime]) -> Optional[datetime]:
   """Ensure timestamps are timezone-aware UTC values."""
   if timestamp is None:
      return None
   if timestamp.tzinfo is None:
      return timestamp.replace(tzinfo=timezone.utc)
   return timestamp.astimezone(timezone.utc)


class FeatureSanitizer:
   """Utility for keeping feature payloads numeric and deterministic."""
    
   @staticmethod
   def as_float_map(features: Dict[str, Optional[float]]) -> Dict[str, float]:
      clean: Dict[str, float] = {}
      for key, value in features.items():
         if value is None:
            continue
         try:
            numeric = float(value)
         except (TypeError, ValueError):
            continue
         if math.isnan(numeric) or math.isinf(numeric):
            continue
         clean[key] = numeric
      return clean


class FeatureHasher:
   """Creates deterministic hashes for feature payloads."""
    
   @staticmethod
   def compute(features: Dict[str, float], version: str) -> str:
      payload = {
         "version": version,
         "features": {k: features[k] for k in sorted(features)},
      }
      serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
      return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class TextFeatureExtractor:
   """Extract deterministic structural features from text."""
    
   SENTENCE_DELIMS = {".", "!", "?"}
   PUNCTUATION = set(".,;:!?\"'()[]{}")
    
   def extract(self, text: str) -> Dict[str, float]:
      normalized = text or ""
      char_count = len(normalized)
      words = normalized.split()
      word_count = len(words)
      sentence_count = max(1, sum(1 for ch in normalized if ch in self.SENTENCE_DELIMS))
      unique_words = {w.strip(".,;:!?\"'").lower() for w in words if w}
      uppercase_count = sum(1 for ch in normalized if ch.isupper())
      digit_count = sum(1 for ch in normalized if ch.isdigit())
      punct_count = sum(1 for ch in normalized if ch in self.PUNCTUATION)
      features: Dict[str, Optional[float]] = {
         "text_char_count": float(char_count),
         "text_word_count": float(word_count),
         "text_sentence_count": float(sentence_count),
         "text_avg_word_length": (sum(len(w) for w in words) / word_count) if word_count else 0.0,
         "text_avg_sentence_length": (word_count / sentence_count) if sentence_count else 0.0,
         "text_unique_word_ratio": (len(unique_words) / word_count) if word_count else 0.0,
         "text_uppercase_ratio": (uppercase_count / char_count) if char_count else 0.0,
         "text_digit_ratio": (digit_count / char_count) if char_count else 0.0,
         "text_punctuation_ratio": (punct_count / char_count) if char_count else 0.0,
         "text_url_count": float(normalized.count("http://") + normalized.count("https://")),
         "text_mention_count": float(normalized.count("@")),
         "text_hashtag_count": float(normalized.count("#")),
      }
      return FeatureSanitizer.as_float_map(features)


class TemporalFeatureBuilder:
   """Extract calendar-based features from timestamps."""
    
   def build(self, timestamp: Optional[datetime]) -> Dict[str, float]:
      ts = _ensure_utc(timestamp)
      if ts is None:
         return {}
      iso_calendar = ts.isocalendar()
      features = {
         "temporal_hour_of_day": float(ts.hour),
         "temporal_day_of_week": float(ts.weekday()),
         "temporal_is_weekend": 1.0 if ts.weekday() >= 5 else 0.0,
         "temporal_month": float(ts.month),
         "temporal_week_of_year": float(iso_calendar[1]),
         "temporal_quarter": float((ts.month - 1) // 3 + 1),
         "temporal_is_us_market_hours": 1.0 if 13 <= ts.hour < 21 and ts.weekday() < 5 else 0.0,
         "temporal_is_asia_session": 1.0 if 0 <= ts.hour < 9 else 0.0,
         "temporal_is_eu_session": 1.0 if 7 <= ts.hour < 16 and ts.weekday() < 5 else 0.0,
      }
      return features


# ============================================================
# NEWS FEATURE PROCESSOR
# ============================================================


class NewsFeatureProcessor(BaseStageProcessor[ProcessedNewsData, FeatureReadyNewsItem]):
   """Extract structural, temporal, and label-derived features for news."""
    
   def __init__(
      self,
      session: Session,
      config: Optional[FeatureConfig] = None,
      version: str = "1.0.0",
   ) -> None:
      super().__init__(session, DataDomain.NEWS, version)
      self._config = config or FeatureConfig()
      self._text_extractor = TextFeatureExtractor()
      self._temporal_builder = TemporalFeatureBuilder()
      self._timestamp_normalizer = TimestampNormalizer()
      self._logger = logging.getLogger("processor.news_features")
    
   @property
   def from_stage(self) -> ProcessingStage:
      return ProcessingStage.LABELED
    
   @property
   def to_stage(self) -> ProcessingStage:
      return ProcessingStage.FEATURE_READY
    
   def load_pending_records(self, limit: int = 100) -> List[ProcessedNewsData]:
      stmt = (
         select(ProcessedNewsData)
         .where(ProcessedNewsData.processing_stage == "labeled")
         .order_by(ProcessedNewsData.processed_at)
         .limit(limit)
      )
      result = self._session.execute(stmt)
      return list(result.scalars().all())
    
   def get_record_id(self, record: ProcessedNewsData) -> UUID:
      return record.processed_news_id
    
   def process_record(self, record: ProcessedNewsData) -> FeatureReadyNewsItem:
      text_payload = " ".join(filter(None, [record.title, record.content]))
      text_features = self._text_extractor.extract(text_payload)
      temporal_features = self._temporal_builder.build(record.published_at)
      topic_meta = self._load_topic_metadata(record.processed_news_id)
      risk_meta = self._load_risk_metadata(record.processed_news_id)
      asset_mentions = len(record.assets_mentioned or [])
      features: Dict[str, Optional[float]] = {}
      features.update(text_features)
      features.update(temporal_features)
      features.update(topic_meta["scores"])
      features.update({
         "news_asset_mention_count": float(asset_mentions),
         "news_risk_keyword_total": float(risk_meta["total"]),
      })
      for category, count in risk_meta["by_category"].items():
         features[f"news_risk_kw_{category}_count"] = float(count)
      features["news_has_summary"] = 1.0 if record.summary else 0.0
      features["news_has_author"] = 1.0 if record.author else 0.0
      features["news_content_hash_entropy"] = self._hash_entropy(record.content_hash)
      payload = FeatureSanitizer.as_float_map(features)
      if not payload:
         raise FeatureExtractionError(
            "No features extracted for news record",
            record_id=record.processed_news_id,
         )
      collected_at_utc = _ensure_utc(record.collected_at) or datetime.now(timezone.utc)
      quality_flag = self._assess_quality(payload)
      primary_topics = topic_meta["topics"]
      news_category = topic_meta["primary"]
      return FeatureReadyNewsItem(
         raw_news_id=record.raw_news_id,
         source=record.source,
         collected_at_utc=collected_at_utc,
         news_category=news_category,
         primary_topics=primary_topics,
         features=payload,
         feature_version=self._version,
         quality_flag=quality_flag,
      )
    
   def persist_result(self, result: FeatureReadyNewsItem, source_id: UUID) -> UUID:
      stmt = select(ProcessedNewsData).where(ProcessedNewsData.processed_news_id == source_id)
      entity = self._session.execute(stmt).scalar_one_or_none()
      if entity:
         entity.processing_stage = "feature_ready"
      feature_hash = FeatureHasher.compute(result.features, self._version)
      vector = NewsFeatureVector(
         processed_news_id=source_id,
         raw_news_id=result.raw_news_id,
         feature_version=self._version,
         feature_hash=feature_hash,
         features=result.features,
         quality_flag=result.quality_flag.value,
      )
      self._session.add(vector)
      self._session.flush()
      return vector.feature_vector_id
    
   def update_source_stage(self, source_id: UUID) -> None:
      # Stage update handled in persist_result.
      pass
    
   def _load_topic_metadata(self, processed_news_id: UUID) -> Dict[str, Any]:
      stmt = (
         select(TopicClassification)
         .where(TopicClassification.processed_news_id == processed_news_id)
         .order_by(TopicClassification.confidence_score.desc())
      )
      rows = self._session.execute(stmt).scalars().all()
      scores: Dict[str, float] = {}
      ordered: List[tuple[str, float]] = []
      primary_topic: Optional[str] = None
      for row in rows:
         score = float(row.confidence_score)
         scores[f"topic_conf_{row.topic}"] = score
         ordered.append((row.topic, score))
         if row.is_primary_topic:
            primary_topic = row.topic
      ordered.sort(key=lambda item: item[1], reverse=True)
      top_topics = [topic for topic, _ in ordered[:3]] or ["other"]
      if primary_topic is None:
         primary_topic = top_topics[0]
      return {
         "primary": primary_topic,
         "topics": top_topics,
         "scores": scores,
      }
    
   def _load_risk_metadata(self, processed_news_id: UUID) -> Dict[str, Any]:
      stmt = select(RiskKeywordDetection).where(
         RiskKeywordDetection.processed_news_id == processed_news_id
      )
      rows = self._session.execute(stmt).scalars().all()
      counter: Counter[str] = Counter()
      for row in rows:
         counter[row.category] += 1
      return {
         "total": sum(counter.values()),
         "by_category": dict(counter),
      }
    
   def _hash_entropy(self, content_hash: str) -> float:
      if not content_hash:
         return 0.0
      counts = Counter(content_hash)
      total = float(len(content_hash))
      entropy = 0.0
      for occurrences in counts.values():
         p = occurrences / total
         entropy -= p * math.log2(p)
      return entropy
    
   def _assess_quality(self, features: Dict[str, float]) -> QualityFlag:
      word_count = features.get("text_word_count", 0.0)
      if word_count < 10:
         return QualityFlag.LOW_QUALITY
      if features.get("news_asset_mention_count", 0.0) == 0 and features.get("text_char_count", 0.0) < 200:
         return QualityFlag.LOW_QUALITY
      return QualityFlag.HIGH_QUALITY


# ============================================================
# MARKET FEATURE PROCESSOR
# ============================================================


class MarketFeatureProcessor(BaseStageProcessor[RawMarketData, FeatureReadyMarketItem]):
   """Extract descriptive market data features."""
    
   def __init__(
      self,
      session: Session,
      config: Optional[FeatureConfig] = None,
      version: str = "1.0.0",
   ) -> None:
      super().__init__(session, DataDomain.MARKET, version)
      self._config = config or FeatureConfig()
      self._symbol_normalizer = SymbolNormalizer()
      self._timestamp_normalizer = TimestampNormalizer()
      self._logger = logging.getLogger("processor.market_features")
    
   @property
   def from_stage(self) -> ProcessingStage:
      return ProcessingStage.LABELED
    
   @property
   def to_stage(self) -> ProcessingStage:
      return ProcessingStage.FEATURE_READY
    
   def load_pending_records(self, limit: int = 100) -> List[RawMarketData]:
      stmt = (
         select(RawMarketData)
         .where(RawMarketData.processing_stage == "labeled")
         .order_by(RawMarketData.collected_at)
         .limit(limit)
      )
      result = self._session.execute(stmt)
      return list(result.scalars().all())
    
   def get_record_id(self, record: RawMarketData) -> UUID:
      return record.raw_market_id
    
   def process_record(self, record: RawMarketData) -> FeatureReadyMarketItem:
      payload = record.raw_payload or {}
      price = _safe_float(payload.get("current_price") or payload.get("price"))
      price_change = _safe_float(payload.get("price_change_24h"))
      price_change_pct = _safe_float(payload.get("price_change_percentage_24h"))
      high_24h = _safe_float(payload.get("high_24h"))
      low_24h = _safe_float(payload.get("low_24h"))
      volume = _safe_float(payload.get("total_volume") or payload.get("volume_24h"))
      market_cap = _safe_float(payload.get("market_cap"))
      collected_at_utc = self._timestamp_normalizer.normalize_to_utc(record.collected_at) or datetime.now(timezone.utc)
      age_minutes = (datetime.now(timezone.utc) - collected_at_utc).total_seconds() / 60.0
      features: Dict[str, Optional[float]] = {
         "market_price_log": _log_value(price),
         "market_price_abs_change": abs(price_change) if price_change is not None else None,
         "market_price_change_ratio": (price_change / price) if price and price_change else None,
         "market_price_change_pct_abs": abs(price_change_pct) if price_change_pct is not None else None,
         "market_range_pct": ((high_24h - low_24h) / low_24h) if high_24h and low_24h and low_24h > 0 else None,
         "market_volume_log": _log_value(volume),
         "market_volume_to_market_cap": (volume / market_cap) if volume and market_cap else None,
         "market_market_cap_log": _log_value(market_cap),
         "market_data_age_minutes": max(age_minutes, 0.0),
      }
      quality_flag = QualityFlag.HIGH_QUALITY if price is not None else QualityFlag.LOW_QUALITY
      payload_sanitized = FeatureSanitizer.as_float_map(features)
      if not payload_sanitized:
         raise FeatureExtractionError(
            "No features extracted for market record",
            record_id=record.raw_market_id,
         )
      symbol_normalized = self._symbol_normalizer.normalize(record.symbol)
      return FeatureReadyMarketItem(
         raw_market_id=record.raw_market_id,
         source=record.source,
         symbol_normalized=symbol_normalized,
         collected_at_utc=collected_at_utc,
         features=payload_sanitized,
         feature_version=self._version,
         quality_flag=quality_flag,
      )
    
   def persist_result(self, result: FeatureReadyMarketItem, source_id: UUID) -> UUID:
      stmt = select(RawMarketData).where(RawMarketData.raw_market_id == source_id)
      entity = self._session.execute(stmt).scalar_one_or_none()
      if entity:
         entity.processing_stage = "feature_ready"
      feature_hash = FeatureHasher.compute(result.features, self._version)
      vector = MarketFeatureVector(
         raw_market_id=source_id,
         source=result.source,
         symbol_normalized=result.symbol_normalized,
         collected_at=result.collected_at_utc,
         feature_version=self._version,
         feature_hash=feature_hash,
         features=result.features,
         quality_flag=result.quality_flag.value,
      )
      self._session.add(vector)
      self._session.flush()
      return vector.feature_vector_id
    
   def update_source_stage(self, source_id: UUID) -> None:
      pass


# ============================================================
# ON-CHAIN FEATURE PROCESSOR
# ============================================================


class OnChainFeatureProcessor(BaseStageProcessor[RawOnChainData, FeatureReadyOnChainItem]):
   """Extract deterministic features from on-chain activity."""
    
   LAYER2_CHAINS = {"ARBITRUM", "OPTIMISM", "POLYGON"}
    
   def __init__(
      self,
      session: Session,
      config: Optional[FeatureConfig] = None,
      version: str = "1.0.0",
   ) -> None:
      super().__init__(session, DataDomain.ONCHAIN, version)
      self._config = config or FeatureConfig()
      self._timestamp_normalizer = TimestampNormalizer()
      self._logger = logging.getLogger("processor.onchain_features")
    
   @property
   def from_stage(self) -> ProcessingStage:
      return ProcessingStage.LABELED
    
   @property
   def to_stage(self) -> ProcessingStage:
      return ProcessingStage.FEATURE_READY
    
   def load_pending_records(self, limit: int = 100) -> List[RawOnChainData]:
      stmt = (
         select(RawOnChainData)
         .where(RawOnChainData.processing_stage == "labeled")
         .order_by(RawOnChainData.collected_at)
         .limit(limit)
      )
      result = self._session.execute(stmt)
      return list(result.scalars().all())
    
   def get_record_id(self, record: RawOnChainData) -> UUID:
      return record.raw_onchain_id
    
   def process_record(self, record: RawOnChainData) -> FeatureReadyOnChainItem:
      payload = record.raw_payload or {}
      chain_normalized = self._normalize_chain(record.chain)
      collected_at_utc = self._timestamp_normalizer.normalize_to_utc(record.collected_at) or datetime.now(timezone.utc)
      value_native = _safe_float(payload.get("value"))
      value_usd = _safe_float(payload.get("valueUsd") or payload.get("value_usd"))
      gas_used = _safe_float(payload.get("gasUsed") or payload.get("gas"))
      gas_price = _safe_float(payload.get("gasPrice"))
      input_data = payload.get("input") or ""
      address_from = payload.get("from")
      address_to = payload.get("to")
      features: Dict[str, Optional[float]] = {
         "onchain_value_usd_log": _log_value(value_usd),
         "onchain_value_native_log": _log_value(value_native),
         "onchain_gas_used_log": _log_value(gas_used),
         "onchain_gas_price_log": _log_value(gas_price),
         "onchain_input_length": float(len(input_data)) if input_data else 0.0,
         "onchain_has_contract_call": 1.0 if input_data and len(input_data) > 10 else 0.0,
         "onchain_has_to_address": 1.0 if address_to else 0.0,
         "onchain_has_from_address": 1.0 if address_from else 0.0,
         "onchain_is_layer2": 1.0 if chain_normalized in self.LAYER2_CHAINS else 0.0,
         "onchain_data_age_minutes": (datetime.now(timezone.utc) - collected_at_utc).total_seconds() / 60.0,
         "onchain_is_large_transfer": 1.0 if value_usd and value_usd >= 100000 else 0.0,
      }
      payload_sanitized = FeatureSanitizer.as_float_map(features)
      if not payload_sanitized:
         raise FeatureExtractionError(
            "No features extracted for on-chain record",
            record_id=record.raw_onchain_id,
         )
      quality_flag = self._assess_quality(value_usd, payload_sanitized)
      return FeatureReadyOnChainItem(
         raw_onchain_id=record.raw_onchain_id,
         chain_normalized=chain_normalized,
         collected_at_utc=collected_at_utc,
         features=payload_sanitized,
         feature_version=self._version,
         quality_flag=quality_flag,
      )
    
   def persist_result(self, result: FeatureReadyOnChainItem, source_id: UUID) -> UUID:
      stmt = select(RawOnChainData).where(RawOnChainData.raw_onchain_id == source_id)
      entity = self._session.execute(stmt).scalar_one_or_none()
      if entity:
         entity.processing_stage = "feature_ready"
      feature_hash = FeatureHasher.compute(result.features, self._version)
      vector = OnChainFeatureVector(
         raw_onchain_id=source_id,
         chain_normalized=result.chain_normalized,
         data_type=entity.data_type if entity else "unknown",
         collected_at=result.collected_at_utc,
         feature_version=self._version,
         feature_hash=feature_hash,
         features=result.features,
         quality_flag=result.quality_flag.value,
      )
      self._session.add(vector)
      self._session.flush()
      return vector.feature_vector_id
    
   def update_source_stage(self, source_id: UUID) -> None:
      pass
    
   def _normalize_chain(self, chain: Optional[str]) -> str:
      if not chain:
         return "UNKNOWN"
      mapping = {
         "eth": "ETHEREUM",
         "ethereum": "ETHEREUM",
         "btc": "BITCOIN",
         "bitcoin": "BITCOIN",
         "bsc": "BSC",
         "binance": "BSC",
         "matic": "POLYGON",
         "polygon": "POLYGON",
         "avax": "AVALANCHE",
         "avalanche": "AVALANCHE",
         "arb": "ARBITRUM",
         "arbitrum": "ARBITRUM",
         "op": "OPTIMISM",
         "optimism": "OPTIMISM",
         "sol": "SOLANA",
         "solana": "SOLANA",
      }
      normalized = mapping.get(chain.lower()) if hasattr(chain, "lower") else None
      return normalized or chain.upper()
    
   def _assess_quality(self, value_usd: Optional[float], features: Dict[str, float]) -> QualityFlag:
      if value_usd is None and features.get("onchain_value_native_log") is None:
         return QualityFlag.INCOMPLETE
      if features.get("onchain_input_length", 0.0) < 5 and features.get("onchain_value_usd_log") is None:
         return QualityFlag.LOW_QUALITY
      return QualityFlag.HIGH_QUALITY
