"""
Smart Money Confidence - Confidence Calculator.

============================================================
MAIN SCORING ENGINE
============================================================

Combines all factors to calculate final confidence score:
- Entity credibility
- Historical accuracy
- Context alignment
- Cluster boost
- Noise penalty

============================================================
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging
import math

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
)
from .config import ConfidenceConfig, ConfidenceThresholds
from .wallet_model import WalletConfidenceModel
from .noise_filter import NoiseFilter, FilterStats
from .cluster_analyzer import ClusterAnalyzer
from .exceptions import InsufficientDataError, CalculationError


logger = logging.getLogger(__name__)


@dataclass
class CalculationComponents:
    """
    Breakdown of calculation components.
    """
    entity_credibility: float = 50.0
    historical_accuracy: float = 50.0
    context_alignment: float = 50.0
    consistency: float = 50.0
    cluster_boost: float = 0.0
    noise_penalty: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            'entity_credibility': round(self.entity_credibility, 2),
            'historical_accuracy': round(self.historical_accuracy, 2),
            'context_alignment': round(self.context_alignment, 2),
            'consistency': round(self.consistency, 2),
            'cluster_boost': round(self.cluster_boost, 2),
            'noise_penalty': round(self.noise_penalty, 2),
        }


class ConfidenceWeightCalculator:
    """
    Main scoring engine for smart money confidence.
    
    Responsibilities:
    - Calculate entity credibility score
    - Calculate historical accuracy score
    - Calculate context alignment score
    - Apply cluster boost
    - Apply noise penalty
    - Combine into final score
    """
    
    def __init__(
        self,
        config: Optional[ConfidenceConfig] = None,
        wallet_model: Optional[WalletConfidenceModel] = None,
        noise_filter: Optional[NoiseFilter] = None,
        cluster_analyzer: Optional[ClusterAnalyzer] = None,
    ):
        """
        Initialize calculator.
        
        Args:
            config: Configuration
            wallet_model: Wallet confidence model
            noise_filter: Noise filter
            cluster_analyzer: Cluster analyzer
        """
        self._config = config or ConfidenceConfig()
        self._wallet_model = wallet_model or WalletConfidenceModel(self._config)
        self._noise_filter = noise_filter or NoiseFilter(self._config)
        self._cluster_analyzer = cluster_analyzer or ClusterAnalyzer(self._config)
    
    # =========================================================
    # MAIN CALCULATION
    # =========================================================
    
    def calculate(
        self,
        token: str,
        activities: List[ActivityRecord],
        market_context: Optional[MarketContext] = None,
        analysis_window_hours: Optional[int] = None,
    ) -> ConfidenceOutput:
        """
        Calculate confidence score for smart money activity.
        
        Args:
            token: Token symbol
            activities: List of activities to analyze
            market_context: Optional market context
            analysis_window_hours: Override default window
            
        Returns:
            ConfidenceOutput with score and breakdown
        """
        window_hours = analysis_window_hours or self._config.default_analysis_window_hours
        thresholds = self._config.thresholds
        
        # Check minimum data requirements
        if not activities:
            return ConfidenceOutput.neutral(token, "No activities provided")
        
        if len(activities) < thresholds.min_activities_for_signal:
            return ConfidenceOutput.neutral(
                token,
                f"Insufficient activities: {len(activities)} < {thresholds.min_activities_for_signal}"
            )
        
        # Get wallet profiles
        wallet_profiles = self._get_wallet_profiles(activities)
        
        # Filter noise
        filtered_activities, filter_stats = self._noise_filter.filter_activities(
            activities, wallet_profiles
        )
        
        # Check after filtering
        if len(filtered_activities) < thresholds.min_activities_for_signal:
            return ConfidenceOutput.neutral(
                token,
                f"Insufficient activities after noise filtering: {len(filtered_activities)}"
            )
        
        # Calculate volume
        total_volume = sum(a.amount_usd for a in filtered_activities)
        if total_volume < thresholds.min_volume_for_signal_usd:
            return ConfidenceOutput.neutral(
                token,
                f"Insufficient volume: ${total_volume:,.0f} < ${thresholds.min_volume_for_signal_usd:,.0f}"
            )
        
        # Calculate components
        components = self._calculate_components(
            filtered_activities,
            wallet_profiles,
            market_context,
            filter_stats,
        )
        
        # Calculate final score
        score = self._combine_scores(components)
        
        # Determine behavior
        behavior, alignment = self._cluster_analyzer.get_dominant_behavior(filtered_activities)
        
        # Calculate net flow
        net_flow = self._calculate_net_flow(filtered_activities)
        
        # Get unique wallets
        wallets = set(a.wallet_address.lower() for a in filtered_activities)
        
        # Build explanation
        explanation = self._build_explanation(
            score, behavior, components, len(wallets), total_volume
        )
        
        # Get warnings
        warnings = self._get_warnings(
            filtered_activities, filter_stats, components
        )
        
        return ConfidenceOutput(
            token=token,
            score=score,
            level=ConfidenceLevel.from_score(score),
            dominant_behavior=behavior,
            explanation=explanation,
            wallet_confidence_avg=components.entity_credibility,
            entity_credibility_score=components.entity_credibility,
            historical_accuracy_score=components.historical_accuracy,
            context_alignment_score=components.context_alignment,
            cluster_boost=components.cluster_boost,
            noise_penalty=components.noise_penalty,
            total_activities_analyzed=len(activities),
            significant_activities=len([a for a in filtered_activities if a.is_significant]),
            wallets_involved=len(wallets),
            total_volume_usd=total_volume,
            net_flow_usd=net_flow,
            analysis_window_hours=window_hours,
            debug_factors=components.to_dict(),
            warnings=warnings,
        )
    
    # =========================================================
    # COMPONENT CALCULATIONS
    # =========================================================
    
    def _calculate_components(
        self,
        activities: List[ActivityRecord],
        wallet_profiles: Dict[str, WalletProfile],
        market_context: Optional[MarketContext],
        filter_stats: FilterStats,
    ) -> CalculationComponents:
        """Calculate all scoring components."""
        components = CalculationComponents()
        
        # Entity credibility
        components.entity_credibility = self._calculate_entity_credibility(
            activities, wallet_profiles
        )
        
        # Historical accuracy
        components.historical_accuracy = self._calculate_historical_accuracy(
            wallet_profiles
        )
        
        # Context alignment
        if market_context:
            components.context_alignment = self._calculate_context_alignment(
                activities, market_context
            )
        
        # Consistency
        components.consistency = self._calculate_consistency(
            activities, wallet_profiles
        )
        
        # Cluster boost
        boost, _ = self._cluster_analyzer.get_cluster_boost(
            activities, wallet_profiles
        )
        components.cluster_boost = boost
        
        # Noise penalty
        components.noise_penalty = self._calculate_noise_penalty(filter_stats)
        
        return components
    
    def _calculate_entity_credibility(
        self,
        activities: List[ActivityRecord],
        wallet_profiles: Dict[str, WalletProfile],
    ) -> float:
        """
        Calculate entity credibility score.
        
        Weighted average of wallet confidences, weighted by volume.
        """
        if not activities:
            return 50.0
        
        total_weighted = 0.0
        total_weight = 0.0
        
        for activity in activities:
            wallet = activity.wallet_address.lower()
            weight = activity.amount_usd
            
            if wallet in wallet_profiles:
                profile = wallet_profiles[wallet]
                credibility = profile.entity_type.get_base_credibility() * 100
                
                # Boost for verified
                if profile.verified:
                    credibility = min(100, credibility * 1.1)
            else:
                credibility = EntityType.UNKNOWN.get_base_credibility() * 100
            
            total_weighted += credibility * weight
            total_weight += weight
        
        if total_weight == 0:
            return 50.0
        
        return total_weighted / total_weight
    
    def _calculate_historical_accuracy(
        self,
        wallet_profiles: Dict[str, WalletProfile],
    ) -> float:
        """
        Calculate historical accuracy score.
        
        Average prediction accuracy of wallets.
        """
        if not wallet_profiles:
            return 50.0
        
        accuracies = []
        for profile in wallet_profiles.values():
            if profile.has_sufficient_history:
                accuracies.append(profile.prediction_accuracy)
        
        if not accuracies:
            return 50.0  # No historical data
        
        avg_accuracy = sum(accuracies) / len(accuracies)
        
        # Convert to 0-100 scale (0.5 = 50, 1.0 = 100, 0.0 = 0)
        return avg_accuracy * 100
    
    def _calculate_context_alignment(
        self,
        activities: List[ActivityRecord],
        context: MarketContext,
    ) -> float:
        """
        Calculate context alignment score.
        
        Measures how well smart money activity aligns with market context.
        """
        if not self._config.context_alignment.enabled:
            return 50.0
        
        score = 50.0
        config = self._config.context_alignment
        
        # Get dominant behavior
        behavior, _ = self._cluster_analyzer.get_dominant_behavior(activities)
        
        # Trend alignment
        if behavior == BehaviorType.ACCUMULATION:
            if context.trend_direction == "down":
                # Smart money buying dip - bullish signal
                score += config.accumulation_in_downtrend_boost
            elif context.trend_direction == "up":
                # Buying in uptrend - confirming
                score += config.accumulation_in_downtrend_boost * 0.5
        
        elif behavior == BehaviorType.DISTRIBUTION:
            if context.trend_direction == "up":
                # Smart money selling rallies - bearish signal
                score += config.distribution_in_uptrend_boost
            elif context.trend_direction == "down":
                # Selling in downtrend - panic?
                score -= 5.0
        
        # Volatility adjustment
        if context.is_high_volatility:
            score -= config.high_volatility_penalty
        elif context.is_low_volatility:
            score += config.low_volatility_boost
        
        # Support/resistance alignment
        if behavior == BehaviorType.ACCUMULATION and context.near_support:
            score += 5.0  # Buying at support is smart
        elif behavior == BehaviorType.DISTRIBUTION and context.near_resistance:
            score += 5.0  # Selling at resistance is smart
        
        return min(max(score, 0), 100)
    
    def _calculate_consistency(
        self,
        activities: List[ActivityRecord],
        wallet_profiles: Dict[str, WalletProfile],
    ) -> float:
        """
        Calculate consistency score.
        
        Measures behavioral consistency across wallets.
        """
        if not activities:
            return 50.0
        
        # Check wallet consistency
        consistent_count = 0
        total_with_profile = 0
        
        for wallet in set(a.wallet_address.lower() for a in activities):
            if wallet in wallet_profiles:
                profile = wallet_profiles[wallet]
                total_with_profile += 1
                if profile.is_consistent:
                    consistent_count += 1
        
        if total_with_profile == 0:
            return 50.0
        
        consistency_ratio = consistent_count / total_with_profile
        
        # Also check behavior alignment
        behavior, alignment = self._cluster_analyzer.get_dominant_behavior(activities)
        
        # Combine (weighted average)
        return (consistency_ratio * 50 + alignment * 50)
    
    def _calculate_noise_penalty(self, filter_stats: FilterStats) -> float:
        """
        Calculate noise penalty.
        
        Based on how much of the data was filtered as noise.
        """
        if filter_stats.total_activities == 0:
            return 0.0
        
        # Penalty based on filter rate
        filter_rate = filter_stats.filter_rate
        max_penalty = 20.0
        
        return filter_rate * max_penalty
    
    # =========================================================
    # SCORE COMBINATION
    # =========================================================
    
    def _combine_scores(self, components: CalculationComponents) -> float:
        """
        Combine component scores into final score.
        
        Uses weighted average with boost/penalty.
        """
        thresholds = self._config.thresholds
        
        # Weighted average of components
        weighted = (
            components.entity_credibility * thresholds.entity_credibility_weight +
            components.historical_accuracy * thresholds.historical_accuracy_weight +
            components.context_alignment * thresholds.context_alignment_weight +
            components.consistency * thresholds.consistency_weight
        )
        
        # Normalize (weights should sum to < 1.0, leaving room for cluster)
        weight_sum = (
            thresholds.entity_credibility_weight +
            thresholds.historical_accuracy_weight +
            thresholds.context_alignment_weight +
            thresholds.consistency_weight
        )
        
        if weight_sum > 0:
            weighted = weighted / weight_sum
        
        # Apply cluster boost
        score = weighted + components.cluster_boost
        
        # Apply noise penalty
        score = score - components.noise_penalty
        
        # Clamp to valid range
        return min(max(score, thresholds.min_score), thresholds.max_score)
    
    # =========================================================
    # HELPERS
    # =========================================================
    
    def _get_wallet_profiles(
        self,
        activities: List[ActivityRecord],
    ) -> Dict[str, WalletProfile]:
        """Get wallet profiles for all wallets in activities."""
        profiles = {}
        for activity in activities:
            wallet = activity.wallet_address.lower()
            if wallet not in profiles:
                profile = self._wallet_model.get_profile(wallet)
                if profile:
                    profiles[wallet] = profile
        return profiles
    
    def _calculate_net_flow(self, activities: List[ActivityRecord]) -> float:
        """
        Calculate net flow from activities.
        
        Positive = net inflow (accumulation)
        Negative = net outflow (distribution)
        """
        inflow = sum(
            a.amount_usd for a in activities
            if a.activity_type.is_bullish()
        )
        outflow = sum(
            a.amount_usd for a in activities
            if a.activity_type.is_bearish()
        )
        return inflow - outflow
    
    def _build_explanation(
        self,
        score: float,
        behavior: BehaviorType,
        components: CalculationComponents,
        wallet_count: int,
        volume: float,
    ) -> str:
        """Build human-readable explanation."""
        level = ConfidenceLevel.from_score(score)
        
        behavior_text = {
            BehaviorType.ACCUMULATION: "accumulating",
            BehaviorType.DISTRIBUTION: "distributing",
            BehaviorType.NEUTRAL: "showing mixed activity in",
            BehaviorType.SHUFFLING: "shuffling",
        }.get(behavior, "active in")
        
        confidence_text = {
            ConfidenceLevel.HIGH: "High confidence",
            ConfidenceLevel.MEDIUM: "Moderate confidence",
            ConfidenceLevel.LOW: "Low confidence",
        }.get(level, "")
        
        explanation = (
            f"{confidence_text}: {wallet_count} wallet(s) {behavior_text} "
            f"with ${volume:,.0f} volume. "
            f"Entity credibility: {components.entity_credibility:.0f}%, "
            f"Historical accuracy: {components.historical_accuracy:.0f}%."
        )
        
        if components.cluster_boost > 0:
            explanation += f" Cluster boost: +{components.cluster_boost:.1f}."
        
        if components.noise_penalty > 0:
            explanation += f" Noise penalty: -{components.noise_penalty:.1f}."
        
        return explanation
    
    def _get_warnings(
        self,
        activities: List[ActivityRecord],
        filter_stats: FilterStats,
        components: CalculationComponents,
    ) -> List[str]:
        """Generate warnings for the output."""
        warnings = []
        
        # High filter rate
        if filter_stats.filter_rate > 0.3:
            warnings.append(
                f"High noise rate: {filter_stats.filter_rate:.0%} of activities filtered"
            )
        
        # Low entity credibility
        if components.entity_credibility < 40:
            warnings.append("Low entity credibility - mostly unknown wallets")
        
        # Low historical accuracy
        if components.historical_accuracy < 40:
            warnings.append("Poor historical prediction accuracy")
        
        # Mixed signals
        behavior_counts = self._cluster_analyzer.get_wallet_count_by_behavior(activities)
        acc = behavior_counts.get(BehaviorType.ACCUMULATION, 0)
        dist = behavior_counts.get(BehaviorType.DISTRIBUTION, 0)
        if acc > 0 and dist > 0:
            ratio = min(acc, dist) / max(acc, dist)
            if ratio > 0.3:
                warnings.append("Mixed signals: some wallets accumulating, others distributing")
        
        return warnings
    
    # =========================================================
    # WALLET MODEL ACCESS
    # =========================================================
    
    @property
    def wallet_model(self) -> WalletConfidenceModel:
        """Get wallet model."""
        return self._wallet_model
    
    @property
    def noise_filter(self) -> NoiseFilter:
        """Get noise filter."""
        return self._noise_filter
    
    @property
    def cluster_analyzer(self) -> ClusterAnalyzer:
        """Get cluster analyzer."""
        return self._cluster_analyzer
