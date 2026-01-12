"""
Strategy Engine - Sentiment Modifier Generator.

============================================================
PURPOSE
============================================================
Analyzes sentiment and news to MODIFY (not create) signals.

============================================================
CRITICAL CONSTRAINT
============================================================
Sentiment is a MODIFIER only - it NEVER creates a trade signal.
It can:
- STRENGTHEN conviction when aligned
- WEAKEN conviction when divergent
- DELAY action during news shocks
- NEUTRAL if no strong sentiment

============================================================
WHAT IT EVALUATES
============================================================
1. Overall sentiment score
2. News shock detection
3. Sentiment-price divergence
4. Fear/greed context
5. Social sentiment changes

============================================================
"""

from datetime import datetime
from typing import Optional, Tuple

from strategy_engine.types import (
    TradeDirection,
    SentimentModifierOutput,
    SentimentInput,
)
from strategy_engine.config import SentimentConfig


class SentimentModifierGenerator:
    """
    Generates sentiment modifiers (NOT signals).
    
    ============================================================
    MODIFIER EFFECTS
    ============================================================
    STRENGTHEN:
    - Sentiment aligns with expected direction
    - No negative news
    - Fear (for longs near bottom) or greed (for shorts near top)
    
    WEAKEN:
    - Sentiment diverges from expected direction
    - Mixed news environment
    - Contrarian extreme readings
    
    DELAY:
    - Major news shock detected
    - Extreme sentiment readings
    - High volatility in sentiment
    
    NEUTRAL:
    - No strong sentiment signal
    - Mixed or unclear sentiment
    
    ============================================================
    """
    
    def __init__(self, config: Optional[SentimentConfig] = None):
        self.config = config or SentimentConfig()
    
    def generate(
        self,
        data: SentimentInput,
        proposed_direction: Optional[TradeDirection] = None
    ) -> SentimentModifierOutput:
        """
        Generate sentiment modifier.
        
        Args:
            data: SentimentInput with sentiment indicators
            proposed_direction: The direction proposed by other signals
                              (used to determine alignment)
        
        Returns:
            SentimentModifierOutput with effect and magnitude
        """
        # --------------------------------------------------
        # Check for news shock (highest priority)
        # --------------------------------------------------
        if data.news_shock_detected:
            return self._handle_news_shock(data)
        
        # --------------------------------------------------
        # Check for extreme fear/greed
        # --------------------------------------------------
        extreme_result = self._check_extreme_sentiment(data, proposed_direction)
        if extreme_result is not None:
            return extreme_result
        
        # --------------------------------------------------
        # Check sentiment alignment with proposed direction
        # --------------------------------------------------
        if proposed_direction and proposed_direction != TradeDirection.NEUTRAL:
            alignment_result = self._check_alignment(data, proposed_direction)
            if alignment_result is not None:
                return alignment_result
        
        # --------------------------------------------------
        # Check for divergence
        # --------------------------------------------------
        divergence_result = self._check_divergence(data, proposed_direction)
        if divergence_result is not None:
            return divergence_result
        
        # --------------------------------------------------
        # Default: Neutral
        # --------------------------------------------------
        return SentimentModifierOutput(
            effect="NEUTRAL",
            magnitude=0.0,
            reason="No significant sentiment signal",
            metrics=self._build_metrics(data),
        )
    
    def _handle_news_shock(self, data: SentimentInput) -> SentimentModifierOutput:
        """
        Handle news shock scenarios.
        
        High-impact news = DELAY action
        """
        impact = data.news_impact_score or 0.5
        
        if impact >= self.config.news_shock_delay_threshold:
            return SentimentModifierOutput(
                effect="DELAY",
                magnitude=self.config.delay_magnitude,
                reason=f"Major news shock detected (impact: {impact:.2f})",
                metrics=self._build_metrics(data),
            )
        
        # Lower impact news - just weaken
        if impact >= self.config.news_shock_high_impact:
            direction = data.news_shock_direction
            return SentimentModifierOutput(
                effect="WEAKEN",
                magnitude=self.config.weaken_magnitude,
                reason=f"News event detected ({direction}, impact: {impact:.2f})",
                metrics=self._build_metrics(data),
            )
        
        return SentimentModifierOutput(
            effect="NEUTRAL",
            magnitude=0.0,
            reason=f"Minor news event ({data.news_shock_direction})",
            metrics=self._build_metrics(data),
        )
    
    def _check_extreme_sentiment(
        self,
        data: SentimentInput,
        proposed_direction: Optional[TradeDirection]
    ) -> Optional[SentimentModifierOutput]:
        """
        Check for extreme fear/greed readings.
        
        Extreme readings are contrarian signals.
        """
        fg_index = data.fear_greed_index
        if fg_index is None:
            return None
        
        # Extreme fear - contrarian bullish
        if fg_index <= self.config.extreme_fear_threshold:
            if proposed_direction == TradeDirection.LONG:
                return SentimentModifierOutput(
                    effect="STRENGTHEN",
                    magnitude=self.config.strengthen_magnitude,
                    reason=f"Extreme fear supports long (FG: {fg_index:.0f})",
                    metrics=self._build_metrics(data),
                )
            elif proposed_direction == TradeDirection.SHORT:
                return SentimentModifierOutput(
                    effect="WEAKEN",
                    magnitude=self.config.weaken_magnitude,
                    reason=f"Extreme fear opposes short (FG: {fg_index:.0f})",
                    metrics=self._build_metrics(data),
                )
        
        # Extreme greed - contrarian bearish
        if fg_index >= self.config.extreme_greed_threshold:
            if proposed_direction == TradeDirection.SHORT:
                return SentimentModifierOutput(
                    effect="STRENGTHEN",
                    magnitude=self.config.strengthen_magnitude,
                    reason=f"Extreme greed supports short (FG: {fg_index:.0f})",
                    metrics=self._build_metrics(data),
                )
            elif proposed_direction == TradeDirection.LONG:
                return SentimentModifierOutput(
                    effect="WEAKEN",
                    magnitude=self.config.weaken_magnitude,
                    reason=f"Extreme greed opposes long (FG: {fg_index:.0f})",
                    metrics=self._build_metrics(data),
                )
        
        return None
    
    def _check_alignment(
        self,
        data: SentimentInput,
        proposed_direction: TradeDirection
    ) -> Optional[SentimentModifierOutput]:
        """
        Check if sentiment aligns with proposed direction.
        
        Alignment strengthens, divergence weakens.
        """
        sentiment = data.sentiment_score
        if sentiment is None:
            return None
        
        # Strong positive sentiment
        if sentiment >= self.config.sentiment_strong_threshold:
            if proposed_direction == TradeDirection.LONG:
                return SentimentModifierOutput(
                    effect="STRENGTHEN",
                    magnitude=self.config.strengthen_magnitude,
                    reason=f"Strong positive sentiment aligns ({sentiment:.2f})",
                    metrics=self._build_metrics(data),
                )
            elif proposed_direction == TradeDirection.SHORT:
                return SentimentModifierOutput(
                    effect="WEAKEN",
                    magnitude=self.config.weaken_magnitude,
                    reason=f"Strong positive sentiment opposes short ({sentiment:.2f})",
                    metrics=self._build_metrics(data),
                )
        
        # Moderate positive sentiment
        elif sentiment >= self.config.sentiment_positive_threshold:
            if proposed_direction == TradeDirection.LONG:
                return SentimentModifierOutput(
                    effect="STRENGTHEN",
                    magnitude=self.config.strengthen_magnitude * 0.5,
                    reason=f"Positive sentiment aligns ({sentiment:.2f})",
                    metrics=self._build_metrics(data),
                )
        
        # Strong negative sentiment
        if sentiment <= -self.config.sentiment_strong_threshold:
            if proposed_direction == TradeDirection.SHORT:
                return SentimentModifierOutput(
                    effect="STRENGTHEN",
                    magnitude=self.config.strengthen_magnitude,
                    reason=f"Strong negative sentiment aligns ({sentiment:.2f})",
                    metrics=self._build_metrics(data),
                )
            elif proposed_direction == TradeDirection.LONG:
                return SentimentModifierOutput(
                    effect="WEAKEN",
                    magnitude=self.config.weaken_magnitude,
                    reason=f"Strong negative sentiment opposes long ({sentiment:.2f})",
                    metrics=self._build_metrics(data),
                )
        
        # Moderate negative sentiment
        elif sentiment <= self.config.sentiment_negative_threshold:
            if proposed_direction == TradeDirection.SHORT:
                return SentimentModifierOutput(
                    effect="STRENGTHEN",
                    magnitude=self.config.strengthen_magnitude * 0.5,
                    reason=f"Negative sentiment aligns ({sentiment:.2f})",
                    metrics=self._build_metrics(data),
                )
        
        return None
    
    def _check_divergence(
        self,
        data: SentimentInput,
        proposed_direction: Optional[TradeDirection]
    ) -> Optional[SentimentModifierOutput]:
        """
        Check for sentiment-price divergence.
        
        Divergence can be a warning sign.
        """
        if not self.config.divergence_significant:
            return None
        
        if not data.sentiment_price_divergence:
            return None
        
        # Bullish divergence (sentiment positive but price down)
        if data.divergence_type == "BULLISH":
            if proposed_direction == TradeDirection.LONG:
                return SentimentModifierOutput(
                    effect="STRENGTHEN",
                    magnitude=self.config.strengthen_magnitude * 0.7,
                    reason="Bullish sentiment divergence supports long",
                    metrics=self._build_metrics(data),
                )
            elif proposed_direction == TradeDirection.SHORT:
                return SentimentModifierOutput(
                    effect="WEAKEN",
                    magnitude=self.config.weaken_magnitude * 0.7,
                    reason="Bullish sentiment divergence warns against short",
                    metrics=self._build_metrics(data),
                )
        
        # Bearish divergence (sentiment negative but price up)
        if data.divergence_type == "BEARISH":
            if proposed_direction == TradeDirection.SHORT:
                return SentimentModifierOutput(
                    effect="STRENGTHEN",
                    magnitude=self.config.strengthen_magnitude * 0.7,
                    reason="Bearish sentiment divergence supports short",
                    metrics=self._build_metrics(data),
                )
            elif proposed_direction == TradeDirection.LONG:
                return SentimentModifierOutput(
                    effect="WEAKEN",
                    magnitude=self.config.weaken_magnitude * 0.7,
                    reason="Bearish sentiment divergence warns against long",
                    metrics=self._build_metrics(data),
                )
        
        return None
    
    def _build_metrics(self, data: SentimentInput) -> dict:
        """Build metrics dictionary."""
        return {
            k: v for k, v in {
                "sentiment_score": data.sentiment_score,
                "sentiment_regime": data.sentiment_regime,
                "news_shock_detected": data.news_shock_detected,
                "news_shock_direction": data.news_shock_direction,
                "news_impact_score": data.news_impact_score,
                "fear_greed_index": data.fear_greed_index,
                "divergence_detected": data.sentiment_price_divergence,
                "divergence_type": data.divergence_type,
            }.items() if v is not None
        }
