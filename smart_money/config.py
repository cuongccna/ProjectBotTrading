"""
Smart Money Configuration - Thresholds and API settings.

All thresholds are configurable for tuning.
API keys are loaded from environment variables for security.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import Chain


@dataclass
class ChainConfig:
    """Configuration for a specific blockchain."""
    chain: Chain
    enabled: bool = True
    
    # API endpoints
    explorer_api_url: str = ""
    explorer_api_key: Optional[str] = None  # Optional for free tier
    rpc_url: str = ""
    
    # Rate limits (conservative for free tier)
    requests_per_second: float = 0.2  # 1 request per 5 seconds
    requests_per_day: int = 100
    
    # Tracking settings
    max_transactions_per_query: int = 100
    lookback_blocks: int = 1000
    
    # Token decimals (common tokens)
    native_decimals: int = 18
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "chain": self.chain.value,
            "enabled": self.enabled,
            "explorer_api_url": self.explorer_api_url,
            "rpc_url": self.rpc_url,
            "requests_per_second": self.requests_per_second,
            "requests_per_day": self.requests_per_day,
        }


@dataclass
class DetectionConfig:
    """Configuration for pattern detection thresholds."""
    
    # Large transfer detection
    large_transfer_usd_threshold: float = 100_000  # $100k
    large_transfer_multiplier: float = 3.0  # 3x wallet average
    
    # CEX flow detection
    cex_flow_usd_threshold: float = 50_000  # $50k
    
    # Dormancy detection
    dormancy_days_threshold: int = 30  # Days of inactivity
    
    # Cluster detection
    cluster_time_window_minutes: int = 30
    cluster_min_transactions: int = 3
    cluster_min_wallets: int = 2
    
    # Activity scoring
    activity_score_decay_hours: int = 24  # Older activity weighted less
    min_confidence_for_signal: float = 0.3
    
    # Volume thresholds for scoring
    volume_low_usd: float = 10_000
    volume_medium_usd: float = 100_000
    volume_high_usd: float = 1_000_000
    volume_very_high_usd: float = 10_000_000
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "large_transfer_usd_threshold": self.large_transfer_usd_threshold,
            "large_transfer_multiplier": self.large_transfer_multiplier,
            "cex_flow_usd_threshold": self.cex_flow_usd_threshold,
            "dormancy_days_threshold": self.dormancy_days_threshold,
            "cluster_time_window_minutes": self.cluster_time_window_minutes,
        }


@dataclass
class SmartMoneyConfig:
    """Main configuration for smart money module."""
    
    # General settings
    enabled: bool = True
    evaluation_window_minutes: int = 60
    max_wallets_per_chain: int = 100
    
    # Chain configurations
    chains: dict[Chain, ChainConfig] = field(default_factory=dict)
    
    # Detection configuration
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    
    # Cache settings
    cache_ttl_seconds: int = 300  # 5 minutes
    stale_cache_ttl_seconds: int = 3600  # 1 hour fallback
    
    # Database
    db_path: str = "storage/smart_money.db"
    
    # Logging
    log_transactions: bool = True
    log_patterns: bool = True
    
    def __post_init__(self) -> None:
        """Initialize default chain configs if not provided."""
        if not self.chains:
            self.chains = self._default_chain_configs()
    
    def _default_chain_configs(self) -> dict[Chain, ChainConfig]:
        """Get default chain configurations with API keys from environment."""
        return {
            Chain.ETHEREUM: ChainConfig(
                chain=Chain.ETHEREUM,
                enabled=True,
                explorer_api_url="https://api.etherscan.io/api",
                explorer_api_key=os.environ.get("ETHERSCAN_API_KEY"),
                rpc_url="https://eth.llamarpc.com",
                requests_per_second=0.2,  # 5 per second free tier, be conservative
                requests_per_day=100,
                native_decimals=18,
            ),
            Chain.SOLANA: ChainConfig(
                chain=Chain.SOLANA,
                enabled=True,
                explorer_api_url="https://api.solscan.io",
                rpc_url="https://api.mainnet-beta.solana.com",
                requests_per_second=0.5,
                requests_per_day=200,
                native_decimals=9,
            ),
            Chain.BSC: ChainConfig(
                chain=Chain.BSC,
                enabled=False,  # Disabled by default
                explorer_api_url="https://api.bscscan.com/api",
                explorer_api_key=os.environ.get("BSC_ETHERSCAN_API_KEY"),
                rpc_url="https://bsc-dataseed.binance.org",
                requests_per_second=0.2,
                requests_per_day=100,
                native_decimals=18,
            ),
            Chain.POLYGON: ChainConfig(
                chain=Chain.POLYGON,
                enabled=False,
                explorer_api_url="https://api.polygonscan.com/api",
                explorer_api_key=os.environ.get("POLYGON_ETHERSCAN_API_KEY"),
                rpc_url="https://polygon-rpc.com",
                requests_per_second=0.2,
                requests_per_day=100,
                native_decimals=18,
            ),
            Chain.ARBITRUM: ChainConfig(
                chain=Chain.ARBITRUM,
                enabled=False,
                explorer_api_url="https://api.arbiscan.io/api",
                explorer_api_key=os.environ.get("ARBITRUM_ETHERSCAN_API_KEY"),
                rpc_url="https://arb1.arbitrum.io/rpc",
                requests_per_second=0.2,
                requests_per_day=100,
                native_decimals=18,
            ),
        }
    
    def get_chain_config(self, chain: Chain) -> Optional[ChainConfig]:
        """Get configuration for a specific chain."""
        return self.chains.get(chain)
    
    def get_enabled_chains(self) -> list[Chain]:
        """Get list of enabled chains."""
        return [
            chain for chain, config in self.chains.items()
            if config.enabled
        ]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "evaluation_window_minutes": self.evaluation_window_minutes,
            "max_wallets_per_chain": self.max_wallets_per_chain,
            "chains": {k.value: v.to_dict() for k, v in self.chains.items()},
            "detection": self.detection.to_dict(),
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "db_path": self.db_path,
        }


# Default configuration instance
_default_config: Optional[SmartMoneyConfig] = None


def get_config() -> SmartMoneyConfig:
    """Get the default configuration."""
    global _default_config
    if _default_config is None:
        _default_config = SmartMoneyConfig()
    return _default_config


def set_config(config: SmartMoneyConfig) -> None:
    """Set the default configuration."""
    global _default_config
    _default_config = config
