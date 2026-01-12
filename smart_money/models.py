"""
Smart Money Data Models - Wallet registry and signal structures.

SAFETY: Smart money signals are CONTEXT ONLY - never a trade trigger.
These signals feed into Flow Scoring for risk adjustment only.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class Chain(Enum):
    """Supported blockchain networks."""
    ETHEREUM = "ethereum"
    SOLANA = "solana"
    BSC = "bsc"
    POLYGON = "polygon"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    BASE = "base"
    AVALANCHE = "avalanche"


class EntityType(Enum):
    """Type of smart money entity."""
    WHALE = "whale"                    # Large individual holder
    FUND = "fund"                      # Crypto fund / VC
    MARKET_MAKER = "market_maker"      # MM / liquidity provider
    CEX_HOT = "cex_hot"                # Exchange hot wallet
    CEX_COLD = "cex_cold"              # Exchange cold wallet
    DEX = "dex"                        # DEX contract/router
    PROTOCOL = "protocol"              # DeFi protocol treasury
    BRIDGE = "bridge"                  # Cross-chain bridge
    SMART_CONTRACT = "smart_contract"  # Generic smart contract
    UNKNOWN = "unknown"


class FlowDirection(Enum):
    """Direction of smart money flow."""
    INFLOW = "inflow"      # Into tracked wallets / bullish signal
    OUTFLOW = "outflow"    # Out of tracked wallets / bearish signal
    NEUTRAL = "neutral"    # Mixed or balanced flow


class SignalConfidence(Enum):
    """Confidence level of the signal."""
    HIGH = "high"          # Multiple confirmations, reliable data
    MEDIUM = "medium"      # Some data, reasonable confidence
    LOW = "low"            # Limited data, use with caution
    DEGRADED = "degraded"  # API failures, incomplete data


class ActivityType(Enum):
    """Type of on-chain activity."""
    TRANSFER = "transfer"
    SWAP = "swap"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    STAKE = "stake"
    UNSTAKE = "unstake"
    BRIDGE = "bridge"
    CONTRACT_INTERACTION = "contract_interaction"
    UNKNOWN = "unknown"


# Entity type weights for signal importance
ENTITY_WEIGHTS: dict[EntityType, float] = {
    EntityType.FUND: 1.0,           # Funds most important
    EntityType.WHALE: 0.9,          # Whales very important
    EntityType.MARKET_MAKER: 0.8,   # MMs important
    EntityType.CEX_COLD: 0.7,       # CEX cold wallet moves
    EntityType.CEX_HOT: 0.5,        # CEX hot less significant
    EntityType.PROTOCOL: 0.6,       # Protocol treasury
    EntityType.BRIDGE: 0.4,         # Bridge activity
    EntityType.DEX: 0.3,            # DEX activity
    EntityType.SMART_CONTRACT: 0.3,
    EntityType.UNKNOWN: 0.2,
}


@dataclass
class WalletInfo:
    """
    Information about a tracked smart money wallet.
    
    Wallets are manually curated from sources like Arkham UI.
    """
    # Primary identifiers
    address: str
    chain: Chain
    
    # Classification
    entity_type: EntityType
    entity_name: Optional[str] = None  # e.g., "Jump Trading", "Wintermute"
    
    # Metadata
    source: str = "arkham_ui"  # Where this wallet was discovered
    confidence_level: float = 0.5  # Manual confidence score 0-1
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    
    # Tracking
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_activity: Optional[datetime] = None
    is_active: bool = True
    
    # Historical stats (updated periodically)
    avg_transaction_value_usd: float = 0.0
    transaction_count_30d: int = 0
    total_volume_30d_usd: float = 0.0
    
    def __post_init__(self) -> None:
        """Normalize address."""
        self.address = self.address.lower().strip()
    
    @property
    def weight(self) -> float:
        """Get entity weight for signal scoring."""
        return ENTITY_WEIGHTS.get(self.entity_type, 0.2)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "chain": self.chain.value,
            "entity_type": self.entity_type.value,
            "entity_name": self.entity_name,
            "source": self.source,
            "confidence_level": self.confidence_level,
            "tags": self.tags,
            "notes": self.notes,
            "first_seen": self.first_seen.isoformat(),
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "is_active": self.is_active,
            "avg_transaction_value_usd": self.avg_transaction_value_usd,
            "transaction_count_30d": self.transaction_count_30d,
            "total_volume_30d_usd": self.total_volume_30d_usd,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WalletInfo":
        return cls(
            address=data["address"],
            chain=Chain(data["chain"]),
            entity_type=EntityType(data["entity_type"]),
            entity_name=data.get("entity_name"),
            source=data.get("source", "arkham_ui"),
            confidence_level=data.get("confidence_level", 0.5),
            tags=data.get("tags", []),
            notes=data.get("notes", ""),
            first_seen=datetime.fromisoformat(data["first_seen"]) if data.get("first_seen") else datetime.utcnow(),
            last_activity=datetime.fromisoformat(data["last_activity"]) if data.get("last_activity") else None,
            is_active=data.get("is_active", True),
            avg_transaction_value_usd=data.get("avg_transaction_value_usd", 0.0),
            transaction_count_30d=data.get("transaction_count_30d", 0),
            total_volume_30d_usd=data.get("total_volume_30d_usd", 0.0),
        )


@dataclass
class WalletActivity:
    """
    Single on-chain activity record for a wallet.
    """
    # Transaction info
    tx_hash: str
    wallet_address: str
    chain: Chain
    timestamp: datetime
    
    # Activity details
    activity_type: ActivityType
    direction: str  # "in" or "out"
    
    # Value
    token_symbol: str
    token_address: Optional[str] = None
    amount: float = 0.0
    value_usd: float = 0.0
    
    # Counterparty
    counterparty_address: Optional[str] = None
    counterparty_entity: Optional[str] = None
    counterparty_type: Optional[EntityType] = None
    
    # Metadata
    block_number: int = 0
    gas_used: int = 0
    gas_price_gwei: float = 0.0
    
    # Flags
    is_large: bool = False  # Above historical average
    is_cex_related: bool = False  # Involves CEX wallet
    is_abnormal: bool = False  # Unusual pattern
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "tx_hash": self.tx_hash,
            "wallet_address": self.wallet_address,
            "chain": self.chain.value,
            "timestamp": self.timestamp.isoformat(),
            "activity_type": self.activity_type.value,
            "direction": self.direction,
            "token_symbol": self.token_symbol,
            "token_address": self.token_address,
            "amount": self.amount,
            "value_usd": self.value_usd,
            "counterparty_address": self.counterparty_address,
            "counterparty_entity": self.counterparty_entity,
            "counterparty_type": self.counterparty_type.value if self.counterparty_type else None,
            "block_number": self.block_number,
            "is_large": self.is_large,
            "is_cex_related": self.is_cex_related,
            "is_abnormal": self.is_abnormal,
        }


@dataclass
class DetectedPattern:
    """
    A detected pattern in smart money activity.
    """
    pattern_type: str  # "large_transfer", "cex_flow", "dormancy_break", "cluster"
    description: str
    severity: float  # 0-1
    confidence: float  # 0-1
    
    # Related data
    wallets_involved: list[str] = field(default_factory=list)
    transactions: list[str] = field(default_factory=list)
    affected_assets: list[str] = field(default_factory=list)
    
    # Context
    timestamp: datetime = field(default_factory=datetime.utcnow)
    time_window_minutes: int = 60
    
    # Metrics
    total_value_usd: float = 0.0
    flow_direction: FlowDirection = FlowDirection.NEUTRAL
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_type": self.pattern_type,
            "description": self.description,
            "severity": self.severity,
            "confidence": self.confidence,
            "wallets_involved": self.wallets_involved,
            "transactions": self.transactions,
            "affected_assets": self.affected_assets,
            "timestamp": self.timestamp.isoformat(),
            "time_window_minutes": self.time_window_minutes,
            "total_value_usd": self.total_value_usd,
            "flow_direction": self.flow_direction.value,
        }


@dataclass
class SmartMoneySignal:
    """
    Aggregated smart money signal output.
    
    SAFETY: This is CONTEXT ONLY - feeds into Flow Scoring.
    Cannot directly trigger trades.
    """
    # Core output
    activity_score: float  # 0-100
    dominant_flow_direction: FlowDirection
    confidence_level: SignalConfidence
    
    # Affected assets
    affected_assets: list[str] = field(default_factory=list)
    primary_asset: Optional[str] = None
    
    # Breakdown
    patterns_detected: list[DetectedPattern] = field(default_factory=list)
    
    # Metrics
    total_volume_usd: float = 0.0
    inflow_volume_usd: float = 0.0
    outflow_volume_usd: float = 0.0
    unique_wallets_active: int = 0
    
    # By entity type
    whale_activity_pct: float = 0.0
    fund_activity_pct: float = 0.0
    cex_activity_pct: float = 0.0
    
    # Time context
    timestamp: datetime = field(default_factory=datetime.utcnow)
    evaluation_window_minutes: int = 60
    
    # Explanation
    explanation: str = ""
    
    # Data quality
    data_completeness: float = 1.0  # 0-1, 1 = all sources responded
    api_failures: list[str] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """Validate score range."""
        self.activity_score = max(0, min(100, self.activity_score))
    
    @property
    def is_significant(self) -> bool:
        """Check if signal is significant enough to report."""
        return self.activity_score >= 30 or len(self.patterns_detected) > 0
    
    @property
    def net_flow_usd(self) -> float:
        """Net flow (positive = inflow, negative = outflow)."""
        return self.inflow_volume_usd - self.outflow_volume_usd
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_score": self.activity_score,
            "dominant_flow_direction": self.dominant_flow_direction.value,
            "confidence_level": self.confidence_level.value,
            "affected_assets": self.affected_assets,
            "primary_asset": self.primary_asset,
            "patterns_detected": [p.to_dict() for p in self.patterns_detected],
            "total_volume_usd": self.total_volume_usd,
            "inflow_volume_usd": self.inflow_volume_usd,
            "outflow_volume_usd": self.outflow_volume_usd,
            "net_flow_usd": self.net_flow_usd,
            "unique_wallets_active": self.unique_wallets_active,
            "whale_activity_pct": self.whale_activity_pct,
            "fund_activity_pct": self.fund_activity_pct,
            "cex_activity_pct": self.cex_activity_pct,
            "timestamp": self.timestamp.isoformat(),
            "evaluation_window_minutes": self.evaluation_window_minutes,
            "explanation": self.explanation,
            "data_completeness": self.data_completeness,
            "api_failures": self.api_failures,
            "is_significant": self.is_significant,
        }
    
    @classmethod
    def empty(cls, reason: str = "No data available") -> "SmartMoneySignal":
        """Create empty signal when no data is available."""
        return cls(
            activity_score=0,
            dominant_flow_direction=FlowDirection.NEUTRAL,
            confidence_level=SignalConfidence.DEGRADED,
            explanation=reason,
            data_completeness=0.0,
        )


@dataclass
class TrackerHealth:
    """Health status of an on-chain tracker."""
    chain: Chain
    is_healthy: bool
    last_check: datetime
    latency_ms: Optional[float] = None
    error_count: int = 0
    last_error: Optional[str] = None
    rate_limit_remaining: Optional[int] = None
    blocks_behind: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "chain": self.chain.value,
            "is_healthy": self.is_healthy,
            "last_check": self.last_check.isoformat(),
            "latency_ms": self.latency_ms,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "rate_limit_remaining": self.rate_limit_remaining,
            "blocks_behind": self.blocks_behind,
        }
