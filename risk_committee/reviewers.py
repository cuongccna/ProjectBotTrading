"""
Risk Committee - Individual Reviewers.

============================================================
COMMITTEE COMPOSITION
============================================================
1. Data Integrity Reviewer - Validates data quality
2. Market Risk Reviewer - Assesses market conditions
3. Execution Quality Reviewer - Evaluates execution performance
4. Capital Preservation Reviewer - Checks capital safety

Each reviewer operates INDEPENDENTLY and produces an EXPLICIT verdict.

============================================================
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from database.models import (
    MarketData, RiskState, ExecutionRecord,
    SystemMonitoring, MarketState, PositionSizing,
)
from .types import (
    ReviewerType,
    ReviewerVerdict,
    DataIntegrityStatus,
    MarketRiskLevel,
    ExecutionQuality,
    CapitalSafetyStatus,
    DataIntegrityReport,
    MarketRiskReport,
    ExecutionQualityReport,
    CapitalSafetyReport,
)


logger = logging.getLogger(__name__)


# ============================================================
# BASE REVIEWER
# ============================================================

class BaseReviewer(ABC):
    """
    Base class for all committee reviewers.
    
    Each reviewer:
    - Reads data (never writes)
    - Produces an explicit verdict
    - Provides detailed reasoning
    """
    
    def __init__(self, session: Session):
        """
        Initialize reviewer with database session.
        
        Args:
            session: SQLAlchemy session (read-only access)
        """
        self._session = session
        self._logger = logging.getLogger(f"risk_committee.{self.reviewer_type.value.lower()}")
    
    @property
    @abstractmethod
    def reviewer_type(self) -> ReviewerType:
        """Return the reviewer type."""
        pass
    
    @abstractmethod
    def review(self, correlation_id: str) -> Any:
        """
        Perform review and return report.
        
        Args:
            correlation_id: Current cycle correlation ID
            
        Returns:
            Specific report type for this reviewer
        """
        pass
    
    def _create_verdict(
        self,
        status: str,
        reason: str,
        details: List[str] = None,
        evidence: Dict[str, Any] = None,
        metrics: Dict[str, float] = None,
    ) -> ReviewerVerdict:
        """Create a reviewer verdict."""
        return ReviewerVerdict(
            reviewer_type=self.reviewer_type,
            status=status,
            reason=reason,
            details=details or [],
            evidence=evidence or {},
            metrics=metrics or {},
        )


# ============================================================
# DATA INTEGRITY REVIEWER
# ============================================================

class DataIntegrityReviewer(BaseReviewer):
    """
    Evaluates data integrity:
    - Are prices real-time?
    - Any mock/placeholder detected?
    - Data freshness within tolerance?
    - Any missing ingestion cycles?
    """
    
    def __init__(
        self,
        session: Session,
        max_data_age_seconds: float = 7200.0,  # 2 hours
        expected_sources: List[str] = None,
    ):
        """
        Initialize Data Integrity Reviewer.
        
        Args:
            session: Database session
            max_data_age_seconds: Maximum allowed data age
            expected_sources: List of expected data sources
        """
        super().__init__(session)
        self._max_data_age = max_data_age_seconds
        self._expected_sources = expected_sources or ["coingecko", "binance"]
    
    @property
    def reviewer_type(self) -> ReviewerType:
        return ReviewerType.DATA_INTEGRITY
    
    def review(self, correlation_id: str) -> DataIntegrityReport:
        """Perform data integrity review."""
        self._logger.info(f"Starting data integrity review | correlation_id={correlation_id}")
        
        now = datetime.utcnow()
        details = []
        evidence = {}
        metrics = {}
        
        # 1. Check price data freshness
        prices_realtime, oldest_age, source_freshness = self._check_price_freshness(now)
        evidence["source_freshness"] = source_freshness
        metrics["oldest_data_age_seconds"] = oldest_age
        
        # 2. Check for mock/placeholder data
        mock_detected = self._check_for_mocks()
        evidence["mock_check"] = {"detected": mock_detected}
        
        # 3. Check data freshness overall
        data_freshness_ok = oldest_age <= self._max_data_age
        
        # 4. Check for missing ingestion cycles
        missing_cycles = self._count_missing_cycles(now)
        metrics["missing_cycles"] = float(missing_cycles)
        
        # 5. Get source statuses
        source_statuses = self._get_source_statuses()
        evidence["source_statuses"] = source_statuses
        
        # Determine status
        if mock_detected:
            status = DataIntegrityStatus.FAIL
            reason = "MOCK DATA DETECTED - Cannot trust data source"
            details.append("Mock or placeholder data detected in system")
        elif missing_cycles > 3:
            status = DataIntegrityStatus.FAIL
            reason = f"CRITICAL: {missing_cycles} missing ingestion cycles"
            details.append(f"Too many missing cycles: {missing_cycles}")
        elif not prices_realtime:
            status = DataIntegrityStatus.FAIL
            reason = f"Price data too old: {oldest_age:.0f}s (max: {self._max_data_age}s)"
            details.append("Price data exceeds maximum allowed age")
        elif not data_freshness_ok:
            status = DataIntegrityStatus.WARN
            reason = f"Data freshness degraded: {oldest_age:.0f}s"
            details.append("Data freshness approaching threshold")
        elif missing_cycles > 0:
            status = DataIntegrityStatus.WARN
            reason = f"Minor data gaps: {missing_cycles} missing cycles"
            details.append(f"Some missing ingestion cycles: {missing_cycles}")
        else:
            status = DataIntegrityStatus.PASS
            reason = "All data integrity checks passed"
            details.append(f"Data age: {oldest_age:.0f}s (within {self._max_data_age}s)")
            details.append("No mock data detected")
            details.append("All sources healthy")
        
        verdict = self._create_verdict(
            status=status.value,
            reason=reason,
            details=details,
            evidence=evidence,
            metrics=metrics,
        )
        
        self._logger.info(
            f"Data integrity review complete | status={status.value} | "
            f"age={oldest_age:.0f}s | mock={mock_detected}"
        )
        
        return DataIntegrityReport(
            verdict=verdict,
            prices_realtime=prices_realtime,
            mock_detected=mock_detected,
            data_freshness_ok=data_freshness_ok,
            missing_cycles=missing_cycles,
            source_statuses=source_statuses,
            oldest_data_age_seconds=oldest_age,
            max_allowed_age_seconds=self._max_data_age,
        )
    
    def _check_price_freshness(
        self, now: datetime
    ) -> Tuple[bool, float, Dict[str, float]]:
        """Check price data freshness by source."""
        source_freshness = {}
        oldest_age = 0.0
        
        # Get latest data per exchange
        for source in self._expected_sources:
            latest = (
                self._session.query(func.max(MarketData.created_at))
                .filter(MarketData.exchange.ilike(f"%{source}%"))
                .scalar()
            )
            
            if latest:
                age = (now - latest).total_seconds()
                source_freshness[source] = age
                oldest_age = max(oldest_age, age)
            else:
                source_freshness[source] = float("inf")
                oldest_age = float("inf")
        
        prices_realtime = oldest_age <= self._max_data_age
        return prices_realtime, oldest_age, source_freshness
    
    def _check_for_mocks(self) -> bool:
        """Check for mock/placeholder data in system."""
        # Check for mock markers in recent data
        recent_cutoff = datetime.utcnow() - timedelta(hours=24)
        
        # Look for "mock", "test", "placeholder" in source_module
        mock_count = (
            self._session.query(func.count(MarketData.id))
            .filter(MarketData.created_at >= recent_cutoff)
            .filter(
                MarketData.source_module.ilike("%mock%") |
                MarketData.source_module.ilike("%test%") |
                MarketData.source_module.ilike("%placeholder%") |
                MarketData.source_module.ilike("%fake%")
            )
            .scalar()
        )
        
        return mock_count > 0
    
    def _count_missing_cycles(self, now: datetime) -> int:
        """Count missing ingestion cycles in last 24 hours."""
        # Expected: 1 cycle per hour
        expected_cycles = 24
        
        # Count actual cycles
        actual_cycles = (
            self._session.query(
                func.count(func.distinct(MarketData.correlation_id))
            )
            .filter(MarketData.created_at >= now - timedelta(hours=24))
            .scalar()
        )
        
        missing = max(0, expected_cycles - (actual_cycles or 0))
        return missing
    
    def _get_source_statuses(self) -> Dict[str, str]:
        """Get status for each data source."""
        statuses = {}
        now = datetime.utcnow()
        
        for source in self._expected_sources:
            latest = (
                self._session.query(func.max(MarketData.created_at))
                .filter(MarketData.exchange.ilike(f"%{source}%"))
                .scalar()
            )
            
            if not latest:
                statuses[source] = "MISSING"
            elif (now - latest).total_seconds() > self._max_data_age:
                statuses[source] = "STALE"
            else:
                statuses[source] = "OK"
        
        return statuses


# ============================================================
# MARKET RISK REVIEWER
# ============================================================

class MarketRiskReviewer(BaseReviewer):
    """
    Evaluates market risk:
    - Current volatility regime
    - Liquidity conditions
    - Abnormal flow/sentiment
    - Market state consistency
    """
    
    def __init__(
        self,
        session: Session,
        high_volatility_threshold: float = 80.0,
        consistency_threshold: float = 70.0,
    ):
        """
        Initialize Market Risk Reviewer.
        
        Args:
            session: Database session
            high_volatility_threshold: Percentile for high volatility
            consistency_threshold: Minimum consistency score
        """
        super().__init__(session)
        self._high_vol_threshold = high_volatility_threshold
        self._consistency_threshold = consistency_threshold
    
    @property
    def reviewer_type(self) -> ReviewerType:
        return ReviewerType.MARKET_RISK
    
    def review(self, correlation_id: str) -> MarketRiskReport:
        """Perform market risk review."""
        self._logger.info(f"Starting market risk review | correlation_id={correlation_id}")
        
        details = []
        evidence = {}
        metrics = {}
        
        # 1. Assess volatility regime
        volatility_regime, vol_percentile = self._assess_volatility()
        metrics["volatility_percentile"] = vol_percentile
        evidence["volatility"] = {"regime": volatility_regime, "percentile": vol_percentile}
        
        # 2. Assess liquidity conditions
        liquidity_condition = self._assess_liquidity()
        evidence["liquidity"] = {"condition": liquidity_condition}
        
        # 3. Assess flow/sentiment risk
        flow_risk = self._assess_flow_risk()
        sentiment_risk = self._assess_sentiment_risk()
        evidence["flow_sentiment"] = {"flow": flow_risk, "sentiment": sentiment_risk}
        
        # 4. Check market state consistency
        consistency_score, cycles_analyzed = self._check_state_consistency()
        metrics["state_consistency_score"] = consistency_score
        metrics["cycles_analyzed"] = float(cycles_analyzed)
        
        # Determine status
        critical_conditions = []
        warning_conditions = []
        
        if volatility_regime == "EXTREME":
            critical_conditions.append("EXTREME volatility detected")
        elif volatility_regime == "HIGH":
            warning_conditions.append("HIGH volatility detected")
        
        if liquidity_condition == "DRY":
            critical_conditions.append("Liquidity is DRY")
        elif liquidity_condition == "THIN":
            warning_conditions.append("Liquidity is THIN")
        
        if flow_risk == "EXTREME" or sentiment_risk == "EXTREME":
            critical_conditions.append("EXTREME flow/sentiment risk")
        
        if consistency_score < 50:
            critical_conditions.append(f"Low state consistency: {consistency_score:.0f}%")
        elif consistency_score < self._consistency_threshold:
            warning_conditions.append(f"Degraded state consistency: {consistency_score:.0f}%")
        
        # Final status
        if critical_conditions:
            status = MarketRiskLevel.HIGH
            reason = f"CRITICAL: {'; '.join(critical_conditions)}"
            details.extend(critical_conditions)
        elif warning_conditions:
            status = MarketRiskLevel.MEDIUM
            reason = f"WARNING: {'; '.join(warning_conditions)}"
            details.extend(warning_conditions)
        else:
            status = MarketRiskLevel.LOW
            reason = "Market conditions favorable"
            details.append(f"Volatility: {volatility_regime}")
            details.append(f"Liquidity: {liquidity_condition}")
            details.append(f"Consistency: {consistency_score:.0f}%")
        
        verdict = self._create_verdict(
            status=status.value,
            reason=reason,
            details=details,
            evidence=evidence,
            metrics=metrics,
        )
        
        self._logger.info(
            f"Market risk review complete | status={status.value} | "
            f"volatility={volatility_regime} | liquidity={liquidity_condition}"
        )
        
        return MarketRiskReport(
            verdict=verdict,
            volatility_regime=volatility_regime,
            volatility_percentile=vol_percentile,
            liquidity_condition=liquidity_condition,
            flow_risk=flow_risk,
            sentiment_risk=sentiment_risk,
            state_consistency_score=consistency_score,
            cycles_analyzed=cycles_analyzed,
        )
    
    def _assess_volatility(self) -> Tuple[str, float]:
        """Assess current volatility regime."""
        # Get recent market states
        recent = (
            self._session.query(MarketState)
            .order_by(desc(MarketState.created_at))
            .limit(10)
            .all()
        )
        
        if not recent:
            return "UNKNOWN", 50.0
        
        # Calculate volatility percentile from available data
        latest = recent[0]
        
        # Try to get volatility from regime or components
        regime = getattr(latest, "volatility_regime", None)
        if regime:
            regime_map = {
                "low": ("LOW", 20.0),
                "normal": ("NORMAL", 50.0),
                "high": ("HIGH", 80.0),
                "extreme": ("EXTREME", 95.0),
            }
            return regime_map.get(str(regime).lower(), ("NORMAL", 50.0))
        
        # Default based on risk scores
        risk_score = getattr(latest, "risk_score", 50.0)
        if risk_score is None:
            risk_score = 50.0
        
        if risk_score >= 80:
            return "EXTREME", 95.0
        elif risk_score >= 60:
            return "HIGH", 80.0
        elif risk_score >= 40:
            return "NORMAL", 50.0
        else:
            return "LOW", 20.0
    
    def _assess_liquidity(self) -> str:
        """Assess current liquidity conditions."""
        # Get recent market data for volume analysis
        recent = (
            self._session.query(MarketData)
            .order_by(desc(MarketData.created_at))
            .limit(100)
            .all()
        )
        
        if not recent:
            return "UNKNOWN"
        
        # Calculate average volume
        volumes = [m.volume for m in recent if m.volume]
        if not volumes:
            return "UNKNOWN"
        
        avg_volume = sum(volumes) / len(volumes)
        recent_volume = volumes[0] if volumes else 0
        
        # Compare recent vs average
        if recent_volume < avg_volume * 0.3:
            return "DRY"
        elif recent_volume < avg_volume * 0.6:
            return "THIN"
        elif recent_volume < avg_volume * 0.9:
            return "MODERATE"
        else:
            return "GOOD"
    
    def _assess_flow_risk(self) -> str:
        """Assess flow risk from recent data."""
        # Get latest risk state
        latest = (
            self._session.query(RiskState)
            .order_by(desc(RiskState.created_at))
            .first()
        )
        
        if not latest:
            return "NEUTRAL"
        
        # Check flow score
        flow_score = getattr(latest, "flow_score", None)
        if flow_score is None:
            return "NEUTRAL"
        
        if flow_score <= 20 or flow_score >= 80:
            return "EXTREME"
        elif flow_score <= 35 or flow_score >= 65:
            return "BEARISH" if flow_score < 50 else "BULLISH"
        else:
            return "NEUTRAL"
    
    def _assess_sentiment_risk(self) -> str:
        """Assess sentiment risk from recent data."""
        latest = (
            self._session.query(RiskState)
            .order_by(desc(RiskState.created_at))
            .first()
        )
        
        if not latest:
            return "NEUTRAL"
        
        sentiment_score = getattr(latest, "sentiment_score", None)
        if sentiment_score is None:
            return "NEUTRAL"
        
        if sentiment_score <= 20 or sentiment_score >= 80:
            return "EXTREME"
        elif sentiment_score <= 35 or sentiment_score >= 65:
            return "BEARISH" if sentiment_score < 50 else "BULLISH"
        else:
            return "NEUTRAL"
    
    def _check_state_consistency(self) -> Tuple[float, int]:
        """Check market state consistency over recent cycles."""
        # Get recent market states
        recent = (
            self._session.query(MarketState)
            .order_by(desc(MarketState.created_at))
            .limit(24)  # Last 24 hours worth
            .all()
        )
        
        if len(recent) < 2:
            return 100.0, len(recent)
        
        # Calculate consistency based on regime stability
        regime_changes = 0
        for i in range(1, len(recent)):
            curr = getattr(recent[i-1], "volatility_regime", "unknown")
            prev = getattr(recent[i], "volatility_regime", "unknown")
            if curr != prev:
                regime_changes += 1
        
        # Consistency score: fewer changes = higher consistency
        max_changes = len(recent) - 1
        consistency = 100.0 * (1 - regime_changes / max_changes) if max_changes > 0 else 100.0
        
        return consistency, len(recent)


# ============================================================
# EXECUTION QUALITY REVIEWER
# ============================================================

class ExecutionQualityReviewer(BaseReviewer):
    """
    Evaluates execution quality:
    - Slippage vs expected
    - Latency stability
    - Fill consistency
    - Execution anomalies
    """
    
    def __init__(
        self,
        session: Session,
        max_slippage_bps: float = 50.0,  # 0.5%
        max_latency_ms: float = 5000.0,  # 5 seconds
        min_fill_rate: float = 95.0,  # 95%
    ):
        """
        Initialize Execution Quality Reviewer.
        
        Args:
            session: Database session
            max_slippage_bps: Maximum acceptable slippage in basis points
            max_latency_ms: Maximum acceptable latency in milliseconds
            min_fill_rate: Minimum acceptable fill rate percentage
        """
        super().__init__(session)
        self._max_slippage = max_slippage_bps
        self._max_latency = max_latency_ms
        self._min_fill_rate = min_fill_rate
    
    @property
    def reviewer_type(self) -> ReviewerType:
        return ReviewerType.EXECUTION_QUALITY
    
    def review(self, correlation_id: str) -> ExecutionQualityReport:
        """Perform execution quality review."""
        self._logger.info(f"Starting execution quality review | correlation_id={correlation_id}")
        
        details = []
        evidence = {}
        metrics = {}
        anomalies = []
        
        # Get recent executions
        lookback = datetime.utcnow() - timedelta(hours=24)
        executions = (
            self._session.query(ExecutionRecord)
            .filter(ExecutionRecord.created_at >= lookback)
            .order_by(desc(ExecutionRecord.created_at))
            .all()
        )
        
        orders_analyzed = len(executions)
        metrics["orders_analyzed"] = float(orders_analyzed)
        
        if orders_analyzed == 0:
            # No executions to analyze - this is OK
            verdict = self._create_verdict(
                status=ExecutionQuality.GOOD.value,
                reason="No recent executions to analyze",
                details=["No trading activity in last 24 hours"],
                evidence={"orders_analyzed": 0},
                metrics=metrics,
            )
            
            return ExecutionQualityReport(
                verdict=verdict,
                orders_analyzed=0,
            )
        
        # 1. Analyze slippage
        slippage_values = [
            e.slippage_percent * 100 for e in executions 
            if e.slippage_percent is not None
        ]
        
        avg_slippage = sum(slippage_values) / len(slippage_values) if slippage_values else 0
        max_slippage = max(slippage_values) if slippage_values else 0
        metrics["avg_slippage_bps"] = avg_slippage
        metrics["max_slippage_bps"] = max_slippage
        
        if max_slippage > self._max_slippage * 2:
            anomalies.append(f"Extreme slippage: {max_slippage:.1f} bps")
        
        # 2. Analyze latency
        latency_values = [e.latency_ms for e in executions if e.latency_ms is not None]
        
        avg_latency = sum(latency_values) / len(latency_values) if latency_values else 0
        sorted_latencies = sorted(latency_values)
        p99_latency = sorted_latencies[int(len(sorted_latencies) * 0.99)] if latency_values else 0
        
        metrics["avg_latency_ms"] = avg_latency
        metrics["p99_latency_ms"] = p99_latency
        
        latency_stable = p99_latency <= self._max_latency
        
        if p99_latency > self._max_latency:
            anomalies.append(f"High latency: p99={p99_latency:.0f}ms")
        
        # 3. Analyze fill rate
        filled = sum(1 for e in executions if e.status == "filled")
        partial = sum(1 for e in executions if e.status == "partial")
        rejected = sum(1 for e in executions if e.status in ("rejected", "failed", "cancelled"))
        
        fill_rate = (filled / orders_analyzed * 100) if orders_analyzed > 0 else 100
        metrics["fill_rate"] = fill_rate
        metrics["partial_fills"] = float(partial)
        metrics["rejected_orders"] = float(rejected)
        
        if fill_rate < self._min_fill_rate:
            anomalies.append(f"Low fill rate: {fill_rate:.1f}%")
        
        evidence["slippage"] = {"avg": avg_slippage, "max": max_slippage}
        evidence["latency"] = {"avg": avg_latency, "p99": p99_latency}
        evidence["fills"] = {"rate": fill_rate, "partial": partial, "rejected": rejected}
        
        # Determine status
        if anomalies and (max_slippage > self._max_slippage * 3 or 
                          p99_latency > self._max_latency * 2 or
                          fill_rate < 80):
            status = ExecutionQuality.UNACCEPTABLE
            reason = f"CRITICAL: {'; '.join(anomalies)}"
        elif anomalies:
            status = ExecutionQuality.DEGRADED
            reason = f"WARNING: {'; '.join(anomalies)}"
        else:
            status = ExecutionQuality.GOOD
            reason = "Execution quality within acceptable bounds"
            details.append(f"Avg slippage: {avg_slippage:.1f} bps")
            details.append(f"P99 latency: {p99_latency:.0f}ms")
            details.append(f"Fill rate: {fill_rate:.1f}%")
        
        details.extend(anomalies)
        
        verdict = self._create_verdict(
            status=status.value,
            reason=reason,
            details=details,
            evidence=evidence,
            metrics=metrics,
        )
        
        self._logger.info(
            f"Execution quality review complete | status={status.value} | "
            f"orders={orders_analyzed} | slippage={avg_slippage:.1f}bps"
        )
        
        return ExecutionQualityReport(
            verdict=verdict,
            avg_slippage_bps=avg_slippage,
            max_slippage_bps=max_slippage,
            slippage_threshold_bps=self._max_slippage,
            avg_latency_ms=avg_latency,
            p99_latency_ms=p99_latency,
            latency_stable=latency_stable,
            fill_rate=fill_rate,
            partial_fills=partial,
            rejected_orders=rejected,
            anomalies_detected=anomalies,
            orders_analyzed=orders_analyzed,
        )


# ============================================================
# CAPITAL PRESERVATION REVIEWER
# ============================================================

class CapitalPreservationReviewer(BaseReviewer):
    """
    Evaluates capital safety:
    - Max drawdown status
    - Risk budget adherence
    - Rule override attempts
    - Position sizing consistency
    """
    
    def __init__(
        self,
        session: Session,
        max_drawdown_pct: float = 10.0,
        max_risk_budget_pct: float = 80.0,
        max_position_pct: float = 10.0,
    ):
        """
        Initialize Capital Preservation Reviewer.
        
        Args:
            session: Database session
            max_drawdown_pct: Maximum allowed drawdown percentage
            max_risk_budget_pct: Maximum risk budget usage percentage
            max_position_pct: Maximum single position percentage
        """
        super().__init__(session)
        self._max_drawdown = max_drawdown_pct
        self._max_risk_budget = max_risk_budget_pct
        self._max_position = max_position_pct
    
    @property
    def reviewer_type(self) -> ReviewerType:
        return ReviewerType.CAPITAL_PRESERVATION
    
    def review(self, correlation_id: str) -> CapitalSafetyReport:
        """Perform capital safety review."""
        self._logger.info(f"Starting capital safety review | correlation_id={correlation_id}")
        
        details = []
        evidence = {}
        metrics = {}
        rule_violations = []
        
        # 1. Check drawdown status
        current_drawdown, drawdown_breached = self._check_drawdown()
        metrics["current_drawdown_pct"] = current_drawdown
        evidence["drawdown"] = {
            "current": current_drawdown,
            "max_allowed": self._max_drawdown,
            "breached": drawdown_breached,
        }
        
        # 2. Check risk budget
        risk_used, risk_remaining, budget_respected = self._check_risk_budget()
        metrics["risk_budget_used_pct"] = risk_used
        metrics["risk_budget_remaining_pct"] = risk_remaining
        evidence["risk_budget"] = {
            "used": risk_used,
            "remaining": risk_remaining,
            "respected": budget_respected,
        }
        
        # 3. Check for override attempts
        override_attempts = self._count_override_attempts()
        metrics["override_attempts"] = float(override_attempts)
        
        if override_attempts > 0:
            rule_violations.append(f"{override_attempts} rule override attempts detected")
        
        # 4. Check position sizing consistency
        position_consistent, max_position, current_exposure = self._check_position_sizing()
        metrics["max_position_size_pct"] = max_position
        metrics["current_exposure_pct"] = current_exposure
        evidence["position_sizing"] = {
            "consistent": position_consistent,
            "max_position": max_position,
            "current_exposure": current_exposure,
        }
        
        if not position_consistent:
            rule_violations.append("Position sizing inconsistency detected")
        
        # Determine status
        if drawdown_breached:
            status = CapitalSafetyStatus.BREACH
            reason = f"DRAWDOWN BREACH: {current_drawdown:.1f}% > {self._max_drawdown}%"
            details.append(reason)
        elif not budget_respected:
            status = CapitalSafetyStatus.BREACH
            reason = f"RISK BUDGET EXCEEDED: {risk_used:.1f}% used"
            details.append(reason)
        elif override_attempts > 0:
            status = CapitalSafetyStatus.WARNING
            reason = f"Override attempts detected: {override_attempts}"
            details.extend(rule_violations)
        elif current_drawdown > self._max_drawdown * 0.8:
            status = CapitalSafetyStatus.WARNING
            reason = f"Approaching drawdown limit: {current_drawdown:.1f}%"
            details.append(f"Current drawdown: {current_drawdown:.1f}%")
            details.append(f"Maximum allowed: {self._max_drawdown}%")
        elif risk_used > self._max_risk_budget * 0.8:
            status = CapitalSafetyStatus.WARNING
            reason = f"Risk budget utilization high: {risk_used:.1f}%"
            details.append(f"Risk budget used: {risk_used:.1f}%")
        else:
            status = CapitalSafetyStatus.SAFE
            reason = "Capital protection rules respected"
            details.append(f"Current drawdown: {current_drawdown:.1f}%")
            details.append(f"Risk budget used: {risk_used:.1f}%")
            details.append("No rule violations detected")
        
        verdict = self._create_verdict(
            status=status.value,
            reason=reason,
            details=details,
            evidence=evidence,
            metrics=metrics,
        )
        
        self._logger.info(
            f"Capital safety review complete | status={status.value} | "
            f"drawdown={current_drawdown:.1f}% | risk_used={risk_used:.1f}%"
        )
        
        return CapitalSafetyReport(
            verdict=verdict,
            current_drawdown_pct=current_drawdown,
            max_allowed_drawdown_pct=self._max_drawdown,
            drawdown_breached=drawdown_breached,
            risk_budget_used_pct=risk_used,
            risk_budget_remaining_pct=risk_remaining,
            risk_budget_respected=budget_respected,
            override_attempts=override_attempts,
            rule_violations=rule_violations,
            position_sizing_consistent=position_consistent,
            max_position_size_pct=max_position,
            current_exposure_pct=current_exposure,
        )
    
    def _check_drawdown(self) -> Tuple[float, bool]:
        """Check current drawdown status."""
        # Get latest risk state
        latest = (
            self._session.query(RiskState)
            .order_by(desc(RiskState.created_at))
            .first()
        )
        
        if not latest:
            return 0.0, False
        
        # Try to get drawdown from risk state
        current_drawdown = getattr(latest, "current_drawdown", 0.0)
        if current_drawdown is None:
            current_drawdown = 0.0
        
        # Convert to percentage if stored as decimal
        if current_drawdown < 1:
            current_drawdown *= 100
        
        breached = current_drawdown > self._max_drawdown
        return current_drawdown, breached
    
    def _check_risk_budget(self) -> Tuple[float, float, bool]:
        """Check risk budget usage."""
        # Get latest position sizing data
        latest = (
            self._session.query(PositionSizing)
            .order_by(desc(PositionSizing.created_at))
            .first()
        )
        
        if not latest:
            return 0.0, 100.0, True
        
        # Calculate budget usage from current exposure
        exposure = getattr(latest, "current_exposure", 0.0)
        portfolio = getattr(latest, "portfolio_value", 1.0)
        
        if portfolio and portfolio > 0:
            risk_used = (exposure / portfolio) * 100
        else:
            risk_used = 0.0
        
        risk_remaining = 100.0 - risk_used
        budget_respected = risk_used <= self._max_risk_budget
        
        return risk_used, risk_remaining, budget_respected
    
    def _count_override_attempts(self) -> int:
        """Count rule override attempts in system monitoring."""
        lookback = datetime.utcnow() - timedelta(hours=24)
        
        count = (
            self._session.query(func.count(SystemMonitoring.id))
            .filter(SystemMonitoring.event_time >= lookback)
            .filter(
                SystemMonitoring.message.ilike("%override%") |
                SystemMonitoring.message.ilike("%bypass%") |
                SystemMonitoring.message.ilike("%violation%")
            )
            .scalar()
        )
        
        return count or 0
    
    def _check_position_sizing(self) -> Tuple[bool, float, float]:
        """Check position sizing consistency."""
        # Get recent position sizings
        recent = (
            self._session.query(PositionSizing)
            .order_by(desc(PositionSizing.created_at))
            .limit(10)
            .all()
        )
        
        if not recent:
            return True, 0.0, 0.0
        
        # Get max position size used
        max_positions = [
            ps.size_percent_of_portfolio for ps in recent 
            if ps.size_percent_of_portfolio is not None
        ]
        
        max_position = max(max_positions) if max_positions else 0.0
        
        # Check current exposure
        latest = recent[0]
        current_exposure = getattr(latest, "current_exposure", 0.0) or 0.0
        portfolio = getattr(latest, "portfolio_value", 1.0) or 1.0
        
        exposure_pct = (current_exposure / portfolio * 100) if portfolio > 0 else 0.0
        
        # Check consistency: no positions > max allowed
        consistent = max_position <= self._max_position
        
        return consistent, max_position, exposure_pct
