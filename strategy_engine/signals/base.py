"""
Strategy Engine - Base Signal Generator.

============================================================
PURPOSE
============================================================
Abstract base class for all signal generators.

Provides common patterns for:
- Input validation
- Threshold checking
- Signal strength determination
- Reason formatting

============================================================
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

from strategy_engine.types import (
    TradeDirection,
    SignalStrength,
    SignalOutput,
)


class BaseSignalGenerator(ABC):
    """
    Abstract base class for signal generators.
    
    ============================================================
    SUBCLASSES MUST IMPLEMENT
    ============================================================
    - signal_name: Name of the signal type
    - generate(): Main signal generation logic
    
    ============================================================
    """
    
    @property
    @abstractmethod
    def signal_name(self) -> str:
        """Return the name of this signal type."""
        pass
    
    def _determine_strength(
        self,
        scores: List[Tuple[float, SignalStrength]],
    ) -> SignalStrength:
        """
        Determine signal strength from component scores.
        
        Takes highest applicable strength level.
        
        Args:
            scores: List of (score, strength_if_achieved) tuples
                   Should be ordered from highest to lowest threshold
        
        Returns:
            Highest achieved SignalStrength
        """
        for score, strength in scores:
            if score > 0:
                return strength
        return SignalStrength.NONE
    
    def _aggregate_direction_votes(
        self,
        votes: List[Tuple[TradeDirection, float]]
    ) -> Tuple[TradeDirection, float]:
        """
        Aggregate direction votes into final direction.
        
        Args:
            votes: List of (direction, weight) tuples
        
        Returns:
            (final_direction, net_score)
        """
        long_score = 0.0
        short_score = 0.0
        
        for direction, weight in votes:
            if direction == TradeDirection.LONG:
                long_score += weight
            elif direction == TradeDirection.SHORT:
                short_score += weight
        
        net_score = long_score - short_score
        
        if abs(net_score) < 0.1:  # Near zero = neutral
            return TradeDirection.NEUTRAL, abs(net_score)
        elif net_score > 0:
            return TradeDirection.LONG, net_score
        else:
            return TradeDirection.SHORT, abs(net_score)
    
    def _check_threshold(
        self,
        value: float,
        threshold: float,
        comparison: str = "gte"
    ) -> bool:
        """
        Check a value against a threshold.
        
        Args:
            value: Value to check
            threshold: Threshold to compare against
            comparison: "gte", "lte", "gt", "lt", "abs_gte"
        
        Returns:
            True if threshold check passes
        """
        if comparison == "gte":
            return value >= threshold
        elif comparison == "lte":
            return value <= threshold
        elif comparison == "gt":
            return value > threshold
        elif comparison == "lt":
            return value < threshold
        elif comparison == "abs_gte":
            return abs(value) >= threshold
        return False
    
    def _safe_get(
        self,
        value: Optional[float],
        default: float = 0.0
    ) -> float:
        """Safely get a float value with default."""
        return value if value is not None else default
    
    def _create_neutral_signal(self, reason: str) -> SignalOutput:
        """Create a neutral signal output."""
        return SignalOutput(
            direction=TradeDirection.NEUTRAL,
            strength=SignalStrength.NONE,
            reason=reason,
            metrics={},
            timestamp=datetime.utcnow(),
        )
    
    def _format_metrics(self, **kwargs) -> Dict[str, Any]:
        """Format metrics dictionary, excluding None values."""
        return {k: v for k, v in kwargs.items() if v is not None}
