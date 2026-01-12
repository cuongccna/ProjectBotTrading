"""
Smart Money Signal Generator - Aggregates patterns into actionable signals.

SAFETY: These signals are CONTEXT ONLY - they feed into Flow Scoring
for risk adjustment. They CANNOT directly trigger trades.
"""

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

from .config import SmartMoneyConfig, get_config
from .detector import PatternDetector
from .models import (
    Chain,
    DetectedPattern,
    EntityType,
    FlowDirection,
    SignalConfidence,
    SmartMoneySignal,
    WalletActivity,
    WalletInfo,
)


logger = logging.getLogger(__name__)


class SmartMoneySignalGenerator:
    """
    Generates aggregated smart money signals from patterns.
    
    The signal generator:
    1. Collects all detected patterns
    2. Aggregates by asset and timeframe
    3. Calculates weighted activity score (0-100)
    4. Determines dominant flow direction
    5. Generates human-readable explanation
    
    SAFETY: Output is CONTEXT ONLY for Flow Scoring.
    """
    
    def __init__(
        self,
        config: Optional[SmartMoneyConfig] = None,
    ) -> None:
        self.config = config or get_config()
        
        # Pattern weights for scoring
        self.pattern_weights = {
            "large_transfer": 1.0,
            "cex_flow": 1.3,      # CEX flows weighted higher
            "dormancy_break": 1.5,  # Dormancy breaks significant
            "cluster": 1.2,
        }
        
        # Statistics
        self._stats = {
            "signals_generated": 0,
            "significant_signals": 0,
            "degraded_signals": 0,
        }
    
    def generate_signal(
        self,
        patterns: list[DetectedPattern],
        activities: list[WalletActivity],
        wallets: list[WalletInfo],
        evaluation_window_minutes: int = 60,
        api_failures: Optional[list[str]] = None,
    ) -> SmartMoneySignal:
        """
        Generate aggregated smart money signal.
        
        Args:
            patterns: Detected patterns from PatternDetector
            activities: Raw wallet activities
            wallets: Tracked wallets
            evaluation_window_minutes: Time window for evaluation
            api_failures: List of failed API sources
            
        Returns:
            SmartMoneySignal with aggregated data
        """
        self._stats["signals_generated"] += 1
        
        # Handle no data case
        if not patterns and not activities:
            signal = SmartMoneySignal.empty("No smart money activity detected")
            signal.evaluation_window_minutes = evaluation_window_minutes
            return signal
        
        # Calculate activity score
        activity_score = self._calculate_activity_score(patterns, activities)
        
        # Determine dominant flow direction
        dominant_flow = self._calculate_dominant_flow(patterns, activities)
        
        # Get affected assets
        affected_assets = self._get_affected_assets(patterns, activities)
        primary_asset = affected_assets[0] if affected_assets else None
        
        # Calculate volume metrics
        inflow_volume, outflow_volume = self._calculate_volumes(activities)
        total_volume = inflow_volume + outflow_volume
        
        # Get entity breakdown
        whale_pct, fund_pct, cex_pct = self._calculate_entity_breakdown(wallets, activities)
        
        # Determine confidence
        confidence = self._determine_confidence(
            patterns, activities, api_failures or []
        )
        
        # Calculate data completeness
        data_completeness = self._calculate_completeness(api_failures or [])
        
        # Generate explanation
        explanation = self._generate_explanation(
            patterns, activity_score, dominant_flow, affected_assets
        )
        
        signal = SmartMoneySignal(
            activity_score=activity_score,
            dominant_flow_direction=dominant_flow,
            confidence_level=confidence,
            affected_assets=affected_assets,
            primary_asset=primary_asset,
            patterns_detected=patterns,
            total_volume_usd=total_volume,
            inflow_volume_usd=inflow_volume,
            outflow_volume_usd=outflow_volume,
            unique_wallets_active=len(set(a.wallet_address for a in activities)),
            whale_activity_pct=whale_pct,
            fund_activity_pct=fund_pct,
            cex_activity_pct=cex_pct,
            timestamp=datetime.utcnow(),
            evaluation_window_minutes=evaluation_window_minutes,
            explanation=explanation,
            data_completeness=data_completeness,
            api_failures=api_failures or [],
        )
        
        if signal.is_significant:
            self._stats["significant_signals"] += 1
        
        if confidence == SignalConfidence.DEGRADED:
            self._stats["degraded_signals"] += 1
        
        return signal
    
    def _calculate_activity_score(
        self,
        patterns: list[DetectedPattern],
        activities: list[WalletActivity],
    ) -> float:
        """
        Calculate activity score (0-100).
        
        Based on:
        - Number and severity of patterns
        - Total volume
        - Pattern diversity
        """
        if not patterns and not activities:
            return 0.0
        
        score = 0.0
        
        # Pattern contribution (up to 60 points)
        pattern_score = 0.0
        for pattern in patterns:
            weight = self.pattern_weights.get(pattern.pattern_type, 1.0)
            pattern_score += pattern.severity * pattern.confidence * weight * 10
        
        pattern_score = min(60, pattern_score)
        score += pattern_score
        
        # Volume contribution (up to 25 points)
        total_volume = sum(a.value_usd for a in activities)
        if total_volume >= 10_000_000:
            volume_score = 25
        elif total_volume >= 1_000_000:
            volume_score = 20
        elif total_volume >= 100_000:
            volume_score = 15
        elif total_volume >= 10_000:
            volume_score = 10
        else:
            volume_score = min(10, total_volume / 1000)
        
        score += volume_score
        
        # Diversity contribution (up to 15 points)
        unique_patterns = len(set(p.pattern_type for p in patterns))
        unique_wallets = len(set(a.wallet_address for a in activities))
        
        diversity_score = min(15, unique_patterns * 3 + unique_wallets * 0.5)
        score += diversity_score
        
        return min(100, max(0, score))
    
    def _calculate_dominant_flow(
        self,
        patterns: list[DetectedPattern],
        activities: list[WalletActivity],
    ) -> FlowDirection:
        """Determine dominant flow direction."""
        # Count from patterns (weighted)
        inflow_weight = sum(
            p.total_value_usd * p.severity
            for p in patterns
            if p.flow_direction == FlowDirection.INFLOW
        )
        
        outflow_weight = sum(
            p.total_value_usd * p.severity
            for p in patterns
            if p.flow_direction == FlowDirection.OUTFLOW
        )
        
        # Count from activities
        inflow_volume = sum(a.value_usd for a in activities if a.direction == "in")
        outflow_volume = sum(a.value_usd for a in activities if a.direction == "out")
        
        total_inflow = inflow_weight + inflow_volume
        total_outflow = outflow_weight + outflow_volume
        
        if total_inflow > total_outflow * 1.3:
            return FlowDirection.INFLOW
        elif total_outflow > total_inflow * 1.3:
            return FlowDirection.OUTFLOW
        else:
            return FlowDirection.NEUTRAL
    
    def _get_affected_assets(
        self,
        patterns: list[DetectedPattern],
        activities: list[WalletActivity],
    ) -> list[str]:
        """Get list of affected assets, ordered by volume."""
        asset_volume: dict[str, float] = defaultdict(float)
        
        for pattern in patterns:
            for asset in pattern.affected_assets:
                asset_volume[asset] += pattern.total_value_usd
        
        for activity in activities:
            asset_volume[activity.token_symbol] += activity.value_usd
        
        # Sort by volume
        sorted_assets = sorted(
            asset_volume.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return [asset for asset, _ in sorted_assets[:10]]
    
    def _calculate_volumes(
        self,
        activities: list[WalletActivity],
    ) -> tuple[float, float]:
        """Calculate inflow and outflow volumes."""
        inflow = sum(a.value_usd for a in activities if a.direction == "in")
        outflow = sum(a.value_usd for a in activities if a.direction == "out")
        return inflow, outflow
    
    def _calculate_entity_breakdown(
        self,
        wallets: list[WalletInfo],
        activities: list[WalletActivity],
    ) -> tuple[float, float, float]:
        """Calculate activity percentage by entity type."""
        wallet_map = {w.address.lower(): w for w in wallets}
        
        whale_volume = 0.0
        fund_volume = 0.0
        cex_volume = 0.0
        total_volume = 0.0
        
        for activity in activities:
            wallet = wallet_map.get(activity.wallet_address.lower())
            if wallet:
                total_volume += activity.value_usd
                
                if wallet.entity_type == EntityType.WHALE:
                    whale_volume += activity.value_usd
                elif wallet.entity_type == EntityType.FUND:
                    fund_volume += activity.value_usd
                elif wallet.entity_type in (EntityType.CEX_HOT, EntityType.CEX_COLD):
                    cex_volume += activity.value_usd
        
        if total_volume == 0:
            return 0.0, 0.0, 0.0
        
        return (
            round(whale_volume / total_volume * 100, 1),
            round(fund_volume / total_volume * 100, 1),
            round(cex_volume / total_volume * 100, 1),
        )
    
    def _determine_confidence(
        self,
        patterns: list[DetectedPattern],
        activities: list[WalletActivity],
        api_failures: list[str],
    ) -> SignalConfidence:
        """Determine signal confidence level."""
        # Degraded if API failures
        if len(api_failures) >= 2:
            return SignalConfidence.DEGRADED
        
        # Low if minimal data
        if len(patterns) < 2 and len(activities) < 5:
            return SignalConfidence.LOW
        
        # Calculate average pattern confidence
        if patterns:
            avg_confidence = sum(p.confidence for p in patterns) / len(patterns)
        else:
            avg_confidence = 0.5
        
        # High confidence conditions
        if (
            len(patterns) >= 3 and
            avg_confidence >= 0.7 and
            len(activities) >= 10 and
            not api_failures
        ):
            return SignalConfidence.HIGH
        
        # Medium otherwise
        return SignalConfidence.MEDIUM
    
    def _calculate_completeness(self, api_failures: list[str]) -> float:
        """Calculate data completeness score."""
        # Assume 2 chains (ETH, SOL) by default
        expected_sources = 2
        failed = len(set(api_failures))
        
        if failed >= expected_sources:
            return 0.0
        
        return (expected_sources - failed) / expected_sources
    
    def _generate_explanation(
        self,
        patterns: list[DetectedPattern],
        activity_score: float,
        dominant_flow: FlowDirection,
        affected_assets: list[str],
    ) -> str:
        """Generate human-readable explanation."""
        parts = []
        
        # Activity level
        if activity_score >= 70:
            parts.append("HIGH smart money activity detected")
        elif activity_score >= 40:
            parts.append("MODERATE smart money activity detected")
        elif activity_score >= 20:
            parts.append("LOW smart money activity detected")
        else:
            parts.append("MINIMAL smart money activity")
        
        # Flow direction
        if dominant_flow == FlowDirection.INFLOW:
            parts.append("with NET INFLOW (accumulation)")
        elif dominant_flow == FlowDirection.OUTFLOW:
            parts.append("with NET OUTFLOW (distribution)")
        else:
            parts.append("with BALANCED flow")
        
        # Pattern summary
        if patterns:
            pattern_counts = Counter(p.pattern_type for p in patterns)
            pattern_summary = []
            
            if pattern_counts.get("cex_flow"):
                pattern_summary.append(f"{pattern_counts['cex_flow']} CEX flow(s)")
            if pattern_counts.get("large_transfer"):
                pattern_summary.append(f"{pattern_counts['large_transfer']} large transfer(s)")
            if pattern_counts.get("dormancy_break"):
                pattern_summary.append(f"{pattern_counts['dormancy_break']} dormancy break(s)")
            if pattern_counts.get("cluster"):
                pattern_summary.append(f"{pattern_counts['cluster']} cluster(s)")
            
            if pattern_summary:
                parts.append(f"Patterns: {', '.join(pattern_summary)}")
        
        # Affected assets
        if affected_assets:
            parts.append(f"Assets: {', '.join(affected_assets[:5])}")
        
        return ". ".join(parts) + "."
    
    def get_stats(self) -> dict[str, Any]:
        """Get generator statistics."""
        return self._stats.copy()
