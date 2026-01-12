"""
Parity Validation Data Models.

============================================================
INSTITUTIONAL-GRADE CRYPTO TRADING SYSTEM
Live vs Backtest Parity Validation
============================================================

PURPOSE:
--------
Defines all data structures for parity validation including:
- Validation modes
- Tolerance definitions
- Parity results
- Drift metrics
- Failure conditions

PHILOSOPHY:
-----------
"Backtest is a hypothesis, not truth.
 Live behavior is the ground truth.
 Any divergence must be explained.
 Unexplained divergence is a risk."

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ============================================================
# VALIDATION MODES
# ============================================================

class ValidationMode(Enum):
    """Parity validation execution mode."""
    SHADOW_MODE = "shadow_mode"  # Live data, no execution
    PAPER_TRADING = "paper_trading"  # Simulated execution
    LIVE_TRADING_OBSERVATION = "live_trading_observation"  # Observe live


class ParityDomain(Enum):
    """Domain of parity validation."""
    DATA = "data"
    FEATURE = "feature"
    DECISION = "decision"
    EXECUTION = "execution"
    ACCOUNTING = "accounting"


class DriftType(Enum):
    """Type of behavioral drift."""
    PARAMETER_DRIFT = "parameter_drift"
    BEHAVIOR_DRIFT = "behavior_drift"
    EXECUTION_DRIFT = "execution_drift"
    RISK_TOLERANCE_DRIFT = "risk_tolerance_drift"


class MismatchSeverity(Enum):
    """Severity of parity mismatch."""
    INFO = "info"  # Minor, within tolerance
    WARNING = "warning"  # Notable, needs monitoring
    CRITICAL = "critical"  # Severe, may require action
    FATAL = "fatal"  # Trading must stop


class MismatchCategory(Enum):
    """Category of execution mismatch."""
    EXPECTED = "expected"  # Market conditions explain it
    UNEXPECTED = "unexpected"  # Logic deviation


class FailureCondition(Enum):
    """Specific parity failure conditions."""
    TRADE_ALLOWED_LIVE_BLOCKED_BACKTEST = "trade_allowed_live_blocked_backtest"
    TRADE_BLOCKED_LIVE_ALLOWED_BACKTEST = "trade_blocked_live_allowed_backtest"
    POSITION_SIZE_DEVIATION = "position_size_deviation"
    RISK_LEVEL_MISMATCH = "risk_level_mismatch"
    UNEXPLAINED_EXECUTION_DIFFERENCE = "unexplained_execution_difference"
    DATA_INPUT_MISMATCH = "data_input_mismatch"
    FEATURE_CALCULATION_MISMATCH = "feature_calculation_mismatch"
    ENTRY_PERMISSION_MISMATCH = "entry_permission_mismatch"


class SystemReaction(Enum):
    """System reaction to parity failure."""
    LOG_ONLY = "log_only"
    ESCALATE_RISK = "escalate_risk"
    NOTIFY_TRADE_GUARD = "notify_trade_guard"
    BLOCK_TRADING = "block_trading"
    REQUIRE_MANUAL_REVIEW = "require_manual_review"


# ============================================================
# TOLERANCE DEFINITIONS
# ============================================================

@dataclass(frozen=True)
class ToleranceConfig:
    """
    Explicit tolerance thresholds for parity validation.
    
    No silent tolerance is allowed - all thresholds are explicit.
    """
    # Price tolerances
    price_absolute_tolerance: Decimal = Decimal("0.0001")  # 0.01%
    price_relative_tolerance: Decimal = Decimal("0.001")  # 0.1%
    
    # Size tolerances
    size_absolute_tolerance: Decimal = Decimal("0.00001")
    size_relative_tolerance: Decimal = Decimal("0.01")  # 1%
    
    # Timing tolerances
    timing_tolerance_seconds: float = 1.0
    
    # Feature calculation tolerances
    feature_relative_tolerance: Decimal = Decimal("0.001")  # 0.1%
    
    # Risk score tolerances
    risk_score_tolerance: Decimal = Decimal("0.05")  # 5%
    
    # Slippage tolerance
    slippage_tolerance: Decimal = Decimal("0.002")  # 0.2%
    
    def is_within_price_tolerance(
        self,
        live_price: Decimal,
        backtest_price: Decimal,
    ) -> bool:
        """Check if price difference is within tolerance."""
        if live_price == backtest_price:
            return True
        
        abs_diff = abs(live_price - backtest_price)
        if abs_diff <= self.price_absolute_tolerance:
            return True
        
        if live_price != 0:
            rel_diff = abs_diff / abs(live_price)
            return rel_diff <= self.price_relative_tolerance
        
        return False
    
    def is_within_size_tolerance(
        self,
        live_size: Decimal,
        backtest_size: Decimal,
    ) -> bool:
        """Check if size difference is within tolerance."""
        if live_size == backtest_size:
            return True
        
        abs_diff = abs(live_size - backtest_size)
        if abs_diff <= self.size_absolute_tolerance:
            return True
        
        if live_size != 0:
            rel_diff = abs_diff / abs(live_size)
            return rel_diff <= self.size_relative_tolerance
        
        return False


# ============================================================
# DATA SNAPSHOTS
# ============================================================

@dataclass
class OHLCVData:
    """OHLCV data point."""
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    symbol: str
    timeframe: str


@dataclass
class MarketSnapshot:
    """Complete market snapshot for parity comparison."""
    snapshot_id: str
    timestamp: datetime
    symbol: str
    
    # OHLCV
    ohlcv: Optional[OHLCVData] = None
    
    # Derived metrics
    volume_24h: Optional[Decimal] = None
    market_condition: Optional[str] = None
    sentiment_score: Optional[Decimal] = None
    flow_score: Optional[Decimal] = None
    aggregated_risk_level: Optional[Decimal] = None
    
    # Metadata
    source: str = ""  # "live" or "backtest"
    version: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "ohlcv": {
                "open": str(self.ohlcv.open) if self.ohlcv else None,
                "high": str(self.ohlcv.high) if self.ohlcv else None,
                "low": str(self.ohlcv.low) if self.ohlcv else None,
                "close": str(self.ohlcv.close) if self.ohlcv else None,
                "volume": str(self.ohlcv.volume) if self.ohlcv else None,
            },
            "volume_24h": str(self.volume_24h) if self.volume_24h else None,
            "market_condition": self.market_condition,
            "sentiment_score": str(self.sentiment_score) if self.sentiment_score else None,
            "flow_score": str(self.flow_score) if self.flow_score else None,
            "aggregated_risk_level": str(self.aggregated_risk_level) if self.aggregated_risk_level else None,
            "source": self.source,
        }


@dataclass
class FeatureSnapshot:
    """Feature calculation snapshot."""
    snapshot_id: str
    timestamp: datetime
    symbol: str
    
    # Calculated features
    features: Dict[str, Decimal] = field(default_factory=dict)
    
    # Metadata
    source: str = ""
    calculation_version: str = ""


@dataclass
class DecisionSnapshot:
    """Decision state snapshot."""
    snapshot_id: str
    timestamp: datetime
    cycle_id: str
    
    # Trade Guard decision
    trade_guard_decision: str = ""  # "ALLOW" or "BLOCK"
    guard_state: str = ""
    reason_codes: List[str] = field(default_factory=list)
    
    # Entry permission
    entry_permitted: bool = False
    entry_reason: str = ""
    
    # Position sizing
    position_size: Optional[Decimal] = None
    position_size_pct: Optional[Decimal] = None
    
    # Risk assessment
    risk_level: Optional[Decimal] = None
    
    # Metadata
    source: str = ""


@dataclass
class ExecutionSnapshot:
    """Execution state snapshot."""
    snapshot_id: str
    timestamp: datetime
    cycle_id: str
    
    # Order details
    order_type: str = ""
    order_side: str = ""
    order_size: Optional[Decimal] = None
    
    # Price details
    entry_price: Optional[Decimal] = None
    expected_price: Optional[Decimal] = None
    slippage: Optional[Decimal] = None
    
    # Fill behavior
    fill_ratio: Optional[Decimal] = None
    fill_time_seconds: Optional[float] = None
    
    # Fees
    fees: Optional[Decimal] = None
    fee_rate: Optional[Decimal] = None
    
    # Metadata
    source: str = ""


# ============================================================
# COMPARISON RESULTS
# ============================================================

@dataclass
class FieldMismatch:
    """Single field mismatch detail."""
    field_name: str
    live_value: Any
    backtest_value: Any
    deviation: Optional[Decimal] = None
    deviation_pct: Optional[Decimal] = None
    within_tolerance: bool = False
    tolerance_used: Optional[Decimal] = None


@dataclass
class ParityComparisonResult:
    """Result of a single parity comparison."""
    comparison_id: str
    timestamp: datetime
    domain: ParityDomain
    cycle_id: str
    
    # Overall result
    is_match: bool
    severity: MismatchSeverity = MismatchSeverity.INFO
    
    # Details
    mismatches: List[FieldMismatch] = field(default_factory=list)
    failure_conditions: List[FailureCondition] = field(default_factory=list)
    
    # Category (for execution mismatches)
    category: Optional[MismatchCategory] = None
    explanation: str = ""
    
    # Raw data
    live_snapshot: Optional[Any] = None
    backtest_snapshot: Optional[Any] = None
    
    def get_critical_mismatches(self) -> List[FieldMismatch]:
        """Get mismatches that exceeded tolerance."""
        return [m for m in self.mismatches if not m.within_tolerance]


@dataclass
class CycleParityReport:
    """Parity report for a single trading cycle."""
    report_id: str
    cycle_id: str
    timestamp: datetime
    
    # Domain results
    data_parity: Optional[ParityComparisonResult] = None
    feature_parity: Optional[ParityComparisonResult] = None
    decision_parity: Optional[ParityComparisonResult] = None
    execution_parity: Optional[ParityComparisonResult] = None
    accounting_parity: Optional[ParityComparisonResult] = None
    
    # Overall assessment
    overall_match: bool = True
    highest_severity: MismatchSeverity = MismatchSeverity.INFO
    failure_conditions: List[FailureCondition] = field(default_factory=list)
    
    # System reaction
    recommended_reaction: SystemReaction = SystemReaction.LOG_ONLY
    
    # Metadata
    validation_mode: ValidationMode = ValidationMode.SHADOW_MODE
    tolerance_config_version: str = ""
    code_version: str = ""
    config_version: str = ""
    
    def add_comparison(self, result: ParityComparisonResult) -> None:
        """Add a comparison result to the report."""
        if result.domain == ParityDomain.DATA:
            self.data_parity = result
        elif result.domain == ParityDomain.FEATURE:
            self.feature_parity = result
        elif result.domain == ParityDomain.DECISION:
            self.decision_parity = result
        elif result.domain == ParityDomain.EXECUTION:
            self.execution_parity = result
        elif result.domain == ParityDomain.ACCOUNTING:
            self.accounting_parity = result
        
        # Update overall assessment
        if not result.is_match:
            self.overall_match = False
            self.failure_conditions.extend(result.failure_conditions)
            
            if result.severity.value > self.highest_severity.value:
                self.highest_severity = result.severity


# ============================================================
# DRIFT METRICS
# ============================================================

@dataclass
class DriftMetric:
    """Quantified drift measurement."""
    drift_id: str
    drift_type: DriftType
    measured_at: datetime
    
    # Measurement
    metric_name: str
    current_value: Decimal
    baseline_value: Decimal
    deviation: Decimal
    deviation_pct: Decimal
    
    # Trend
    trend_direction: str = ""  # "increasing", "decreasing", "stable"
    measurement_window: str = ""  # e.g., "1h", "24h"
    sample_count: int = 0
    
    # Significance
    is_significant: bool = False
    significance_threshold: Optional[Decimal] = None


@dataclass
class DriftReport:
    """Comprehensive drift analysis report."""
    report_id: str
    generated_at: datetime
    analysis_window_start: datetime
    analysis_window_end: datetime
    
    # Drift metrics by type
    parameter_drifts: List[DriftMetric] = field(default_factory=list)
    behavior_drifts: List[DriftMetric] = field(default_factory=list)
    execution_drifts: List[DriftMetric] = field(default_factory=list)
    risk_tolerance_drifts: List[DriftMetric] = field(default_factory=list)
    
    # Summary statistics
    total_drift_count: int = 0
    significant_drift_count: int = 0
    
    # Root cause hints
    root_cause_hints: List[str] = field(default_factory=list)


# ============================================================
# DAILY SUMMARY
# ============================================================

@dataclass
class DailyParitySummary:
    """Daily parity validation summary."""
    summary_id: str
    date: datetime
    
    # Counts
    total_cycles: int = 0
    matched_cycles: int = 0
    mismatched_cycles: int = 0
    
    # Severity breakdown
    info_count: int = 0
    warning_count: int = 0
    critical_count: int = 0
    fatal_count: int = 0
    
    # Failure condition counts
    failure_condition_counts: Dict[str, int] = field(default_factory=dict)
    
    # Domain breakdown
    domain_mismatch_counts: Dict[str, int] = field(default_factory=dict)
    
    # Match rate
    @property
    def match_rate(self) -> float:
        if self.total_cycles == 0:
            return 100.0
        return (self.matched_cycles / self.total_cycles) * 100
    
    # Drift summary
    drift_detected: bool = False
    drift_metrics: List[DriftMetric] = field(default_factory=list)
    
    # System reactions taken
    reactions_taken: List[SystemReaction] = field(default_factory=list)


# ============================================================
# AUDIT RECORD
# ============================================================

@dataclass
class ParityAuditRecord:
    """Audit record for parity validation."""
    audit_id: str
    timestamp: datetime
    
    # Validation context
    cycle_id: str
    validation_mode: ValidationMode
    
    # Code and config versions
    code_version: str
    code_commit_hash: str
    config_version: str
    config_hash: str
    
    # Tolerance config
    tolerance_config: ToleranceConfig = field(default_factory=ToleranceConfig)
    
    # Results
    parity_report: Optional[CycleParityReport] = None
    
    # Reproducibility
    input_data_hash: str = ""
    random_seed: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "audit_id": self.audit_id,
            "timestamp": self.timestamp.isoformat(),
            "cycle_id": self.cycle_id,
            "validation_mode": self.validation_mode.value,
            "code_version": self.code_version,
            "code_commit_hash": self.code_commit_hash,
            "config_version": self.config_version,
            "config_hash": self.config_hash,
            "input_data_hash": self.input_data_hash,
        }
