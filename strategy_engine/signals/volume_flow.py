"""
Strategy Engine - Volume Flow Signal Generator.

============================================================
PURPOSE
============================================================
Analyzes volume and order flow to determine directional bias.

============================================================
WHAT IT EVALUATES
============================================================
1. Relative volume (expansion/contraction)
2. Directional volume (buy vs sell dominance)
3. Volume delta
4. Absorption patterns
5. Volume spikes

============================================================
SIGNAL LOGIC
============================================================
LONG signal when:
- Volume expanding + buy dominance
- Positive volume delta
- Buy-side absorption detected

SHORT signal when:
- Volume expanding + sell dominance
- Negative volume delta
- Sell-side absorption detected

NEUTRAL when:
- Volume contracting
- No directional dominance
- Conflicting signals

============================================================
"""

from datetime import datetime
from typing import Optional, List, Tuple

from strategy_engine.types import (
    TradeDirection,
    SignalStrength,
    SignalOutput,
    VolumeFlowInput,
)
from strategy_engine.config import VolumeFlowConfig
from .base import BaseSignalGenerator


class VolumeFlowSignalGenerator(BaseSignalGenerator):
    """
    Generates signals based on volume and flow analysis.
    
    ============================================================
    SIGNAL STRENGTH DETERMINATION
    ============================================================
    STRONG:
    - Volume spike + strong directional bias
    - Strong absorption
    - Multiple volume confirmations
    
    MODERATE:
    - Volume expansion + clear bias
    - Moderate absorption
    - Some confirmation
    
    WEAK:
    - Normal volume + slight bias
    - No absorption
    - Single indicator
    
    ============================================================
    """
    
    def __init__(self, config: Optional[VolumeFlowConfig] = None):
        self.config = config or VolumeFlowConfig()
    
    @property
    def signal_name(self) -> str:
        return "VolumeFlow"
    
    def generate(self, data: VolumeFlowInput) -> SignalOutput:
        """
        Generate volume flow signal from input data.
        
        Args:
            data: VolumeFlowInput with volume/flow indicators
        
        Returns:
            SignalOutput with direction and strength
        """
        # --------------------------------------------------
        # Validate minimum data
        # --------------------------------------------------
        if not data.has_minimum_data:
            return self._create_neutral_signal(
                "Insufficient volume data"
            )
        
        # --------------------------------------------------
        # Check volume conditions
        # --------------------------------------------------
        volume_ratio = self._safe_get(data.volume_ratio_vs_average, 1.0)
        
        # Low volume = reduced signal weight
        if volume_ratio < self.config.volume_contraction_threshold:
            # Still analyze but note low volume
            volume_context = "low"
        elif volume_ratio >= self.config.volume_spike_threshold:
            volume_context = "spike"
        elif volume_ratio >= self.config.volume_expansion_threshold:
            volume_context = "expansion"
        else:
            volume_context = "normal"
        
        # --------------------------------------------------
        # Collect directional votes
        # --------------------------------------------------
        votes: List[Tuple[TradeDirection, float]] = []
        reasons: List[str] = []
        
        # --------------------------------------------------
        # 1. Directional Volume Analysis
        # --------------------------------------------------
        dir_direction, dir_weight, dir_reason = self._analyze_directional_volume(data)
        if dir_direction != TradeDirection.NEUTRAL:
            # Adjust weight based on volume context
            adjusted_weight = self._adjust_weight_for_volume(dir_weight, volume_context)
            votes.append((dir_direction, adjusted_weight))
            reasons.append(dir_reason)
        
        # --------------------------------------------------
        # 2. Volume Delta Analysis
        # --------------------------------------------------
        delta_direction, delta_weight, delta_reason = self._analyze_volume_delta(data)
        if delta_direction != TradeDirection.NEUTRAL:
            adjusted_weight = self._adjust_weight_for_volume(delta_weight, volume_context)
            votes.append((delta_direction, adjusted_weight))
            reasons.append(delta_reason)
        
        # --------------------------------------------------
        # 3. Absorption Pattern Analysis
        # --------------------------------------------------
        abs_direction, abs_weight, abs_reason = self._analyze_absorption(data)
        if abs_direction != TradeDirection.NEUTRAL:
            votes.append((abs_direction, abs_weight))
            reasons.append(abs_reason)
        
        # --------------------------------------------------
        # 4. Exhaustion Detection
        # --------------------------------------------------
        exh_direction, exh_weight, exh_reason = self._analyze_exhaustion(data)
        if exh_direction != TradeDirection.NEUTRAL:
            votes.append((exh_direction, exh_weight))
            reasons.append(exh_reason)
        
        # --------------------------------------------------
        # 5. Volume Pattern Analysis
        # --------------------------------------------------
        pat_direction, pat_weight, pat_reason = self._analyze_volume_patterns(data)
        if pat_direction != TradeDirection.NEUTRAL:
            votes.append((pat_direction, pat_weight))
            reasons.append(pat_reason)
        
        # --------------------------------------------------
        # Aggregate votes
        # --------------------------------------------------
        if not votes:
            return self._create_neutral_signal(
                f"No clear volume signals (volume {volume_context})"
            )
        
        final_direction, net_score = self._aggregate_direction_votes(votes)
        
        # --------------------------------------------------
        # Low volume penalty
        # --------------------------------------------------
        if volume_context == "low":
            net_score *= 0.5
        
        # --------------------------------------------------
        # Determine signal strength
        # --------------------------------------------------
        strength = self._determine_signal_strength(
            net_score=net_score,
            num_confirming_signals=len(votes),
            volume_context=volume_context,
            has_absorption=data.absorption_score is not None and abs(self._safe_get(data.absorption_score)) > 0.3,
        )
        
        # --------------------------------------------------
        # Format reason
        # --------------------------------------------------
        primary_reason = reasons[0] if reasons else "Volume flow signal"
        if volume_context == "low":
            primary_reason = f"[Low volume] {primary_reason}"
        elif volume_context == "spike":
            primary_reason = f"[Volume spike] {primary_reason}"
        
        # --------------------------------------------------
        # Build metrics
        # --------------------------------------------------
        metrics = self._format_metrics(
            volume_ratio=volume_ratio,
            volume_context=volume_context,
            buy_volume_ratio=data.buy_volume_ratio,
            sell_volume_ratio=data.sell_volume_ratio,
            volume_delta=data.volume_delta,
            absorption_score=data.absorption_score,
            exhaustion_detected=data.exhaustion_detected,
            net_score=net_score,
            num_signals=len(votes),
        )
        
        return SignalOutput(
            direction=final_direction,
            strength=strength,
            reason=primary_reason,
            metrics=metrics,
            timestamp=datetime.utcnow(),
        )
    
    def _adjust_weight_for_volume(
        self,
        weight: float,
        volume_context: str
    ) -> float:
        """
        Adjust signal weight based on volume context.
        
        High volume = more weight
        Low volume = less weight
        """
        if volume_context == "spike":
            return weight * 1.5
        elif volume_context == "expansion":
            return weight * 1.2
        elif volume_context == "low":
            return weight * 0.5
        return weight
    
    def _analyze_directional_volume(
        self,
        data: VolumeFlowInput
    ) -> Tuple[TradeDirection, float, str]:
        """
        Analyze buy vs sell volume dominance.
        
        Returns:
            (direction, weight, reason)
        """
        buy_ratio = self._safe_get(data.buy_volume_ratio)
        sell_ratio = self._safe_get(data.sell_volume_ratio)
        
        # Need valid ratios
        if buy_ratio == 0 and sell_ratio == 0:
            return TradeDirection.NEUTRAL, 0.0, ""
        
        # Strong buy dominance
        if buy_ratio >= self.config.strong_dominance_threshold:
            return TradeDirection.LONG, 1.0, f"Strong buy dominance ({buy_ratio:.1%})"
        
        # Buy dominance
        if buy_ratio >= self.config.buy_dominance_threshold:
            return TradeDirection.LONG, 0.6, f"Buy dominance ({buy_ratio:.1%})"
        
        # Strong sell dominance
        if sell_ratio >= self.config.strong_dominance_threshold:
            return TradeDirection.SHORT, 1.0, f"Strong sell dominance ({sell_ratio:.1%})"
        
        # Sell dominance
        if sell_ratio >= self.config.sell_dominance_threshold:
            return TradeDirection.SHORT, 0.6, f"Sell dominance ({sell_ratio:.1%})"
        
        return TradeDirection.NEUTRAL, 0.0, ""
    
    def _analyze_volume_delta(
        self,
        data: VolumeFlowInput
    ) -> Tuple[TradeDirection, float, str]:
        """
        Analyze volume delta (buy - sell).
        
        Returns:
            (direction, weight, reason)
        """
        delta = self._safe_get(data.volume_delta)
        
        # Strong positive delta
        if delta >= self.config.delta_strong_threshold:
            return TradeDirection.LONG, 0.8, f"Strong positive delta ({delta:.2f})"
        
        # Positive delta
        if delta >= self.config.delta_bullish_threshold:
            return TradeDirection.LONG, 0.5, f"Positive delta ({delta:.2f})"
        
        # Strong negative delta
        if delta <= -self.config.delta_strong_threshold:
            return TradeDirection.SHORT, 0.8, f"Strong negative delta ({delta:.2f})"
        
        # Negative delta
        if delta <= self.config.delta_bearish_threshold:
            return TradeDirection.SHORT, 0.5, f"Negative delta ({delta:.2f})"
        
        return TradeDirection.NEUTRAL, 0.0, ""
    
    def _analyze_absorption(
        self,
        data: VolumeFlowInput
    ) -> Tuple[TradeDirection, float, str]:
        """
        Analyze absorption patterns.
        
        Absorption = large volume absorbed without price movement
        - Buy absorption at lows = bullish
        - Sell absorption at highs = bearish
        
        Returns:
            (direction, weight, reason)
        """
        absorption = self._safe_get(data.absorption_score)
        
        # Strong buy-side absorption
        if absorption >= self.config.absorption_strong_threshold:
            return TradeDirection.LONG, 0.9, f"Strong buy absorption ({absorption:.2f})"
        
        # Buy-side absorption
        if absorption >= self.config.absorption_threshold:
            return TradeDirection.LONG, 0.6, f"Buy absorption ({absorption:.2f})"
        
        # Strong sell-side absorption
        if absorption <= -self.config.absorption_strong_threshold:
            return TradeDirection.SHORT, 0.9, f"Strong sell absorption ({absorption:.2f})"
        
        # Sell-side absorption
        if absorption <= -self.config.absorption_threshold:
            return TradeDirection.SHORT, 0.6, f"Sell absorption ({absorption:.2f})"
        
        return TradeDirection.NEUTRAL, 0.0, ""
    
    def _analyze_exhaustion(
        self,
        data: VolumeFlowInput
    ) -> Tuple[TradeDirection, float, str]:
        """
        Analyze exhaustion patterns.
        
        Exhaustion = move running out of steam
        - Bullish exhaustion = potential short
        - Bearish exhaustion = potential long
        
        Returns:
            (direction, weight, reason)
        """
        if not data.exhaustion_detected:
            return TradeDirection.NEUTRAL, 0.0, ""
        
        # Bullish exhaustion = short opportunity (reversal)
        if data.exhaustion_direction == "BULLISH":
            return TradeDirection.SHORT, 0.5, "Bullish exhaustion detected"
        
        # Bearish exhaustion = long opportunity (reversal)
        if data.exhaustion_direction == "BEARISH":
            return TradeDirection.LONG, 0.5, "Bearish exhaustion detected"
        
        return TradeDirection.NEUTRAL, 0.0, ""
    
    def _analyze_volume_patterns(
        self,
        data: VolumeFlowInput
    ) -> Tuple[TradeDirection, float, str]:
        """
        Analyze volume expansion/contraction patterns.
        
        Returns:
            (direction, weight, reason)
        """
        # Volume spike with direction
        if data.volume_spike_detected:
            delta = self._safe_get(data.volume_delta)
            if delta > 0:
                return TradeDirection.LONG, 0.4, "Volume spike with buying pressure"
            elif delta < 0:
                return TradeDirection.SHORT, 0.4, "Volume spike with selling pressure"
        
        return TradeDirection.NEUTRAL, 0.0, ""
    
    def _determine_signal_strength(
        self,
        net_score: float,
        num_confirming_signals: int,
        volume_context: str,
        has_absorption: bool,
    ) -> SignalStrength:
        """
        Determine overall signal strength.
        
        Args:
            net_score: Net directional score
            num_confirming_signals: Number of aligned signals
            volume_context: Volume environment
            has_absorption: Whether absorption was detected
        
        Returns:
            SignalStrength
        """
        # Low volume caps strength at WEAK
        if volume_context == "low":
            if net_score >= 0.3:
                return SignalStrength.WEAK
            return SignalStrength.NONE
        
        # Strong: Volume spike + multiple confirmations
        if volume_context == "spike" and num_confirming_signals >= 2 and net_score >= 1.0:
            return SignalStrength.STRONG
        
        # Strong: Good score with absorption
        if has_absorption and net_score >= 1.0:
            return SignalStrength.STRONG
        
        # Moderate: Expansion + confirmations
        if volume_context == "expansion" and num_confirming_signals >= 2:
            return SignalStrength.MODERATE
        
        # Moderate: Good score
        if net_score >= 0.8:
            return SignalStrength.MODERATE
        
        # Weak: Some signal
        if net_score >= 0.3:
            return SignalStrength.WEAK
        
        return SignalStrength.NONE
