"""
Sentiment Normalization Pipeline - Combines and normalizes sentiment from multiple sources.

SAFETY: Aggregated sentiment is CONTEXT ONLY - never a standalone trade trigger.

This pipeline:
1. Collects sentiment from multiple sources
2. Weights by source reliability
3. Aggregates into unified sentiment score
4. Detects conflicting signals
5. Provides confidence measure
"""

import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Optional

from .models import (
    AggregatedSentiment,
    EventType,
    SentimentCategory,
    SentimentData,
    SentimentRequest,
)


logger = logging.getLogger(__name__)


class SentimentPipeline:
    """
    Pipeline for normalizing and aggregating sentiment data.
    
    Takes raw sentiment from multiple sources and produces
    a unified, weighted sentiment score with confidence measure.
    
    SAFETY REMINDER: Output is CONTEXT ONLY, never a trade trigger.
    """
    
    # Minimum data points for reasonable confidence
    MIN_DATA_POINTS_FOR_CONFIDENCE = 5
    
    # Agreement threshold for high confidence
    AGREEMENT_THRESHOLD = 0.7  # 70% agreement
    
    def __init__(
        self,
        recency_weight: float = 0.3,  # How much to weight recent data
        recency_hours: int = 4,  # What counts as "recent"
    ) -> None:
        self.recency_weight = recency_weight
        self.recency_hours = recency_hours
    
    def aggregate(
        self,
        sentiments: list[SentimentData],
        symbol: Optional[str] = None,
        time_range_hours: int = 24,
    ) -> AggregatedSentiment:
        """
        Aggregate multiple sentiment data points into unified output.
        
        Args:
            sentiments: List of sentiment data from various sources
            symbol: Primary symbol to filter for (optional)
            time_range_hours: Time range of the data
            
        Returns:
            AggregatedSentiment with weighted score and confidence
        """
        if not sentiments:
            return self._empty_aggregate(symbol, time_range_hours)
        
        # Filter by symbol if specified
        if symbol:
            symbol_upper = symbol.upper()
            filtered = [
                s for s in sentiments
                if symbol_upper in [sym.upper() for sym in s.symbols]
                or (s.primary_symbol and s.primary_symbol.upper() == symbol_upper)
            ]
            if filtered:
                sentiments = filtered
        
        # Calculate weighted sentiment score
        overall_score = self._calculate_weighted_score(sentiments)
        
        # Calculate confidence based on agreement
        confidence = self._calculate_confidence(sentiments)
        
        # Get event type breakdown
        event_counts = Counter(s.event_type for s in sentiments)
        dominant_event = event_counts.most_common(1)[0][0]
        
        # Get source breakdown
        sources = list(set(
            s.source_name.split("/")[0] if "/" in s.source_name else s.source_name
            for s in sentiments
        ))
        
        # Check for alerts
        has_breaking = any(s.is_breaking for s in sentiments)
        has_negative = any(
            s.event_type in {
                EventType.HACK, EventType.EXPLOIT, EventType.RUG_PULL,
                EventType.SCAM, EventType.REGULATORY_NEGATIVE,
            }
            for s in sentiments
        )
        has_positive = any(
            s.event_type in {
                EventType.LISTING, EventType.ETF_APPROVAL,
                EventType.PARTNERSHIP, EventType.INSTITUTIONAL_BUY,
            }
            for s in sentiments
        )
        
        return AggregatedSentiment(
            overall_score=overall_score,
            confidence=confidence,
            dominant_event_type=dominant_event,
            event_types={et: c for et, c in event_counts.items()},
            source_count=len(sources),
            sources_used=sources,
            timestamp=datetime.utcnow(),
            time_range_hours=time_range_hours,
            data_points=len(sentiments),
            symbol=symbol,
            has_breaking_news=has_breaking,
            has_negative_events=has_negative,
            has_positive_events=has_positive,
            individual_sentiments=sentiments,
        )
    
    def _calculate_weighted_score(
        self,
        sentiments: list[SentimentData],
    ) -> float:
        """
        Calculate weighted average sentiment score.
        
        Weights:
        1. Source reliability weight
        2. Recency (more recent = higher weight)
        3. Importance score
        """
        if not sentiments:
            return 0.0
        
        now = datetime.utcnow()
        recency_cutoff = now - timedelta(hours=self.recency_hours)
        
        total_weight = 0.0
        weighted_sum = 0.0
        
        for s in sentiments:
            # Base weight from source reliability
            weight = s.source_reliability_weight
            
            # Recency bonus
            if s.timestamp >= recency_cutoff:
                weight *= (1 + self.recency_weight)
            
            # Importance multiplier
            weight *= (0.5 + s.importance * 0.5)
            
            # Verified bonus
            if s.is_verified:
                weight *= 1.2
            
            weighted_sum += s.sentiment_score * weight
            total_weight += weight
        
        if total_weight == 0:
            return 0.0
        
        return max(-1.0, min(1.0, weighted_sum / total_weight))
    
    def _calculate_confidence(
        self,
        sentiments: list[SentimentData],
    ) -> float:
        """
        Calculate confidence in the aggregated sentiment.
        
        Based on:
        1. Number of data points
        2. Agreement between sources
        3. Source diversity
        """
        if not sentiments:
            return 0.0
        
        n = len(sentiments)
        
        # Base confidence from data count
        if n < self.MIN_DATA_POINTS_FOR_CONFIDENCE:
            base_confidence = n / self.MIN_DATA_POINTS_FOR_CONFIDENCE * 0.5
        else:
            base_confidence = 0.5 + min(0.3, (n - 5) / 50 * 0.3)
        
        # Agreement factor
        bullish_count = sum(1 for s in sentiments if s.sentiment_score > 0.2)
        bearish_count = sum(1 for s in sentiments if s.sentiment_score < -0.2)
        neutral_count = n - bullish_count - bearish_count
        
        max_agreement = max(bullish_count, bearish_count, neutral_count)
        agreement_ratio = max_agreement / n if n > 0 else 0
        
        if agreement_ratio >= self.AGREEMENT_THRESHOLD:
            agreement_boost = 0.2
        elif agreement_ratio >= 0.5:
            agreement_boost = 0.1
        else:
            agreement_boost = 0.0
        
        # Source diversity factor
        unique_sources = len(set(s.source_name.split("/")[0] for s in sentiments))
        diversity_boost = min(0.1, unique_sources * 0.05)
        
        confidence = base_confidence + agreement_boost + diversity_boost
        return min(1.0, max(0.0, confidence))
    
    def _empty_aggregate(
        self,
        symbol: Optional[str],
        time_range_hours: int,
    ) -> AggregatedSentiment:
        """Return empty aggregate when no data available."""
        return AggregatedSentiment(
            overall_score=0.0,
            confidence=0.0,
            dominant_event_type=EventType.UNKNOWN,
            event_types={},
            source_count=0,
            sources_used=[],
            timestamp=datetime.utcnow(),
            time_range_hours=time_range_hours,
            data_points=0,
            symbol=symbol,
            has_breaking_news=False,
            has_negative_events=False,
            has_positive_events=False,
            individual_sentiments=[],
        )
    
    def filter_by_time(
        self,
        sentiments: list[SentimentData],
        hours: int,
    ) -> list[SentimentData]:
        """Filter sentiments to only those within time range."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [s for s in sentiments if s.timestamp >= cutoff]
    
    def filter_by_importance(
        self,
        sentiments: list[SentimentData],
        min_importance: float = 0.5,
    ) -> list[SentimentData]:
        """Filter to only important sentiments."""
        return [s for s in sentiments if s.importance >= min_importance]
    
    def filter_by_event_type(
        self,
        sentiments: list[SentimentData],
        event_types: list[EventType],
    ) -> list[SentimentData]:
        """Filter by specific event types."""
        event_set = set(event_types)
        return [s for s in sentiments if s.event_type in event_set]
    
    def get_alerts(
        self,
        sentiments: list[SentimentData],
    ) -> list[SentimentData]:
        """Get high-priority alerts from sentiment data."""
        alerts = []
        
        # Breaking news
        alerts.extend(s for s in sentiments if s.is_breaking)
        
        # High-impact negative events
        negative_events = {
            EventType.HACK, EventType.EXPLOIT, EventType.RUG_PULL,
            EventType.SECURITY_BREACH, EventType.REGULATORY_NEGATIVE,
        }
        alerts.extend(
            s for s in sentiments
            if s.event_type in negative_events and s.importance >= 0.6
        )
        
        # Deduplicate
        seen = set()
        unique_alerts = []
        for alert in alerts:
            key = (alert.title, alert.timestamp.isoformat())
            if key not in seen:
                seen.add(key)
                unique_alerts.append(alert)
        
        return sorted(unique_alerts, key=lambda x: x.importance, reverse=True)
    
    def get_summary_stats(
        self,
        sentiments: list[SentimentData],
    ) -> dict[str, Any]:
        """Get summary statistics for sentiment data."""
        if not sentiments:
            return {
                "count": 0,
                "avg_score": 0.0,
                "bullish_pct": 0.0,
                "bearish_pct": 0.0,
                "neutral_pct": 0.0,
                "avg_importance": 0.0,
                "breaking_count": 0,
            }
        
        n = len(sentiments)
        bullish = sum(1 for s in sentiments if s.sentiment_score > 0.2)
        bearish = sum(1 for s in sentiments if s.sentiment_score < -0.2)
        neutral = n - bullish - bearish
        
        return {
            "count": n,
            "avg_score": sum(s.sentiment_score for s in sentiments) / n,
            "bullish_pct": round(bullish / n * 100, 1),
            "bearish_pct": round(bearish / n * 100, 1),
            "neutral_pct": round(neutral / n * 100, 1),
            "avg_importance": sum(s.importance for s in sentiments) / n,
            "breaking_count": sum(1 for s in sentiments if s.is_breaking),
        }
