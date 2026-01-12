"""
Smart Money Confidence - Data Models.

============================================================
CORE DATA STRUCTURES
============================================================

Defines all data models for confidence weighting:
- EntityType: Fund, Whale, Market Maker, CEX, Unknown
- ConfidenceLevel: LOW, MEDIUM, HIGH
- BehaviorType: Accumulation, Distribution, Neutral
- WalletProfile: Dynamic confidence profile for a wallet
- ActivityRecord: Single activity record
- ConfidenceOutput: Final output of confidence calculation

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Set
from uuid import UUID, uuid4


# =============================================================
# ENUMS
# =============================================================


class EntityType(str, Enum):
    """
    Type of entity controlling the wallet.
    
    Credibility order: FUND > MARKET_MAKER > WHALE > UNKNOWN
    """
    FUND = "fund"                    # Known fund/institution
    MARKET_MAKER = "market_maker"    # Market maker
    WHALE = "whale"                  # Large individual holder
    CEX = "cex"                      # Centralized exchange
    DEX = "dex"                      # DEX contract/pool
    BRIDGE = "bridge"                # Cross-chain bridge
    UNKNOWN = "unknown"              # Unidentified wallet
    
    def get_base_credibility(self) -> float:
        """Get base credibility score (0-1)."""
        return {
            EntityType.FUND: 0.9,
            EntityType.MARKET_MAKER: 0.7,
            EntityType.WHALE: 0.5,
            EntityType.CEX: 0.3,  # CEX movements are often noise
            EntityType.DEX: 0.2,
            EntityType.BRIDGE: 0.1,  # Bridge activity is usually noise
            EntityType.UNKNOWN: 0.2,
        }.get(self, 0.2)


class ConfidenceLevel(str, Enum):
    """
    Confidence level for smart money signal.
    
    Used to determine how much weight to give the signal.
    """
    LOW = "low"          # score < 40
    MEDIUM = "medium"    # 40 <= score < 70
    HIGH = "high"        # score >= 70
    
    @classmethod
    def from_score(cls, score: float) -> "ConfidenceLevel":
        """Determine level from score."""
        if score >= 70:
            return cls.HIGH
        elif score >= 40:
            return cls.MEDIUM
        else:
            return cls.LOW


class BehaviorType(str, Enum):
    """
    Dominant behavior pattern detected.
    """
    ACCUMULATION = "accumulation"    # Net buying
    DISTRIBUTION = "distribution"    # Net selling
    NEUTRAL = "neutral"              # Mixed/unclear
    SHUFFLING = "shuffling"          # Internal movement (noise)


class ActivityType(str, Enum):
    """
    Type of wallet activity.
    """
    BUY = "buy"
    SELL = "sell"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    BRIDGE_IN = "bridge_in"
    BRIDGE_OUT = "bridge_out"
    SWAP = "swap"
    STAKE = "stake"
    UNSTAKE = "unstake"
    UNKNOWN = "unknown"
    
    def is_bullish(self) -> bool:
        """Check if activity is bullish."""
        return self in (ActivityType.BUY, ActivityType.TRANSFER_IN, ActivityType.STAKE)
    
    def is_bearish(self) -> bool:
        """Check if activity is bearish."""
        return self in (ActivityType.SELL, ActivityType.TRANSFER_OUT, ActivityType.UNSTAKE)


class DataSource(str, Enum):
    """
    Source of wallet/activity data.
    
    Reliability: MANUAL > ON_CHAIN > COINGLASS > API
    """
    MANUAL = "manual"              # Manually verified
    ON_CHAIN = "on_chain"          # Direct on-chain analysis
    COINGLASS = "coinglass"        # Coinglass API
    CRYPTO_NEWS_API = "crypto_news_api"  # CryptoNews API
    ARKHAM = "arkham"              # Arkham Intelligence
    NANSEN = "nansen"              # Nansen labels
    UNKNOWN = "unknown"
    
    def get_reliability(self) -> float:
        """Get source reliability score (0-1)."""
        return {
            DataSource.MANUAL: 1.0,
            DataSource.ARKHAM: 0.9,
            DataSource.NANSEN: 0.9,
            DataSource.ON_CHAIN: 0.8,
            DataSource.COINGLASS: 0.7,
            DataSource.CRYPTO_NEWS_API: 0.6,
            DataSource.UNKNOWN: 0.3,
        }.get(self, 0.3)


# =============================================================
# ACTIVITY RECORD
# =============================================================


@dataclass
class ActivityRecord:
    """
    Single wallet activity record.
    """
    wallet_address: str
    activity_type: ActivityType
    token: str
    amount_usd: float
    timestamp: datetime
    
    # Optional details
    tx_hash: Optional[str] = None
    chain: str = "ethereum"
    counterparty: Optional[str] = None  # For transfers
    price_at_activity: Optional[float] = None
    
    # Metadata
    source: DataSource = DataSource.UNKNOWN
    record_id: UUID = field(default_factory=uuid4)
    
    # Post-activity market movement (for historical analysis)
    price_change_1h: Optional[float] = None  # % change 1h after
    price_change_24h: Optional[float] = None  # % change 24h after
    
    def __post_init__(self) -> None:
        """Validate record."""
        if self.amount_usd < 0:
            self.amount_usd = abs(self.amount_usd)
    
    @property
    def is_significant(self) -> bool:
        """Check if activity is significant (> $100k)."""
        return self.amount_usd >= 100_000
    
    @property
    def is_whale_sized(self) -> bool:
        """Check if activity is whale-sized (> $1M)."""
        return self.amount_usd >= 1_000_000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "wallet_address": self.wallet_address,
            "activity_type": self.activity_type.value,
            "token": self.token,
            "amount_usd": self.amount_usd,
            "timestamp": self.timestamp.isoformat(),
            "chain": self.chain,
            "source": self.source.value,
        }


# =============================================================
# WALLET PROFILE
# =============================================================


@dataclass
class WalletProfile:
    """
    Dynamic confidence profile for a wallet.
    
    Tracks historical behavior and updates confidence over time.
    """
    address: str
    entity_type: EntityType = EntityType.UNKNOWN
    
    # Attribution
    entity_name: Optional[str] = None  # e.g., "Alameda Research"
    labels: Set[str] = field(default_factory=set)
    source: DataSource = DataSource.UNKNOWN
    verified: bool = False
    
    # Historical metrics
    total_activities: int = 0
    successful_predictions: int = 0  # Times activity preceded favorable move
    failed_predictions: int = 0
    
    # Consistency metrics
    avg_activity_size_usd: float = 0.0
    activity_size_std_dev: float = 0.0
    avg_activities_per_week: float = 0.0
    
    # Behavioral patterns
    dominant_behavior: BehaviorType = BehaviorType.NEUTRAL
    accumulation_count: int = 0
    distribution_count: int = 0
    
    # Market impact correlation
    market_impact_correlation: float = 0.0  # -1 to 1
    avg_price_change_after_activity: float = 0.0
    
    # Timestamps
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_activity: Optional[datetime] = None
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    # Calculated confidence
    base_confidence: float = 50.0  # 0-100
    dynamic_confidence: float = 50.0  # Adjusted based on history
    
    @property
    def confidence_score(self) -> float:
        """Get current confidence score."""
        return self.dynamic_confidence
    
    @property
    def prediction_accuracy(self) -> float:
        """Calculate prediction accuracy rate."""
        total = self.successful_predictions + self.failed_predictions
        if total == 0:
            return 0.5  # Neutral if no history
        return self.successful_predictions / total
    
    @property
    def is_consistent(self) -> bool:
        """Check if wallet behavior is consistent."""
        # Low variance in activity size = consistent
        if self.avg_activity_size_usd == 0:
            return False
        coefficient_of_variation = self.activity_size_std_dev / self.avg_activity_size_usd
        return coefficient_of_variation < 0.5
    
    @property
    def is_active(self) -> bool:
        """Check if wallet is actively trading."""
        return self.avg_activities_per_week >= 1.0
    
    @property
    def has_sufficient_history(self) -> bool:
        """Check if wallet has enough history for reliable scoring."""
        return self.total_activities >= 10
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "address": self.address,
            "entity_type": self.entity_type.value,
            "entity_name": self.entity_name,
            "source": self.source.value,
            "verified": self.verified,
            "total_activities": self.total_activities,
            "prediction_accuracy": round(self.prediction_accuracy, 3),
            "confidence_score": round(self.confidence_score, 1),
            "dominant_behavior": self.dominant_behavior.value,
            "is_consistent": self.is_consistent,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
        }


# =============================================================
# CLUSTER SIGNAL
# =============================================================


@dataclass
class ClusterSignal:
    """
    Signal from cluster analysis.
    
    Represents coordinated activity across multiple wallets.
    """
    cluster_id: UUID = field(default_factory=uuid4)
    wallets: List[str] = field(default_factory=list)
    
    # Cluster metrics
    wallet_count: int = 0
    total_volume_usd: float = 0.0
    avg_wallet_confidence: float = 0.0
    
    # Behavior
    dominant_behavior: BehaviorType = BehaviorType.NEUTRAL
    behavior_alignment: float = 0.0  # 0-1, how aligned are wallets
    
    # Timing
    time_window_seconds: int = 0
    first_activity: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    
    # Confidence boost
    cluster_confidence_boost: float = 0.0  # Additional confidence from clustering
    
    # Token focus
    tokens: Set[str] = field(default_factory=set)
    primary_token: Optional[str] = None
    
    @property
    def is_significant(self) -> bool:
        """Check if cluster is significant."""
        return (
            self.wallet_count >= 3 and
            self.total_volume_usd >= 1_000_000 and
            self.behavior_alignment >= 0.7
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "cluster_id": str(self.cluster_id),
            "wallet_count": self.wallet_count,
            "total_volume_usd": self.total_volume_usd,
            "dominant_behavior": self.dominant_behavior.value,
            "behavior_alignment": round(self.behavior_alignment, 2),
            "cluster_confidence_boost": round(self.cluster_confidence_boost, 1),
            "is_significant": self.is_significant,
        }


# =============================================================
# MARKET CONTEXT
# =============================================================


@dataclass
class MarketContext:
    """
    Current market context for confidence adjustment.
    """
    token: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Price action
    price: float = 0.0
    price_change_1h: float = 0.0
    price_change_24h: float = 0.0
    
    # Trend
    is_trending: bool = False
    trend_direction: str = "neutral"  # up, down, neutral
    trend_strength: float = 0.0  # 0-1
    
    # Volatility
    volatility_percentile: float = 50.0  # 0-100
    is_volatility_expanding: bool = False
    
    # Volume
    volume_24h: float = 0.0
    volume_change_24h: float = 0.0
    
    # Market structure
    near_support: bool = False
    near_resistance: bool = False
    
    @property
    def is_high_volatility(self) -> bool:
        """Check if volatility is high."""
        return self.volatility_percentile >= 70
    
    @property
    def is_low_volatility(self) -> bool:
        """Check if volatility is low."""
        return self.volatility_percentile <= 30


# =============================================================
# CONFIDENCE OUTPUT
# =============================================================


@dataclass
class ConfidenceOutput:
    """
    Final output of confidence calculation.
    
    This is what gets fed to the Flow Scoring module.
    """
    # Core output
    token: str
    score: float  # 0-100
    level: ConfidenceLevel
    dominant_behavior: BehaviorType
    explanation: str
    
    # Components
    wallet_confidence_avg: float
    entity_credibility_score: float
    historical_accuracy_score: float
    context_alignment_score: float
    cluster_boost: float
    noise_penalty: float
    
    # Activity summary
    total_activities_analyzed: int
    significant_activities: int
    wallets_involved: int
    
    # Volume
    total_volume_usd: float
    net_flow_usd: float  # Positive = inflow, negative = outflow
    
    # Time
    analysis_window_hours: int
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    calculation_id: UUID = field(default_factory=uuid4)
    
    # Debugging
    debug_factors: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    
    @property
    def is_actionable(self) -> bool:
        """Check if signal is actionable (high enough confidence)."""
        return self.level == ConfidenceLevel.HIGH
    
    @property
    def suggests_accumulation(self) -> bool:
        """Check if smart money is accumulating."""
        return (
            self.dominant_behavior == BehaviorType.ACCUMULATION and
            self.level in (ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH)
        )
    
    @property
    def suggests_distribution(self) -> bool:
        """Check if smart money is distributing."""
        return (
            self.dominant_behavior == BehaviorType.DISTRIBUTION and
            self.level in (ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH)
        )
    
    def get_risk_adjustment(self) -> float:
        """
        Get risk adjustment factor based on confidence.
        
        Returns:
            Float from 0.5 to 1.5:
            - < 1.0: Reduce risk (distribution or low confidence)
            - 1.0: Neutral
            - > 1.0: Can increase risk (accumulation + high confidence)
        """
        if self.level == ConfidenceLevel.LOW:
            return 1.0  # Neutral on low confidence
        
        if self.dominant_behavior == BehaviorType.ACCUMULATION:
            if self.level == ConfidenceLevel.HIGH:
                return 1.2  # Slight increase
            return 1.1
        
        elif self.dominant_behavior == BehaviorType.DISTRIBUTION:
            if self.level == ConfidenceLevel.HIGH:
                return 0.7  # Reduce risk
            return 0.85
        
        return 1.0  # Neutral
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/logging."""
        return {
            "token": self.token,
            "score": round(self.score, 2),
            "level": self.level.value,
            "dominant_behavior": self.dominant_behavior.value,
            "explanation": self.explanation,
            "wallet_confidence_avg": round(self.wallet_confidence_avg, 2),
            "entity_credibility_score": round(self.entity_credibility_score, 2),
            "historical_accuracy_score": round(self.historical_accuracy_score, 2),
            "context_alignment_score": round(self.context_alignment_score, 2),
            "cluster_boost": round(self.cluster_boost, 2),
            "noise_penalty": round(self.noise_penalty, 2),
            "total_activities_analyzed": self.total_activities_analyzed,
            "wallets_involved": self.wallets_involved,
            "total_volume_usd": round(self.total_volume_usd, 2),
            "net_flow_usd": round(self.net_flow_usd, 2),
            "risk_adjustment": self.get_risk_adjustment(),
            "calculated_at": self.calculated_at.isoformat(),
            "warnings": self.warnings,
        }
    
    @classmethod
    def neutral(cls, token: str, reason: str) -> "ConfidenceOutput":
        """Create a neutral output (no actionable signal)."""
        return cls(
            token=token,
            score=50.0,
            level=ConfidenceLevel.LOW,
            dominant_behavior=BehaviorType.NEUTRAL,
            explanation=reason,
            wallet_confidence_avg=50.0,
            entity_credibility_score=50.0,
            historical_accuracy_score=50.0,
            context_alignment_score=50.0,
            cluster_boost=0.0,
            noise_penalty=0.0,
            total_activities_analyzed=0,
            significant_activities=0,
            wallets_involved=0,
            total_volume_usd=0.0,
            net_flow_usd=0.0,
            analysis_window_hours=24,
            warnings=[reason],
        )
