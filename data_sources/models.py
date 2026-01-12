"""
Data Source Models - Normalized market data structures.

Provides strict typing for market data normalization across all providers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class SourceStatus(Enum):
    """Health status of a data source."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class DataType(Enum):
    """Types of market data supported."""
    KLINE = "kline"
    TICKER = "ticker"
    ORDERBOOK = "orderbook"
    TRADES = "trades"
    FUNDING_RATE = "funding_rate"
    OPEN_INTEREST = "open_interest"


class Interval(Enum):
    """Supported kline intervals."""
    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H2 = "2h"
    H4 = "4h"
    H6 = "6h"
    H8 = "8h"
    H12 = "12h"
    D1 = "1d"
    D3 = "3d"
    W1 = "1w"
    MO1 = "1M"


@dataclass(frozen=True)
class NormalizedMarketData:
    """
    Normalized market data output - STRICT schema.
    
    All providers MUST normalize their data to this format.
    No downstream module depends on provider-specific fields.
    """
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    funding_rate: Optional[Decimal]
    open_interest: Optional[Decimal]
    source_name: str
    
    # Optional extended fields
    quote_volume: Optional[Decimal] = None
    trades_count: Optional[int] = None
    taker_buy_volume: Optional[Decimal] = None
    taker_sell_volume: Optional[Decimal] = None
    interval: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
            "funding_rate": str(self.funding_rate) if self.funding_rate else None,
            "open_interest": str(self.open_interest) if self.open_interest else None,
            "source_name": self.source_name,
            "quote_volume": str(self.quote_volume) if self.quote_volume else None,
            "trades_count": self.trades_count,
            "taker_buy_volume": str(self.taker_buy_volume) if self.taker_buy_volume else None,
            "taker_sell_volume": str(self.taker_sell_volume) if self.taker_sell_volume else None,
            "interval": self.interval,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedMarketData":
        """Create from dictionary."""
        return cls(
            symbol=data["symbol"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            open=Decimal(data["open"]),
            high=Decimal(data["high"]),
            low=Decimal(data["low"]),
            close=Decimal(data["close"]),
            volume=Decimal(data["volume"]),
            funding_rate=Decimal(data["funding_rate"]) if data.get("funding_rate") else None,
            open_interest=Decimal(data["open_interest"]) if data.get("open_interest") else None,
            source_name=data["source_name"],
            quote_volume=Decimal(data["quote_volume"]) if data.get("quote_volume") else None,
            trades_count=data.get("trades_count"),
            taker_buy_volume=Decimal(data["taker_buy_volume"]) if data.get("taker_buy_volume") else None,
            taker_sell_volume=Decimal(data["taker_sell_volume"]) if data.get("taker_sell_volume") else None,
            interval=data.get("interval"),
        )


@dataclass
class SourceHealth:
    """Health status of a data source."""
    status: SourceStatus
    last_check: datetime
    latency_ms: Optional[float] = None
    error_count: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    consecutive_failures: int = 0
    uptime_percentage: float = 100.0
    
    def is_healthy(self) -> bool:
        """Check if source is operational."""
        return self.status == SourceStatus.HEALTHY
    
    def is_usable(self) -> bool:
        """Check if source can still be used (healthy or degraded)."""
        return self.status in (SourceStatus.HEALTHY, SourceStatus.DEGRADED)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "last_check": self.last_check.isoformat(),
            "latency_ms": self.latency_ms,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
            "consecutive_failures": self.consecutive_failures,
            "uptime_percentage": self.uptime_percentage,
        }


@dataclass
class SourceMetadata:
    """Metadata about a data source provider."""
    name: str
    display_name: str
    version: str
    supported_symbols: list[str]
    supported_intervals: list[Interval]
    supported_data_types: list[DataType]
    rate_limit_per_minute: int
    rate_limit_per_second: Optional[int] = None
    requires_auth: bool = False
    base_url: str = ""
    documentation_url: str = ""
    priority: int = 0  # Lower = higher priority for fallback
    tags: list[str] = field(default_factory=list)
    
    def supports_symbol(self, symbol: str) -> bool:
        """Check if symbol is supported."""
        # Empty list means all symbols supported
        if not self.supported_symbols:
            return True
        return symbol.upper() in [s.upper() for s in self.supported_symbols]
    
    def supports_interval(self, interval: Interval) -> bool:
        """Check if interval is supported."""
        return interval in self.supported_intervals
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "version": self.version,
            "supported_symbols": self.supported_symbols,
            "supported_intervals": [i.value for i in self.supported_intervals],
            "supported_data_types": [d.value for d in self.supported_data_types],
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "rate_limit_per_second": self.rate_limit_per_second,
            "requires_auth": self.requires_auth,
            "base_url": self.base_url,
            "documentation_url": self.documentation_url,
            "priority": self.priority,
            "tags": self.tags,
        }


@dataclass
class FetchRequest:
    """Request parameters for fetching market data."""
    symbol: str
    interval: Interval = Interval.H1
    data_type: DataType = DataType.KLINE
    limit: int = 100
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def validate(self) -> None:
        """Validate request parameters."""
        if not self.symbol:
            raise ValueError("Symbol is required")
        if self.limit < 1 or self.limit > 1500:
            raise ValueError("Limit must be between 1 and 1500")
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")


@dataclass
class SourceIncident:
    """Record of a data source incident."""
    source_name: str
    incident_type: str
    timestamp: datetime
    error_message: str
    request_params: Optional[dict[str, Any]] = None
    resolution: Optional[str] = None
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_name": self.source_name,
            "incident_type": self.incident_type,
            "timestamp": self.timestamp.isoformat(),
            "error_message": self.error_message,
            "request_params": self.request_params,
            "resolution": self.resolution,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
