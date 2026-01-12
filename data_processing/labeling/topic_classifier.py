"""
Data Processing - Topic Classifier.

============================================================
RESPONSIBILITY
============================================================
Classifies text content into predefined topic categories.

- Assigns topic labels to news and content
- Supports multi-label classification
- Provides confidence scores per topic
- Enables topic-based filtering

============================================================
DESIGN PRINCIPLES
============================================================
- Topics are predefined, not discovered
- Multiple topics per item allowed
- Confidence score required for each label
- Configurable topic taxonomy
- DESCRIPTIVE labels only - no predictive labels

============================================================
TOPIC TAXONOMY
============================================================
- regulation: Government, legal, compliance
- technology: Protocol updates, technical
- market: Price, trading, market structure
- adoption: Partnerships, integrations
- security: Hacks, vulnerabilities
- macro: Economic, geopolitical
- defi: DeFi protocols, yields
- nft: NFT, digital collectibles
- other: Uncategorized

============================================================
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple


# ============================================================
# CONFIGURATION
# ============================================================


@dataclass
class TopicClassifierConfig:
    """Configuration for topic classification."""
    
    # Topics to classify
    topics: List[str] = field(default_factory=lambda: [
        "regulation",
        "technology",
        "market",
        "adoption",
        "security",
        "macro",
        "defi",
        "nft",
        "other",
    ])
    
    # Confidence thresholds
    min_confidence: float = 0.3
    
    # Maximum labels per item
    max_labels: int = 3
    
    # Classification method
    method: str = "rule_based"  # rule_based, ml, hybrid
    
    # Version
    version: str = "1.0.0"


# ============================================================
# RESULT TYPES
# ============================================================


@dataclass
class TopicLabel:
    """A single topic label with confidence."""
    
    topic: str
    confidence: float
    is_primary: bool = False


@dataclass
class ClassificationResult:
    """Result of topic classification."""
    
    labels: List[TopicLabel]
    primary_topic: str
    classified_at: datetime = field(default_factory=datetime.utcnow)
    method: str = "rule_based"
    version: str = "1.0.0"
    
    @property
    def topic_list(self) -> List[str]:
        """Get list of topic names."""
        return [label.topic for label in self.labels]
    
    @property
    def confidence_dict(self) -> Dict[str, float]:
        """Get topic -> confidence mapping."""
        return {label.topic: label.confidence for label in self.labels}


# ============================================================
# KEYWORD PATTERNS
# ============================================================


# Topic keyword patterns (descriptive, not predictive)
TOPIC_KEYWORDS: Dict[str, Set[str]] = {
    "regulation": {
        "sec", "cftc", "regulation", "regulatory", "compliance",
        "lawsuit", "legal", "court", "ruling", "legislation",
        "law", "bill", "congress", "senate", "policy",
        "government", "authority", "enforcement", "ban", "prohibition",
        "license", "licensing", "framework", "guidelines", "rules",
        "investigation", "subpoena", "settlement", "fine", "penalty",
    },
    "technology": {
        "upgrade", "update", "protocol", "fork", "hard fork",
        "soft fork", "mainnet", "testnet", "launch", "release",
        "developer", "development", "code", "github", "repository",
        "smart contract", "consensus", "scaling", "layer 2", "l2",
        "rollup", "zk", "zero knowledge", "proof", "algorithm",
        "network", "node", "validator", "mining", "hash",
    },
    "market": {
        "price", "trading", "volume", "exchange", "liquidity",
        "order", "buy", "sell", "market cap", "capitalization",
        "spot", "futures", "options", "derivatives", "leverage",
        "margin", "long", "short", "position", "trade",
        "pair", "listing", "delist", "ipo", "ido",
    },
    "adoption": {
        "partnership", "partner", "integration", "integrate",
        "collaboration", "announce", "announcement", "launch",
        "accept", "acceptance", "payment", "merchant", "retail",
        "institution", "institutional", "corporate", "company",
        "bank", "banking", "mainstream", "mass adoption",
    },
    "security": {
        "hack", "hacked", "exploit", "vulnerability", "breach",
        "attack", "attacker", "theft", "stolen", "drain",
        "bug", "flaw", "security", "audit", "auditor",
        "whitehack", "blackhat", "malware", "phishing", "scam",
        "rug", "rugpull", "compromise", "compromised",
    },
    "macro": {
        "inflation", "interest rate", "fed", "federal reserve",
        "economy", "economic", "gdp", "recession", "crisis",
        "central bank", "monetary", "fiscal", "treasury",
        "geopolitical", "war", "sanctions", "global", "world",
        "dollar", "usd", "currency", "forex", "fx",
    },
    "defi": {
        "defi", "decentralized finance", "lending", "borrowing",
        "yield", "apy", "apr", "farming", "liquidity pool",
        "amm", "dex", "swap", "bridge", "cross-chain",
        "staking", "stake", "unstake", "vault", "protocol",
        "dao", "governance", "token", "tvl", "total value",
    },
    "nft": {
        "nft", "non-fungible", "collectible", "collection",
        "digital art", "artwork", "artist", "creator",
        "marketplace", "opensea", "mint", "minting", "drop",
        "floor price", "rarity", "traits", "pfp", "avatar",
        "metaverse", "virtual", "gaming", "play to earn", "p2e",
    },
}


# ============================================================
# TOPIC CLASSIFIER
# ============================================================


class TopicClassifier:
    """
    Classifies text into predefined topic categories.
    
    ============================================================
    USAGE
    ============================================================
    ```python
    config = TopicClassifierConfig()
    classifier = TopicClassifier(config)
    
    result = classifier.classify(title, content)
    print(result.primary_topic)
    print(result.topic_list)
    ```
    
    ============================================================
    """
    
    def __init__(self, config: Optional[TopicClassifierConfig] = None) -> None:
        """
        Initialize the topic classifier.
        
        Args:
            config: Classification configuration
        """
        self._config = config or TopicClassifierConfig()
        
        # Build keyword patterns
        self._patterns = self._build_patterns()
    
    @property
    def version(self) -> str:
        """Get classifier version."""
        return self._config.version
    
    def get_topics(self) -> List[str]:
        """Get list of available topics."""
        return self._config.topics.copy()
    
    # =========================================================
    # PUBLIC API
    # =========================================================
    
    def classify(
        self,
        title: str,
        content: Optional[str] = None,
    ) -> ClassificationResult:
        """
        Classify text into topics.
        
        Args:
            title: Article title
            content: Article content (optional)
            
        Returns:
            ClassificationResult with topic labels
        """
        # Combine text for analysis
        text = f"{title} {content or ''}".lower()
        
        # Calculate scores for each topic
        scores: Dict[str, float] = {}
        
        for topic in self._config.topics:
            if topic == "other":
                continue
            score = self._calculate_topic_score(text, topic)
            if score > 0:
                scores[topic] = score
        
        # Normalize scores
        total_score = sum(scores.values())
        if total_score > 0:
            scores = {k: v / total_score for k, v in scores.items()}
        
        # Filter by minimum confidence
        scores = {
            k: v for k, v in scores.items()
            if v >= self._config.min_confidence
        }
        
        # Sort by score and limit
        sorted_topics = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_topics = sorted_topics[:self._config.max_labels]
        
        # Create labels
        labels: List[TopicLabel] = []
        for i, (topic, confidence) in enumerate(top_topics):
            labels.append(TopicLabel(
                topic=topic,
                confidence=confidence,
                is_primary=(i == 0),
            ))
        
        # Determine primary topic
        if labels:
            primary_topic = labels[0].topic
        else:
            primary_topic = "other"
            labels.append(TopicLabel(
                topic="other",
                confidence=1.0,
                is_primary=True,
            ))
        
        return ClassificationResult(
            labels=labels,
            primary_topic=primary_topic,
            method=self._config.method,
            version=self._config.version,
        )
    
    def classify_batch(
        self,
        items: List[Tuple[str, Optional[str]]],
    ) -> List[ClassificationResult]:
        """
        Classify a batch of items.
        
        Args:
            items: List of (title, content) tuples
            
        Returns:
            List of ClassificationResult
        """
        return [self.classify(title, content) for title, content in items]
    
    # =========================================================
    # INTERNAL METHODS
    # =========================================================
    
    def _build_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Build regex patterns for each topic."""
        patterns: Dict[str, List[re.Pattern]] = {}
        
        for topic, keywords in TOPIC_KEYWORDS.items():
            if topic not in self._config.topics:
                continue
            
            topic_patterns = []
            for keyword in keywords:
                # Escape special regex characters
                escaped = re.escape(keyword)
                # Create word boundary pattern
                pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
                topic_patterns.append(pattern)
            
            patterns[topic] = topic_patterns
        
        return patterns
    
    def _calculate_topic_score(self, text: str, topic: str) -> float:
        """
        Calculate score for a topic based on keyword matches.
        
        Returns a score between 0 and 1.
        """
        if topic not in self._patterns:
            return 0.0
        
        patterns = self._patterns[topic]
        if not patterns:
            return 0.0
        
        # Count matches
        match_count = 0
        for pattern in patterns:
            matches = pattern.findall(text)
            match_count += len(matches)
        
        # Score based on match count (with diminishing returns)
        # 1 match = 0.3, 2 = 0.5, 3 = 0.6, 4+ = 0.7+
        if match_count == 0:
            return 0.0
        elif match_count == 1:
            return 0.3
        elif match_count == 2:
            return 0.5
        elif match_count == 3:
            return 0.6
        else:
            # Logarithmic scale for more matches
            return min(0.9, 0.6 + 0.1 * (match_count - 3) ** 0.5)
    
    # =========================================================
    # TOPIC METADATA
    # =========================================================
    
    def get_topic_keywords(self, topic: str) -> List[str]:
        """Get keywords for a specific topic."""
        return list(TOPIC_KEYWORDS.get(topic, set()))
    
    def get_topic_description(self, topic: str) -> str:
        """Get description for a topic."""
        descriptions = {
            "regulation": "Government, legal, and compliance news",
            "technology": "Protocol updates and technical developments",
            "market": "Price, trading, and market structure news",
            "adoption": "Partnerships, integrations, and mainstream adoption",
            "security": "Hacks, vulnerabilities, and security incidents",
            "macro": "Economic and geopolitical news affecting crypto",
            "defi": "Decentralized finance protocols and developments",
            "nft": "NFTs, digital collectibles, and metaverse",
            "other": "Uncategorized news",
        }
        return descriptions.get(topic, "Unknown topic")
