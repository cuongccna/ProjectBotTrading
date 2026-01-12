"""
Smart Money / Whale Tracking Module.

SAFETY WARNING: Smart money signals are CONTEXT ONLY.
They feed into Flow Scoring for risk adjustment.
They CANNOT directly trigger trades.

This module operates in FREE MODE using:
- Manually curated wallets from Arkham UI
- Etherscan API (free tier) for ETH tracking
- Solana RPC for SOL tracking

Architecture is PREMIUM-READY:
- Replace public APIs with Arkham API / Nansen / Glassnode
- No changes required in Risk Scoring, Strategy, or Execution engines

Usage:
    from smart_money import SmartMoneyManager

    manager = SmartMoneyManager()
    await manager.initialize()
    
    # Get smart money signal
    signal = await manager.evaluate(time_window_minutes=60)
    
    print(f"Activity Score: {signal.activity_score}")
    print(f"Flow Direction: {signal.dominant_flow_direction.value}")
    print(f"Confidence: {signal.confidence_level.value}")
    print(f"Explanation: {signal.explanation}")

Signal Output:
- activity_score: 0-100 indicating smart money activity level
- dominant_flow_direction: inflow / outflow / neutral
- affected_assets: List of assets involved
- confidence_level: high / medium / low / degraded
- explanation: Human-readable description

Wallet Registry:
    from smart_money import WalletRegistryManager, WalletInfo, Chain, EntityType
    
    registry = WalletRegistryManager()
    
    # Add a wallet (manually sourced from Arkham UI)
    wallet = WalletInfo(
        address="0x...",
        chain=Chain.ETHEREUM,
        entity_type=EntityType.WHALE,
        entity_name="Large Holder",
        confidence_level=0.8,
    )
    registry.add_wallet(wallet)
"""

from .config import (
    ChainConfig,
    DetectionConfig,
    SmartMoneyConfig,
    get_config,
    set_config,
)
from .detector import PatternDetector
from .exceptions import (
    APIError,
    ConfigurationError,
    ParseError,
    RateLimitError,
    RPCError,
    SmartMoneyError,
    StorageError,
    TrackerUnavailableError,
    WalletNotFoundError,
)
from .manager import SmartMoneyManager, evaluate_smart_money, get_manager
from .models import (
    ActivityType,
    Chain,
    DetectedPattern,
    ENTITY_WEIGHTS,
    EntityType,
    FlowDirection,
    SignalConfidence,
    SmartMoneySignal,
    TrackerHealth,
    WalletActivity,
    WalletInfo,
)
from .registry import WalletRegistryManager
from .signal_generator import SmartMoneySignalGenerator
from .trackers import BaseOnChainTracker, EthereumTracker, SolanaTracker


__all__ = [
    # Main manager
    "SmartMoneyManager",
    "get_manager",
    "evaluate_smart_money",
    
    # Registry
    "WalletRegistryManager",
    
    # Trackers
    "BaseOnChainTracker",
    "EthereumTracker",
    "SolanaTracker",
    
    # Detector & Generator
    "PatternDetector",
    "SmartMoneySignalGenerator",
    
    # Models
    "Chain",
    "EntityType",
    "FlowDirection",
    "SignalConfidence",
    "ActivityType",
    "WalletInfo",
    "WalletActivity",
    "DetectedPattern",
    "SmartMoneySignal",
    "TrackerHealth",
    "ENTITY_WEIGHTS",
    
    # Config
    "SmartMoneyConfig",
    "ChainConfig",
    "DetectionConfig",
    "get_config",
    "set_config",
    
    # Exceptions
    "SmartMoneyError",
    "RateLimitError",
    "RPCError",
    "APIError",
    "WalletNotFoundError",
    "ParseError",
    "StorageError",
    "ConfigurationError",
    "TrackerUnavailableError",
]


# Version
__version__ = "1.0.0"
