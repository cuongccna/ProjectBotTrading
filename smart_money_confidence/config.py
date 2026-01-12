"""
Smart Money Confidence - Configuration.

============================================================
CONFIGURABLE THRESHOLDS AND WEIGHTS
============================================================

All configuration values are designed to be:
- Easily tunable
- Well-documented
- Safe defaults

============================================================
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from .models import EntityType, DataSource


# =============================================================
# ENTITY WEIGHTS
# =============================================================


@dataclass
class EntityWeights:
    """
    Weights for different entity types.
    
    Higher weight = more trusted source.
    """
    fund: float = 1.0            # Highest trust
    market_maker: float = 0.8    # High trust
    whale: float = 0.6           # Medium trust
    cex: float = 0.3             # Low trust (often noise)
    dex: float = 0.2             # Low trust (liquidity operations)
    bridge: float = 0.1          # Very low (usually noise)
    unknown: float = 0.3         # Default low trust
    
    def get_weight(self, entity_type: EntityType) -> float:
        """Get weight for entity type."""
        return {
            EntityType.FUND: self.fund,
            EntityType.MARKET_MAKER: self.market_maker,
            EntityType.WHALE: self.whale,
            EntityType.CEX: self.cex,
            EntityType.DEX: self.dex,
            EntityType.BRIDGE: self.bridge,
            EntityType.UNKNOWN: self.unknown,
        }.get(entity_type, self.unknown)


# =============================================================
# NOISE FILTER CONFIG
# =============================================================


@dataclass
class NoiseFilterConfig:
    """
    Configuration for noise filtering.
    """
    # Enable/disable filters
    filter_cex_internal: bool = True      # Filter CEX internal movements
    filter_bridge_activity: bool = True   # Filter bridge transfers
    filter_dust_transactions: bool = True  # Filter tiny transactions
    filter_round_trip: bool = True        # Filter buy+sell within window
    
    # Thresholds
    dust_threshold_usd: float = 100.0     # Ignore transactions below this
    round_trip_window_hours: int = 4      # Window for round-trip detection
    round_trip_tolerance_pct: float = 0.05  # 5% tolerance for matching
    
    # CEX detection
    cex_rotation_window_hours: int = 6    # Window for detecting CEX rotation
    
    # Bridge detection
    bridge_follow_through_hours: int = 24  # Wait for follow-through after bridge
    
    # Known noise addresses (CEX hot wallets, bridges, etc.)
    known_noise_addresses: set = field(default_factory=set)
    
    # Penalty applied for suspected noise
    noise_penalty_factor: float = 0.5     # Reduce confidence by 50%


# =============================================================
# CLUSTER CONFIG
# =============================================================


@dataclass
class ClusterConfig:
    """
    Configuration for cluster analysis.
    """
    # Enable/disable
    enabled: bool = True
    
    # Minimum cluster size
    min_cluster_size: int = 3             # Need at least 3 wallets
    
    # Time window
    cluster_window_minutes: int = 60      # 1 hour window
    
    # Alignment thresholds
    min_behavior_alignment: float = 0.7   # 70% must agree on direction
    
    # Confidence boost
    max_cluster_boost: float = 15.0       # Max points added for clustering
    boost_per_aligned_wallet: float = 2.0  # Points per additional wallet
    
    # Volume requirements
    min_cluster_volume_usd: float = 500_000  # Minimum cluster volume


# =============================================================
# HISTORICAL ACCURACY CONFIG
# =============================================================


@dataclass
class HistoricalAccuracyConfig:
    """
    Configuration for historical accuracy scoring.
    """
    # Minimum history required
    min_activities_for_accuracy: int = 10
    
    # Time horizons for measuring "success"
    short_horizon_hours: int = 1          # 1 hour after activity
    medium_horizon_hours: int = 24        # 24 hours after activity
    
    # Success thresholds
    success_threshold_pct: float = 2.0    # 2% move in predicted direction
    
    # Weight decay for old activities
    decay_half_life_days: int = 30        # Older activities count less
    
    # Accuracy scoring
    min_accuracy_for_boost: float = 0.6   # Need 60% accuracy for boost
    max_accuracy_boost: float = 20.0      # Max points for accuracy


# =============================================================
# CONTEXT ALIGNMENT CONFIG
# =============================================================


@dataclass
class ContextAlignmentConfig:
    """
    Configuration for context alignment scoring.
    """
    # Enable/disable
    enabled: bool = True
    
    # Alignment factors
    trend_alignment_weight: float = 0.4   # Weight for trend alignment
    volatility_weight: float = 0.3        # Weight for volatility context
    level_proximity_weight: float = 0.3   # Weight for support/resistance
    
    # Trend alignment
    accumulation_in_downtrend_boost: float = 10.0  # Smart money buys dips
    distribution_in_uptrend_boost: float = 10.0    # Smart money sells rallies
    
    # Volatility adjustments
    high_volatility_penalty: float = 5.0  # Reduce confidence in high vol
    low_volatility_boost: float = 5.0     # Increase confidence in calm markets


# =============================================================
# CONFIDENCE THRESHOLDS
# =============================================================


@dataclass
class ConfidenceThresholds:
    """
    Thresholds for confidence levels.
    """
    # Level boundaries
    low_max: float = 40.0                 # Below this = LOW
    medium_max: float = 70.0              # Below this = MEDIUM, above = HIGH
    
    # Minimum data requirements
    min_activities_for_signal: int = 3    # Need at least 3 activities
    min_volume_for_signal_usd: float = 100_000  # Need at least $100k
    min_wallets_for_signal: int = 1       # Need at least 1 wallet
    
    # Score components
    base_score: float = 50.0              # Starting score
    max_score: float = 100.0              # Maximum possible
    min_score: float = 0.0                # Minimum possible
    
    # Component weights
    entity_credibility_weight: float = 0.25
    historical_accuracy_weight: float = 0.25
    context_alignment_weight: float = 0.20
    cluster_weight: float = 0.15
    consistency_weight: float = 0.15


# =============================================================
# MAIN CONFIG
# =============================================================


@dataclass
class ConfidenceConfig:
    """
    Main configuration for Smart Money Confidence module.
    """
    # Sub-configs
    entity_weights: EntityWeights = field(default_factory=EntityWeights)
    noise_filter: NoiseFilterConfig = field(default_factory=NoiseFilterConfig)
    cluster: ClusterConfig = field(default_factory=ClusterConfig)
    historical_accuracy: HistoricalAccuracyConfig = field(default_factory=HistoricalAccuracyConfig)
    context_alignment: ContextAlignmentConfig = field(default_factory=ContextAlignmentConfig)
    thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    
    # Analysis window
    default_analysis_window_hours: int = 24
    
    # Data source reliability weights
    source_weights: Dict[str, float] = field(default_factory=lambda: {
        DataSource.MANUAL.value: 1.0,
        DataSource.ARKHAM.value: 0.95,
        DataSource.NANSEN.value: 0.9,
        DataSource.ON_CHAIN.value: 0.85,
        DataSource.COINGLASS.value: 0.7,
        DataSource.CRYPTO_NEWS_API.value: 0.6,
        DataSource.UNKNOWN.value: 0.4,
    })
    
    # Caching
    profile_cache_ttl_seconds: int = 3600  # 1 hour
    result_cache_ttl_seconds: int = 300    # 5 minutes
    
    # Logging
    debug_mode: bool = False
    log_calculations: bool = True
    
    @classmethod
    def from_yaml(cls, path: Path) -> "ConfidenceConfig":
        """Load configuration from YAML file."""
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML is required to load config from YAML. Install with: pip install pyyaml")
        
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        config = cls()
        
        # Load entity weights
        if 'entity_weights' in data:
            ew = data['entity_weights']
            config.entity_weights = EntityWeights(
                fund=ew.get('fund', 1.0),
                market_maker=ew.get('market_maker', 0.8),
                whale=ew.get('whale', 0.6),
                cex=ew.get('cex', 0.3),
                dex=ew.get('dex', 0.2),
                bridge=ew.get('bridge', 0.1),
                unknown=ew.get('unknown', 0.3),
            )
        
        # Load noise filter config
        if 'noise_filter' in data:
            nf = data['noise_filter']
            config.noise_filter = NoiseFilterConfig(
                filter_cex_internal=nf.get('filter_cex_internal', True),
                filter_bridge_activity=nf.get('filter_bridge_activity', True),
                filter_dust_transactions=nf.get('filter_dust_transactions', True),
                dust_threshold_usd=nf.get('dust_threshold_usd', 100.0),
            )
        
        # Load cluster config
        if 'cluster' in data:
            cc = data['cluster']
            config.cluster = ClusterConfig(
                enabled=cc.get('enabled', True),
                min_cluster_size=cc.get('min_cluster_size', 3),
                cluster_window_minutes=cc.get('cluster_window_minutes', 60),
            )
        
        # Load thresholds
        if 'thresholds' in data:
            th = data['thresholds']
            config.thresholds = ConfidenceThresholds(
                low_max=th.get('low_max', 40.0),
                medium_max=th.get('medium_max', 70.0),
                min_activities_for_signal=th.get('min_activities', 3),
            )
        
        # Load top-level settings
        config.default_analysis_window_hours = data.get('analysis_window_hours', 24)
        config.debug_mode = data.get('debug_mode', False)
        
        return config
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'entity_weights': {
                'fund': self.entity_weights.fund,
                'market_maker': self.entity_weights.market_maker,
                'whale': self.entity_weights.whale,
                'cex': self.entity_weights.cex,
                'dex': self.entity_weights.dex,
                'bridge': self.entity_weights.bridge,
                'unknown': self.entity_weights.unknown,
            },
            'noise_filter': {
                'filter_cex_internal': self.noise_filter.filter_cex_internal,
                'filter_bridge_activity': self.noise_filter.filter_bridge_activity,
                'dust_threshold_usd': self.noise_filter.dust_threshold_usd,
            },
            'cluster': {
                'enabled': self.cluster.enabled,
                'min_cluster_size': self.cluster.min_cluster_size,
                'cluster_window_minutes': self.cluster.cluster_window_minutes,
            },
            'thresholds': {
                'low_max': self.thresholds.low_max,
                'medium_max': self.thresholds.medium_max,
            },
            'analysis_window_hours': self.default_analysis_window_hours,
            'debug_mode': self.debug_mode,
        }


# =============================================================
# DEFAULT CONFIG INSTANCE
# =============================================================


def get_default_config() -> ConfidenceConfig:
    """Get default configuration."""
    return ConfidenceConfig()


def load_config(path: Optional[Path] = None) -> ConfidenceConfig:
    """
    Load configuration from file or return defaults.
    
    Args:
        path: Optional path to YAML config file
        
    Returns:
        ConfidenceConfig instance
    """
    if path and path.exists():
        return ConfidenceConfig.from_yaml(path)
    return get_default_config()
