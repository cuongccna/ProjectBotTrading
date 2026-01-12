"""
Twitter Keyword Scraper - Rate-limited social sentiment source.

SAFETY: This data is CONTEXT ONLY - never a trade trigger.

This adapter uses a lightweight keyword-based approach:
- Searches for crypto-related keywords via public endpoints
- Rate-limited to avoid API abuse
- Caches aggressively to reduce requests
- Falls back gracefully on rate limits

NOTE: For production, consider using official Twitter API v2 with proper auth.
This implementation uses a simplified scraping approach for the free tier.
"""

import asyncio
import hashlib
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import quote

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


# Crypto influencer accounts for sentiment weighting
INFLUENTIAL_ACCOUNTS: set[str] = {
    "cz_binance", "elonmusk", "sloyer", "vitalikbuterin",
    "CryptoCapo_", "crypto_birb", "AltcoinGordon", "inversebrah",
    "woonomic", "glassnode", "santaborto", "whale_alert",
}

# Sentiment keywords
BULLISH_KEYWORDS = [
    "bullish", "moon", "pump", "buy", "long", "breakout",
    "ath", "all time high", "accumulate", "accumulation",
    "fomo", "send it", "wagmi", "gm", "lfg", "diamond hands",
    "green candle", "rally", "surge", "soaring", "rocket",
]

BEARISH_KEYWORDS = [
    "bearish", "dump", "sell", "short", "breakdown",
    "crash", "plunge", "capitulation", "fear", "panic",
    "rekt", "ngmi", "scam", "dead", "down", "falling",
    "red candle", "collapse", "correction", "tank",
]


class TwitterScraperSource(BaseSentimentSource):
    """
    Twitter/X keyword-based sentiment scraper.
    
    STRICT rate limiting:
    - 5 requests per minute max
    - 100 requests per day max
    - Heavy caching (30 min TTL)
    
    Uses simplified search to avoid API costs.
    For production, integrate with Twitter API v2.
    """
    
    # Very conservative to avoid rate limits
    DEFAULT_CACHE_TTL = 1800  # 30 minutes
    RATE_LIMIT_PER_MINUTE = 5
    RATE_LIMIT_PER_DAY = 100
    
    # Lower reliability - unverified social content
    RELIABILITY_WEIGHT = 0.35
    
    # Search endpoints (simplified mock for demo)
    # In production, use Twitter API v2 or nitter instances
    SEARCH_TEMPLATE = "https://nitter.net/search?f=tweets&q={query}"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(
            api_key,
            cache_ttl or self.DEFAULT_CACHE_TTL,
            timeout or 15,
        )
        self._session: Optional[aiohttp.ClientSession] = None
        self._simulated_mode = True  # Use simulated data by default
    
    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            name="twitter",
            display_name="Twitter/X Scraper",
            version="1.0.0",
            reliability_weight=self.RELIABILITY_WEIGHT,
            rate_limit_per_minute=self.RATE_LIMIT_PER_MINUTE,
            rate_limit_per_day=self.RATE_LIMIT_PER_DAY,
            requires_api_key=False,
            is_free_tier=True,
            cache_ttl_seconds=self.cache_ttl,
            base_url="",
            documentation_url="https://developer.twitter.com/en/docs",
            priority=2,
            tags=["social", "sentiment", "twitter", "realtime"],
        )
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                "Accept-Language": "en-US,en;q=0.5",
            }
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
            )
        return self._session
    
    async def _fetch_raw(
        self,
        request: SentimentRequest,
    ) -> list[dict[str, Any]]:
        """
        Fetch tweet data.
        
        In simulated mode, generates realistic mock data.
        In live mode, attempts to scrape from public sources.
        """
        if self._simulated_mode:
            return await self._fetch_simulated(request)
        else:
            return await self._fetch_live(request)
    
    async def _fetch_simulated(
        self,
        request: SentimentRequest,
    ) -> list[dict[str, Any]]:
        """Generate simulated Twitter sentiment data."""
        # Simulate network delay
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        results = []
        now = datetime.utcnow()
        
        # Generate mock tweets based on symbols
        for symbol in request.symbols[:3]:  # Limit to 3 symbols
            # Generate 5-15 mock tweets per symbol
            count = random.randint(5, min(15, request.limit // len(request.symbols)))
            
            for i in range(count):
                # Random timestamp within time range
                hours_ago = random.uniform(0, request.time_range_hours)
                tweet_time = now - timedelta(hours=hours_ago)
                
                # Random sentiment
                sentiment_type = random.choices(
                    ["bullish", "bearish", "neutral"],
                    weights=[0.4, 0.35, 0.25],
                )[0]
                
                # Generate mock tweet
                tweet = self._generate_mock_tweet(symbol, sentiment_type, tweet_time)
                results.append(tweet)
        
        # Shuffle and limit
        random.shuffle(results)
        return results[:request.limit]
    
    def _generate_mock_tweet(
        self,
        symbol: str,
        sentiment_type: str,
        timestamp: datetime,
    ) -> dict[str, Any]:
        """Generate a mock tweet."""
        # Templates
        bullish_templates = [
            f"${symbol} looking bullish 📈 Breaking out of resistance",
            f"Just loaded up on more ${symbol} 🚀 Moon soon",
            f"${symbol} accumulation zone. Smart money buying.",
            f"Feeling very bullish on ${symbol} this week",
            f"${symbol} breakout incoming 💎🙌",
        ]
        
        bearish_templates = [
            f"${symbol} breakdown below support 📉 Be careful",
            f"Sold my ${symbol} position. Looking weak.",
            f"${symbol} bearish divergence on daily chart",
            f"Not a good time to buy ${symbol} imo",
            f"${symbol} heading lower. Wait for better entry.",
        ]
        
        neutral_templates = [
            f"${symbol} consolidating. Waiting for direction.",
            f"Watching ${symbol} closely for next move",
            f"${symbol} ranging between key levels",
            f"No clear direction for ${symbol} right now",
            f"${symbol} volume decreasing. Could go either way.",
        ]
        
        if sentiment_type == "bullish":
            text = random.choice(bullish_templates)
        elif sentiment_type == "bearish":
            text = random.choice(bearish_templates)
        else:
            text = random.choice(neutral_templates)
        
        # Mock engagement
        likes = random.randint(0, 1000) if random.random() > 0.7 else random.randint(0, 100)
        retweets = int(likes * random.uniform(0.1, 0.5))
        
        # Random username
        usernames = [
            "CryptoTrader123", "DeFiDegen", "BTCMaximalist",
            "AltSeason2025", "ChartWhiz", "BlockchainBull",
        ]
        
        return {
            "text": text,
            "username": random.choice(usernames),
            "timestamp": timestamp.isoformat(),
            "likes": likes,
            "retweets": retweets,
            "replies": random.randint(0, 50),
            "symbol": symbol,
            "sentiment_hint": sentiment_type,
            "is_influential": random.random() > 0.9,
        }
    
    async def _fetch_live(
        self,
        request: SentimentRequest,
    ) -> list[dict[str, Any]]:
        """
        Attempt live scraping from public sources.
        
        NOTE: This is fragile and may break.
        Consider using official Twitter API v2 for production.
        """
        session = await self._get_session()
        results = []
        
        for symbol in request.symbols[:2]:  # Limit queries
            query = f"${symbol} crypto"
            encoded_query = quote(query)
            url = self.SEARCH_TEMPLATE.format(query=encoded_query)
            
            try:
                async with session.get(url) as response:
                    if response.status == 429:
                        raise RateLimitError(
                            "Twitter rate limit exceeded",
                            source_name=self.metadata.name,
                            retry_after_seconds=900,  # 15 minutes
                        )
                    
                    if response.status != 200:
                        logger.warning(f"Twitter scrape failed: {response.status}")
                        continue
                    
                    html = await response.text()
                    
                    # Parse tweets from HTML (simplified)
                    tweets = self._parse_tweets_html(html, symbol)
                    results.extend(tweets)
                    
            except aiohttp.ClientError as e:
                logger.warning(f"Twitter network error: {e}")
                continue
            
            # Rate limit between requests
            await asyncio.sleep(1)
        
        return results[:request.limit]
    
    def _parse_tweets_html(
        self,
        html: str,
        symbol: str,
    ) -> list[dict[str, Any]]:
        """Parse tweets from HTML (simplified extractor)."""
        # This is a placeholder - actual parsing would be more complex
        # For production, use official APIs
        tweets = []
        
        # Simple regex to find tweet-like content
        # This is intentionally simplified
        pattern = r'class="tweet-content[^"]*"[^>]*>([^<]+)</div>'
        matches = re.findall(pattern, html, re.IGNORECASE)
        
        for text in matches[:20]:
            text = text.strip()
            if len(text) > 10 and symbol.lower() in text.lower():
                tweets.append({
                    "text": text,
                    "username": "unknown",
                    "timestamp": datetime.utcnow().isoformat(),
                    "likes": 0,
                    "retweets": 0,
                    "replies": 0,
                    "symbol": symbol,
                    "sentiment_hint": None,
                    "is_influential": False,
                })
        
        return tweets
    
    def _normalize(
        self,
        raw_data: dict[str, Any],
    ) -> Optional[SentimentData]:
        """Normalize tweet data to SentimentData."""
        try:
            text = raw_data.get("text", "")
            username = raw_data.get("username", "unknown")
            
            # Parse timestamp
            ts_str = raw_data.get("timestamp", "")
            if ts_str:
                try:
                    timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    timestamp = timestamp.replace(tzinfo=None)
                except ValueError:
                    timestamp = datetime.utcnow()
            else:
                timestamp = datetime.utcnow()
            
            # Get symbol
            symbol = raw_data.get("symbol", "")
            symbols = [symbol.upper()] if symbol else []
            
            # Calculate sentiment from text
            sentiment_score = self._analyze_text_sentiment(text)
            
            # If we have a hint, blend it
            hint = raw_data.get("sentiment_hint")
            if hint:
                hint_score = {"bullish": 0.5, "bearish": -0.5, "neutral": 0.0}.get(hint, 0.0)
                sentiment_score = (sentiment_score * 0.6) + (hint_score * 0.4)
            
            # Detect event type
            event_type = self._detect_event_type(text)
            
            # Calculate importance from engagement
            likes = raw_data.get("likes", 0)
            retweets = raw_data.get("retweets", 0)
            importance = self._calculate_importance(likes, retweets, username)
            
            # Adjust reliability for influential accounts
            reliability = self.RELIABILITY_WEIGHT
            if raw_data.get("is_influential") or username.lower() in INFLUENTIAL_ACCOUNTS:
                reliability = min(1.0, reliability + 0.15)
            
            return SentimentData(
                sentiment_score=sentiment_score,
                event_type=event_type,
                source_reliability_weight=reliability,
                timestamp=timestamp,
                source_name=f"Twitter/@{username}",
                title=text[:100] + "..." if len(text) > 100 else text,
                summary="",
                url=None,
                symbols=symbols,
                primary_symbol=symbols[0] if symbols else None,
                raw_sentiment=hint,
                votes_positive=likes,
                votes_negative=0,
                importance=importance,
                is_verified=False,
                is_breaking=False,
                requires_confirmation=True,
            )
            
        except Exception as e:
            logger.warning(f"Failed to normalize tweet: {e}")
            return None
    
    def _analyze_text_sentiment(self, text: str) -> float:
        """Analyze sentiment from tweet text."""
        text_lower = text.lower()
        
        bullish_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text_lower)
        bearish_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text_lower)
        
        # Emoji analysis
        bullish_emojis = ["🚀", "📈", "💎", "🔥", "💪", "🌙", "⬆️", "🟢"]
        bearish_emojis = ["📉", "💀", "😱", "🔴", "⬇️", "❌", "😰"]
        
        for emoji in bullish_emojis:
            if emoji in text:
                bullish_count += 0.5
        
        for emoji in bearish_emojis:
            if emoji in text:
                bearish_count += 0.5
        
        # Calculate score
        if bullish_count + bearish_count == 0:
            return 0.0
        
        score = (bullish_count - bearish_count) / max(bullish_count + bearish_count, 1)
        return max(-1.0, min(1.0, score))
    
    def _detect_event_type(self, text: str) -> EventType:
        """Detect event type from tweet text."""
        text_lower = text.lower()
        
        # Check for specific events
        if any(w in text_lower for w in ["hack", "exploit", "stolen"]):
            return EventType.HACK
        if any(w in text_lower for w in ["listing", "listed", "binance listing"]):
            return EventType.LISTING
        if any(w in text_lower for w in ["etf", "etf approved"]):
            return EventType.ETF_APPROVAL
        if any(w in text_lower for w in ["partnership", "partner"]):
            return EventType.PARTNERSHIP
        if any(w in text_lower for w in ["whale", "large buy", "accumulation"]):
            return EventType.WHALE_ACCUMULATION
        if any(w in text_lower for w in ["dump", "large sell"]):
            return EventType.WHALE_DUMP
        
        return EventType.GENERAL_NEWS
    
    def _calculate_importance(
        self,
        likes: int,
        retweets: int,
        username: str,
    ) -> float:
        """Calculate importance from engagement."""
        base = 0.2
        
        # Engagement score
        engagement = likes + (retweets * 2)
        if engagement > 1000:
            base += 0.3
        elif engagement > 100:
            base += 0.2
        elif engagement > 10:
            base += 0.1
        
        # Influential account bonus
        if username.lower() in INFLUENTIAL_ACCOUNTS:
            base += 0.2
        
        return min(1.0, base)
    
    def set_simulated_mode(self, enabled: bool) -> None:
        """Enable/disable simulated data mode."""
        self._simulated_mode = enabled
    
    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
