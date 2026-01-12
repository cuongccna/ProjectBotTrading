"""
Data Source Health - Data Models.

============================================================
CORE DATA STRUCTURES
============================================================

Defines all data models for health scoring:
- HealthState: Enumeration of health states
- DimensionType: Types of health dimensions
- DimensionScore: Score for a single dimension
- HealthScore: Aggregated health score
- SourceHealthRecord: Complete health record for a source
- HealthTransition: State transition event

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4


# =============================================================
# ENUMS
# =============================================================


class HealthState(str, Enum):
    """
    Health state of a data source.
    
    States determine system behavior:
    - HEALTHY: Normal operation
    - DEGRADED: Reduce risk appetite, prefer alternatives
    - CRITICAL: Disable source, notify Risk Controller
    - UNKNOWN: Initial state, not yet evaluated
    """
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
    
    def is_usable(self) -> bool:
        """Check if source is usable for trading."""
        return self in (HealthState.HEALTHY, HealthState.DEGRADED)
    
    def requires_fallback(self) -> bool:
        """Check if fallback source should be used."""
        return self in (HealthState.CRITICAL, HealthState.UNKNOWN)
    
    def should_reduce_risk(self) -> bool:
        """Check if risk should be reduced."""
        return self != HealthState.HEALTHY


class DimensionType(str, Enum):
    """
    Types of health dimensions being evaluated.
    
    Each dimension contributes to the overall health score.
    """
    AVAILABILITY = "availability"
    FRESHNESS = "freshness"
    CONSISTENCY = "consistency"
    COMPLETENESS = "completeness"
    ERROR_RATE = "error_rate"


class SourceType(str, Enum):
    """
    Types of data sources.
    
    Used to apply source-specific evaluation logic.
    """
    MARKET_DATA = "market_data"
    ONCHAIN = "onchain"
    SENTIMENT = "sentiment"
    NEWS = "news"
    MACRO = "macro"
    UNKNOWN = "unknown"


class TransitionReason(str, Enum):
    """Reasons for health state transitions."""
    INITIAL_EVALUATION = "initial_evaluation"
    SCORE_IMPROVED = "score_improved"
    SCORE_DEGRADED = "score_degraded"
    MANUAL_OVERRIDE = "manual_override"
    TIMEOUT = "timeout"
    ERROR_SPIKE = "error_spike"
    DATA_STALE = "data_stale"
    RECOVERED = "recovered"


# =============================================================
# DATA CLASSES
# =============================================================


@dataclass(frozen=True)
class DimensionScore:
    """
    Score for a single health dimension.
    
    Each dimension is scored 0-100 with explanation.
    """
    dimension: DimensionType
    score: float  # 0-100
    weight: float  # 0-1
    weighted_score: float  # score * weight
    explanation: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    evaluated_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self) -> None:
        """Validate score ranges."""
        if not 0 <= self.score <= 100:
            object.__setattr__(self, 'score', max(0, min(100, self.score)))
        if not 0 <= self.weight <= 1:
            object.__setattr__(self, 'weight', max(0, min(1, self.weight)))


@dataclass
class HealthScore:
    """
    Aggregated health score for a data source.
    
    Combines all dimension scores into final health assessment.
    """
    source_name: str
    source_type: SourceType
    final_score: float  # 0-100
    state: HealthState
    dimensions: Dict[DimensionType, DimensionScore]
    evaluated_at: datetime = field(default_factory=datetime.utcnow)
    evaluation_duration_ms: float = 0.0
    
    # Previous state for transition tracking
    previous_state: Optional[HealthState] = None
    previous_score: Optional[float] = None
    
    # Metadata
    evaluation_id: UUID = field(default_factory=uuid4)
    
    @property
    def is_healthy(self) -> bool:
        """Check if source is healthy."""
        return self.state == HealthState.HEALTHY
    
    @property
    def is_degraded(self) -> bool:
        """Check if source is degraded."""
        return self.state == HealthState.DEGRADED
    
    @property
    def is_critical(self) -> bool:
        """Check if source is critical."""
        return self.state == HealthState.CRITICAL
    
    @property
    def state_changed(self) -> bool:
        """Check if state changed from previous evaluation."""
        return self.previous_state is not None and self.previous_state != self.state
    
    def get_dimension_score(self, dimension: DimensionType) -> Optional[float]:
        """Get score for a specific dimension."""
        if dimension in self.dimensions:
            return self.dimensions[dimension].score
        return None
    
    def get_weakest_dimension(self) -> Optional[DimensionScore]:
        """Get the dimension with lowest score."""
        if not self.dimensions:
            return None
        return min(self.dimensions.values(), key=lambda d: d.score)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "source_name": self.source_name,
            "source_type": self.source_type.value,
            "final_score": round(self.final_score, 2),
            "state": self.state.value,
            "dimensions": {
                d.value: {
                    "score": round(v.score, 2),
                    "weight": v.weight,
                    "weighted_score": round(v.weighted_score, 2),
                    "explanation": v.explanation,
                }
                for d, v in self.dimensions.items()
            },
            "evaluated_at": self.evaluated_at.isoformat(),
            "evaluation_duration_ms": round(self.evaluation_duration_ms, 2),
            "state_changed": self.state_changed,
            "previous_state": self.previous_state.value if self.previous_state else None,
        }


@dataclass
class HealthTransition:
    """
    Record of a health state transition.
    
    Used for audit logging and alerting.
    """
    source_name: str
    from_state: HealthState
    to_state: HealthState
    from_score: float
    to_score: float
    reason: TransitionReason
    timestamp: datetime = field(default_factory=datetime.utcnow)
    transition_id: UUID = field(default_factory=uuid4)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_degradation(self) -> bool:
        """Check if this is a degradation (worsening)."""
        state_order = {
            HealthState.HEALTHY: 3,
            HealthState.DEGRADED: 2,
            HealthState.CRITICAL: 1,
            HealthState.UNKNOWN: 0,
        }
        return state_order.get(self.to_state, 0) < state_order.get(self.from_state, 0)
    
    @property
    def is_recovery(self) -> bool:
        """Check if this is a recovery (improvement)."""
        state_order = {
            HealthState.HEALTHY: 3,
            HealthState.DEGRADED: 2,
            HealthState.CRITICAL: 1,
            HealthState.UNKNOWN: 0,
        }
        return state_order.get(self.to_state, 0) > state_order.get(self.from_state, 0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "source_name": self.source_name,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "from_score": round(self.from_score, 2),
            "to_score": round(self.to_score, 2),
            "reason": self.reason.value,
            "timestamp": self.timestamp.isoformat(),
            "is_degradation": self.is_degradation,
            "is_recovery": self.is_recovery,
        }


@dataclass
class SourceHealthRecord:
    """
    Complete health record for a data source.
    
    Maintains history and current state.
    """
    source_name: str
    source_type: SourceType
    
    # Current state
    current_health: Optional[HealthScore] = None
    
    # History (last N evaluations)
    health_history: List[HealthScore] = field(default_factory=list)
    max_history_size: int = 100
    
    # Transitions
    transitions: List[HealthTransition] = field(default_factory=list)
    max_transitions_size: int = 50
    
    # Registration info
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_evaluated_at: Optional[datetime] = None
    evaluation_count: int = 0
    
    # Manual overrides
    is_disabled: bool = False
    disabled_reason: Optional[str] = None
    disabled_at: Optional[datetime] = None
    
    @property
    def state(self) -> HealthState:
        """Get current health state."""
        if self.is_disabled:
            return HealthState.CRITICAL
        if self.current_health is None:
            return HealthState.UNKNOWN
        return self.current_health.state
    
    @property
    def score(self) -> float:
        """Get current health score."""
        if self.current_health is None:
            return 0.0
        return self.current_health.final_score
    
    def update_health(self, health: HealthScore) -> Optional[HealthTransition]:
        """
        Update with new health score.
        
        Returns transition if state changed.
        """
        # Store previous state
        prev_state = self.state
        prev_score = self.score
        
        # Update health with previous info
        health.previous_state = prev_state
        health.previous_score = prev_score
        
        # Set current
        self.current_health = health
        self.last_evaluated_at = health.evaluated_at
        self.evaluation_count += 1
        
        # Add to history
        self.health_history.append(health)
        if len(self.health_history) > self.max_history_size:
            self.health_history = self.health_history[-self.max_history_size:]
        
        # Check for transition
        transition = None
        if prev_state != health.state:
            reason = self._determine_transition_reason(prev_state, health.state, prev_score, health.final_score)
            transition = HealthTransition(
                source_name=self.source_name,
                from_state=prev_state,
                to_state=health.state,
                from_score=prev_score,
                to_score=health.final_score,
                reason=reason,
            )
            self.transitions.append(transition)
            if len(self.transitions) > self.max_transitions_size:
                self.transitions = self.transitions[-self.max_transitions_size:]
        
        return transition
    
    def _determine_transition_reason(
        self,
        from_state: HealthState,
        to_state: HealthState,
        from_score: float,
        to_score: float,
    ) -> TransitionReason:
        """Determine the reason for a state transition."""
        if from_state == HealthState.UNKNOWN:
            return TransitionReason.INITIAL_EVALUATION
        
        if to_score > from_score:
            if to_state == HealthState.HEALTHY:
                return TransitionReason.RECOVERED
            return TransitionReason.SCORE_IMPROVED
        else:
            return TransitionReason.SCORE_DEGRADED
    
    def disable(self, reason: str) -> None:
        """Manually disable this source."""
        self.is_disabled = True
        self.disabled_reason = reason
        self.disabled_at = datetime.utcnow()
    
    def enable(self) -> None:
        """Re-enable this source."""
        self.is_disabled = False
        self.disabled_reason = None
        self.disabled_at = None
    
    def get_average_score(self, window: int = 10) -> float:
        """Get average score over last N evaluations."""
        if not self.health_history:
            return 0.0
        recent = self.health_history[-window:]
        return sum(h.final_score for h in recent) / len(recent)
    
    def get_score_trend(self, window: int = 10) -> float:
        """
        Get score trend (positive = improving, negative = degrading).
        
        Returns difference between recent average and older average.
        """
        if len(self.health_history) < window * 2:
            return 0.0
        
        recent = self.health_history[-window:]
        older = self.health_history[-window*2:-window]
        
        recent_avg = sum(h.final_score for h in recent) / len(recent)
        older_avg = sum(h.final_score for h in older) / len(older)
        
        return recent_avg - older_avg
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "source_name": self.source_name,
            "source_type": self.source_type.value,
            "state": self.state.value,
            "score": round(self.score, 2),
            "is_disabled": self.is_disabled,
            "evaluation_count": self.evaluation_count,
            "last_evaluated_at": self.last_evaluated_at.isoformat() if self.last_evaluated_at else None,
            "average_score": round(self.get_average_score(), 2),
            "score_trend": round(self.get_score_trend(), 2),
        }
