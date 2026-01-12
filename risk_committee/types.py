"""
Risk Committee - Type Definitions.

============================================================
INSTITUTIONAL RISK REVIEW COMMITTEE
============================================================
All type definitions for the committee simulation.

Each reviewer produces an explicit verdict with reasoning.
The committee aggregates verdicts into a final decision.

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import uuid4


# ============================================================
# REVIEWER STATUS ENUMS
# ============================================================

class DataIntegrityStatus(str, Enum):
    """
    Data Integrity Reviewer output.
    
    Evaluates:
    - Price data freshness
    - Mock/placeholder detection
    - Missing ingestion cycles
    - Data source health
    """
    
    PASS = "PASS"
    """All data integrity checks passed."""
    
    WARN = "WARN"
    """Minor data issues detected, proceed with caution."""
    
    FAIL = "FAIL"
    """Critical data integrity failure. Cannot trust data."""


class MarketRiskLevel(str, Enum):
    """
    Market Risk Reviewer output.
    
    Evaluates:
    - Current volatility regime
    - Liquidity conditions
    - Abnormal flow/sentiment
    - Market state consistency
    """
    
    LOW = "LOW"
    """Market conditions favorable for trading."""
    
    MEDIUM = "MEDIUM"
    """Elevated risk, proceed with reduced exposure."""
    
    HIGH = "HIGH"
    """Extreme risk conditions. Recommend halt."""


class ExecutionQuality(str, Enum):
    """
    Execution Quality Reviewer output.
    
    Evaluates:
    - Slippage vs expected
    - Latency stability
    - Fill consistency
    - Execution anomalies
    """
    
    GOOD = "GOOD"
    """Execution quality within acceptable bounds."""
    
    DEGRADED = "DEGRADED"
    """Execution quality degraded, monitor closely."""
    
    UNACCEPTABLE = "UNACCEPTABLE"
    """Execution quality unacceptable. Halt trading."""


class CapitalSafetyStatus(str, Enum):
    """
    Capital Preservation Reviewer output.
    
    Evaluates:
    - Max drawdown status
    - Risk budget adherence
    - Rule override attempts
    - Position sizing consistency
    """
    
    SAFE = "SAFE"
    """Capital protection rules respected."""
    
    WARNING = "WARNING"
    """Approaching limits, reduce exposure."""
    
    BREACH = "BREACH"
    """Capital safety rules breached. Halt immediately."""


class CommitteeDecision(str, Enum):
    """
    Final committee decision.
    
    Decision Logic:
    - If ANY = FAIL/BREACH/UNACCEPTABLE → BLOCK
    - If 2+ WARNINGS/WARN/DEGRADED/MEDIUM → HOLD
    - If ALL PASS/SAFE/GOOD/LOW → APPROVE
    """
    
    APPROVE = "APPROVE"
    """Allow continuation of current trading mode."""
    
    HOLD = "HOLD"
    """Freeze new trades, allow monitoring only."""
    
    BLOCK = "BLOCK"
    """Trigger System Risk Controller global halt."""


class ReviewerType(str, Enum):
    """Types of committee reviewers."""
    
    DATA_INTEGRITY = "DATA_INTEGRITY"
    MARKET_RISK = "MARKET_RISK"
    EXECUTION_QUALITY = "EXECUTION_QUALITY"
    CAPITAL_PRESERVATION = "CAPITAL_PRESERVATION"


# ============================================================
# REVIEWER VERDICTS
# ============================================================

@dataclass
class ReviewerVerdict:
    """
    Base verdict from any reviewer.
    
    Every verdict must be explainable with:
    - Clear status
    - Reasoning
    - Evidence from data
    """
    
    reviewer_type: ReviewerType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Status (actual enum value stored as string for JSON serialization)
    status: str = ""
    
    # Reasoning
    reason: str = ""
    details: List[str] = field(default_factory=list)
    
    # Evidence
    evidence: Dict[str, Any] = field(default_factory=dict)
    
    # Metrics
    metrics: Dict[str, float] = field(default_factory=dict)
    
    def is_critical(self) -> bool:
        """Check if verdict indicates critical failure."""
        critical_statuses = {"FAIL", "BREACH", "UNACCEPTABLE", "HIGH"}
        return self.status in critical_statuses
    
    def is_warning(self) -> bool:
        """Check if verdict indicates warning condition."""
        warning_statuses = {"WARN", "WARNING", "DEGRADED", "MEDIUM"}
        return self.status in warning_statuses
    
    def is_ok(self) -> bool:
        """Check if verdict indicates acceptable condition."""
        ok_statuses = {"PASS", "SAFE", "GOOD", "LOW"}
        return self.status in ok_statuses


# ============================================================
# INDIVIDUAL REVIEWER REPORTS
# ============================================================

@dataclass
class DataIntegrityReport:
    """
    Data Integrity Reviewer full report.
    """
    
    verdict: ReviewerVerdict
    
    # Specific checks
    prices_realtime: bool = False
    mock_detected: bool = False
    data_freshness_ok: bool = False
    missing_cycles: int = 0
    
    # Data source status
    source_statuses: Dict[str, str] = field(default_factory=dict)
    
    # Freshness metrics
    oldest_data_age_seconds: float = 0.0
    max_allowed_age_seconds: float = 7200.0  # 2 hours default
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "verdict": {
                "reviewer_type": self.verdict.reviewer_type.value,
                "status": self.verdict.status,
                "reason": self.verdict.reason,
                "details": self.verdict.details,
                "evidence": self.verdict.evidence,
                "metrics": self.verdict.metrics,
                "timestamp": self.verdict.timestamp.isoformat(),
            },
            "prices_realtime": self.prices_realtime,
            "mock_detected": self.mock_detected,
            "data_freshness_ok": self.data_freshness_ok,
            "missing_cycles": self.missing_cycles,
            "source_statuses": self.source_statuses,
            "oldest_data_age_seconds": self.oldest_data_age_seconds,
            "max_allowed_age_seconds": self.max_allowed_age_seconds,
        }


@dataclass
class MarketRiskReport:
    """
    Market Risk Reviewer full report.
    """
    
    verdict: ReviewerVerdict
    
    # Volatility assessment
    volatility_regime: str = "UNKNOWN"  # LOW, NORMAL, HIGH, EXTREME
    volatility_percentile: float = 0.0
    
    # Liquidity assessment
    liquidity_condition: str = "UNKNOWN"  # GOOD, MODERATE, THIN, DRY
    
    # Flow/sentiment
    flow_risk: str = "NEUTRAL"  # BULLISH, NEUTRAL, BEARISH, EXTREME
    sentiment_risk: str = "NEUTRAL"
    
    # Market state consistency
    state_consistency_score: float = 0.0  # 0-100
    cycles_analyzed: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "verdict": {
                "reviewer_type": self.verdict.reviewer_type.value,
                "status": self.verdict.status,
                "reason": self.verdict.reason,
                "details": self.verdict.details,
                "evidence": self.verdict.evidence,
                "metrics": self.verdict.metrics,
                "timestamp": self.verdict.timestamp.isoformat(),
            },
            "volatility_regime": self.volatility_regime,
            "volatility_percentile": self.volatility_percentile,
            "liquidity_condition": self.liquidity_condition,
            "flow_risk": self.flow_risk,
            "sentiment_risk": self.sentiment_risk,
            "state_consistency_score": self.state_consistency_score,
            "cycles_analyzed": self.cycles_analyzed,
        }


@dataclass
class ExecutionQualityReport:
    """
    Execution Quality Reviewer full report.
    """
    
    verdict: ReviewerVerdict
    
    # Slippage metrics
    avg_slippage_bps: float = 0.0
    max_slippage_bps: float = 0.0
    slippage_threshold_bps: float = 50.0  # 0.5%
    
    # Latency metrics
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    latency_stable: bool = True
    
    # Fill metrics
    fill_rate: float = 100.0  # percentage
    partial_fills: int = 0
    rejected_orders: int = 0
    
    # Anomalies
    anomalies_detected: List[str] = field(default_factory=list)
    
    # Sample size
    orders_analyzed: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "verdict": {
                "reviewer_type": self.verdict.reviewer_type.value,
                "status": self.verdict.status,
                "reason": self.verdict.reason,
                "details": self.verdict.details,
                "evidence": self.verdict.evidence,
                "metrics": self.verdict.metrics,
                "timestamp": self.verdict.timestamp.isoformat(),
            },
            "avg_slippage_bps": self.avg_slippage_bps,
            "max_slippage_bps": self.max_slippage_bps,
            "slippage_threshold_bps": self.slippage_threshold_bps,
            "avg_latency_ms": self.avg_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "latency_stable": self.latency_stable,
            "fill_rate": self.fill_rate,
            "partial_fills": self.partial_fills,
            "rejected_orders": self.rejected_orders,
            "anomalies_detected": self.anomalies_detected,
            "orders_analyzed": self.orders_analyzed,
        }


@dataclass
class CapitalSafetyReport:
    """
    Capital Preservation Reviewer full report.
    """
    
    verdict: ReviewerVerdict
    
    # Drawdown status
    current_drawdown_pct: float = 0.0
    max_allowed_drawdown_pct: float = 10.0
    drawdown_breached: bool = False
    
    # Risk budget
    risk_budget_used_pct: float = 0.0
    risk_budget_remaining_pct: float = 100.0
    risk_budget_respected: bool = True
    
    # Rule compliance
    override_attempts: int = 0
    rule_violations: List[str] = field(default_factory=list)
    
    # Position sizing
    position_sizing_consistent: bool = True
    max_position_size_pct: float = 0.0
    current_exposure_pct: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "verdict": {
                "reviewer_type": self.verdict.reviewer_type.value,
                "status": self.verdict.status,
                "reason": self.verdict.reason,
                "details": self.verdict.details,
                "evidence": self.verdict.evidence,
                "metrics": self.verdict.metrics,
                "timestamp": self.verdict.timestamp.isoformat(),
            },
            "current_drawdown_pct": self.current_drawdown_pct,
            "max_allowed_drawdown_pct": self.max_allowed_drawdown_pct,
            "drawdown_breached": self.drawdown_breached,
            "risk_budget_used_pct": self.risk_budget_used_pct,
            "risk_budget_remaining_pct": self.risk_budget_remaining_pct,
            "risk_budget_respected": self.risk_budget_respected,
            "override_attempts": self.override_attempts,
            "rule_violations": self.rule_violations,
            "position_sizing_consistent": self.position_sizing_consistent,
            "max_position_size_pct": self.max_position_size_pct,
            "current_exposure_pct": self.current_exposure_pct,
        }


# ============================================================
# COMMITTEE REPORT
# ============================================================

@dataclass
class CommitteeReport:
    """
    Full Risk Committee Report.
    
    Aggregates all reviewer verdicts into final decision.
    Must be fully explainable and auditable.
    """
    
    # Identification
    report_id: str = field(default_factory=lambda: str(uuid4()))
    correlation_id: str = ""
    cycle_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Individual reports
    data_integrity: Optional[DataIntegrityReport] = None
    market_risk: Optional[MarketRiskReport] = None
    execution_quality: Optional[ExecutionQualityReport] = None
    capital_safety: Optional[CapitalSafetyReport] = None
    
    # Committee decision
    decision: CommitteeDecision = CommitteeDecision.BLOCK  # Default safe
    decision_reason: str = ""
    decision_details: List[str] = field(default_factory=list)
    
    # Vote summary
    critical_count: int = 0
    warning_count: int = 0
    ok_count: int = 0
    
    # Processing time
    review_duration_ms: float = 0.0
    
    def get_all_verdicts(self) -> List[ReviewerVerdict]:
        """Get list of all reviewer verdicts."""
        verdicts = []
        if self.data_integrity:
            verdicts.append(self.data_integrity.verdict)
        if self.market_risk:
            verdicts.append(self.market_risk.verdict)
        if self.execution_quality:
            verdicts.append(self.execution_quality.verdict)
        if self.capital_safety:
            verdicts.append(self.capital_safety.verdict)
        return verdicts
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "report_id": self.report_id,
            "correlation_id": self.correlation_id,
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp.isoformat(),
            "data_integrity": self.data_integrity.to_dict() if self.data_integrity else None,
            "market_risk": self.market_risk.to_dict() if self.market_risk else None,
            "execution_quality": self.execution_quality.to_dict() if self.execution_quality else None,
            "capital_safety": self.capital_safety.to_dict() if self.capital_safety else None,
            "decision": self.decision.value,
            "decision_reason": self.decision_reason,
            "decision_details": self.decision_details,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "ok_count": self.ok_count,
            "review_duration_ms": self.review_duration_ms,
        }
    
    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"=== RISK COMMITTEE REPORT ===",
            f"Report ID: {self.report_id[:8]}",
            f"Time: {self.timestamp.isoformat()}",
            f"",
            f"DECISION: {self.decision.value}",
            f"Reason: {self.decision_reason}",
            f"",
            f"Vote Summary:",
            f"  Critical: {self.critical_count}",
            f"  Warning:  {self.warning_count}",
            f"  OK:       {self.ok_count}",
            f"",
        ]
        
        if self.data_integrity:
            lines.append(f"Data Integrity: {self.data_integrity.verdict.status}")
        if self.market_risk:
            lines.append(f"Market Risk: {self.market_risk.verdict.status}")
        if self.execution_quality:
            lines.append(f"Execution Quality: {self.execution_quality.verdict.status}")
        if self.capital_safety:
            lines.append(f"Capital Safety: {self.capital_safety.verdict.status}")
        
        if self.decision_details:
            lines.append("")
            lines.append("Details:")
            for detail in self.decision_details:
                lines.append(f"  - {detail}")
        
        return "\n".join(lines)
