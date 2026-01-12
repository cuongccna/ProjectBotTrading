"""
Risk Scoring Engine - Type Definitions.

============================================================
PURPOSE
============================================================
Data contracts for the Risk Scoring Engine.

This module defines all types, enums, and dataclasses used
by the risk scoring system. These contracts ensure
type safety and provide clear documentation of the
engine's inputs and outputs.

============================================================
DESIGN PRINCIPLES
============================================================
- All types are immutable where possible
- Enums for discrete state values
- Dataclasses for structured data
- Clear separation between input and output types

============================================================
RISK DIMENSIONS
============================================================
The engine evaluates exactly four risk dimensions:

1. MARKET - Broad market instability
2. LIQUIDITY - Trading volume and spread issues
3. VOLATILITY - Short-term price range expansion
4. SYSTEM_INTEGRITY - Data and pipeline health

Each dimension outputs a discrete state: SAFE (0), WARNING (1), DANGEROUS (2)

============================================================
CAPITAL AGNOSTIC
============================================================
CRITICAL: This module contains NO references to:
- Account equity
- Position size
- Stop loss distance
- Dollar amounts

Risk scoring is purely environmental assessment.

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


# ============================================================
# ENUMS
# ============================================================


class RiskDimension(str, Enum):
    """
    The four risk dimensions evaluated by the engine.
    
    Each dimension is independent and contributes to the
    total environmental risk score.
    """
    
    MARKET = "market"
    LIQUIDITY = "liquidity"
    VOLATILITY = "volatility"
    SYSTEM_INTEGRITY = "system_integrity"
    
    @classmethod
    def all_dimensions(cls) -> List["RiskDimension"]:
        """Return all risk dimensions in evaluation order."""
        return [cls.MARKET, cls.LIQUIDITY, cls.VOLATILITY, cls.SYSTEM_INTEGRITY]


class RiskState(IntEnum):
    """
    Discrete risk state for each dimension.
    
    Values are integers that sum to produce total risk score.
    
    - SAFE (0): Normal conditions, no concerns
    - WARNING (1): Elevated risk, proceed with caution
    - DANGEROUS (2): High risk, maximum caution required
    """
    
    SAFE = 0
    WARNING = 1
    DANGEROUS = 2
    
    @classmethod
    def from_value(cls, value: int) -> "RiskState":
        """Convert integer to RiskState, clamping to valid range."""
        clamped = max(0, min(2, value))
        return cls(clamped)
    
    @property
    def label(self) -> str:
        """Human-readable label for the state."""
        return self.name.lower()


class RiskLevel(str, Enum):
    """
    Overall risk level classification based on total score.
    
    Total Score Range:
    - LOW: 0-2 (all dimensions safe or one warning)
    - MEDIUM: 3-4 (multiple warnings)
    - HIGH: 5-6 (one or more dangerous)
    - CRITICAL: 7-8 (multiple dangerous)
    """
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    
    @classmethod
    def from_total_score(cls, score: int) -> "RiskLevel":
        """
        Classify risk level from total score.
        
        Args:
            score: Total risk score (0-8)
            
        Returns:
            Appropriate RiskLevel classification
        """
        if score <= 2:
            return cls.LOW
        elif score <= 4:
            return cls.MEDIUM
        elif score <= 6:
            return cls.HIGH
        else:
            return cls.CRITICAL
    
    @property
    def severity_order(self) -> int:
        """Numeric ordering for severity comparison."""
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}[self.value]


class DataFreshnessStatus(str, Enum):
    """
    Status of input data freshness.
    
    Used by System Integrity assessor to determine data health.
    """
    
    FRESH = "fresh"          # Data within expected age
    STALE = "stale"          # Data older than threshold but usable
    MISSING = "missing"      # Data not available
    INVALID = "invalid"      # Data present but malformed


# ============================================================
# INPUT DATA CONTRACTS
# ============================================================


@dataclass(frozen=True)
class MarketDataInput:
    """
    Input data for Market Risk assessment.
    
    All fields are environmental indicators, not account-specific.
    """
    
    # Broad market movement
    btc_price_change_24h_pct: Optional[float] = None
    eth_price_change_24h_pct: Optional[float] = None
    
    # Market correlation indicator
    altcoin_correlation_with_btc: Optional[float] = None
    
    # Market breadth
    advancing_assets_count: Optional[int] = None
    declining_assets_count: Optional[int] = None
    
    # Extreme movement detection
    assets_down_more_than_10pct: Optional[int] = None
    assets_up_more_than_10pct: Optional[int] = None
    
    # Data timestamp
    data_timestamp: Optional[datetime] = None
    
    @property
    def has_minimum_data(self) -> bool:
        """Check if minimum required data is present."""
        return self.btc_price_change_24h_pct is not None


@dataclass(frozen=True)
class LiquidityDataInput:
    """
    Input data for Liquidity Risk assessment.
    
    All fields represent market-wide liquidity conditions.
    """
    
    # Volume indicators (normalized, not absolute values)
    volume_24h_vs_7d_avg_ratio: Optional[float] = None
    volume_24h_vs_30d_avg_ratio: Optional[float] = None
    
    # Spread indicators (percentage)
    avg_bid_ask_spread_pct: Optional[float] = None
    max_bid_ask_spread_pct: Optional[float] = None
    
    # Order book depth indicator (normalized)
    order_book_depth_score: Optional[float] = None  # 0-1, lower = thinner
    
    # Data timestamp
    data_timestamp: Optional[datetime] = None
    
    @property
    def has_minimum_data(self) -> bool:
        """Check if minimum required data is present."""
        return self.volume_24h_vs_7d_avg_ratio is not None


@dataclass(frozen=True)
class VolatilityDataInput:
    """
    Input data for Volatility Risk assessment.
    
    All fields represent current volatility conditions.
    """
    
    # Recent volatility
    price_range_1h_pct: Optional[float] = None
    price_range_4h_pct: Optional[float] = None
    price_range_24h_pct: Optional[float] = None
    
    # Volatility vs historical baseline
    current_volatility_vs_7d_avg_ratio: Optional[float] = None
    current_volatility_vs_30d_avg_ratio: Optional[float] = None
    
    # Large candle detection
    max_candle_range_1h_pct: Optional[float] = None
    abnormal_candle_count_24h: Optional[int] = None
    
    # Data timestamp
    data_timestamp: Optional[datetime] = None
    
    @property
    def has_minimum_data(self) -> bool:
        """Check if minimum required data is present."""
        return self.price_range_24h_pct is not None


@dataclass(frozen=True)
class SystemIntegrityDataInput:
    """
    Input data for System Integrity Risk assessment.
    
    All fields represent system health indicators.
    """
    
    # Data pipeline health
    market_data_age_seconds: Optional[float] = None
    news_data_age_seconds: Optional[float] = None
    onchain_data_age_seconds: Optional[float] = None
    
    # Feature pipeline health
    feature_pipeline_last_run_seconds_ago: Optional[float] = None
    feature_pipeline_success_rate_1h: Optional[float] = None  # 0-1
    
    # System latency
    api_latency_ms: Optional[float] = None
    database_latency_ms: Optional[float] = None
    
    # Error indicators
    error_count_1h: Optional[int] = None
    critical_error_count_1h: Optional[int] = None
    
    # Synchronization
    data_sync_lag_seconds: Optional[float] = None
    
    # Data timestamp
    data_timestamp: Optional[datetime] = None
    
    @property
    def has_minimum_data(self) -> bool:
        """Check if minimum required data is present."""
        return self.market_data_age_seconds is not None


@dataclass(frozen=True)
class RiskScoringInput:
    """
    Complete input bundle for risk scoring.
    
    Aggregates all dimension inputs into a single structure.
    """
    
    market: MarketDataInput = field(default_factory=MarketDataInput)
    liquidity: LiquidityDataInput = field(default_factory=LiquidityDataInput)
    volatility: VolatilityDataInput = field(default_factory=VolatilityDataInput)
    system_integrity: SystemIntegrityDataInput = field(default_factory=SystemIntegrityDataInput)
    
    # Metadata
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# OUTPUT DATA CONTRACTS
# ============================================================


@dataclass(frozen=True)
class DimensionAssessment:
    """
    Assessment result for a single risk dimension.
    
    Contains the discrete state, supporting metrics, and
    explanation for transparency.
    """
    
    dimension: RiskDimension
    state: RiskState
    
    # Explanation for the assessment
    reason: str
    
    # Supporting metrics that led to this assessment
    contributing_factors: Dict[str, Any] = field(default_factory=dict)
    
    # Data freshness for this dimension
    data_freshness: DataFreshnessStatus = DataFreshnessStatus.FRESH
    data_age_seconds: Optional[float] = None
    
    @property
    def score_contribution(self) -> int:
        """The integer contribution to total score."""
        return int(self.state)
    
    @property
    def is_safe(self) -> bool:
        return self.state == RiskState.SAFE
    
    @property
    def is_warning(self) -> bool:
        return self.state == RiskState.WARNING
    
    @property
    def is_dangerous(self) -> bool:
        return self.state == RiskState.DANGEROUS


@dataclass(frozen=True)
class RiskScoringOutput:
    """
    Complete output from the Risk Scoring Engine.
    
    This is the primary output contract consumed by:
    - Strategy Engine
    - Risk Budget Manager
    - Monitoring and Dashboard
    
    ============================================================
    OUTPUT GUARANTEES
    ============================================================
    - total_risk_score: Always 0-8
    - risk_level: Always one of LOW, MEDIUM, HIGH, CRITICAL
    - All four dimensions always present
    - Timestamp always set
    
    ============================================================
    CAPITAL AGNOSTIC
    ============================================================
    This output contains NO information about:
    - Account equity
    - Position sizing
    - Trade decisions
    
    It is purely an environmental risk assessment.
    
    ============================================================
    """
    
    # Unique identifier for this assessment
    assessment_id: UUID = field(default_factory=uuid4)
    
    # Primary outputs
    total_risk_score: int = 0  # 0-8
    risk_level: RiskLevel = RiskLevel.LOW
    
    # Per-dimension breakdown
    market_assessment: DimensionAssessment = field(default_factory=lambda: DimensionAssessment(
        dimension=RiskDimension.MARKET,
        state=RiskState.SAFE,
        reason="No assessment performed",
    ))
    liquidity_assessment: DimensionAssessment = field(default_factory=lambda: DimensionAssessment(
        dimension=RiskDimension.LIQUIDITY,
        state=RiskState.SAFE,
        reason="No assessment performed",
    ))
    volatility_assessment: DimensionAssessment = field(default_factory=lambda: DimensionAssessment(
        dimension=RiskDimension.VOLATILITY,
        state=RiskState.SAFE,
        reason="No assessment performed",
    ))
    system_integrity_assessment: DimensionAssessment = field(default_factory=lambda: DimensionAssessment(
        dimension=RiskDimension.SYSTEM_INTEGRITY,
        state=RiskState.SAFE,
        reason="No assessment performed",
    ))
    
    # Timestamps
    assessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data_as_of: Optional[datetime] = None
    
    # Data freshness metadata
    oldest_data_age_seconds: Optional[float] = None
    all_data_fresh: bool = True
    
    # Engine metadata
    engine_version: str = "1.0.0"
    
    def get_assessment(self, dimension: RiskDimension) -> DimensionAssessment:
        """Get assessment for a specific dimension."""
        mapping = {
            RiskDimension.MARKET: self.market_assessment,
            RiskDimension.LIQUIDITY: self.liquidity_assessment,
            RiskDimension.VOLATILITY: self.volatility_assessment,
            RiskDimension.SYSTEM_INTEGRITY: self.system_integrity_assessment,
        }
        return mapping[dimension]
    
    @property
    def all_assessments(self) -> List[DimensionAssessment]:
        """Return all dimension assessments as a list."""
        return [
            self.market_assessment,
            self.liquidity_assessment,
            self.volatility_assessment,
            self.system_integrity_assessment,
        ]
    
    @property
    def dangerous_dimensions(self) -> List[RiskDimension]:
        """Return list of dimensions in DANGEROUS state."""
        return [a.dimension for a in self.all_assessments if a.is_dangerous]
    
    @property
    def warning_dimensions(self) -> List[RiskDimension]:
        """Return list of dimensions in WARNING state."""
        return [a.dimension for a in self.all_assessments if a.is_warning]
    
    @property
    def is_critical(self) -> bool:
        """Check if overall risk level is CRITICAL."""
        return self.risk_level == RiskLevel.CRITICAL
    
    @property
    def is_high_or_critical(self) -> bool:
        """Check if overall risk level is HIGH or CRITICAL."""
        return self.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "assessment_id": str(self.assessment_id),
            "total_risk_score": self.total_risk_score,
            "risk_level": self.risk_level.value,
            "assessments": {
                "market": {
                    "state": self.market_assessment.state.value,
                    "state_label": self.market_assessment.state.label,
                    "reason": self.market_assessment.reason,
                    "factors": self.market_assessment.contributing_factors,
                },
                "liquidity": {
                    "state": self.liquidity_assessment.state.value,
                    "state_label": self.liquidity_assessment.state.label,
                    "reason": self.liquidity_assessment.reason,
                    "factors": self.liquidity_assessment.contributing_factors,
                },
                "volatility": {
                    "state": self.volatility_assessment.state.value,
                    "state_label": self.volatility_assessment.state.label,
                    "reason": self.volatility_assessment.reason,
                    "factors": self.volatility_assessment.contributing_factors,
                },
                "system_integrity": {
                    "state": self.system_integrity_assessment.state.value,
                    "state_label": self.system_integrity_assessment.state.label,
                    "reason": self.system_integrity_assessment.reason,
                    "factors": self.system_integrity_assessment.contributing_factors,
                },
            },
            "assessed_at": self.assessed_at.isoformat(),
            "data_as_of": self.data_as_of.isoformat() if self.data_as_of else None,
            "oldest_data_age_seconds": self.oldest_data_age_seconds,
            "all_data_fresh": self.all_data_fresh,
            "engine_version": self.engine_version,
        }


# ============================================================
# STATE CHANGE TYPES
# ============================================================


@dataclass(frozen=True)
class RiskStateChange:
    """
    Represents a change in risk state.
    
    Used for alerting and audit trail.
    """
    
    dimension: Optional[RiskDimension]  # None for overall level change
    previous_state: Optional[RiskState]
    new_state: Optional[RiskState]
    
    previous_level: Optional[RiskLevel]  # For overall level changes
    new_level: Optional[RiskLevel]
    
    previous_total_score: Optional[int]
    new_total_score: int
    
    changed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def is_escalation(self) -> bool:
        """Check if this represents an escalation in risk."""
        if self.new_level and self.previous_level:
            return self.new_level.severity_order > self.previous_level.severity_order
        if self.new_state is not None and self.previous_state is not None:
            return int(self.new_state) > int(self.previous_state)
        return False
    
    @property
    def is_de_escalation(self) -> bool:
        """Check if this represents a de-escalation in risk."""
        if self.new_level and self.previous_level:
            return self.new_level.severity_order < self.previous_level.severity_order
        if self.new_state is not None and self.previous_state is not None:
            return int(self.new_state) < int(self.previous_state)
        return False
    
    @property
    def change_description(self) -> str:
        """Human-readable description of the change."""
        if self.dimension:
            return (
                f"{self.dimension.value} risk changed from "
                f"{self.previous_state.label if self.previous_state else 'unknown'} to "
                f"{self.new_state.label if self.new_state else 'unknown'}"
            )
        else:
            return (
                f"Overall risk level changed from "
                f"{self.previous_level.value if self.previous_level else 'unknown'} to "
                f"{self.new_level.value if self.new_level else 'unknown'} "
                f"(score: {self.previous_total_score} → {self.new_total_score})"
            )


# ============================================================
# ERROR TYPES
# ============================================================


class RiskScoringError(Exception):
    """Base exception for risk scoring errors."""
    
    def __init__(self, message: str, dimension: Optional[RiskDimension] = None) -> None:
        super().__init__(message)
        self.dimension = dimension


class InsufficientDataError(RiskScoringError):
    """
    Raised when insufficient data is available for assessment.
    
    NOTE: This should trigger DANGEROUS state for System Integrity,
    not cause the engine to fail silently.
    """
    pass


class AssessmentError(RiskScoringError):
    """Raised when an assessment cannot be completed."""
    pass
