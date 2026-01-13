"""
Signal Tier Filter - Subscription-based Signal Access Control.

============================================================
PURPOSE
============================================================
Filters strategy signals based on user subscription level.
Config-driven access control for signal tiers.

============================================================
SUBSCRIPTION LEVELS
============================================================
- Free: INFORMATIONAL only
- Paid: INFORMATIONAL + ACTIONABLE
- Premium: INFORMATIONAL + ACTIONABLE + PREMIUM

============================================================
USAGE
============================================================
    filter = SignalTierFilter.from_config(config)
    
    # Filter a single signal
    if filter.allows(signal, subscription_level="paid"):
        await notifier.send_strategy_signal(signal)
    
    # Filter multiple signals
    allowed = filter.filter_signals(signals, subscription_level="premium")

============================================================
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, Set, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from strategy_engine.types import StrategySignal, SignalBundle

logger = logging.getLogger(__name__)


# ============================================================
# SUBSCRIPTION LEVEL ENUM
# ============================================================


class SubscriptionLevel(str, Enum):
    """
    User subscription levels for signal access.
    
    Determines which signal tiers the user can access.
    """
    FREE = "free"
    PAID = "paid"
    PREMIUM = "premium"
    
    @property
    def display_name(self) -> str:
        """Human-readable name."""
        return self.value.capitalize()
    
    @classmethod
    def from_string(cls, value: str) -> "SubscriptionLevel":
        """Parse from string, case-insensitive."""
        try:
            return cls(value.lower())
        except ValueError:
            logger.warning(f"Unknown subscription level '{value}', defaulting to FREE")
            return cls.FREE


# ============================================================
# TIER ACCESS CONFIG
# ============================================================


@dataclass
class TierAccessConfig:
    """
    Configuration for a subscription level's tier access.
    """
    level: SubscriptionLevel
    allowed_tiers: Set[str]
    description: str = ""
    
    def allows_tier(self, tier: str) -> bool:
        """Check if this subscription allows the given tier."""
        return tier.lower() in self.allowed_tiers


@dataclass
class SignalTierFilterConfig:
    """
    Complete configuration for signal tier filtering.
    """
    # Mapping of subscription level to allowed tiers
    access_rules: Dict[SubscriptionLevel, TierAccessConfig] = field(default_factory=dict)
    
    # Default subscription level
    default_level: SubscriptionLevel = SubscriptionLevel.FREE
    
    # Whether to log filtered signals
    log_filtered: bool = True
    
    # Whether to include tier badge in notifications
    include_tier_badge: bool = True
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "SignalTierFilterConfig":
        """
        Create config from dictionary (parsed YAML).
        
        Expected structure:
        {
            "subscription_levels": {
                "free": {"allowed_tiers": ["informational"], ...},
                "paid": {"allowed_tiers": ["informational", "actionable"], ...},
                ...
            },
            "default_level": "free",
            "log_filtered": true,
            ...
        }
        """
        access_rules = {}
        
        levels_config = config.get("subscription_levels", {})
        for level_name, level_config in levels_config.items():
            try:
                level = SubscriptionLevel(level_name.lower())
                allowed = set(t.lower() for t in level_config.get("allowed_tiers", []))
                description = level_config.get("description", "")
                
                access_rules[level] = TierAccessConfig(
                    level=level,
                    allowed_tiers=allowed,
                    description=description,
                )
            except ValueError:
                logger.warning(f"Unknown subscription level in config: {level_name}")
        
        # Ensure all levels have a config (use defaults if missing)
        if SubscriptionLevel.FREE not in access_rules:
            access_rules[SubscriptionLevel.FREE] = TierAccessConfig(
                level=SubscriptionLevel.FREE,
                allowed_tiers={"informational"},
                description="Free tier - informational only",
            )
        
        if SubscriptionLevel.PAID not in access_rules:
            access_rules[SubscriptionLevel.PAID] = TierAccessConfig(
                level=SubscriptionLevel.PAID,
                allowed_tiers={"informational", "actionable"},
                description="Paid tier - informational and actionable",
            )
        
        if SubscriptionLevel.PREMIUM not in access_rules:
            access_rules[SubscriptionLevel.PREMIUM] = TierAccessConfig(
                level=SubscriptionLevel.PREMIUM,
                allowed_tiers={"informational", "actionable", "premium"},
                description="Premium tier - all signals",
            )
        
        # Parse other settings
        default_str = config.get("default_level", "free")
        default_level = SubscriptionLevel.from_string(default_str)
        
        return cls(
            access_rules=access_rules,
            default_level=default_level,
            log_filtered=config.get("log_filtered", True),
            include_tier_badge=config.get("include_tier_badge", True),
        )
    
    @classmethod
    def default(cls) -> "SignalTierFilterConfig":
        """Create default configuration."""
        return cls.from_dict({})


# ============================================================
# SIGNAL TIER FILTER
# ============================================================


class SignalTierFilter:
    """
    Filters signals based on subscription level.
    
    ============================================================
    FILTER RULES
    ============================================================
    - Free users: INFORMATIONAL only
    - Paid users: INFORMATIONAL + ACTIONABLE
    - Premium users: INFORMATIONAL + ACTIONABLE + PREMIUM
    
    ============================================================
    """
    
    def __init__(self, config: Optional[SignalTierFilterConfig] = None):
        """
        Initialize filter with configuration.
        
        Args:
            config: Filter configuration. Uses defaults if None.
        """
        self._config = config or SignalTierFilterConfig.default()
        logger.info(
            f"SignalTierFilter initialized with default_level={self._config.default_level.value}"
        )
    
    @classmethod
    def from_config_file(cls, config_path: str) -> "SignalTierFilter":
        """
        Create filter from YAML config file.
        
        Args:
            config_path: Path to alerts.yaml or similar config file
        """
        try:
            with open(config_path, 'r') as f:
                full_config = yaml.safe_load(f)
            
            tier_access_config = full_config.get("signal_tier_access", {})
            config = SignalTierFilterConfig.from_dict(tier_access_config)
            
            return cls(config)
            
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            return cls(SignalTierFilterConfig.default())
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "SignalTierFilter":
        """
        Create filter from dictionary config.
        
        Args:
            config_dict: signal_tier_access section of config
        """
        config = SignalTierFilterConfig.from_dict(config_dict)
        return cls(config)
    
    # --------------------------------------------------------
    # FILTERING METHODS
    # --------------------------------------------------------
    
    def allows(
        self,
        signal: "StrategySignal",
        subscription_level: str = None,
    ) -> bool:
        """
        Check if a signal is allowed for the subscription level.
        
        Args:
            signal: The StrategySignal to check
            subscription_level: Subscription level (free, paid, premium)
                               Uses default if None
        
        Returns:
            True if signal tier is allowed for subscription level
        """
        # Get subscription level
        if subscription_level:
            level = SubscriptionLevel.from_string(subscription_level)
        else:
            level = self._config.default_level
        
        # Get allowed tiers for this level
        access_config = self._config.access_rules.get(level)
        if not access_config:
            logger.warning(f"No access config for level {level}, using defaults")
            access_config = self._config.access_rules.get(SubscriptionLevel.FREE)
        
        # Check if signal's tier is allowed
        signal_tier = signal.tier.value
        allowed = access_config.allows_tier(signal_tier)
        
        if not allowed and self._config.log_filtered:
            logger.debug(
                f"Signal filtered: tier={signal_tier}, "
                f"subscription={level.value}, symbol={signal.symbol}"
            )
        
        return allowed
    
    def filter_signals(
        self,
        signals: List["StrategySignal"],
        subscription_level: str = None,
    ) -> List["StrategySignal"]:
        """
        Filter a list of signals by subscription level.
        
        Args:
            signals: List of StrategySignal objects
            subscription_level: Subscription level (free, paid, premium)
        
        Returns:
            List of allowed signals
        """
        allowed = [s for s in signals if self.allows(s, subscription_level)]
        
        if self._config.log_filtered:
            filtered_count = len(signals) - len(allowed)
            if filtered_count > 0:
                level = subscription_level or self._config.default_level.value
                logger.info(
                    f"Signal filter: {len(allowed)}/{len(signals)} signals allowed "
                    f"for subscription={level}"
                )
        
        return allowed
    
    def filter_bundle(
        self,
        bundle: "SignalBundle",
        subscription_level: str = None,
    ) -> List["StrategySignal"]:
        """
        Filter signals from a SignalBundle.
        
        Args:
            bundle: SignalBundle from StrategyEngine
            subscription_level: Subscription level
        
        Returns:
            List of allowed signals
        """
        return self.filter_signals(bundle.signals, subscription_level)
    
    # --------------------------------------------------------
    # UTILITY METHODS
    # --------------------------------------------------------
    
    def get_allowed_tiers(self, subscription_level: str) -> Set[str]:
        """
        Get the set of allowed tiers for a subscription level.
        
        Args:
            subscription_level: Subscription level name
        
        Returns:
            Set of allowed tier names
        """
        level = SubscriptionLevel.from_string(subscription_level)
        access_config = self._config.access_rules.get(level)
        
        if access_config:
            return access_config.allowed_tiers.copy()
        
        return {"informational"}
    
    def get_tier_badge(self, tier: str) -> str:
        """
        Get a display badge for a tier.
        
        Args:
            tier: Tier name
        
        Returns:
            Badge string for display
        """
        badges = {
            "informational": "ℹ️ INFO",
            "actionable": "⚡ ACTIONABLE",
            "premium": "💎 PREMIUM",
        }
        return badges.get(tier.lower(), tier.upper())
    
    def get_subscription_info(self, subscription_level: str) -> Dict[str, Any]:
        """
        Get information about a subscription level.
        
        Args:
            subscription_level: Subscription level name
        
        Returns:
            Dict with level info
        """
        level = SubscriptionLevel.from_string(subscription_level)
        access_config = self._config.access_rules.get(level)
        
        if access_config:
            return {
                "level": level.value,
                "display_name": level.display_name,
                "allowed_tiers": list(access_config.allowed_tiers),
                "description": access_config.description,
            }
        
        return {
            "level": "free",
            "display_name": "Free",
            "allowed_tiers": ["informational"],
            "description": "Free tier",
        }
    
    @property
    def config(self) -> SignalTierFilterConfig:
        """Access the filter configuration."""
        return self._config


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================


def create_signal_filter(
    config_path: Optional[str] = None,
    config_dict: Optional[Dict[str, Any]] = None,
) -> SignalTierFilter:
    """
    Create a SignalTierFilter from config.
    
    Args:
        config_path: Path to YAML config file (optional)
        config_dict: Config dictionary (optional)
    
    Returns:
        Configured SignalTierFilter
    """
    if config_path:
        return SignalTierFilter.from_config_file(config_path)
    elif config_dict:
        return SignalTierFilter.from_dict(config_dict)
    else:
        return SignalTierFilter()


def filter_signals_for_user(
    signals: List["StrategySignal"],
    subscription_level: str,
    config_path: Optional[str] = None,
) -> List["StrategySignal"]:
    """
    Filter signals for a specific user subscription level.
    
    Convenience function for one-off filtering.
    
    Args:
        signals: List of signals to filter
        subscription_level: User's subscription level
        config_path: Optional path to config file
    
    Returns:
        Filtered list of signals
    """
    filter_instance = create_signal_filter(config_path=config_path)
    return filter_instance.filter_signals(signals, subscription_level)


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    # Enums
    "SubscriptionLevel",
    # Config
    "TierAccessConfig",
    "SignalTierFilterConfig",
    # Main class
    "SignalTierFilter",
    # Convenience functions
    "create_signal_filter",
    "filter_signals_for_user",
]
