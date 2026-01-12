"""
Strategy Engine - Signal Generators Package.

============================================================
PURPOSE
============================================================
Signal generators analyze specific data domains and produce
directional signals.

Three signal categories:
1. Market Structure: Trend, breakouts, price action
2. Volume Flow: Volume, order flow, absorption
3. Sentiment: News, social, fear/greed (MODIFIER ONLY)

============================================================
"""

from .base import BaseSignalGenerator
from .market_structure import MarketStructureSignalGenerator
from .volume_flow import VolumeFlowSignalGenerator
from .sentiment import SentimentModifierGenerator


__all__ = [
    "BaseSignalGenerator",
    "MarketStructureSignalGenerator",
    "VolumeFlowSignalGenerator",
    "SentimentModifierGenerator",
]
