"""
Data Source Health - Dimension Scorers.

============================================================
HEALTH DIMENSION SCORING
============================================================

Individual scorers for each health dimension:
1. Availability  - API uptime, timeout frequency, retry success
2. Freshness     - Data delay, timestamp drift, stale detection
3. Consistency   - Value jumps, cross-source deviation
4. Completeness  - Missing fields, partial records
5. Error Rate    - HTTP errors, parsing failures

Each scorer:
- Takes raw metrics
- Returns normalized score (0-100)
- Provides explanation

============================================================
SCORING PHILOSOPHY
============================================================

- All scores normalized to 0-100
- Higher is always better
- Fully explainable (no ML)
- Configurable thresholds

============================================================
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional
import logging

from .config import (
    HealthConfig,
    AvailabilityThresholds,
    FreshnessThresholds,
    ConsistencyThresholds,
    CompletenessThresholds,
    ErrorRateThresholds,
    get_config,
)
from .models import DimensionType, DimensionScore
from .metrics import SourceMetrics


logger = logging.getLogger(__name__)


# =============================================================
# BASE DIMENSION SCORER
# =============================================================


class BaseDimensionScorer(ABC):
    """
    Abstract base class for dimension scorers.
    
    Each dimension scorer calculates a normalized score (0-100)
    from raw metrics.
    """
    
    dimension_type: DimensionType
    
    def __init__(self, config: Optional[HealthConfig] = None) -> None:
        """Initialize scorer with configuration."""
        self._config = config or get_config()
    
    @abstractmethod
    def score(
        self,
        metrics: SourceMetrics,
        window_seconds: Optional[int] = None,
    ) -> DimensionScore:
        """
        Calculate score for this dimension.
        
        Args:
            metrics: Source metrics container
            window_seconds: Time window for calculation
            
        Returns:
            DimensionScore with score, explanation, and metrics
        """
        pass
    
    def _normalize_score(self, raw_score: float) -> float:
        """Normalize score to 0-100 range."""
        return max(0.0, min(100.0, raw_score))
    
    def _interpolate_score(
        self,
        value: float,
        excellent_threshold: float,
        good_threshold: float,
        poor_threshold: float,
        inverted: bool = False,
    ) -> float:
        """
        Interpolate score based on thresholds.
        
        Args:
            value: The metric value
            excellent_threshold: Value for score 100
            good_threshold: Value for score 85
            poor_threshold: Value for score 50
            inverted: If True, lower values are better
            
        Returns:
            Interpolated score (0-100)
        """
        if inverted:
            # Lower values are better (e.g., error rate)
            if value <= excellent_threshold:
                return 100.0
            elif value <= good_threshold:
                # Interpolate between 100 and 85
                ratio = (value - excellent_threshold) / (good_threshold - excellent_threshold)
                return 100.0 - (ratio * 15.0)
            elif value <= poor_threshold:
                # Interpolate between 85 and 50
                ratio = (value - good_threshold) / (poor_threshold - good_threshold)
                return 85.0 - (ratio * 35.0)
            else:
                # Below poor threshold, scale down to 0
                # Assume critical at 2x poor threshold
                critical = poor_threshold * 2
                if value >= critical:
                    return 0.0
                ratio = (value - poor_threshold) / (critical - poor_threshold)
                return 50.0 - (ratio * 50.0)
        else:
            # Higher values are better (e.g., uptime)
            if value >= excellent_threshold:
                return 100.0
            elif value >= good_threshold:
                ratio = (value - good_threshold) / (excellent_threshold - good_threshold)
                return 85.0 + (ratio * 15.0)
            elif value >= poor_threshold:
                ratio = (value - poor_threshold) / (good_threshold - poor_threshold)
                return 50.0 + (ratio * 35.0)
            else:
                # Below poor threshold
                if value <= 0:
                    return 0.0
                ratio = value / poor_threshold
                return ratio * 50.0


# =============================================================
# AVAILABILITY SCORER
# =============================================================


class AvailabilityScorer(BaseDimensionScorer):
    """
    Scores availability based on:
    - Uptime percentage
    - Timeout frequency
    - Retry success rate
    """
    
    dimension_type = DimensionType.AVAILABILITY
    
    def __init__(self, config: Optional[HealthConfig] = None) -> None:
        super().__init__(config)
        self._thresholds: AvailabilityThresholds = self._config.availability
    
    def score(
        self,
        metrics: SourceMetrics,
        window_seconds: Optional[int] = None,
    ) -> DimensionScore:
        """Calculate availability score."""
        # Get metrics
        avail_metrics = metrics.get_availability_metrics(window_seconds)
        
        # No samples - assume healthy
        if avail_metrics["sample_count"] == 0:
            return DimensionScore(
                dimension=self.dimension_type,
                score=100.0,
                weight=self._config.weights.availability,
                weighted_score=100.0 * self._config.weights.availability,
                explanation="No data yet - assuming healthy",
                metrics=avail_metrics,
            )
        
        # Score uptime (higher is better)
        uptime_score = self._interpolate_score(
            avail_metrics["uptime_percent"],
            self._thresholds.uptime_excellent,  # 99.9%
            self._thresholds.uptime_good,       # 99.0%
            self._thresholds.uptime_poor,       # 95.0%
            inverted=False,
        )
        
        # Score timeout rate (lower is better)
        timeout_score = self._interpolate_score(
            avail_metrics["timeout_percent"],
            self._thresholds.timeout_excellent,  # 0.1%
            self._thresholds.timeout_good,       # 1.0%
            self._thresholds.timeout_poor,       # 5.0%
            inverted=True,
        )
        
        # Score retry success (higher is better)
        retry_score = self._interpolate_score(
            avail_metrics["retry_success_rate"],
            self._thresholds.retry_success_excellent,  # 95%
            self._thresholds.retry_success_good,       # 80%
            self._thresholds.retry_success_poor,       # 50%
            inverted=False,
        )
        
        # Weighted average (uptime most important)
        final_score = (
            uptime_score * 0.5 +
            timeout_score * 0.3 +
            retry_score * 0.2
        )
        final_score = self._normalize_score(final_score)
        
        # Build explanation
        explanation = (
            f"Uptime: {avail_metrics['uptime_percent']:.1f}% ({uptime_score:.0f}), "
            f"Timeouts: {avail_metrics['timeout_percent']:.1f}% ({timeout_score:.0f}), "
            f"Retry success: {avail_metrics['retry_success_rate']:.1f}% ({retry_score:.0f})"
        )
        
        return DimensionScore(
            dimension=self.dimension_type,
            score=final_score,
            weight=self._config.weights.availability,
            weighted_score=final_score * self._config.weights.availability,
            explanation=explanation,
            metrics={
                **avail_metrics,
                "uptime_score": uptime_score,
                "timeout_score": timeout_score,
                "retry_score": retry_score,
            },
        )


# =============================================================
# FRESHNESS SCORER
# =============================================================


class FreshnessScorer(BaseDimensionScorer):
    """
    Scores freshness based on:
    - Data delay vs expected interval
    - Timestamp drift
    - Stale data percentage
    """
    
    dimension_type = DimensionType.FRESHNESS
    
    def __init__(self, config: Optional[HealthConfig] = None) -> None:
        super().__init__(config)
        self._thresholds: FreshnessThresholds = self._config.freshness
    
    def score(
        self,
        metrics: SourceMetrics,
        window_seconds: Optional[int] = None,
    ) -> DimensionScore:
        """Calculate freshness score."""
        # Get metrics
        fresh_metrics = metrics.get_freshness_metrics(window_seconds)
        
        # No samples - assume healthy
        if fresh_metrics["sample_count"] == 0:
            return DimensionScore(
                dimension=self.dimension_type,
                score=100.0,
                weight=self._config.weights.freshness,
                weighted_score=100.0 * self._config.weights.freshness,
                explanation="No data yet - assuming healthy",
                metrics=fresh_metrics,
            )
        
        # Score average delay (lower is better)
        delay_score = self._interpolate_score(
            fresh_metrics["avg_delay_seconds"],
            self._thresholds.delay_excellent,  # 1s
            self._thresholds.delay_good,       # 5s
            self._thresholds.delay_poor,       # 30s
            inverted=True,
        )
        
        # Check for stale data
        if fresh_metrics["max_delay_seconds"] >= self._thresholds.delay_stale:
            delay_score = min(delay_score, 30.0)  # Cap at 30 if stale
        
        # Score stale percentage (lower is better)
        stale_score = 100.0 - fresh_metrics["stale_percent"]
        
        # Score timestamp drift (lower is better)
        drift_score = self._interpolate_score(
            fresh_metrics["timestamp_drift_seconds"],
            self._thresholds.drift_excellent,  # 0.5s
            self._thresholds.drift_good,       # 2s
            self._thresholds.drift_poor,       # 10s
            inverted=True,
        )
        
        # Weighted average
        final_score = (
            delay_score * 0.5 +
            stale_score * 0.3 +
            drift_score * 0.2
        )
        final_score = self._normalize_score(final_score)
        
        # Build explanation
        explanation = (
            f"Avg delay: {fresh_metrics['avg_delay_seconds']:.1f}s ({delay_score:.0f}), "
            f"Stale: {fresh_metrics['stale_percent']:.1f}% ({stale_score:.0f}), "
            f"Drift: {fresh_metrics['timestamp_drift_seconds']:.1f}s ({drift_score:.0f})"
        )
        
        return DimensionScore(
            dimension=self.dimension_type,
            score=final_score,
            weight=self._config.weights.freshness,
            weighted_score=final_score * self._config.weights.freshness,
            explanation=explanation,
            metrics={
                **fresh_metrics,
                "delay_score": delay_score,
                "stale_score": stale_score,
                "drift_score": drift_score,
            },
        )


# =============================================================
# CONSISTENCY SCORER
# =============================================================


class ConsistencyScorer(BaseDimensionScorer):
    """
    Scores consistency based on:
    - Sudden value jumps
    - Standard deviation
    - Schema stability (via field count)
    """
    
    dimension_type = DimensionType.CONSISTENCY
    
    def __init__(self, config: Optional[HealthConfig] = None) -> None:
        super().__init__(config)
        self._thresholds: ConsistencyThresholds = self._config.consistency
    
    def score(
        self,
        metrics: SourceMetrics,
        window_seconds: Optional[int] = None,
        tracked_field: str = "price",
    ) -> DimensionScore:
        """Calculate consistency score."""
        # Get metrics
        consist_metrics = metrics.get_consistency_metrics(tracked_field, window_seconds)
        
        # No samples - assume healthy
        if consist_metrics["sample_count"] < 2:
            return DimensionScore(
                dimension=self.dimension_type,
                score=100.0,
                weight=self._config.weights.consistency,
                weighted_score=100.0 * self._config.weights.consistency,
                explanation="Insufficient data for consistency check",
                metrics=consist_metrics,
            )
        
        # Score max jump (lower is better)
        jump_score = self._interpolate_score(
            consist_metrics["max_jump_percent"],
            self._thresholds.jump_normal,    # 5%
            self._thresholds.jump_warning,   # 10%
            self._thresholds.jump_anomaly,   # 20%
            inverted=True,
        )
        
        # Score average change (lower is better for stability)
        change_score = self._interpolate_score(
            consist_metrics["value_change_percent"],
            self._thresholds.deviation_excellent,  # 0.1%
            self._thresholds.deviation_good,       # 0.5%
            self._thresholds.deviation_poor,       # 2%
            inverted=True,
        )
        
        # Weighted average
        final_score = (
            jump_score * 0.6 +
            change_score * 0.4
        )
        final_score = self._normalize_score(final_score)
        
        # Build explanation
        explanation = (
            f"Max jump: {consist_metrics['max_jump_percent']:.2f}% ({jump_score:.0f}), "
            f"Avg change: {consist_metrics['value_change_percent']:.2f}% ({change_score:.0f})"
        )
        
        return DimensionScore(
            dimension=self.dimension_type,
            score=final_score,
            weight=self._config.weights.consistency,
            weighted_score=final_score * self._config.weights.consistency,
            explanation=explanation,
            metrics={
                **consist_metrics,
                "jump_score": jump_score,
                "change_score": change_score,
            },
        )


# =============================================================
# COMPLETENESS SCORER
# =============================================================


class CompletenessScorer(BaseDimensionScorer):
    """
    Scores completeness based on:
    - Missing fields percentage
    - Partial record percentage
    - Empty response percentage
    """
    
    dimension_type = DimensionType.COMPLETENESS
    
    def __init__(self, config: Optional[HealthConfig] = None) -> None:
        super().__init__(config)
        self._thresholds: CompletenessThresholds = self._config.completeness
    
    def score(
        self,
        metrics: SourceMetrics,
        window_seconds: Optional[int] = None,
    ) -> DimensionScore:
        """Calculate completeness score."""
        # Get metrics
        comp_metrics = metrics.get_completeness_metrics(window_seconds)
        
        # No samples - assume healthy
        if comp_metrics["sample_count"] == 0:
            return DimensionScore(
                dimension=self.dimension_type,
                score=100.0,
                weight=self._config.weights.completeness,
                weighted_score=100.0 * self._config.weights.completeness,
                explanation="No data yet - assuming healthy",
                metrics=comp_metrics,
            )
        
        # Score missing fields (lower is better)
        missing_score = self._interpolate_score(
            comp_metrics["missing_fields_percent"],
            self._thresholds.missing_excellent,  # 0%
            self._thresholds.missing_good,       # 5%
            self._thresholds.missing_poor,       # 20%
            inverted=True,
        )
        
        # Score partial records (lower is better)
        partial_score = self._interpolate_score(
            comp_metrics["partial_record_percent"],
            self._thresholds.partial_excellent,  # 0%
            self._thresholds.partial_good,       # 2%
            self._thresholds.partial_poor,       # 10%
            inverted=True,
        )
        
        # Score empty responses (lower is better)
        empty_score = 100.0 - comp_metrics["empty_response_percent"]
        
        # Weighted average
        final_score = (
            missing_score * 0.4 +
            partial_score * 0.3 +
            empty_score * 0.3
        )
        final_score = self._normalize_score(final_score)
        
        # Build explanation
        explanation = (
            f"Missing: {comp_metrics['missing_fields_percent']:.1f}% ({missing_score:.0f}), "
            f"Partial: {comp_metrics['partial_record_percent']:.1f}% ({partial_score:.0f}), "
            f"Empty: {comp_metrics['empty_response_percent']:.1f}%"
        )
        
        return DimensionScore(
            dimension=self.dimension_type,
            score=final_score,
            weight=self._config.weights.completeness,
            weighted_score=final_score * self._config.weights.completeness,
            explanation=explanation,
            metrics={
                **comp_metrics,
                "missing_score": missing_score,
                "partial_score": partial_score,
                "empty_score": empty_score,
            },
        )


# =============================================================
# ERROR RATE SCORER
# =============================================================


class ErrorRateScorer(BaseDimensionScorer):
    """
    Scores error rate based on:
    - Overall error percentage
    - HTTP error rate
    - Parse error rate
    """
    
    dimension_type = DimensionType.ERROR_RATE
    
    def __init__(self, config: Optional[HealthConfig] = None) -> None:
        super().__init__(config)
        self._thresholds: ErrorRateThresholds = self._config.error_rate
    
    def score(
        self,
        metrics: SourceMetrics,
        window_seconds: Optional[int] = None,
    ) -> DimensionScore:
        """Calculate error rate score."""
        # Get metrics
        error_metrics = metrics.get_error_rate_metrics(window_seconds)
        
        # No samples - assume healthy
        if error_metrics["sample_count"] == 0:
            return DimensionScore(
                dimension=self.dimension_type,
                score=100.0,
                weight=self._config.weights.error_rate,
                weighted_score=100.0 * self._config.weights.error_rate,
                explanation="No data yet - assuming healthy",
                metrics=error_metrics,
            )
        
        # Score overall error rate (lower is better)
        overall_score = self._interpolate_score(
            error_metrics["error_rate_percent"],
            self._thresholds.error_excellent,   # 0.1%
            self._thresholds.error_good,        # 1%
            self._thresholds.error_poor,        # 5%
            inverted=True,
        )
        
        # Check for critical error rate
        if error_metrics["error_rate_percent"] >= self._thresholds.error_critical:
            overall_score = 0.0
        
        # Score HTTP errors specifically
        http_score = self._interpolate_score(
            error_metrics["http_error_rate"],
            self._thresholds.error_excellent,
            self._thresholds.error_good,
            self._thresholds.error_poor,
            inverted=True,
        )
        
        # Weighted average
        final_score = (
            overall_score * 0.7 +
            http_score * 0.3
        )
        final_score = self._normalize_score(final_score)
        
        # Build explanation
        explanation = (
            f"Error rate: {error_metrics['error_rate_percent']:.2f}% ({overall_score:.0f}), "
            f"HTTP errors: {error_metrics['http_error_rate']:.2f}%"
        )
        
        return DimensionScore(
            dimension=self.dimension_type,
            score=final_score,
            weight=self._config.weights.error_rate,
            weighted_score=final_score * self._config.weights.error_rate,
            explanation=explanation,
            metrics={
                **error_metrics,
                "overall_score": overall_score,
                "http_score": http_score,
            },
        )


# =============================================================
# SCORER FACTORY
# =============================================================


class DimensionScorerFactory:
    """Factory for creating dimension scorers."""
    
    _scorers = {
        DimensionType.AVAILABILITY: AvailabilityScorer,
        DimensionType.FRESHNESS: FreshnessScorer,
        DimensionType.CONSISTENCY: ConsistencyScorer,
        DimensionType.COMPLETENESS: CompletenessScorer,
        DimensionType.ERROR_RATE: ErrorRateScorer,
    }
    
    @classmethod
    def create(
        cls,
        dimension: DimensionType,
        config: Optional[HealthConfig] = None,
    ) -> BaseDimensionScorer:
        """Create a scorer for the given dimension."""
        scorer_class = cls._scorers.get(dimension)
        if scorer_class is None:
            raise ValueError(f"Unknown dimension: {dimension}")
        return scorer_class(config)
    
    @classmethod
    def create_all(
        cls,
        config: Optional[HealthConfig] = None,
    ) -> Dict[DimensionType, BaseDimensionScorer]:
        """Create scorers for all dimensions."""
        return {
            dimension: cls.create(dimension, config)
            for dimension in DimensionType
        }
