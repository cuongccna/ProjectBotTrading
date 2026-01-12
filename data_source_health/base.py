"""
Data Source Health - Base Health Scorer.

============================================================
ABSTRACT BASE HEALTH SCORER
============================================================

Defines the interface for all health evaluators:
- BaseHealthScorer: Abstract base for all evaluators
- Provides common evaluation workflow
- Handles failure safety

============================================================
FAILURE SAFETY
============================================================

Per requirements:
- This module must NEVER crash the system
- If scoring fails, assume worst-case (CRITICAL)
- Notify Risk Controller

============================================================
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Optional
import logging
import time

from .config import HealthConfig, get_config
from .models import (
    DimensionType,
    DimensionScore,
    HealthScore,
    HealthState,
    SourceType,
)
from .metrics import SourceMetrics
from .scorers import DimensionScorerFactory, BaseDimensionScorer
from .exceptions import EvaluationError


logger = logging.getLogger(__name__)


class BaseHealthScorer(ABC):
    """
    Abstract base class for health evaluators.
    
    ============================================================
    DESIGN
    ============================================================
    
    Each health scorer:
    - Evaluates a specific type of data source
    - Uses dimension scorers to calculate scores
    - Aggregates into final health score
    - Handles failures gracefully
    
    ============================================================
    SUBCLASSING
    ============================================================
    
    Subclasses should:
    1. Set source_type class attribute
    2. Override _get_tracked_field() if needed
    3. Override _evaluate_custom_dimensions() if needed
    
    ============================================================
    USAGE
    ============================================================
    
    ```python
    class MarketDataHealthScorer(BaseHealthScorer):
        source_type = SourceType.MARKET_DATA
        
        def _get_tracked_field(self) -> str:
            return "price"
    
    scorer = MarketDataHealthScorer()
    health = scorer.evaluate(metrics)
    ```
    
    ============================================================
    """
    
    source_type: SourceType = SourceType.UNKNOWN
    
    def __init__(
        self,
        source_name: str,
        config: Optional[HealthConfig] = None,
    ) -> None:
        """
        Initialize health scorer.
        
        Args:
            source_name: Name of the data source
            config: Health configuration
        """
        self._source_name = source_name
        self._config = config or get_config()
        
        # Create dimension scorers
        self._dimension_scorers = DimensionScorerFactory.create_all(self._config)
        
        # Track last evaluation
        self._last_health: Optional[HealthScore] = None
        
        logger.debug(f"Initialized {self.__class__.__name__} for {source_name}")
    
    @property
    def source_name(self) -> str:
        """Get source name."""
        return self._source_name
    
    def evaluate(
        self,
        metrics: SourceMetrics,
        window_seconds: Optional[int] = None,
    ) -> HealthScore:
        """
        Evaluate health of the data source.
        
        This is the main entry point for health evaluation.
        Handles all errors gracefully - never crashes.
        
        Args:
            metrics: Source metrics container
            window_seconds: Time window for evaluation
            
        Returns:
            HealthScore with final score and state
        """
        start_time = time.time()
        window = window_seconds or self._config.metrics_window_seconds
        
        try:
            # Evaluate all dimensions
            dimension_scores = self._evaluate_dimensions(metrics, window)
            
            # Calculate final score
            final_score = sum(
                ds.weighted_score
                for ds in dimension_scores.values()
            )
            final_score = max(0.0, min(100.0, final_score))
            
            # Determine state
            state = self._config.thresholds.get_state(final_score)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Build health score
            health = HealthScore(
                source_name=self._source_name,
                source_type=self.source_type,
                final_score=final_score,
                state=state,
                dimensions=dimension_scores,
                evaluation_duration_ms=duration_ms,
                previous_state=self._last_health.state if self._last_health else None,
                previous_score=self._last_health.final_score if self._last_health else None,
            )
            
            # Store for next evaluation
            self._last_health = health
            
            # Log evaluation
            self._log_evaluation(health)
            
            return health
            
        except Exception as e:
            # FAILURE SAFETY: On any error, assume CRITICAL
            logger.error(
                f"Health evaluation failed for {self._source_name}: {e}",
                exc_info=True,
            )
            
            return self._create_critical_health(
                reason=f"Evaluation error: {str(e)}",
                duration_ms=(time.time() - start_time) * 1000,
            )
    
    def _evaluate_dimensions(
        self,
        metrics: SourceMetrics,
        window_seconds: int,
    ) -> Dict[DimensionType, DimensionScore]:
        """
        Evaluate all dimensions.
        
        Individual dimension failures don't stop evaluation.
        """
        dimension_scores: Dict[DimensionType, DimensionScore] = {}
        
        for dimension_type, scorer in self._dimension_scorers.items():
            try:
                if dimension_type == DimensionType.CONSISTENCY:
                    # Consistency needs tracked field
                    tracked_field = self._get_tracked_field()
                    score = scorer.score(metrics, window_seconds, tracked_field=tracked_field)
                else:
                    score = scorer.score(metrics, window_seconds)
                
                dimension_scores[dimension_type] = score
                
            except Exception as e:
                # Log error but continue with other dimensions
                logger.warning(
                    f"Failed to score {dimension_type.value} for {self._source_name}: {e}"
                )
                
                # Use zero score for failed dimension
                dimension_scores[dimension_type] = DimensionScore(
                    dimension=dimension_type,
                    score=0.0,
                    weight=self._config.weights.get_weight(dimension_type),
                    weighted_score=0.0,
                    explanation=f"Scoring failed: {str(e)}",
                )
        
        return dimension_scores
    
    def _get_tracked_field(self) -> str:
        """
        Get the field name to track for consistency scoring.
        
        Override in subclasses for source-specific fields.
        """
        return "value"
    
    def _create_critical_health(
        self,
        reason: str,
        duration_ms: float,
    ) -> HealthScore:
        """
        Create a CRITICAL health score (fallback on errors).
        
        Per requirements: If scoring fails, assume worst-case.
        """
        # Create zero scores for all dimensions
        dimension_scores = {}
        for dimension_type in DimensionType:
            dimension_scores[dimension_type] = DimensionScore(
                dimension=dimension_type,
                score=0.0,
                weight=self._config.weights.get_weight(dimension_type),
                weighted_score=0.0,
                explanation=reason,
            )
        
        return HealthScore(
            source_name=self._source_name,
            source_type=self.source_type,
            final_score=0.0,
            state=HealthState.CRITICAL,
            dimensions=dimension_scores,
            evaluation_duration_ms=duration_ms,
            previous_state=self._last_health.state if self._last_health else None,
            previous_score=self._last_health.final_score if self._last_health else None,
        )
    
    def _log_evaluation(self, health: HealthScore) -> None:
        """Log the evaluation result."""
        if self._config.log_transitions_only and not health.state_changed:
            return
        
        if not self._config.log_all_evaluations:
            return
        
        log_level = logging.INFO
        if health.state == HealthState.CRITICAL:
            log_level = logging.ERROR
        elif health.state == HealthState.DEGRADED:
            log_level = logging.WARNING
        
        weakest = health.get_weakest_dimension()
        weakest_info = f", weakest: {weakest.dimension.value}={weakest.score:.0f}" if weakest else ""
        
        logger.log(
            log_level,
            f"[{self._source_name}] Health: {health.final_score:.1f} "
            f"({health.state.value}){weakest_info} "
            f"[{health.evaluation_duration_ms:.1f}ms]"
        )


# =============================================================
# SOURCE-SPECIFIC HEALTH SCORERS
# =============================================================


class MarketDataHealthScorer(BaseHealthScorer):
    """
    Health scorer for market data sources.
    
    Tracks price data for consistency scoring.
    """
    
    source_type = SourceType.MARKET_DATA
    
    def _get_tracked_field(self) -> str:
        """Track price for consistency."""
        return "price"


class OnChainHealthScorer(BaseHealthScorer):
    """
    Health scorer for on-chain data sources.
    
    Tracks transaction counts for consistency.
    """
    
    source_type = SourceType.ONCHAIN
    
    def _get_tracked_field(self) -> str:
        """Track transaction count for consistency."""
        return "tx_count"


class SentimentHealthScorer(BaseHealthScorer):
    """
    Health scorer for sentiment data sources.
    
    Tracks sentiment scores for consistency.
    """
    
    source_type = SourceType.SENTIMENT
    
    def _get_tracked_field(self) -> str:
        """Track sentiment score for consistency."""
        return "sentiment_score"


class NewsHealthScorer(BaseHealthScorer):
    """
    Health scorer for news data sources.
    
    Tracks article count for consistency.
    """
    
    source_type = SourceType.NEWS
    
    def _get_tracked_field(self) -> str:
        """Track article count for consistency."""
        return "article_count"


class MacroHealthScorer(BaseHealthScorer):
    """
    Health scorer for macro data sources.
    
    Tracks indicator values for consistency.
    """
    
    source_type = SourceType.MACRO
    
    def _get_tracked_field(self) -> str:
        """Track indicator value for consistency."""
        return "indicator_value"


# =============================================================
# SCORER FACTORY
# =============================================================


class HealthScorerFactory:
    """Factory for creating appropriate health scorer."""
    
    _scorers = {
        SourceType.MARKET_DATA: MarketDataHealthScorer,
        SourceType.ONCHAIN: OnChainHealthScorer,
        SourceType.SENTIMENT: SentimentHealthScorer,
        SourceType.NEWS: NewsHealthScorer,
        SourceType.MACRO: MacroHealthScorer,
        SourceType.UNKNOWN: BaseHealthScorer,
    }
    
    @classmethod
    def create(
        cls,
        source_name: str,
        source_type: SourceType,
        config: Optional[HealthConfig] = None,
    ) -> BaseHealthScorer:
        """
        Create appropriate health scorer for source type.
        
        Args:
            source_name: Name of the data source
            source_type: Type of the data source
            config: Health configuration
            
        Returns:
            Appropriate health scorer instance
        """
        scorer_class = cls._scorers.get(source_type, BaseHealthScorer)
        
        # Handle abstract base class
        if scorer_class == BaseHealthScorer:
            # Create concrete subclass on the fly
            class GenericHealthScorer(BaseHealthScorer):
                source_type = source_type
            
            return GenericHealthScorer(source_name, config)
        
        return scorer_class(source_name, config)
