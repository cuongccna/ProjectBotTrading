"""
Data Source Health - Configuration.

============================================================
CONFIGURABLE HEALTH SCORING
============================================================

All scoring parameters are configurable:
- Dimension weights
- Health thresholds
- Evaluation intervals
- Metric windows

Configuration can be loaded from:
- Default values
- Environment variables
- YAML config file

============================================================
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Optional
from pathlib import Path
import logging

from .models import DimensionType, HealthState


logger = logging.getLogger(__name__)


# =============================================================
# DIMENSION WEIGHTS
# =============================================================


@dataclass
class DimensionWeights:
    """
    Weights for each health dimension.
    
    All weights must sum to 1.0 for proper scoring.
    """
    availability: float = 0.25
    freshness: float = 0.25
    consistency: float = 0.20
    completeness: float = 0.20
    error_rate: float = 0.10
    
    def __post_init__(self) -> None:
        """Validate weights sum to 1.0."""
        total = self.total()
        if abs(total - 1.0) > 0.001:
            logger.warning(f"Dimension weights sum to {total}, normalizing to 1.0")
            self._normalize()
    
    def total(self) -> float:
        """Get sum of all weights."""
        return (
            self.availability +
            self.freshness +
            self.consistency +
            self.completeness +
            self.error_rate
        )
    
    def _normalize(self) -> None:
        """Normalize weights to sum to 1.0."""
        total = self.total()
        if total > 0:
            self.availability /= total
            self.freshness /= total
            self.consistency /= total
            self.completeness /= total
            self.error_rate /= total
    
    def get_weight(self, dimension: DimensionType) -> float:
        """Get weight for a specific dimension."""
        return {
            DimensionType.AVAILABILITY: self.availability,
            DimensionType.FRESHNESS: self.freshness,
            DimensionType.CONSISTENCY: self.consistency,
            DimensionType.COMPLETENESS: self.completeness,
            DimensionType.ERROR_RATE: self.error_rate,
        }.get(dimension, 0.0)
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "availability": self.availability,
            "freshness": self.freshness,
            "consistency": self.consistency,
            "completeness": self.completeness,
            "error_rate": self.error_rate,
        }


# =============================================================
# HEALTH THRESHOLDS
# =============================================================


@dataclass
class HealthThresholds:
    """
    Thresholds for determining health states.
    
    - HEALTHY:   score >= healthy_threshold
    - DEGRADED:  degraded_threshold <= score < healthy_threshold
    - CRITICAL:  score < degraded_threshold
    """
    healthy_threshold: float = 85.0
    degraded_threshold: float = 65.0
    
    def __post_init__(self) -> None:
        """Validate thresholds."""
        if self.degraded_threshold >= self.healthy_threshold:
            raise ValueError("degraded_threshold must be < healthy_threshold")
        if not 0 <= self.degraded_threshold <= 100:
            raise ValueError("degraded_threshold must be 0-100")
        if not 0 <= self.healthy_threshold <= 100:
            raise ValueError("healthy_threshold must be 0-100")
    
    def get_state(self, score: float) -> HealthState:
        """Determine health state from score."""
        if score >= self.healthy_threshold:
            return HealthState.HEALTHY
        elif score >= self.degraded_threshold:
            return HealthState.DEGRADED
        else:
            return HealthState.CRITICAL
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "healthy_threshold": self.healthy_threshold,
            "degraded_threshold": self.degraded_threshold,
        }


# =============================================================
# DIMENSION-SPECIFIC THRESHOLDS
# =============================================================


@dataclass
class AvailabilityThresholds:
    """Thresholds for availability dimension."""
    # Uptime percentage thresholds
    uptime_excellent: float = 99.9  # Score 100
    uptime_good: float = 99.0       # Score 85
    uptime_poor: float = 95.0       # Score 50
    
    # Timeout thresholds (percentage of requests)
    timeout_excellent: float = 0.1  # Score 100
    timeout_good: float = 1.0       # Score 85
    timeout_poor: float = 5.0       # Score 50
    
    # Retry success rate thresholds
    retry_success_excellent: float = 95.0
    retry_success_good: float = 80.0
    retry_success_poor: float = 50.0


@dataclass
class FreshnessThresholds:
    """Thresholds for freshness dimension."""
    # Data delay thresholds (in seconds)
    delay_excellent: float = 1.0    # Score 100
    delay_good: float = 5.0         # Score 85
    delay_poor: float = 30.0        # Score 50
    delay_stale: float = 60.0       # Score 0 (stale)
    
    # Timestamp drift thresholds (in seconds)
    drift_excellent: float = 0.5
    drift_good: float = 2.0
    drift_poor: float = 10.0


@dataclass
class ConsistencyThresholds:
    """Thresholds for consistency dimension."""
    # Value jump thresholds (percentage change)
    jump_normal: float = 5.0        # Expected variation
    jump_warning: float = 10.0      # Suspicious
    jump_anomaly: float = 20.0      # Likely error
    
    # Cross-source deviation thresholds (percentage)
    deviation_excellent: float = 0.1
    deviation_good: float = 0.5
    deviation_poor: float = 2.0


@dataclass
class CompletenessThresholds:
    """Thresholds for completeness dimension."""
    # Missing fields thresholds (percentage)
    missing_excellent: float = 0.0   # Score 100
    missing_good: float = 5.0        # Score 85
    missing_poor: float = 20.0       # Score 50
    
    # Partial record thresholds
    partial_excellent: float = 0.0
    partial_good: float = 2.0
    partial_poor: float = 10.0


@dataclass
class ErrorRateThresholds:
    """Thresholds for error rate dimension."""
    # Error rate thresholds (percentage)
    error_excellent: float = 0.1    # Score 100
    error_good: float = 1.0         # Score 85
    error_poor: float = 5.0         # Score 50
    error_critical: float = 10.0    # Score 0


# =============================================================
# MAIN CONFIGURATION
# =============================================================


@dataclass
class HealthConfig:
    """
    Main configuration for health scoring.
    
    Combines all sub-configurations.
    """
    # Dimension weights
    weights: DimensionWeights = field(default_factory=DimensionWeights)
    
    # Health state thresholds
    thresholds: HealthThresholds = field(default_factory=HealthThresholds)
    
    # Dimension-specific thresholds
    availability: AvailabilityThresholds = field(default_factory=AvailabilityThresholds)
    freshness: FreshnessThresholds = field(default_factory=FreshnessThresholds)
    consistency: ConsistencyThresholds = field(default_factory=ConsistencyThresholds)
    completeness: CompletenessThresholds = field(default_factory=CompletenessThresholds)
    error_rate: ErrorRateThresholds = field(default_factory=ErrorRateThresholds)
    
    # Evaluation settings
    evaluation_interval_seconds: int = 30
    metrics_window_seconds: int = 300  # 5 minutes
    min_samples_for_scoring: int = 5
    
    # Alerting
    alert_on_degradation: bool = True
    alert_on_critical: bool = True
    alert_on_recovery: bool = True
    
    # Fallback behavior
    assume_critical_on_error: bool = True
    auto_disable_on_critical: bool = False
    critical_count_before_disable: int = 3
    
    # Logging
    log_all_evaluations: bool = True
    log_transitions_only: bool = False
    
    @classmethod
    def from_env(cls) -> "HealthConfig":
        """
        Load configuration from environment variables.
        
        Environment variables:
        - HEALTH_WEIGHT_AVAILABILITY
        - HEALTH_WEIGHT_FRESHNESS
        - HEALTH_WEIGHT_CONSISTENCY
        - HEALTH_WEIGHT_COMPLETENESS
        - HEALTH_WEIGHT_ERROR_RATE
        - HEALTH_THRESHOLD_HEALTHY
        - HEALTH_THRESHOLD_DEGRADED
        - HEALTH_EVALUATION_INTERVAL
        - HEALTH_METRICS_WINDOW
        """
        config = cls()
        
        # Load weights from env
        if os.getenv("HEALTH_WEIGHT_AVAILABILITY"):
            config.weights.availability = float(os.getenv("HEALTH_WEIGHT_AVAILABILITY"))
        if os.getenv("HEALTH_WEIGHT_FRESHNESS"):
            config.weights.freshness = float(os.getenv("HEALTH_WEIGHT_FRESHNESS"))
        if os.getenv("HEALTH_WEIGHT_CONSISTENCY"):
            config.weights.consistency = float(os.getenv("HEALTH_WEIGHT_CONSISTENCY"))
        if os.getenv("HEALTH_WEIGHT_COMPLETENESS"):
            config.weights.completeness = float(os.getenv("HEALTH_WEIGHT_COMPLETENESS"))
        if os.getenv("HEALTH_WEIGHT_ERROR_RATE"):
            config.weights.error_rate = float(os.getenv("HEALTH_WEIGHT_ERROR_RATE"))
        
        # Normalize weights after loading
        config.weights._normalize()
        
        # Load thresholds from env
        if os.getenv("HEALTH_THRESHOLD_HEALTHY"):
            config.thresholds.healthy_threshold = float(os.getenv("HEALTH_THRESHOLD_HEALTHY"))
        if os.getenv("HEALTH_THRESHOLD_DEGRADED"):
            config.thresholds.degraded_threshold = float(os.getenv("HEALTH_THRESHOLD_DEGRADED"))
        
        # Load evaluation settings from env
        if os.getenv("HEALTH_EVALUATION_INTERVAL"):
            config.evaluation_interval_seconds = int(os.getenv("HEALTH_EVALUATION_INTERVAL"))
        if os.getenv("HEALTH_METRICS_WINDOW"):
            config.metrics_window_seconds = int(os.getenv("HEALTH_METRICS_WINDOW"))
        
        return config
    
    @classmethod
    def from_yaml(cls, path: Path) -> "HealthConfig":
        """Load configuration from YAML file."""
        try:
            import yaml
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
            
            config = cls()
            
            # Load weights
            if 'weights' in data:
                w = data['weights']
                config.weights = DimensionWeights(
                    availability=w.get('availability', 0.25),
                    freshness=w.get('freshness', 0.25),
                    consistency=w.get('consistency', 0.20),
                    completeness=w.get('completeness', 0.20),
                    error_rate=w.get('error_rate', 0.10),
                )
            
            # Load thresholds
            if 'thresholds' in data:
                t = data['thresholds']
                config.thresholds = HealthThresholds(
                    healthy_threshold=t.get('healthy', 85.0),
                    degraded_threshold=t.get('degraded', 65.0),
                )
            
            # Load other settings
            if 'evaluation_interval_seconds' in data:
                config.evaluation_interval_seconds = data['evaluation_interval_seconds']
            if 'metrics_window_seconds' in data:
                config.metrics_window_seconds = data['metrics_window_seconds']
            
            return config
            
        except Exception as e:
            logger.warning(f"Failed to load YAML config from {path}: {e}")
            return cls()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "weights": self.weights.to_dict(),
            "thresholds": self.thresholds.to_dict(),
            "evaluation_interval_seconds": self.evaluation_interval_seconds,
            "metrics_window_seconds": self.metrics_window_seconds,
            "min_samples_for_scoring": self.min_samples_for_scoring,
            "assume_critical_on_error": self.assume_critical_on_error,
        }


# =============================================================
# GLOBAL CONFIG SINGLETON
# =============================================================


_default_config: Optional[HealthConfig] = None


def get_config() -> HealthConfig:
    """Get the global health configuration."""
    global _default_config
    if _default_config is None:
        _default_config = HealthConfig.from_env()
    return _default_config


def set_config(config: HealthConfig) -> None:
    """Set the global health configuration."""
    global _default_config
    _default_config = config
