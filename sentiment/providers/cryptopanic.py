"""
CryptoPanic Sentiment Source - Free tier crypto news aggregator.

SAFETY: This data is CONTEXT ONLY - never a trade trigger.

CryptoPanic provides:
- Aggregated crypto news from multiple sources
- Community voting (bullish/bearish)
- Event classification
- Free tier: 100 requests/hour (no auth), 1000/hour (with free API key)
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

import aiohttp

from ..base import BaseSentimentSource
from ..exceptions import FetchError, ParseError, RateLimitError
from ..models import (
    EVENT_SENTIMENT_IMPACT,
    EventType,
    SentimentData,
    SentimentRequest,
    SourceMetadata,
)


logger = logging.getLogger(__name__)


# Keyword to event type mapping for classification
EVENT_KEYWORDS: dict[str, list[str]] = {
    # Negative events
    "hack": ["hack", "hacked", "exploit", "breach", "stolen", "attack", "vulnerability"],
    "exploit": ["exploit", "exploited", "flash loan", "reentrancy", "vulnerability"],
    "rug_pull": ["rug", "rugged", "rug pull", "exit scam", "abandoned"],
    "scam": ["scam", "fraud", "ponzi", "fake", "phishing"],
    "regulatory_negative": ["ban", "banned", "crackdown", "lawsuit", "sec lawsuit", "enforcement", "investigation"],
    "exchange_issue": ["withdrawal", "suspended", "halted", "insolvent", "frozen"],
    "delisting": ["delist", "delisting", "removed", "removal"],
    "security_breach": ["breach", "leaked", "compromised", "data leak"],
    "whale_dump": ["whale sell", "large sell", "dumping", "whale dump"],
    
    # Positive events  
    "listing": ["list", "listed", "listing", "binance listing", "coinbase listing", "new listing"],
    "partnership": ["partner", "partnership", "collaboration", "integration", "teams up"],
    "adoption": ["adopt", "adoption", "accept", "payment", "merchant"],
    "regulatory_positive": ["approved", "approval", "license", "regulated", "legal", "clarity"],
    "etf_approval": ["etf", "etf approved", "etf application", "bitcoin etf", "spot etf"],
    "upgrade": ["upgrade", "v2", "v3", "mainnet", "hardfork", "fork", "merge"],
    "mainnet_launch": ["mainnet", "launch", "launched", "live", "genesis"],
    "airdrop": ["airdrop", "free tokens", "token distribution"],
    "whale_accumulation": ["whale buy", "accumulation", "whale accumulating", "large buy"],
    "institutional_buy": ["institutional", "microstrategy", "tesla", "grayscale", "blackrock", "fidelity"],
}


# Symbol normalization mapping
SYMBOL_ALIASES: dict[str, str] = {
    "bitcoin": "BTC",
    "btc": "BTC",
    "ethereum": "ETH",
    "eth": "ETH",
    "ether": "ETH",
    "xrp": "XRP",
    "ripple": "XRP",
    "solana": "SOL",
    "sol": "SOL",
    "cardano": "ADA",
    "ada": "ADA",
    "dogecoin": "DOGE",
    "doge": "DOGE",
    "polygon": "MATIC",
    "matic": "MATIC",
    "polkadot": "DOT",
    "dot": "DOT",
    "avalanche": "AVAX",
    "avax": "AVAX",
    "chainlink": "LINK",
    "link": "LINK",
    "uniswap": "UNI",
    "uni": "UNI",
    "litecoin": "LTC",
    "ltc": "LTC",
    "binance coin": "BNB",
    "bnb": "BNB",
}


class CryptoPanicSource(BaseSentimentSource):
    """
    CryptoPanic news aggregator sentiment source.
    
    Free tier limitations:
    - Without API key: 100 requests/hour
    - With free API key: 1000 requests/hour
    
    Features:
    - Community voting (bullish/bearish sentiment)
    - Multiple news sources aggregated
    - Filter by currencies
    - Filter by kind (news, media)
    """
    
    BASE_URL = "https://cryptopanic.com/api/v1"
    DEFAULT_CACHE_TTL = 300  # 5 minutes
    
    # Source reliability (0.6 - community curated but not verified)
    RELIABILITY_WEIGHT = 0.6
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(api_key, cache_ttl, timeout)
        self._session: Optional[aiohttp.ClientSession] = None
    
    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            name="cryptopanic",
            display_name="CryptoPanic",
            version="1.0.0",
            reliability_weight=self.RELIABILITY_WEIGHT,
            rate_limit_per_minute=100 if not self.api_key else 1000,
            rate_limit_per_day=None,  # Only hourly limit
            requires_api_key=False,
            is_free_tier=True,
            cache_ttl_seconds=self.cache_ttl,
            base_url=self.BASE_URL,
            documentation_url="https://cryptopanic.com/developers/api/",
            priority=1,
            tags=["news", "sentiment", "voting", "aggregator"],
        )
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def _fetch_raw(
        self,
        request: SentimentRequest,
    ) -> list[dict[str, Any]]:
        """
        Fetch raw news data from CryptoPanic.
        
        API endpoint: /posts/
        Params:
        - auth_token: API key (optional for free tier)
        - currencies: Comma-separated symbols
        - filter: rising, hot, bullish, bearish, important, saved, lol
        - public: true/false
        - kind: news, media, all
        """
        session = await self._get_session()
        
        # Build URL
        url = f"{self.BASE_URL}/posts/"
        
        # Build params
        params: dict[str, str] = {
            "public": "true",
            "kind": "news",
        }
        
        # Add API key if available
        if self.api_key:
            params["auth_token"] = self.api_key
        
        # Add currencies filter
        if request.symbols:
            # Normalize symbols
            currencies = ",".join(s.upper() for s in request.symbols)
            params["currencies"] = currencies
        
        try:
            async with session.get(url, params=params) as response:
                # Check rate limit
                if response.status == 429:
                    retry_after = response.headers.get("Retry-After", "60")
                    raise RateLimitError(
                        f"CryptoPanic rate limit exceeded",
                        source_name=self.metadata.name,
                        retry_after_seconds=int(retry_after),
                    )
                
                if response.status != 200:
                    text = await response.text()
                    raise FetchError(
                        f"CryptoPanic API error: {response.status}",
                        source_name=self.metadata.name,
                        status_code=response.status,
                        url=str(response.url),
                        details={"response": text[:500]},
                    )
                
                data = await response.json()
                
                # Extract results
                results = data.get("results", [])
                
                # Filter by time range
                cutoff = datetime.utcnow() - timedelta(hours=request.time_range_hours)
                filtered = []
                
                for item in results:
                    # Parse timestamp
                    published = item.get("published_at", "")
                    if published:
                        try:
                            # Handle ISO format with Z suffix
                            if published.endswith("Z"):
                                published = published[:-1] + "+00:00"
                            item_time = datetime.fromisoformat(published.replace("Z", "+00:00"))
                            if item_time.replace(tzinfo=None) >= cutoff:
                                filtered.append(item)
                        except (ValueError, TypeError):
                            # Include if we can't parse time
                            filtered.append(item)
                    else:
                        filtered.append(item)
                
                # Apply limit
                return filtered[:request.limit]
                
        except aiohttp.ClientError as e:
            raise FetchError(
                f"Network error: {e}",
                source_name=self.metadata.name,
            )
    
    def _normalize(
        self,
        raw_data: dict[str, Any],
    ) -> Optional[SentimentData]:
        """
        Normalize CryptoPanic news item to SentimentData.
        
        CryptoPanic provides:
        - votes: {positive, negative, important, liked, disliked, lol, toxic, saved, comments}
        - currencies: [{code, title, slug, url}]
        - kind: news, media
        """
        try:
            # Extract basic fields
            title = raw_data.get("title", "")
            url = raw_data.get("url", "")
            source_name = raw_data.get("source", {}).get("title", "unknown")
            
            # Parse timestamp
            published = raw_data.get("published_at", "")
            if published:
                if published.endswith("Z"):
                    published = published[:-1] + "+00:00"
                timestamp = datetime.fromisoformat(published.replace("Z", "+00:00"))
                timestamp = timestamp.replace(tzinfo=None)
            else:
                timestamp = datetime.utcnow()
            
            # Extract votes
            votes = raw_data.get("votes", {})
            votes_positive = votes.get("positive", 0) + votes.get("liked", 0)
            votes_negative = votes.get("negative", 0) + votes.get("disliked", 0) + votes.get("toxic", 0)
            
            # Extract symbols
            currencies = raw_data.get("currencies", [])
            symbols = [c.get("code", "").upper() for c in currencies if c.get("code")]
            primary_symbol = symbols[0] if symbols else None
            
            # Detect event type from title
            event_type = self._detect_event_type(title)
            
            # Calculate sentiment score
            sentiment_score = self._calculate_sentiment(
                votes_positive,
                votes_negative,
                event_type,
                title,
            )
            
            # Determine importance
            importance = self._calculate_importance(raw_data)
            
            # Check if it's important/breaking
            is_important = votes.get("important", 0) > 0
            
            return SentimentData(
                sentiment_score=sentiment_score,
                event_type=event_type,
                source_reliability_weight=self.RELIABILITY_WEIGHT,
                timestamp=timestamp,
                source_name=f"CryptoPanic/{source_name}",
                title=title,
                summary="",  # CryptoPanic doesn't provide summaries
                url=url,
                symbols=symbols,
                primary_symbol=primary_symbol,
                raw_sentiment=raw_data.get("filter", "neutral"),
                votes_positive=votes_positive,
                votes_negative=votes_negative,
                importance=importance,
                is_verified=False,
                is_breaking=is_important,
                requires_confirmation=True,
            )
            
        except Exception as e:
            logger.warning(f"Failed to normalize CryptoPanic data: {e}")
            return None
    
    def _detect_event_type(self, title: str) -> EventType:
        """Detect event type from title keywords."""
        title_lower = title.lower()
        
        for event_type, keywords in EVENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword in title_lower:
                    try:
                        return EventType(event_type)
                    except ValueError:
                        continue
        
        return EventType.GENERAL_NEWS
    
    def _calculate_sentiment(
        self,
        votes_positive: int,
        votes_negative: int,
        event_type: EventType,
        title: str,
    ) -> float:
        """
        Calculate sentiment score from votes and event type.
        
        Combines:
        1. Community voting sentiment
        2. Event type typical impact
        3. Title keyword analysis
        """
        # Base from event type
        event_impact = EVENT_SENTIMENT_IMPACT.get(event_type, 0.0)
        
        # Voting sentiment
        total_votes = votes_positive + votes_negative
        if total_votes > 0:
            vote_score = (votes_positive - votes_negative) / total_votes
        else:
            vote_score = 0.0
        
        # Combine: 60% event type, 40% voting
        sentiment = (event_impact * 0.6) + (vote_score * 0.4)
        
        # Clamp to [-1, 1]
        return max(-1.0, min(1.0, sentiment))
    
    def _calculate_importance(self, raw_data: dict[str, Any]) -> float:
        """Calculate importance score."""
        votes = raw_data.get("votes", {})
        
        # Factors
        important_votes = votes.get("important", 0)
        total_votes = sum(votes.values()) if votes else 0
        comments = votes.get("comments", 0)
        
        # Simple importance calculation
        score = 0.3  # Base importance
        
        if important_votes > 0:
            score += min(0.3, important_votes * 0.1)
        
        if total_votes > 10:
            score += 0.2
        
        if comments > 5:
            score += 0.1
        
        return min(1.0, score)
    
    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
