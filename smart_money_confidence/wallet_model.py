"""
Smart Money Confidence - Wallet Confidence Model.

============================================================
DYNAMIC WALLET CONFIDENCE PROFILES
============================================================

Manages wallet profiles with dynamic confidence updating:
- Track historical behavior
- Update confidence based on prediction accuracy
- Maintain entity attribution

============================================================
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import math

from .models import (
    WalletProfile,
    ActivityRecord,
    EntityType,
    ActivityType,
    BehaviorType,
    DataSource,
)
from .config import ConfidenceConfig, HistoricalAccuracyConfig
from .exceptions import WalletNotFoundError, InvalidActivityError


logger = logging.getLogger(__name__)


class WalletConfidenceModel:
    """
    Manages wallet confidence profiles.
    
    Responsibilities:
    - Store and retrieve wallet profiles
    - Update profiles based on new activity
    - Calculate dynamic confidence scores
    - Track prediction accuracy over time
    """
    
    def __init__(self, config: Optional[ConfidenceConfig] = None):
        """
        Initialize wallet model.
        
        Args:
            config: Configuration, uses defaults if not provided
        """
        self._config = config or ConfidenceConfig()
        self._profiles: Dict[str, WalletProfile] = {}
        self._activity_history: Dict[str, List[ActivityRecord]] = {}
    
    # =========================================================
    # PROFILE MANAGEMENT
    # =========================================================
    
    def get_profile(self, address: str) -> Optional[WalletProfile]:
        """
        Get wallet profile.
        
        Args:
            address: Wallet address
            
        Returns:
            WalletProfile or None if not found
        """
        return self._profiles.get(address.lower())
    
    def get_or_create_profile(self, address: str) -> WalletProfile:
        """
        Get or create wallet profile.
        
        Args:
            address: Wallet address
            
        Returns:
            WalletProfile (existing or new)
        """
        address = address.lower()
        if address not in self._profiles:
            self._profiles[address] = WalletProfile(address=address)
            self._activity_history[address] = []
        return self._profiles[address]
    
    def set_profile(
        self,
        address: str,
        entity_type: EntityType,
        entity_name: Optional[str] = None,
        source: DataSource = DataSource.UNKNOWN,
        verified: bool = False,
        labels: Optional[set] = None,
    ) -> WalletProfile:
        """
        Set or update wallet profile with attribution.
        
        Args:
            address: Wallet address
            entity_type: Type of entity
            entity_name: Name of entity (e.g., "Alameda Research")
            source: Source of attribution
            verified: Whether attribution is verified
            labels: Additional labels
            
        Returns:
            Updated WalletProfile
        """
        profile = self.get_or_create_profile(address)
        profile.entity_type = entity_type
        profile.entity_name = entity_name
        profile.source = source
        profile.verified = verified
        if labels:
            profile.labels.update(labels)
        profile.last_updated = datetime.utcnow()
        
        # Recalculate base confidence
        profile.base_confidence = self._calculate_base_confidence(profile)
        profile.dynamic_confidence = profile.base_confidence
        
        logger.debug(f"Set profile for {address}: {entity_type.value}, confidence={profile.base_confidence}")
        return profile
    
    def has_profile(self, address: str) -> bool:
        """Check if profile exists."""
        return address.lower() in self._profiles
    
    def get_all_profiles(self) -> List[WalletProfile]:
        """Get all wallet profiles."""
        return list(self._profiles.values())
    
    def get_profiles_by_entity(self, entity_type: EntityType) -> List[WalletProfile]:
        """Get all profiles of a specific entity type."""
        return [p for p in self._profiles.values() if p.entity_type == entity_type]
    
    # =========================================================
    # ACTIVITY TRACKING
    # =========================================================
    
    def record_activity(self, activity: ActivityRecord) -> WalletProfile:
        """
        Record a new activity for a wallet.
        
        Updates profile metrics based on activity.
        
        Args:
            activity: Activity record to add
            
        Returns:
            Updated WalletProfile
        """
        address = activity.wallet_address.lower()
        profile = self.get_or_create_profile(address)
        
        # Add to history
        if address not in self._activity_history:
            self._activity_history[address] = []
        self._activity_history[address].append(activity)
        
        # Update profile metrics
        profile.total_activities += 1
        profile.last_activity = activity.timestamp
        
        # Update behavior tracking
        if activity.activity_type.is_bullish():
            profile.accumulation_count += 1
        elif activity.activity_type.is_bearish():
            profile.distribution_count += 1
        
        # Update dominant behavior
        profile.dominant_behavior = self._determine_dominant_behavior(profile)
        
        # Update activity size metrics
        self._update_size_metrics(profile, activity)
        
        # Update activity frequency
        self._update_frequency_metrics(profile)
        
        # Recalculate dynamic confidence
        profile.dynamic_confidence = self._calculate_dynamic_confidence(profile)
        profile.last_updated = datetime.utcnow()
        
        return profile
    
    def get_activity_history(
        self,
        address: str,
        hours: int = 24,
        activity_types: Optional[List[ActivityType]] = None,
    ) -> List[ActivityRecord]:
        """
        Get activity history for wallet.
        
        Args:
            address: Wallet address
            hours: Number of hours to look back
            activity_types: Filter by activity types
            
        Returns:
            List of ActivityRecords
        """
        address = address.lower()
        if address not in self._activity_history:
            return []
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        activities = [
            a for a in self._activity_history[address]
            if a.timestamp >= cutoff
        ]
        
        if activity_types:
            activities = [a for a in activities if a.activity_type in activity_types]
        
        return sorted(activities, key=lambda x: x.timestamp, reverse=True)
    
    # =========================================================
    # PREDICTION TRACKING
    # =========================================================
    
    def record_prediction_outcome(
        self,
        address: str,
        activity: ActivityRecord,
        price_change_pct: float,
    ) -> None:
        """
        Record the outcome of a prediction.
        
        Used to track how accurate wallet's activities are.
        
        Args:
            address: Wallet address
            activity: The original activity
            price_change_pct: Price change after activity (positive = up)
        """
        profile = self.get_profile(address)
        if not profile:
            return
        
        accuracy_config = self._config.historical_accuracy
        threshold = accuracy_config.success_threshold_pct
        
        # Determine if prediction was successful
        is_success = False
        if activity.activity_type.is_bullish() and price_change_pct >= threshold:
            is_success = True
        elif activity.activity_type.is_bearish() and price_change_pct <= -threshold:
            is_success = True
        
        if is_success:
            profile.successful_predictions += 1
        else:
            profile.failed_predictions += 1
        
        # Update price change tracking
        if profile.avg_price_change_after_activity == 0:
            profile.avg_price_change_after_activity = price_change_pct
        else:
            # Exponential moving average
            alpha = 0.2
            profile.avg_price_change_after_activity = (
                alpha * price_change_pct +
                (1 - alpha) * profile.avg_price_change_after_activity
            )
        
        # Recalculate confidence
        profile.dynamic_confidence = self._calculate_dynamic_confidence(profile)
    
    # =========================================================
    # CONFIDENCE CALCULATIONS
    # =========================================================
    
    def _calculate_base_confidence(self, profile: WalletProfile) -> float:
        """
        Calculate base confidence score for profile.
        
        Based on:
        - Entity type credibility
        - Source reliability
        - Verification status
        """
        # Entity credibility (0-1)
        entity_weight = self._config.entity_weights.get_weight(profile.entity_type)
        
        # Source reliability (0-1)
        source_weight = self._config.source_weights.get(
            profile.source.value,
            self._config.source_weights[DataSource.UNKNOWN.value]
        )
        
        # Verification bonus
        verified_bonus = 0.1 if profile.verified else 0
        
        # Calculate base score (0-100)
        base = (
            (entity_weight * 0.5 + source_weight * 0.3 + verified_bonus) * 100
        )
        
        return min(max(base, 0), 100)
    
    def _calculate_dynamic_confidence(self, profile: WalletProfile) -> float:
        """
        Calculate dynamic confidence score.
        
        Adjusts base confidence based on:
        - Historical accuracy
        - Consistency
        - Activity level
        - Recency of activity
        """
        base = profile.base_confidence
        adjustment = 0.0
        
        # Historical accuracy adjustment
        if profile.has_sufficient_history:
            accuracy = profile.prediction_accuracy
            accuracy_config = self._config.historical_accuracy
            
            if accuracy >= accuracy_config.min_accuracy_for_boost:
                # Boost for high accuracy
                accuracy_bonus = (accuracy - 0.5) * accuracy_config.max_accuracy_boost
                adjustment += accuracy_bonus
            elif accuracy < 0.4:
                # Penalty for low accuracy
                accuracy_penalty = (0.5 - accuracy) * accuracy_config.max_accuracy_boost
                adjustment -= accuracy_penalty
        
        # Consistency adjustment
        if profile.is_consistent:
            adjustment += 5.0
        
        # Activity level adjustment
        if profile.is_active:
            adjustment += 3.0
        elif profile.total_activities < 3:
            adjustment -= 5.0  # Not enough data
        
        # Recency adjustment
        if profile.last_activity:
            days_since = (datetime.utcnow() - profile.last_activity).days
            if days_since > 30:
                # Stale profile penalty
                adjustment -= min(10, days_since / 10)
        
        # Apply adjustment
        dynamic = base + adjustment
        
        return min(max(dynamic, 0), 100)
    
    def get_confidence_score(self, address: str) -> float:
        """
        Get current confidence score for wallet.
        
        Args:
            address: Wallet address
            
        Returns:
            Confidence score (0-100)
        """
        profile = self.get_profile(address)
        if not profile:
            return self._config.thresholds.base_score
        return profile.dynamic_confidence
    
    def get_confidence_components(self, address: str) -> Dict[str, float]:
        """
        Get breakdown of confidence score components.
        
        Args:
            address: Wallet address
            
        Returns:
            Dict with component scores
        """
        profile = self.get_profile(address)
        if not profile:
            return {
                'base_confidence': self._config.thresholds.base_score,
                'entity_credibility': 0.2,
                'source_reliability': 0.4,
                'historical_accuracy': 0.5,
                'consistency_score': 0.5,
                'activity_score': 0.0,
            }
        
        return {
            'base_confidence': profile.base_confidence,
            'dynamic_confidence': profile.dynamic_confidence,
            'entity_credibility': profile.entity_type.get_base_credibility(),
            'source_reliability': profile.source.get_reliability(),
            'historical_accuracy': profile.prediction_accuracy,
            'consistency_score': 1.0 if profile.is_consistent else 0.5,
            'activity_score': min(1.0, profile.avg_activities_per_week / 5),
            'is_verified': 1.0 if profile.verified else 0.0,
        }
    
    # =========================================================
    # HELPER METHODS
    # =========================================================
    
    def _determine_dominant_behavior(self, profile: WalletProfile) -> BehaviorType:
        """Determine dominant behavior from accumulation/distribution counts."""
        total = profile.accumulation_count + profile.distribution_count
        if total == 0:
            return BehaviorType.NEUTRAL
        
        acc_ratio = profile.accumulation_count / total
        if acc_ratio >= 0.6:
            return BehaviorType.ACCUMULATION
        elif acc_ratio <= 0.4:
            return BehaviorType.DISTRIBUTION
        else:
            return BehaviorType.NEUTRAL
    
    def _update_size_metrics(self, profile: WalletProfile, activity: ActivityRecord) -> None:
        """Update activity size metrics."""
        n = profile.total_activities
        old_avg = profile.avg_activity_size_usd
        new_value = activity.amount_usd
        
        # Update running average
        profile.avg_activity_size_usd = old_avg + (new_value - old_avg) / n
        
        # Update running standard deviation (Welford's algorithm)
        if n > 1:
            old_std = profile.activity_size_std_dev
            variance = old_std ** 2
            delta = new_value - old_avg
            delta2 = new_value - profile.avg_activity_size_usd
            variance = variance + (delta * delta2 - variance) / n
            profile.activity_size_std_dev = math.sqrt(max(0, variance))
    
    def _update_frequency_metrics(self, profile: WalletProfile) -> None:
        """Update activity frequency metrics."""
        if not self._activity_history.get(profile.address):
            return
        
        history = self._activity_history[profile.address]
        if len(history) < 2:
            return
        
        # Calculate activities per week
        first = history[0].timestamp
        last = history[-1].timestamp
        days = max(1, (last - first).days)
        weeks = days / 7
        
        if weeks > 0:
            profile.avg_activities_per_week = len(history) / weeks
    
    # =========================================================
    # BULK OPERATIONS
    # =========================================================
    
    def import_profiles(self, profiles: List[Dict]) -> int:
        """
        Bulk import wallet profiles.
        
        Args:
            profiles: List of profile dicts with address, entity_type, etc.
            
        Returns:
            Number of profiles imported
        """
        count = 0
        for p in profiles:
            try:
                self.set_profile(
                    address=p['address'],
                    entity_type=EntityType(p.get('entity_type', 'unknown')),
                    entity_name=p.get('entity_name'),
                    source=DataSource(p.get('source', 'unknown')),
                    verified=p.get('verified', False),
                    labels=set(p.get('labels', [])),
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to import profile: {e}")
        
        logger.info(f"Imported {count} wallet profiles")
        return count
    
    def export_profiles(self) -> List[Dict]:
        """
        Export all profiles to list of dicts.
        
        Returns:
            List of profile dictionaries
        """
        return [p.to_dict() for p in self._profiles.values()]
    
    def clear(self) -> None:
        """Clear all profiles and history."""
        self._profiles.clear()
        self._activity_history.clear()
        logger.info("Cleared all wallet profiles and history")
