"""
Strategy Engine - Market Structure Signal Generator.

============================================================
PURPOSE
============================================================
Analyzes market structure to determine trend direction
and generate directional signals.

============================================================
WHAT IT EVALUATES
============================================================
1. Trend direction (1H, 4H)
2. Trend strength
3. Higher highs / lower lows
4. Breakout detection
5. Support/resistance proximity
6. Moving average context

============================================================
SIGNAL LOGIC
============================================================
LONG signal when:
- Trend direction is positive
- OR breakout to upside detected
- OR price bouncing off support with bullish structure

SHORT signal when:
- Trend direction is negative
- OR breakout to downside detected
- OR price rejecting resistance with bearish structure

NEUTRAL when:
- Conflicting signals
- No clear trend
- Ranging without S/R context

============================================================
"""

from datetime import datetime
from typing import Optional, List, Tuple

from strategy_engine.types import (
    TradeDirection,
    SignalStrength,
    SignalOutput,
    MarketStructureInput,
)
from strategy_engine.config import MarketStructureConfig
from .base import BaseSignalGenerator


class MarketStructureSignalGenerator(BaseSignalGenerator):
    """
    Generates signals based on market structure analysis.
    
    ============================================================
    SIGNAL STRENGTH DETERMINATION
    ============================================================
    STRONG:
    - Clear trend + breakout confirmation
    - Multiple timeframe alignment
    - Strong trend strength (>0.7)
    
    MODERATE:
    - Clear trend OR breakout
    - Single timeframe confirmation
    - Moderate trend strength (0.5-0.7)
    
    WEAK:
    - Marginal trend direction
    - No breakout
    - Weak trend strength (<0.5)
    
    ============================================================
    """
    
    def __init__(self, config: Optional[MarketStructureConfig] = None):
        self.config = config or MarketStructureConfig()
    
    @property
    def signal_name(self) -> str:
        return "MarketStructure"
    
    def generate(self, data: MarketStructureInput) -> SignalOutput:
        """
        Generate market structure signal from input data.
        
        Args:
            data: MarketStructureInput with structure indicators
        
        Returns:
            SignalOutput with direction and strength
        """
        # --------------------------------------------------
        # Validate minimum data
        # --------------------------------------------------
        if not data.has_minimum_data:
            return self._create_neutral_signal(
                "Insufficient market structure data"
            )
        
        # --------------------------------------------------
        # Collect directional votes
        # --------------------------------------------------
        votes: List[Tuple[TradeDirection, float]] = []
        reasons: List[str] = []
        
        # --------------------------------------------------
        # 1. Trend Direction Analysis
        # --------------------------------------------------
        trend_direction, trend_weight, trend_reason = self._analyze_trend(data)
        if trend_direction != TradeDirection.NEUTRAL:
            votes.append((trend_direction, trend_weight))
            reasons.append(trend_reason)
        
        # --------------------------------------------------
        # 2. Breakout Analysis
        # --------------------------------------------------
        breakout_direction, breakout_weight, breakout_reason = self._analyze_breakout(data)
        if breakout_direction != TradeDirection.NEUTRAL:
            votes.append((breakout_direction, breakout_weight))
            reasons.append(breakout_reason)
        
        # --------------------------------------------------
        # 3. Price Action (HH/HL/LH/LL) Analysis
        # --------------------------------------------------
        pa_direction, pa_weight, pa_reason = self._analyze_price_action(data)
        if pa_direction != TradeDirection.NEUTRAL:
            votes.append((pa_direction, pa_weight))
            reasons.append(pa_reason)
        
        # --------------------------------------------------
        # 4. Support/Resistance Context
        # --------------------------------------------------
        sr_direction, sr_weight, sr_reason = self._analyze_support_resistance(data)
        if sr_direction != TradeDirection.NEUTRAL:
            votes.append((sr_direction, sr_weight))
            reasons.append(sr_reason)
        
        # --------------------------------------------------
        # 5. Moving Average Context
        # --------------------------------------------------
        ma_direction, ma_weight, ma_reason = self._analyze_moving_averages(data)
        if ma_direction != TradeDirection.NEUTRAL:
            votes.append((ma_direction, ma_weight))
            reasons.append(ma_reason)
        
        # --------------------------------------------------
        # Aggregate votes
        # --------------------------------------------------
        if not votes:
            return self._create_neutral_signal(
                "No clear market structure signals"
            )
        
        final_direction, net_score = self._aggregate_direction_votes(votes)
        
        # --------------------------------------------------
        # Determine signal strength
        # --------------------------------------------------
        strength = self._determine_signal_strength(
            net_score=net_score,
            num_confirming_signals=len(votes),
            trend_strength=self._safe_get(data.trend_strength),
            has_breakout=data.breakout_detected or False,
        )
        
        # --------------------------------------------------
        # Format reason
        # --------------------------------------------------
        primary_reason = reasons[0] if reasons else "Market structure signal"
        
        # --------------------------------------------------
        # Build metrics
        # --------------------------------------------------
        metrics = self._format_metrics(
            trend_direction_1h=data.trend_direction_1h,
            trend_direction_4h=data.trend_direction_4h,
            trend_strength=data.trend_strength,
            breakout_detected=data.breakout_detected,
            breakout_direction=data.breakout_direction,
            higher_high=data.higher_high,
            higher_low=data.higher_low,
            lower_high=data.lower_high,
            lower_low=data.lower_low,
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
    
    def _analyze_trend(
        self,
        data: MarketStructureInput
    ) -> Tuple[TradeDirection, float, str]:
        """
        Analyze trend direction indicators.
        
        Returns:
            (direction, weight, reason)
        """
        direction = TradeDirection.NEUTRAL
        weight = 0.0
        reason = ""
        
        # Get trend directions
        trend_1h = self._safe_get(data.trend_direction_1h)
        trend_4h = self._safe_get(data.trend_direction_4h)
        trend_strength = self._safe_get(data.trend_strength)
        
        # Calculate average trend direction
        if data.trend_direction_1h is not None and data.trend_direction_4h is not None:
            avg_trend = (trend_1h + trend_4h) / 2
            # Bonus for alignment
            if (trend_1h > 0 and trend_4h > 0) or (trend_1h < 0 and trend_4h < 0):
                avg_trend *= 1.2  # 20% bonus for alignment
        elif data.trend_direction_1h is not None:
            avg_trend = trend_1h
        elif data.trend_direction_4h is not None:
            avg_trend = trend_4h
        else:
            return TradeDirection.NEUTRAL, 0.0, ""
        
        # Check thresholds
        if avg_trend >= self.config.trend_strong_threshold:
            direction = TradeDirection.LONG
            weight = 1.0 * (1 + trend_strength)
            reason = f"Strong uptrend ({avg_trend:.2f})"
        elif avg_trend >= self.config.trend_clear_threshold:
            direction = TradeDirection.LONG
            weight = 0.7 * (1 + trend_strength * 0.5)
            reason = f"Clear uptrend ({avg_trend:.2f})"
        elif avg_trend <= -self.config.trend_strong_threshold:
            direction = TradeDirection.SHORT
            weight = 1.0 * (1 + trend_strength)
            reason = f"Strong downtrend ({avg_trend:.2f})"
        elif avg_trend <= -self.config.trend_clear_threshold:
            direction = TradeDirection.SHORT
            weight = 0.7 * (1 + trend_strength * 0.5)
            reason = f"Clear downtrend ({avg_trend:.2f})"
        
        return direction, weight, reason
    
    def _analyze_breakout(
        self,
        data: MarketStructureInput
    ) -> Tuple[TradeDirection, float, str]:
        """
        Analyze breakout signals.
        
        Returns:
            (direction, weight, reason)
        """
        if not data.breakout_detected:
            return TradeDirection.NEUTRAL, 0.0, ""
        
        breakout_strength = self._safe_get(data.breakout_strength)
        
        if data.breakout_direction == "UP":
            if breakout_strength >= self.config.breakout_strength_strong:
                return TradeDirection.LONG, 1.2, f"Strong breakout UP ({breakout_strength:.2f})"
            elif breakout_strength >= self.config.breakout_strength_moderate:
                return TradeDirection.LONG, 0.8, f"Breakout UP ({breakout_strength:.2f})"
            elif breakout_strength >= self.config.breakout_strength_weak:
                return TradeDirection.LONG, 0.5, f"Weak breakout UP ({breakout_strength:.2f})"
        
        elif data.breakout_direction == "DOWN":
            if breakout_strength >= self.config.breakout_strength_strong:
                return TradeDirection.SHORT, 1.2, f"Strong breakout DOWN ({breakout_strength:.2f})"
            elif breakout_strength >= self.config.breakout_strength_moderate:
                return TradeDirection.SHORT, 0.8, f"Breakout DOWN ({breakout_strength:.2f})"
            elif breakout_strength >= self.config.breakout_strength_weak:
                return TradeDirection.SHORT, 0.5, f"Weak breakout DOWN ({breakout_strength:.2f})"
        
        return TradeDirection.NEUTRAL, 0.0, ""
    
    def _analyze_price_action(
        self,
        data: MarketStructureInput
    ) -> Tuple[TradeDirection, float, str]:
        """
        Analyze higher high/lower low patterns.
        
        Returns:
            (direction, weight, reason)
        """
        bullish_count = 0
        bearish_count = 0
        
        # Count bullish signals
        if data.higher_high:
            bullish_count += 1
        if data.higher_low:
            bullish_count += 1
        
        # Count bearish signals
        if data.lower_high:
            bearish_count += 1
        if data.lower_low:
            bearish_count += 1
        
        # Determine direction
        if bullish_count >= 2:
            return TradeDirection.LONG, 0.8, "HH + HL confirmed"
        elif bullish_count == 1 and bearish_count == 0:
            if data.higher_high:
                return TradeDirection.LONG, 0.4, "Higher high forming"
            else:
                return TradeDirection.LONG, 0.3, "Higher low forming"
        
        if bearish_count >= 2:
            return TradeDirection.SHORT, 0.8, "LH + LL confirmed"
        elif bearish_count == 1 and bullish_count == 0:
            if data.lower_low:
                return TradeDirection.SHORT, 0.4, "Lower low forming"
            else:
                return TradeDirection.SHORT, 0.3, "Lower high forming"
        
        return TradeDirection.NEUTRAL, 0.0, ""
    
    def _analyze_support_resistance(
        self,
        data: MarketStructureInput
    ) -> Tuple[TradeDirection, float, str]:
        """
        Analyze support/resistance context.
        
        Near support + bullish = LONG
        Near resistance + bearish = SHORT
        
        Returns:
            (direction, weight, reason)
        """
        # Need trend context to interpret S/R
        trend_1h = self._safe_get(data.trend_direction_1h)
        
        # Near support with bullish lean
        if data.near_support and trend_1h > 0:
            distance = self._safe_get(data.support_distance_pct)
            if distance <= self.config.sr_close_threshold_pct:
                return TradeDirection.LONG, 0.6, f"Bouncing from support ({distance:.2f}%)"
            elif distance <= self.config.sr_near_threshold_pct:
                return TradeDirection.LONG, 0.4, f"Near support ({distance:.2f}%)"
        
        # Near resistance with bearish lean
        if data.near_resistance and trend_1h < 0:
            distance = self._safe_get(data.resistance_distance_pct)
            if distance <= self.config.sr_close_threshold_pct:
                return TradeDirection.SHORT, 0.6, f"Rejecting resistance ({distance:.2f}%)"
            elif distance <= self.config.sr_near_threshold_pct:
                return TradeDirection.SHORT, 0.4, f"Near resistance ({distance:.2f}%)"
        
        return TradeDirection.NEUTRAL, 0.0, ""
    
    def _analyze_moving_averages(
        self,
        data: MarketStructureInput
    ) -> Tuple[TradeDirection, float, str]:
        """
        Analyze moving average context.
        
        Returns:
            (direction, weight, reason)
        """
        price_vs_ma20 = self._safe_get(data.price_vs_ma_20)
        price_vs_ma50 = self._safe_get(data.price_vs_ma_50)
        ma20_slope = self._safe_get(data.ma_20_slope)
        ma50_slope = self._safe_get(data.ma_50_slope)
        
        bullish_signals = 0
        bearish_signals = 0
        
        # Price above MAs with positive slope
        if price_vs_ma20 > self.config.price_above_ma_bullish:
            if ma20_slope > self.config.ma_slope_bullish_threshold:
                bullish_signals += 1
        
        if price_vs_ma50 > self.config.price_above_ma_bullish:
            if ma50_slope > self.config.ma_slope_bullish_threshold:
                bullish_signals += 1
        
        # Price below MAs with negative slope
        if price_vs_ma20 < self.config.price_below_ma_bearish:
            if ma20_slope < self.config.ma_slope_bearish_threshold:
                bearish_signals += 1
        
        if price_vs_ma50 < self.config.price_below_ma_bearish:
            if ma50_slope < self.config.ma_slope_bearish_threshold:
                bearish_signals += 1
        
        # Determine direction
        if bullish_signals >= 2:
            return TradeDirection.LONG, 0.5, "Above rising MAs"
        elif bullish_signals == 1:
            return TradeDirection.LONG, 0.3, "Above MA with positive slope"
        
        if bearish_signals >= 2:
            return TradeDirection.SHORT, 0.5, "Below falling MAs"
        elif bearish_signals == 1:
            return TradeDirection.SHORT, 0.3, "Below MA with negative slope"
        
        return TradeDirection.NEUTRAL, 0.0, ""
    
    def _determine_signal_strength(
        self,
        net_score: float,
        num_confirming_signals: int,
        trend_strength: float,
        has_breakout: bool,
    ) -> SignalStrength:
        """
        Determine overall signal strength.
        
        Args:
            net_score: Net directional score
            num_confirming_signals: Number of aligned signals
            trend_strength: Trend strength (0-1)
            has_breakout: Whether breakout was detected
        
        Returns:
            SignalStrength
        """
        # Strong: High net score + multiple confirmations + strong trend
        if (net_score >= 1.5 and num_confirming_signals >= 3 and 
            trend_strength >= self.config.trend_strength_strong):
            return SignalStrength.STRONG
        
        # Strong: Breakout with good trend
        if has_breakout and net_score >= 1.0 and trend_strength >= self.config.trend_strength_moderate:
            return SignalStrength.STRONG
        
        # Moderate: Good score or multiple confirmations
        if net_score >= 1.0 or (num_confirming_signals >= 2 and trend_strength >= self.config.trend_strength_weak):
            return SignalStrength.MODERATE
        
        # Weak: Some signal present
        if net_score >= 0.3 or num_confirming_signals >= 1:
            return SignalStrength.WEAK
        
        return SignalStrength.NONE
