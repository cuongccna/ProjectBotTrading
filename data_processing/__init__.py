"""
Data Processing Package.

This package handles all data processing, cleaning,
labeling, and feature engineering.

Sub-packages:
- cleaning: Text cleaning and deduplication
- labeling: Topic classification and keyword detection
- sentiment: Sentiment analysis and calibration

Main modules:
- feature_engineering: Feature computation
- contracts: Data contracts for processed market state
- processing_module: Main processing pipeline module
"""

# Data contracts for downstream consumers
from .contracts import (
    TrendState,
    VolatilityLevel,
    LiquidityGrade,
    ProcessedMarketState,
    ProcessedMarketStateBundle,
)

# Main processing module
from .processing_module import ProcessingPipelineModule

__all__ = [
    # Enums
    "TrendState",
    "VolatilityLevel",
    "LiquidityGrade",
    # Main contract
    "ProcessedMarketState",
    "ProcessedMarketStateBundle",
    # Module
    "ProcessingPipelineModule",
]
