"""
Smart Money Confidence - Main Engine.

============================================================
MAIN ORCHESTRATOR
============================================================

The ConfidenceEngine is the main entry point for the module.
It coordinates all components:
- WalletConfidenceModel
- NoiseFilter  
- ClusterAnalyzer
- ConfidenceWeightCalculator

============================================================
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging
import json

from .models import (
    ActivityRecord,
    WalletProfile,
    ConfidenceOutput,
    ConfidenceLevel,
    BehaviorType,
    MarketContext,
    ClusterSignal,
    EntityType,
    ActivityType,
    DataSource,
)
from .config import ConfidenceConfig, load_config
from .wallet_model import WalletConfidenceModel
from .noise_filter import NoiseFilter, FilterStats
from .cluster_analyzer import ClusterAnalyzer
from .calculator import ConfidenceWeightCalculator
from .exceptions import (
    SmartMoneyConfidenceError,
    InsufficientDataError,
    ConfigurationError,
)


logger = logging.getLogger(__name__)


class ConfidenceEngine:
    """
    Main orchestrator for Smart Money Confidence module.
    
    Usage:
        engine = ConfidenceEngine()
        
        # Add known wallets
        engine.register_wallet(
            address="0x123...",
            entity_type=EntityType.FUND,
            entity_name="Example Fund",
            verified=True,
        )
        
        # Calculate confidence
        output = engine.calculate_confidence(
            token="BTC",
            activities=[...],
            market_context=context,
        )
        
        print(f"Score: {output.score}")
        print(f"Level: {output.level.value}")
        print(f"Behavior: {output.dominant_behavior.value}")
    """
    
    def __init__(
        self,
        config: Optional[ConfidenceConfig] = None,
        config_path: Optional[Path] = None,
    ):
        """
        Initialize engine.
        
        Args:
            config: Configuration object
            config_path: Path to YAML config file
        """
        if config:
            self._config = config
        elif config_path:
            self._config = load_config(config_path)
        else:
            self._config = ConfidenceConfig()
        
        # Initialize components
        self._wallet_model = WalletConfidenceModel(self._config)
        self._noise_filter = NoiseFilter(self._config)
        self._cluster_analyzer = ClusterAnalyzer(self._config)
        self._calculator = ConfidenceWeightCalculator(
            config=self._config,
            wallet_model=self._wallet_model,
            noise_filter=self._noise_filter,
            cluster_analyzer=self._cluster_analyzer,
        )
        
        logger.info("ConfidenceEngine initialized")
    
    # =========================================================
    # MAIN API
    # =========================================================
    
    def calculate_confidence(
        self,
        token: str,
        activities: List[ActivityRecord],
        market_context: Optional[MarketContext] = None,
        analysis_window_hours: Optional[int] = None,
    ) -> ConfidenceOutput:
        """
        Calculate confidence score for smart money activity.
        
        This is the main entry point for confidence calculation.
        
        Args:
            token: Token symbol (e.g., "BTC", "ETH")
            activities: List of activity records to analyze
            market_context: Optional market context for alignment
            analysis_window_hours: Override default window
            
        Returns:
            ConfidenceOutput with score, level, behavior, and explanation
            
        Example:
            >>> output = engine.calculate_confidence("BTC", activities)
            >>> if output.level == ConfidenceLevel.HIGH:
            ...     print(f"High confidence {output.dominant_behavior.value}")
        """
        try:
            output = self._calculator.calculate(
                token=token,
                activities=activities,
                market_context=market_context,
                analysis_window_hours=analysis_window_hours,
            )
            
            if self._config.log_calculations:
                logger.info(
                    f"Confidence calculated for {token}: "
                    f"score={output.score:.1f}, level={output.level.value}, "
                    f"behavior={output.dominant_behavior.value}"
                )
            
            return output
            
        except Exception as e:
            logger.error(f"Error calculating confidence: {e}")
            return ConfidenceOutput.neutral(token, f"Calculation error: {str(e)}")
    
    def quick_score(
        self,
        token: str,
        activities: List[ActivityRecord],
    ) -> float:
        """
        Get just the confidence score (0-100).
        
        Simplified API for quick checks.
        
        Args:
            token: Token symbol
            activities: List of activities
            
        Returns:
            Confidence score (0-100)
        """
        output = self.calculate_confidence(token, activities)
        return output.score
    
    def get_risk_adjustment(
        self,
        token: str,
        activities: List[ActivityRecord],
        market_context: Optional[MarketContext] = None,
    ) -> float:
        """
        Get risk adjustment factor based on smart money confidence.
        
        Returns:
            Float from 0.5 to 1.5:
            - < 1.0: Reduce risk (distribution or low confidence)
            - 1.0: Neutral
            - > 1.0: Can consider increasing risk (accumulation + high confidence)
        """
        output = self.calculate_confidence(token, activities, market_context)
        return output.get_risk_adjustment()
    
    # =========================================================
    # WALLET MANAGEMENT
    # =========================================================
    
    def register_wallet(
        self,
        address: str,
        entity_type: EntityType,
        entity_name: Optional[str] = None,
        source: DataSource = DataSource.MANUAL,
        verified: bool = False,
        labels: Optional[set] = None,
    ) -> WalletProfile:
        """
        Register a known wallet.
        
        Args:
            address: Wallet address
            entity_type: Type of entity
            entity_name: Name (e.g., "Alameda Research")
            source: Source of information
            verified: Whether attribution is verified
            labels: Additional labels
            
        Returns:
            Created/updated WalletProfile
        """
        return self._wallet_model.set_profile(
            address=address,
            entity_type=entity_type,
            entity_name=entity_name,
            source=source,
            verified=verified,
            labels=labels,
        )
    
    def register_wallets_bulk(self, wallets: List[Dict[str, Any]]) -> int:
        """
        Bulk register wallets.
        
        Args:
            wallets: List of wallet dicts with keys:
                - address (required)
                - entity_type (required)
                - entity_name (optional)
                - source (optional)
                - verified (optional)
                - labels (optional)
                
        Returns:
            Number of wallets registered
        """
        return self._wallet_model.import_profiles(wallets)
    
    def get_wallet_confidence(self, address: str) -> float:
        """
        Get confidence score for a specific wallet.
        
        Args:
            address: Wallet address
            
        Returns:
            Confidence score (0-100)
        """
        return self._wallet_model.get_confidence_score(address)
    
    def get_wallet_profile(self, address: str) -> Optional[WalletProfile]:
        """
        Get wallet profile.
        
        Args:
            address: Wallet address
            
        Returns:
            WalletProfile or None
        """
        return self._wallet_model.get_profile(address)
    
    # =========================================================
    # ACTIVITY TRACKING
    # =========================================================
    
    def record_activity(self, activity: ActivityRecord) -> WalletProfile:
        """
        Record an activity for a wallet.
        
        This updates the wallet's profile with the new activity.
        
        Args:
            activity: Activity record
            
        Returns:
            Updated WalletProfile
        """
        return self._wallet_model.record_activity(activity)
    
    def record_activities_bulk(self, activities: List[ActivityRecord]) -> int:
        """
        Bulk record activities.
        
        Args:
            activities: List of activities
            
        Returns:
            Number recorded
        """
        count = 0
        for activity in activities:
            try:
                self._wallet_model.record_activity(activity)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to record activity: {e}")
        return count
    
    def record_prediction_outcome(
        self,
        address: str,
        activity: ActivityRecord,
        price_change_pct: float,
    ) -> None:
        """
        Record outcome of a prediction for historical accuracy tracking.
        
        Args:
            address: Wallet address
            activity: Original activity
            price_change_pct: Price change after activity (positive = up)
        """
        self._wallet_model.record_prediction_outcome(
            address, activity, price_change_pct
        )
    
    # =========================================================
    # NOISE MANAGEMENT
    # =========================================================
    
    def add_cex_address(self, address: str) -> None:
        """Add known CEX address for noise filtering."""
        self._noise_filter.add_cex_address(address)
    
    def add_bridge_address(self, address: str) -> None:
        """Add known bridge address for noise filtering."""
        self._noise_filter.add_bridge_address(address)
    
    def import_cex_addresses(self, addresses: List[str]) -> int:
        """Bulk import CEX addresses."""
        return self._noise_filter.import_cex_addresses(addresses)
    
    def import_bridge_addresses(self, addresses: List[str]) -> int:
        """Bulk import bridge addresses."""
        return self._noise_filter.import_bridge_addresses(addresses)
    
    # =========================================================
    # ANALYSIS
    # =========================================================
    
    def analyze_clusters(
        self,
        activities: List[ActivityRecord],
    ) -> List[ClusterSignal]:
        """
        Analyze activities for cluster behavior.
        
        Args:
            activities: List of activities
            
        Returns:
            List of detected ClusterSignals
        """
        wallet_profiles = {
            a.wallet_address.lower(): self._wallet_model.get_profile(a.wallet_address)
            for a in activities
            if self._wallet_model.get_profile(a.wallet_address)
        }
        return self._cluster_analyzer.analyze(activities, wallet_profiles)
    
    def filter_noise(
        self,
        activities: List[ActivityRecord],
    ) -> tuple[List[ActivityRecord], FilterStats]:
        """
        Filter noise from activities.
        
        Args:
            activities: List of activities
            
        Returns:
            Tuple of (filtered_activities, stats)
        """
        wallet_profiles = {
            a.wallet_address.lower(): self._wallet_model.get_profile(a.wallet_address)
            for a in activities
            if self._wallet_model.get_profile(a.wallet_address)
        }
        return self._noise_filter.filter_activities(activities, wallet_profiles)
    
    # =========================================================
    # EXPORT/IMPORT
    # =========================================================
    
    def export_profiles(self) -> List[Dict]:
        """Export all wallet profiles."""
        return self._wallet_model.export_profiles()
    
    def export_profiles_to_file(self, path: Path) -> int:
        """
        Export profiles to JSON file.
        
        Args:
            path: File path
            
        Returns:
            Number of profiles exported
        """
        profiles = self.export_profiles()
        with open(path, 'w') as f:
            json.dump(profiles, f, indent=2, default=str)
        logger.info(f"Exported {len(profiles)} profiles to {path}")
        return len(profiles)
    
    def import_profiles_from_file(self, path: Path) -> int:
        """
        Import profiles from JSON file.
        
        Args:
            path: File path
            
        Returns:
            Number of profiles imported
        """
        with open(path, 'r') as f:
            profiles = json.load(f)
        count = self.register_wallets_bulk(profiles)
        logger.info(f"Imported {count} profiles from {path}")
        return count
    
    # =========================================================
    # CONFIGURATION
    # =========================================================
    
    @property
    def config(self) -> ConfidenceConfig:
        """Get current configuration."""
        return self._config
    
    def update_config(self, **kwargs) -> None:
        """
        Update configuration values.
        
        Args:
            **kwargs: Configuration values to update
        """
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
                logger.debug(f"Updated config: {key}={value}")
    
    # =========================================================
    # HEALTH & STATUS
    # =========================================================
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get engine status and statistics.
        
        Returns:
            Dict with status information
        """
        return {
            'status': 'healthy',
            'registered_wallets': len(self._wallet_model.get_all_profiles()),
            'wallets_by_entity_type': {
                et.value: len(self._wallet_model.get_profiles_by_entity(et))
                for et in EntityType
            },
            'noise_filter_stats': {
                'cex_addresses': len(self._noise_filter._cex_addresses),
                'bridge_addresses': len(self._noise_filter._bridge_addresses),
            },
            'config': {
                'analysis_window_hours': self._config.default_analysis_window_hours,
                'min_activities_for_signal': self._config.thresholds.min_activities_for_signal,
                'cluster_enabled': self._config.cluster.enabled,
            },
        }
    
    def clear_all(self) -> None:
        """Clear all data (profiles, history, etc.)."""
        self._wallet_model.clear()
        self._noise_filter.reset_stats()
        logger.info("Cleared all engine data")


# =============================================================
# CONVENIENCE FUNCTIONS
# =============================================================


def create_engine(config_path: Optional[Path] = None) -> ConfidenceEngine:
    """
    Create a new ConfidenceEngine instance.
    
    Args:
        config_path: Optional path to config file
        
    Returns:
        ConfidenceEngine instance
    """
    return ConfidenceEngine(config_path=config_path)


def calculate_confidence(
    token: str,
    activities: List[ActivityRecord],
    market_context: Optional[MarketContext] = None,
) -> ConfidenceOutput:
    """
    Quick confidence calculation with default engine.
    
    Note: Creates a new engine each time. For repeated use,
    create an engine instance and reuse it.
    
    Args:
        token: Token symbol
        activities: List of activities
        market_context: Optional market context
        
    Returns:
        ConfidenceOutput
    """
    engine = ConfidenceEngine()
    return engine.calculate_confidence(token, activities, market_context)
