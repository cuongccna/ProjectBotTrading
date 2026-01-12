"""
Smart Money Confidence - Noise Filter.

============================================================
FILTER OUT NOISE FROM SMART MONEY DATA
============================================================

Detects and filters:
- Internal wallet shuffling
- CEX deposit/withdrawal rotations
- Bridge activity without follow-through
- Dust transactions
- Round-trip trades (buy then sell quickly)

============================================================
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
import logging

from .models import (
    ActivityRecord,
    ActivityType,
    EntityType,
    WalletProfile,
    DataSource,
)
from .config import ConfidenceConfig, NoiseFilterConfig
from .exceptions import NoiseFilterError


logger = logging.getLogger(__name__)


@dataclass
class NoiseResult:
    """
    Result of noise analysis.
    """
    is_noise: bool
    noise_type: Optional[str]
    confidence: float  # 0-1, how confident we are this is noise
    explanation: str
    penalty: float  # Confidence penalty to apply
    
    @classmethod
    def not_noise(cls) -> "NoiseResult":
        """Return result for non-noise activity."""
        return cls(
            is_noise=False,
            noise_type=None,
            confidence=0.0,
            explanation="Activity appears genuine",
            penalty=0.0,
        )
    
    @classmethod
    def noise(cls, noise_type: str, confidence: float, explanation: str, penalty: float) -> "NoiseResult":
        """Return result for noise activity."""
        return cls(
            is_noise=True,
            noise_type=noise_type,
            confidence=confidence,
            explanation=explanation,
            penalty=penalty,
        )


@dataclass
class FilterStats:
    """
    Statistics from noise filtering.
    """
    total_activities: int = 0
    filtered_activities: int = 0
    dust_filtered: int = 0
    round_trip_filtered: int = 0
    cex_rotation_filtered: int = 0
    bridge_noise_filtered: int = 0
    internal_shuffle_filtered: int = 0
    total_penalty: float = 0.0
    
    @property
    def filter_rate(self) -> float:
        """Get percentage of activities filtered."""
        if self.total_activities == 0:
            return 0.0
        return self.filtered_activities / self.total_activities


class NoiseFilter:
    """
    Filters noise from smart money activity data.
    
    Responsibilities:
    - Detect dust transactions
    - Detect round-trip trades
    - Detect CEX internal rotations
    - Detect bridge activity without follow-through
    - Detect internal wallet shuffling
    """
    
    def __init__(self, config: Optional[ConfidenceConfig] = None):
        """
        Initialize noise filter.
        
        Args:
            config: Configuration, uses defaults if not provided
        """
        self._config = config or ConfidenceConfig()
        self._noise_config = self._config.noise_filter
        
        # Known CEX addresses (simplified - in production load from data source)
        self._cex_addresses: Set[str] = set()
        self._bridge_addresses: Set[str] = set()
        
        # Stats
        self._stats = FilterStats()
    
    # =========================================================
    # MAIN FILTERING
    # =========================================================
    
    def filter_activities(
        self,
        activities: List[ActivityRecord],
        wallet_profiles: Optional[Dict[str, WalletProfile]] = None,
    ) -> Tuple[List[ActivityRecord], FilterStats]:
        """
        Filter noise from activity list.
        
        Args:
            activities: List of activities to filter
            wallet_profiles: Optional wallet profiles for context
            
        Returns:
            Tuple of (filtered_activities, stats)
        """
        if not activities:
            return [], FilterStats()
        
        # Reset stats
        stats = FilterStats(total_activities=len(activities))
        
        filtered = []
        for activity in activities:
            result = self.analyze_activity(
                activity,
                activities,
                wallet_profiles,
            )
            
            if result.is_noise:
                stats.filtered_activities += 1
                stats.total_penalty += result.penalty
                
                # Track by type
                if result.noise_type == "dust":
                    stats.dust_filtered += 1
                elif result.noise_type == "round_trip":
                    stats.round_trip_filtered += 1
                elif result.noise_type == "cex_rotation":
                    stats.cex_rotation_filtered += 1
                elif result.noise_type == "bridge_noise":
                    stats.bridge_noise_filtered += 1
                elif result.noise_type == "internal_shuffle":
                    stats.internal_shuffle_filtered += 1
                
                logger.debug(
                    f"Filtered activity: {activity.activity_type.value} "
                    f"${activity.amount_usd:,.0f} - {result.noise_type}"
                )
            else:
                filtered.append(activity)
        
        self._stats = stats
        return filtered, stats
    
    def analyze_activity(
        self,
        activity: ActivityRecord,
        all_activities: List[ActivityRecord],
        wallet_profiles: Optional[Dict[str, WalletProfile]] = None,
    ) -> NoiseResult:
        """
        Analyze a single activity for noise.
        
        Args:
            activity: Activity to analyze
            all_activities: All activities for context
            wallet_profiles: Optional wallet profiles
            
        Returns:
            NoiseResult
        """
        # Check each noise type
        checks = [
            self._check_dust(activity),
            self._check_round_trip(activity, all_activities),
            self._check_cex_rotation(activity, all_activities, wallet_profiles),
            self._check_bridge_noise(activity, all_activities, wallet_profiles),
            self._check_internal_shuffle(activity, all_activities, wallet_profiles),
        ]
        
        # Return first noise match
        for result in checks:
            if result.is_noise:
                return result
        
        return NoiseResult.not_noise()
    
    def get_noise_penalty(
        self,
        activities: List[ActivityRecord],
        wallet_profiles: Optional[Dict[str, WalletProfile]] = None,
    ) -> float:
        """
        Calculate noise penalty for a set of activities.
        
        Returns value between 0 and max penalty.
        Higher = more noise detected.
        """
        if not activities:
            return 0.0
        
        _, stats = self.filter_activities(activities, wallet_profiles)
        
        # Calculate penalty based on filter rate
        filter_rate = stats.filter_rate
        max_penalty = 20.0  # Maximum 20 points penalty
        
        return filter_rate * max_penalty
    
    # =========================================================
    # NOISE CHECKS
    # =========================================================
    
    def _check_dust(self, activity: ActivityRecord) -> NoiseResult:
        """Check if activity is dust (too small to matter)."""
        if not self._noise_config.filter_dust_transactions:
            return NoiseResult.not_noise()
        
        if activity.amount_usd < self._noise_config.dust_threshold_usd:
            return NoiseResult.noise(
                noise_type="dust",
                confidence=0.95,
                explanation=f"Dust transaction (${activity.amount_usd:.2f} < threshold)",
                penalty=self._noise_config.noise_penalty_factor * 5,
            )
        
        return NoiseResult.not_noise()
    
    def _check_round_trip(
        self,
        activity: ActivityRecord,
        all_activities: List[ActivityRecord],
    ) -> NoiseResult:
        """
        Check if activity is part of a round-trip trade.
        
        Round-trip = buy then sell (or vice versa) within short window.
        """
        if not self._noise_config.filter_round_trip:
            return NoiseResult.not_noise()
        
        window = timedelta(hours=self._noise_config.round_trip_window_hours)
        tolerance = self._noise_config.round_trip_tolerance_pct
        
        # Get same-wallet activities within window
        same_wallet = [
            a for a in all_activities
            if (
                a.wallet_address == activity.wallet_address and
                a.token == activity.token and
                a.record_id != activity.record_id and
                abs((a.timestamp - activity.timestamp)) <= window
            )
        ]
        
        for other in same_wallet:
            # Check if opposite direction
            is_opposite = (
                (activity.activity_type.is_bullish() and other.activity_type.is_bearish()) or
                (activity.activity_type.is_bearish() and other.activity_type.is_bullish())
            )
            
            if not is_opposite:
                continue
            
            # Check if similar size
            size_diff = abs(activity.amount_usd - other.amount_usd)
            avg_size = (activity.amount_usd + other.amount_usd) / 2
            if avg_size > 0 and size_diff / avg_size <= tolerance:
                return NoiseResult.noise(
                    noise_type="round_trip",
                    confidence=0.85,
                    explanation=(
                        f"Round-trip detected: {activity.activity_type.value} "
                        f"followed by {other.activity_type.value} within {window}"
                    ),
                    penalty=self._noise_config.noise_penalty_factor * 10,
                )
        
        return NoiseResult.not_noise()
    
    def _check_cex_rotation(
        self,
        activity: ActivityRecord,
        all_activities: List[ActivityRecord],
        wallet_profiles: Optional[Dict[str, WalletProfile]] = None,
    ) -> NoiseResult:
        """
        Check if activity is CEX internal rotation.
        
        CEX rotation = deposit to CEX followed by withdrawal (or vice versa).
        """
        if not self._noise_config.filter_cex_internal:
            return NoiseResult.not_noise()
        
        # Check if counterparty is CEX
        if activity.counterparty:
            counterparty_lower = activity.counterparty.lower()
            
            # Check known CEX addresses
            if counterparty_lower in self._cex_addresses:
                is_cex = True
            elif wallet_profiles and counterparty_lower in wallet_profiles:
                is_cex = wallet_profiles[counterparty_lower].entity_type == EntityType.CEX
            else:
                is_cex = False
            
            if is_cex:
                # Check for matching opposite transaction
                window = timedelta(hours=self._noise_config.cex_rotation_window_hours)
                
                opposite_type = (
                    ActivityType.TRANSFER_OUT if activity.activity_type == ActivityType.TRANSFER_IN
                    else ActivityType.TRANSFER_IN
                )
                
                matching = [
                    a for a in all_activities
                    if (
                        a.wallet_address == activity.wallet_address and
                        a.activity_type == opposite_type and
                        a.counterparty == activity.counterparty and
                        abs((a.timestamp - activity.timestamp)) <= window
                    )
                ]
                
                if matching:
                    return NoiseResult.noise(
                        noise_type="cex_rotation",
                        confidence=0.8,
                        explanation="CEX deposit/withdrawal rotation detected",
                        penalty=self._noise_config.noise_penalty_factor * 8,
                    )
        
        return NoiseResult.not_noise()
    
    def _check_bridge_noise(
        self,
        activity: ActivityRecord,
        all_activities: List[ActivityRecord],
        wallet_profiles: Optional[Dict[str, WalletProfile]] = None,
    ) -> NoiseResult:
        """
        Check if activity is bridge noise.
        
        Bridge noise = bridge transfer without meaningful follow-through.
        """
        if not self._noise_config.filter_bridge_activity:
            return NoiseResult.not_noise()
        
        # Check if this is a bridge activity
        is_bridge = activity.activity_type in (
            ActivityType.BRIDGE_IN,
            ActivityType.BRIDGE_OUT,
        )
        
        if not is_bridge:
            # Check if counterparty is bridge
            if activity.counterparty:
                counterparty_lower = activity.counterparty.lower()
                if counterparty_lower in self._bridge_addresses:
                    is_bridge = True
                elif wallet_profiles and counterparty_lower in wallet_profiles:
                    is_bridge = wallet_profiles[counterparty_lower].entity_type == EntityType.BRIDGE
        
        if not is_bridge:
            return NoiseResult.not_noise()
        
        # Check for follow-through activity
        follow_window = timedelta(hours=self._noise_config.bridge_follow_through_hours)
        
        follow_through = [
            a for a in all_activities
            if (
                a.wallet_address == activity.wallet_address and
                a.timestamp > activity.timestamp and
                (a.timestamp - activity.timestamp) <= follow_window and
                a.activity_type in (ActivityType.BUY, ActivityType.SELL, ActivityType.SWAP)
            )
        ]
        
        if not follow_through:
            return NoiseResult.noise(
                noise_type="bridge_noise",
                confidence=0.7,
                explanation=f"Bridge activity without follow-through within {follow_window}",
                penalty=self._noise_config.noise_penalty_factor * 5,
            )
        
        return NoiseResult.not_noise()
    
    def _check_internal_shuffle(
        self,
        activity: ActivityRecord,
        all_activities: List[ActivityRecord],
        wallet_profiles: Optional[Dict[str, WalletProfile]] = None,
    ) -> NoiseResult:
        """
        Check if activity is internal wallet shuffling.
        
        Internal shuffle = transfer between wallets owned by same entity.
        """
        if activity.activity_type not in (ActivityType.TRANSFER_IN, ActivityType.TRANSFER_OUT):
            return NoiseResult.not_noise()
        
        if not activity.counterparty or not wallet_profiles:
            return NoiseResult.not_noise()
        
        # Get profiles
        wallet_lower = activity.wallet_address.lower()
        counterparty_lower = activity.counterparty.lower()
        
        wallet_profile = wallet_profiles.get(wallet_lower)
        counterparty_profile = wallet_profiles.get(counterparty_lower)
        
        if not wallet_profile or not counterparty_profile:
            return NoiseResult.not_noise()
        
        # Check if same entity
        if (
            wallet_profile.entity_name and
            counterparty_profile.entity_name and
            wallet_profile.entity_name == counterparty_profile.entity_name
        ):
            return NoiseResult.noise(
                noise_type="internal_shuffle",
                confidence=0.9,
                explanation=f"Internal transfer between {wallet_profile.entity_name} wallets",
                penalty=self._noise_config.noise_penalty_factor * 10,
            )
        
        return NoiseResult.not_noise()
    
    # =========================================================
    # ADDRESS MANAGEMENT
    # =========================================================
    
    def add_cex_address(self, address: str) -> None:
        """Add known CEX address."""
        self._cex_addresses.add(address.lower())
    
    def add_bridge_address(self, address: str) -> None:
        """Add known bridge address."""
        self._bridge_addresses.add(address.lower())
    
    def add_noise_address(self, address: str) -> None:
        """Add address to known noise list."""
        self._noise_config.known_noise_addresses.add(address.lower())
    
    def import_cex_addresses(self, addresses: List[str]) -> int:
        """Bulk import CEX addresses."""
        for addr in addresses:
            self._cex_addresses.add(addr.lower())
        return len(addresses)
    
    def import_bridge_addresses(self, addresses: List[str]) -> int:
        """Bulk import bridge addresses."""
        for addr in addresses:
            self._bridge_addresses.add(addr.lower())
        return len(addresses)
    
    # =========================================================
    # STATS
    # =========================================================
    
    def get_stats(self) -> FilterStats:
        """Get filtering statistics."""
        return self._stats
    
    def reset_stats(self) -> None:
        """Reset filtering statistics."""
        self._stats = FilterStats()
