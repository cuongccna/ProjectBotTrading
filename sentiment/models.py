"""
Sentiment Data Models - Normalized sentiment structures.

SAFETY WARNING: Sentiment is NEVER a standalone trade trigger.
Used ONLY as a context modifier for signal validation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class SourceStatus(Enum):
    """Health status of a sentiment source."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class EventType(Enum):
    """Types of crypto events detected from sentiment sources."""
    # Negative events
    HACK = "hack"
    EXPLOIT = "exploit"
    RUG_PULL = "rug_pull"
    SCAM = "scam"
    REGULATORY_NEGATIVE = "regulatory_negative"
    EXCHANGE_ISSUE = "exchange_issue"
    DELISTING = "delisting"
    LAWSUIT = "lawsuit"
    SECURITY_BREACH = "security_breach"
    WHALE_DUMP = "whale_dump"
    
    # Positive events
    LISTING = "listing"
    PARTNERSHIP = "partnership"
    ADOPTION = "adoption"
    REGULATORY_POSITIVE = "regulatory_positive"
    ETF_APPROVAL = "etf_approval"
    UPGRADE = "upgrade"
    MAINNET_LAUNCH = "mainnet_launch"
    AIRDROP = "airdrop"
    WHALE_ACCUMULATION = "whale_accumulation"
    INSTITUTIONAL_BUY = "institutional_buy"
    
    # Neutral events
    GENERAL_NEWS = "general_news"
    PRICE_ANALYSIS = "price_analysis"
    TECHNICAL_UPDATE = "technical_update"
    MARKET_UPDATE = "market_update"
    
    # Unknown/Other
    UNKNOWN = "unknown"


class SentimentCategory(Enum):
    """Broad sentiment categories."""
    VERY_BEARISH = "very_bearish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    BULLISH = "bullish"
    VERY_BULLISH = "very_bullish"


# Event type to typical sentiment impact mapping
EVENT_SENTIMENT_IMPACT: dict[EventType, float] = {
    # Negative events (-1.0 to -0.3)
    EventType.HACK: -0.9,
    EventType.EXPLOIT: -0.85,
    EventType.RUG_PULL: -1.0,
    EventType.SCAM: -0.9,
    EventType.REGULATORY_NEGATIVE: -0.7,
    EventType.EXCHANGE_ISSUE: -0.6,
    EventType.DELISTING: -0.8,
    EventType.LAWSUIT: -0.5,
    EventType.SECURITY_BREACH: -0.75,
    EventType.WHALE_DUMP: -0.4,
    
    # Positive events (+0.3 to +1.0)
    EventType.LISTING: 0.7,
    EventType.PARTNERSHIP: 0.5,
    EventType.ADOPTION: 0.6,
    EventType.REGULATORY_POSITIVE: 0.7,
    EventType.ETF_APPROVAL: 0.9,
    EventType.UPGRADE: 0.4,
    EventType.MAINNET_LAUNCH: 0.6,
    EventType.AIRDROP: 0.3,
    EventType.WHALE_ACCUMULATION: 0.5,
    EventType.INSTITUTIONAL_BUY: 0.7,
    
    # Neutral events (-0.3 to +0.3)
    EventType.GENERAL_NEWS: 0.0,
    EventType.PRICE_ANALYSIS: 0.0,
    EventType.TECHNICAL_UPDATE: 0.1,
    EventType.MARKET_UPDATE: 0.0,
    
    # Unknown
    EventType.UNKNOWN: 0.0,
}


@dataclass(frozen=True)
class SentimentData:
    """
    Normalized sentiment data output - STRICT schema.
    
    SAFETY: This data is ONLY for context modification.
    NEVER use as a standalone trade trigger.
    
    sentiment_score: -1.0 (very bearish) to +1.0 (very bullish)
    """
    # Core fields (required)
    sentiment_score: float  # -1.0 to +1.0
    event_type: EventType
    source_reliability_weight: float  # 0.0 to 1.0
    timestamp: datetime
    
    # Context fields
    source_name: str = ""
    title: str = ""
    summary: str = ""
    url: Optional[str] = None
    
    # Asset context
    symbols: list[str] = field(default_factory=list)
    primary_symbol: Optional[str] = None
    
    # Metadata
    raw_sentiment: Optional[str] = None  # Original sentiment label
    votes_positive: int = 0
    votes_negative: int = 0
    importance: float = 0.5  # 0.0 to 1.0
    
    # Safety flags
    is_verified: bool = False
    is_breaking: bool = False
    requires_confirmation: bool = True
    
    # Cache info
    cached: bool = False
    cache_age_seconds: Optional[float] = None
    
    def __post_init__(self) -> None:
        """Validate sentiment score range."""
        if not -1.0 <= self.sentiment_score <= 1.0:
            object.__setattr__(
                self, 'sentiment_score',
                max(-1.0, min(1.0, self.sentiment_score))
            )
        if not 0.0 <= self.source_reliability_weight <= 1.0:
            object.__setattr__(
                self, 'source_reliability_weight',
                max(0.0, min(1.0, self.source_reliability_weight))
            )
    
    @property
    def weighted_score(self) -> float:
        """Get sentiment score weighted by source reliability."""
        return self.sentiment_score * self.source_reliability_weight
    
    @property
    def category(self) -> SentimentCategory:
        """Get broad sentiment category."""
        if self.sentiment_score <= -0.6:
            return SentimentCategory.VERY_BEARISH
        elif self.sentiment_score <= -0.2:
            return SentimentCategory.BEARISH
        elif self.sentiment_score <= 0.2:
            return SentimentCategory.NEUTRAL
        elif self.sentiment_score <= 0.6:
            return SentimentCategory.BULLISH
        else:
            return SentimentCategory.VERY_BULLISH
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "sentiment_score": self.sentiment_score,
            "event_type": self.event_type.value,
            "source_reliability_weight": self.source_reliability_weight,
            "timestamp": self.timestamp.isoformat(),
            "source_name": self.source_name,
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "symbols": self.symbols,
            "primary_symbol": self.primary_symbol,
            "raw_sentiment": self.raw_sentiment,
            "votes_positive": self.votes_positive,
            "votes_negative": self.votes_negative,
            "importance": self.importance,
            "is_verified": self.is_verified,
            "is_breaking": self.is_breaking,
            "requires_confirmation": self.requires_confirmation,
            "weighted_score": self.weighted_score,
            "category": self.category.value,
            "cached": self.cached,
            "cache_age_seconds": self.cache_age_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SentimentData":
        """Create from dictionary."""
        return cls(
            sentiment_score=float(data["sentiment_score"]),
            event_type=EventType(data["event_type"]),
            source_reliability_weight=float(data["source_reliability_weight"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source_name=data.get("source_name", ""),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            url=data.get("url"),
            symbols=data.get("symbols", []),
            primary_symbol=data.get("primary_symbol"),
            raw_sentiment=data.get("raw_sentiment"),
            votes_positive=data.get("votes_positive", 0),
            votes_negative=data.get("votes_negative", 0),
            importance=data.get("importance", 0.5),
            is_verified=data.get("is_verified", False),
            is_breaking=data.get("is_breaking", False),
            requires_confirmation=data.get("requires_confirmation", True),
            cached=data.get("cached", False),
            cache_age_seconds=data.get("cache_age_seconds"),
        )


@dataclass
class AggregatedSentiment:
    """
    Aggregated sentiment from multiple sources.
    
    SAFETY: This is CONTEXT ONLY. Never use as standalone trigger.
    """
    # Weighted average sentiment
    overall_score: float  # -1.0 to +1.0
    confidence: float  # 0.0 to 1.0 based on source agreement
    
    # Event breakdown
    dominant_event_type: EventType
    event_types: dict[EventType, int]  # Count of each event type
    
    # Source breakdown
    source_count: int
    sources_used: list[str]
    
    # Time range
    timestamp: datetime
    time_range_hours: int
    data_points: int
    
    # Symbol context
    symbol: Optional[str] = None
    
    # Alerts
    has_breaking_news: bool = False
    has_negative_events: bool = False
    has_positive_events: bool = False
    
    # Raw data
    individual_sentiments: list[SentimentData] = field(default_factory=list)
    
    @property
    def category(self) -> SentimentCategory:
        """Get broad sentiment category."""
        if self.overall_score <= -0.6:
            return SentimentCategory.VERY_BEARISH
        elif self.overall_score <= -0.2:
            return SentimentCategory.BEARISH
        elif self.overall_score <= 0.2:
            return SentimentCategory.NEUTRAL
        elif self.overall_score <= 0.6:
            return SentimentCategory.BULLISH
        else:
            return SentimentCategory.VERY_BULLISH
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "overall_score": self.overall_score,
            "confidence": self.confidence,
            "category": self.category.value,
            "dominant_event_type": self.dominant_event_type.value,
            "event_types": {k.value: v for k, v in self.event_types.items()},
            "source_count": self.source_count,
            "sources_used": self.sources_used,
            "timestamp": self.timestamp.isoformat(),
            "time_range_hours": self.time_range_hours,
            "data_points": self.data_points,
            "symbol": self.symbol,
            "has_breaking_news": self.has_breaking_news,
            "has_negative_events": self.has_negative_events,
            "has_positive_events": self.has_positive_events,
        }


@dataclass
class SourceHealth:
    """Health status of a sentiment source."""
    status: SourceStatus
    last_check: datetime
    latency_ms: Optional[float] = None
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    consecutive_failures: int = 0
    requests_today: int = 0
    daily_limit: Optional[int] = None
    
    def is_healthy(self) -> bool:
        return self.status == SourceStatus.HEALTHY
    
    def is_usable(self) -> bool:
        return self.status in (SourceStatus.HEALTHY, SourceStatus.DEGRADED)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "last_check": self.last_check.isoformat(),
            "latency_ms": self.latency_ms,
            "rate_limit_remaining": self.rate_limit_remaining,
            "rate_limit_reset": self.rate_limit_reset.isoformat() if self.rate_limit_reset else None,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "requests_today": self.requests_today,
            "daily_limit": self.daily_limit,
        }


@dataclass
class SourceMetadata:
    """Metadata about a sentiment source."""
    name: str
    display_name: str
    version: str
    reliability_weight: float  # Base reliability weight (0.0 to 1.0)
    rate_limit_per_minute: Optional[int] = None
    rate_limit_per_day: Optional[int] = None
    requires_api_key: bool = False
    is_free_tier: bool = True
    cache_ttl_seconds: int = 300
    base_url: str = ""
    documentation_url: str = ""
    priority: int = 0
    tags: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "version": self.version,
            "reliability_weight": self.reliability_weight,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "rate_limit_per_day": self.rate_limit_per_day,
            "requires_api_key": self.requires_api_key,
            "is_free_tier": self.is_free_tier,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "base_url": self.base_url,
            "priority": self.priority,
            "tags": self.tags,
        }


@dataclass
class SentimentRequest:
    """Request parameters for fetching sentiment data."""
    symbols: list[str] = field(default_factory=lambda: ["BTC", "ETH"])
    time_range_hours: int = 24
    limit: int = 50
    filter_events: Optional[list[EventType]] = None
    min_importance: float = 0.0
    include_general_news: bool = True
    use_cache: bool = True
    
    def validate(self) -> None:
        """Validate request parameters."""
        if self.time_range_hours < 1 or self.time_range_hours > 168:
            raise ValueError("time_range_hours must be between 1 and 168")
        if self.limit < 1 or self.limit > 500:
            raise ValueError("limit must be between 1 and 500")
        if not 0.0 <= self.min_importance <= 1.0:
            raise ValueError("min_importance must be between 0.0 and 1.0")


@dataclass
class SourceIncident:
    """Record of a source incident."""
    source_name: str
    incident_type: str
    timestamp: datetime
    error_message: str
    request_params: Optional[dict[str, Any]] = None
    resolution: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "incident_type": self.incident_type,
            "timestamp": self.timestamp.isoformat(),
            "error_message": self.error_message,
            "request_params": self.request_params,
            "resolution": self.resolution,
        }
