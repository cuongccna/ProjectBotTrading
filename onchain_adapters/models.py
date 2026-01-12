"""
On-chain Data Models - Normalized metrics for signal context and validation.

These metrics are used for signal enrichment ONLY, not for execution decisions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class AdapterStatus(Enum):
    """Health status of an on-chain adapter."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class Chain(Enum):
    """Supported blockchain networks."""
    ETHEREUM = "ethereum"
    BSC = "bsc"
    POLYGON = "polygon"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    AVALANCHE = "avalanche"
    BASE = "base"


class MetricType(Enum):
    """Types of on-chain metrics."""
    TX_COUNT = "tx_count"
    ACTIVE_ADDRESSES = "active_addresses"
    GAS_USED = "gas_used"
    NET_FLOW = "net_flow"
    WHALE_ACTIVITY = "whale_activity"
    TVL = "tvl"
    VOLUME = "volume"


@dataclass(frozen=True)
class OnchainMetrics:
    """
    Normalized on-chain metrics output - STRICT schema.
    
    Used for signal context and validation ONLY.
    Not used for execution decisions.
    """
    chain: str
    timestamp: datetime
    
    # Core metrics (always available)
    tx_count: int
    active_addresses: int
    gas_used: int
    
    # Optional metrics
    net_flow: Optional[Decimal] = None  # Net token flow (positive = inflow)
    whale_activity_score: Optional[float] = None  # 0-100 approximate score
    
    # Extended metrics
    avg_gas_price_gwei: Optional[float] = None
    pending_tx_count: Optional[int] = None
    block_number: Optional[int] = None
    avg_block_time: Optional[float] = None
    
    # Token-specific (if querying specific token)
    token_address: Optional[str] = None
    token_symbol: Optional[str] = None
    token_transfers: Optional[int] = None
    unique_holders: Optional[int] = None
    
    # Source info
    source_name: str = ""
    cached: bool = False
    cache_age_seconds: Optional[float] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "chain": self.chain,
            "timestamp": self.timestamp.isoformat(),
            "tx_count": self.tx_count,
            "active_addresses": self.active_addresses,
            "gas_used": self.gas_used,
            "net_flow": str(self.net_flow) if self.net_flow else None,
            "whale_activity_score": self.whale_activity_score,
            "avg_gas_price_gwei": self.avg_gas_price_gwei,
            "pending_tx_count": self.pending_tx_count,
            "block_number": self.block_number,
            "avg_block_time": self.avg_block_time,
            "token_address": self.token_address,
            "token_symbol": self.token_symbol,
            "token_transfers": self.token_transfers,
            "unique_holders": self.unique_holders,
            "source_name": self.source_name,
            "cached": self.cached,
            "cache_age_seconds": self.cache_age_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OnchainMetrics":
        """Create from dictionary."""
        return cls(
            chain=data["chain"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            tx_count=data["tx_count"],
            active_addresses=data["active_addresses"],
            gas_used=data["gas_used"],
            net_flow=Decimal(data["net_flow"]) if data.get("net_flow") else None,
            whale_activity_score=data.get("whale_activity_score"),
            avg_gas_price_gwei=data.get("avg_gas_price_gwei"),
            pending_tx_count=data.get("pending_tx_count"),
            block_number=data.get("block_number"),
            avg_block_time=data.get("avg_block_time"),
            token_address=data.get("token_address"),
            token_symbol=data.get("token_symbol"),
            token_transfers=data.get("token_transfers"),
            unique_holders=data.get("unique_holders"),
            source_name=data.get("source_name", ""),
            cached=data.get("cached", False),
            cache_age_seconds=data.get("cache_age_seconds"),
        )
    
    def is_stale(self, max_age_seconds: float = 300) -> bool:
        """Check if cached data is stale."""
        if not self.cached or self.cache_age_seconds is None:
            return False
        return self.cache_age_seconds > max_age_seconds


@dataclass
class AdapterHealth:
    """Health status of an on-chain adapter."""
    status: AdapterStatus
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
        """Check if adapter is operational."""
        return self.status == AdapterStatus.HEALTHY
    
    def is_usable(self) -> bool:
        """Check if adapter can still be used."""
        return self.status in (AdapterStatus.HEALTHY, AdapterStatus.DEGRADED)
    
    def is_rate_limited(self) -> bool:
        """Check if adapter is rate limited."""
        return self.status == AdapterStatus.RATE_LIMITED
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "last_check": self.last_check.isoformat(),
            "latency_ms": self.latency_ms,
            "rate_limit_remaining": self.rate_limit_remaining,
            "rate_limit_reset": self.rate_limit_reset.isoformat() if self.rate_limit_reset else None,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
            "consecutive_failures": self.consecutive_failures,
            "requests_today": self.requests_today,
            "daily_limit": self.daily_limit,
        }


@dataclass
class AdapterMetadata:
    """Metadata about an on-chain data adapter."""
    name: str
    display_name: str
    version: str
    supported_chains: list[Chain]
    supported_metrics: list[MetricType]
    rate_limit_per_second: Optional[float] = None
    rate_limit_per_day: Optional[int] = None
    requires_api_key: bool = False
    is_free_tier: bool = True
    cache_ttl_seconds: int = 300  # Default 5 min cache
    base_url: str = ""
    documentation_url: str = ""
    priority: int = 0
    tags: list[str] = field(default_factory=list)
    
    def supports_chain(self, chain: Chain) -> bool:
        """Check if chain is supported."""
        return chain in self.supported_chains
    
    def supports_metric(self, metric: MetricType) -> bool:
        """Check if metric is supported."""
        return metric in self.supported_metrics
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "version": self.version,
            "supported_chains": [c.value for c in self.supported_chains],
            "supported_metrics": [m.value for m in self.supported_metrics],
            "rate_limit_per_second": self.rate_limit_per_second,
            "rate_limit_per_day": self.rate_limit_per_day,
            "requires_api_key": self.requires_api_key,
            "is_free_tier": self.is_free_tier,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "base_url": self.base_url,
            "documentation_url": self.documentation_url,
            "priority": self.priority,
            "tags": self.tags,
        }


@dataclass
class MetricsRequest:
    """Request parameters for fetching on-chain metrics."""
    chain: Chain = Chain.ETHEREUM
    token_address: Optional[str] = None
    metrics: list[MetricType] = field(default_factory=lambda: [
        MetricType.TX_COUNT,
        MetricType.ACTIVE_ADDRESSES,
        MetricType.GAS_USED,
    ])
    time_range_hours: int = 24
    use_cache: bool = True
    max_cache_age_seconds: float = 300
    
    def validate(self) -> None:
        """Validate request parameters."""
        if self.time_range_hours < 1 or self.time_range_hours > 168:  # Max 1 week
            raise ValueError("time_range_hours must be between 1 and 168")
        if self.token_address and not self.token_address.startswith("0x"):
            raise ValueError("token_address must start with 0x")


@dataclass
class CacheEntry:
    """Cache entry for on-chain metrics."""
    data: OnchainMetrics
    created_at: datetime
    expires_at: datetime
    hits: int = 0
    
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return datetime.utcnow() > self.expires_at
    
    def age_seconds(self) -> float:
        """Get age of cache entry in seconds."""
        return (datetime.utcnow() - self.created_at).total_seconds()


@dataclass
class AdapterIncident:
    """Record of an adapter incident."""
    adapter_name: str
    incident_type: str
    timestamp: datetime
    error_message: str
    chain: Optional[str] = None
    request_params: Optional[dict[str, Any]] = None
    resolution: Optional[str] = None
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "adapter_name": self.adapter_name,
            "incident_type": self.incident_type,
            "timestamp": self.timestamp.isoformat(),
            "error_message": self.error_message,
            "chain": self.chain,
            "request_params": self.request_params,
            "resolution": self.resolution,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
