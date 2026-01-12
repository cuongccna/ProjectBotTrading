"""
Smart Money Confidence - Cluster Analyzer.

============================================================
DETECT COORDINATED WALLET ACTIVITY
============================================================

Detects when multiple wallets are acting in a coordinated manner:
- Same direction (all accumulating or all distributing)
- Within a time window
- Similar tokens

Coordinated activity increases confidence in the signal.

============================================================
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from uuid import uuid4
import logging

from .models import (
    ActivityRecord,
    ActivityType,
    BehaviorType,
    ClusterSignal,
    WalletProfile,
)
from .config import ConfidenceConfig, ClusterConfig
from .exceptions import ClusterAnalysisError


logger = logging.getLogger(__name__)


@dataclass
class ClusterCandidate:
    """
    Candidate cluster before validation.
    """
    token: str
    wallets: Set[str] = field(default_factory=set)
    activities: List[ActivityRecord] = field(default_factory=list)
    bullish_count: int = 0
    bearish_count: int = 0
    total_volume_usd: float = 0.0
    first_activity: Optional[datetime] = None
    last_activity: Optional[datetime] = None


class ClusterAnalyzer:
    """
    Analyzes wallet activity for coordinated behavior.
    
    Responsibilities:
    - Group activities by time window and token
    - Detect alignment in behavior
    - Calculate cluster confidence boost
    """
    
    def __init__(self, config: Optional[ConfidenceConfig] = None):
        """
        Initialize cluster analyzer.
        
        Args:
            config: Configuration, uses defaults if not provided
        """
        self._config = config or ConfidenceConfig()
        self._cluster_config = self._config.cluster
    
    # =========================================================
    # MAIN ANALYSIS
    # =========================================================
    
    def analyze(
        self,
        activities: List[ActivityRecord],
        wallet_profiles: Optional[Dict[str, WalletProfile]] = None,
    ) -> List[ClusterSignal]:
        """
        Analyze activities for cluster behavior.
        
        Args:
            activities: List of activities to analyze
            wallet_profiles: Optional wallet profiles for confidence weighting
            
        Returns:
            List of detected ClusterSignals
        """
        if not self._cluster_config.enabled:
            return []
        
        if len(activities) < self._cluster_config.min_cluster_size:
            return []
        
        # Group by token and time window
        candidates = self._group_activities(activities)
        
        # Validate and convert to signals
        signals = []
        for candidate in candidates:
            signal = self._validate_cluster(candidate, wallet_profiles)
            if signal:
                signals.append(signal)
        
        logger.debug(f"Found {len(signals)} cluster signals from {len(activities)} activities")
        return signals
    
    def get_cluster_boost(
        self,
        activities: List[ActivityRecord],
        wallet_profiles: Optional[Dict[str, WalletProfile]] = None,
    ) -> Tuple[float, List[ClusterSignal]]:
        """
        Get confidence boost from cluster analysis.
        
        Args:
            activities: List of activities
            wallet_profiles: Optional wallet profiles
            
        Returns:
            Tuple of (boost_amount, cluster_signals)
        """
        signals = self.analyze(activities, wallet_profiles)
        
        if not signals:
            return 0.0, []
        
        # Sum up boosts from all significant clusters
        total_boost = sum(s.cluster_confidence_boost for s in signals if s.is_significant)
        
        # Cap at max boost
        max_boost = self._cluster_config.max_cluster_boost
        capped_boost = min(total_boost, max_boost)
        
        return capped_boost, signals
    
    # =========================================================
    # GROUPING
    # =========================================================
    
    def _group_activities(self, activities: List[ActivityRecord]) -> List[ClusterCandidate]:
        """
        Group activities into cluster candidates.
        
        Groups by:
        - Token
        - Time window
        """
        # Sort by timestamp
        sorted_activities = sorted(activities, key=lambda x: x.timestamp)
        
        # Group by token first
        by_token: Dict[str, List[ActivityRecord]] = defaultdict(list)
        for activity in sorted_activities:
            by_token[activity.token.upper()].append(activity)
        
        candidates = []
        window = timedelta(minutes=self._cluster_config.cluster_window_minutes)
        
        for token, token_activities in by_token.items():
            # Sliding window grouping
            i = 0
            while i < len(token_activities):
                candidate = ClusterCandidate(token=token)
                candidate.first_activity = token_activities[i].timestamp
                candidate.last_activity = token_activities[i].timestamp
                
                # Add activities within window
                j = i
                while j < len(token_activities):
                    activity = token_activities[j]
                    
                    # Check if within window of first activity
                    if activity.timestamp - candidate.first_activity <= window:
                        self._add_to_candidate(candidate, activity)
                        candidate.last_activity = activity.timestamp
                        j += 1
                    else:
                        break
                
                # Only keep if meets minimum size
                if len(candidate.wallets) >= self._cluster_config.min_cluster_size:
                    candidates.append(candidate)
                
                # Move to next starting point
                i = max(i + 1, j - len(candidate.wallets) + 1)
        
        return candidates
    
    def _add_to_candidate(self, candidate: ClusterCandidate, activity: ActivityRecord) -> None:
        """Add activity to cluster candidate."""
        candidate.wallets.add(activity.wallet_address.lower())
        candidate.activities.append(activity)
        candidate.total_volume_usd += activity.amount_usd
        
        if activity.activity_type.is_bullish():
            candidate.bullish_count += 1
        elif activity.activity_type.is_bearish():
            candidate.bearish_count += 1
    
    # =========================================================
    # VALIDATION
    # =========================================================
    
    def _validate_cluster(
        self,
        candidate: ClusterCandidate,
        wallet_profiles: Optional[Dict[str, WalletProfile]] = None,
    ) -> Optional[ClusterSignal]:
        """
        Validate cluster candidate and convert to signal.
        
        Args:
            candidate: Cluster candidate
            wallet_profiles: Optional wallet profiles
            
        Returns:
            ClusterSignal if valid, None otherwise
        """
        # Check minimum wallets
        if len(candidate.wallets) < self._cluster_config.min_cluster_size:
            return None
        
        # Check minimum volume
        if candidate.total_volume_usd < self._cluster_config.min_cluster_volume_usd:
            return None
        
        # Calculate behavior alignment
        total_directional = candidate.bullish_count + candidate.bearish_count
        if total_directional == 0:
            return None
        
        bullish_ratio = candidate.bullish_count / total_directional
        bearish_ratio = candidate.bearish_count / total_directional
        
        alignment = max(bullish_ratio, bearish_ratio)
        
        # Check minimum alignment
        if alignment < self._cluster_config.min_behavior_alignment:
            return None
        
        # Determine dominant behavior
        if bullish_ratio > bearish_ratio:
            dominant_behavior = BehaviorType.ACCUMULATION
        elif bearish_ratio > bullish_ratio:
            dominant_behavior = BehaviorType.DISTRIBUTION
        else:
            dominant_behavior = BehaviorType.NEUTRAL
        
        # Calculate average wallet confidence
        avg_confidence = self._calculate_avg_wallet_confidence(
            list(candidate.wallets),
            wallet_profiles,
        )
        
        # Calculate confidence boost
        boost = self._calculate_cluster_boost(
            wallet_count=len(candidate.wallets),
            alignment=alignment,
            avg_confidence=avg_confidence,
            volume=candidate.total_volume_usd,
        )
        
        # Calculate time window
        time_window = 0
        if candidate.first_activity and candidate.last_activity:
            time_window = int(
                (candidate.last_activity - candidate.first_activity).total_seconds()
            )
        
        # Create signal
        signal = ClusterSignal(
            cluster_id=uuid4(),
            wallets=list(candidate.wallets),
            wallet_count=len(candidate.wallets),
            total_volume_usd=candidate.total_volume_usd,
            avg_wallet_confidence=avg_confidence,
            dominant_behavior=dominant_behavior,
            behavior_alignment=alignment,
            time_window_seconds=time_window,
            first_activity=candidate.first_activity,
            last_activity=candidate.last_activity,
            cluster_confidence_boost=boost,
            tokens={candidate.token},
            primary_token=candidate.token,
        )
        
        return signal
    
    def _calculate_avg_wallet_confidence(
        self,
        wallets: List[str],
        wallet_profiles: Optional[Dict[str, WalletProfile]],
    ) -> float:
        """Calculate average confidence score for wallets in cluster."""
        if not wallet_profiles:
            return 50.0  # Default
        
        confidences = []
        for wallet in wallets:
            wallet_lower = wallet.lower()
            if wallet_lower in wallet_profiles:
                confidences.append(wallet_profiles[wallet_lower].dynamic_confidence)
            else:
                confidences.append(50.0)  # Default for unknown
        
        if not confidences:
            return 50.0
        
        return sum(confidences) / len(confidences)
    
    def _calculate_cluster_boost(
        self,
        wallet_count: int,
        alignment: float,
        avg_confidence: float,
        volume: float,
    ) -> float:
        """
        Calculate confidence boost from cluster.
        
        Factors:
        - Number of wallets (more = higher boost)
        - Behavior alignment (higher = higher boost)
        - Average wallet confidence (higher = higher boost)
        - Volume (higher = slight boost)
        """
        config = self._cluster_config
        
        # Base boost from wallet count
        extra_wallets = wallet_count - config.min_cluster_size
        wallet_boost = extra_wallets * config.boost_per_aligned_wallet
        
        # Alignment multiplier (1.0 at min, up to 1.5 at 100%)
        alignment_multiplier = 0.5 + (alignment / 2)
        
        # Confidence multiplier (0.5 at 0 confidence, 1.5 at 100)
        confidence_multiplier = 0.5 + (avg_confidence / 100)
        
        # Volume multiplier (slight boost for very large volumes)
        volume_multiplier = 1.0
        if volume >= 5_000_000:  # $5M+
            volume_multiplier = 1.2
        elif volume >= 1_000_000:  # $1M+
            volume_multiplier = 1.1
        
        # Calculate total boost
        boost = (
            wallet_boost *
            alignment_multiplier *
            confidence_multiplier *
            volume_multiplier
        )
        
        # Cap at max
        return min(boost, config.max_cluster_boost)
    
    # =========================================================
    # UTILITIES
    # =========================================================
    
    def get_dominant_behavior(
        self,
        activities: List[ActivityRecord],
    ) -> Tuple[BehaviorType, float]:
        """
        Get dominant behavior from activities.
        
        Returns:
            Tuple of (BehaviorType, alignment_ratio)
        """
        if not activities:
            return BehaviorType.NEUTRAL, 0.0
        
        bullish = sum(1 for a in activities if a.activity_type.is_bullish())
        bearish = sum(1 for a in activities if a.activity_type.is_bearish())
        total = bullish + bearish
        
        if total == 0:
            return BehaviorType.NEUTRAL, 0.0
        
        bullish_ratio = bullish / total
        bearish_ratio = bearish / total
        
        if bullish_ratio > bearish_ratio:
            return BehaviorType.ACCUMULATION, bullish_ratio
        elif bearish_ratio > bullish_ratio:
            return BehaviorType.DISTRIBUTION, bearish_ratio
        else:
            return BehaviorType.NEUTRAL, 0.5
    
    def get_wallet_count_by_behavior(
        self,
        activities: List[ActivityRecord],
    ) -> Dict[BehaviorType, int]:
        """
        Count unique wallets by behavior type.
        
        Returns:
            Dict mapping BehaviorType to count
        """
        bullish_wallets: Set[str] = set()
        bearish_wallets: Set[str] = set()
        neutral_wallets: Set[str] = set()
        
        for activity in activities:
            wallet = activity.wallet_address.lower()
            if activity.activity_type.is_bullish():
                bullish_wallets.add(wallet)
            elif activity.activity_type.is_bearish():
                bearish_wallets.add(wallet)
            else:
                neutral_wallets.add(wallet)
        
        return {
            BehaviorType.ACCUMULATION: len(bullish_wallets),
            BehaviorType.DISTRIBUTION: len(bearish_wallets),
            BehaviorType.NEUTRAL: len(neutral_wallets),
        }
