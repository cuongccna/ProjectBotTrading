"""
Risk Committee - Main Engine.

============================================================
INSTITUTIONAL RISK REVIEW COMMITTEE
============================================================
This engine orchestrates all reviewers and produces the final
committee decision with full audit trail.

DECISION LOGIC (EXPLICIT):
- If ANY = FAIL / BREACH / UNACCEPTABLE → decision = BLOCK
- If 2+ WARNINGS → decision = HOLD
- If ALL PASS/SAFE/GOOD/LOW → decision = APPROVE

AUTHORITY:
- APPROVE → allow continuation of current mode only
- HOLD → freeze new trades, allow monitoring
- BLOCK → trigger System Risk Controller global halt

============================================================
"""

import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session

from database.engine import get_session, transaction_scope
from .types import (
    CommitteeDecision,
    CommitteeReport,
    DataIntegrityReport,
    MarketRiskReport,
    ExecutionQualityReport,
    CapitalSafetyReport,
)
from .reviewers import (
    DataIntegrityReviewer,
    MarketRiskReviewer,
    ExecutionQualityReviewer,
    CapitalPreservationReviewer,
)
from .models import (
    RiskCommitteeReport as DBReport,
    CommitteeDecisionEnum,
    DataIntegrityStatusEnum,
    MarketRiskLevelEnum,
    ExecutionQualityEnum,
    CapitalSafetyEnum,
)


logger = logging.getLogger("risk_committee.engine")


class RiskCommitteeEngine:
    """
    Institutional Risk Review Committee Engine.
    
    Orchestrates all reviewers and produces final decision.
    This module does NOT trade.
    This module does NOT modify market data.
    This module has VETO AUTHORITY over trading modes.
    """
    
    def __init__(
        self,
        session: Optional[Session] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize Risk Committee Engine.
        
        Args:
            session: SQLAlchemy session (optional, will create if None)
            config: Configuration dictionary
        """
        self._session = session
        self._owns_session = session is None
        self._config = config or {}
        
        # Extract configuration
        self._max_data_age = self._config.get("max_data_age_seconds", 7200.0)
        self._expected_sources = self._config.get("expected_sources", ["coingecko", "binance"])
        self._high_volatility_threshold = self._config.get("high_volatility_threshold", 80.0)
        self._max_slippage_bps = self._config.get("max_slippage_bps", 50.0)
        self._max_drawdown_pct = self._config.get("max_drawdown_pct", 10.0)
        
        self._initialized = False
        logger.info("RiskCommitteeEngine initialized")
    
    def _get_session(self) -> Session:
        """Get database session."""
        if self._session is None:
            self._session = get_session()
            self._owns_session = True
        return self._session
    
    def _close_session(self):
        """Close session if we own it."""
        if self._owns_session and self._session:
            self._session.close()
            self._session = None
    
    # ============================================================
    # MODULE PROTOCOL
    # ============================================================
    
    async def start(self) -> None:
        """Start the committee engine."""
        self._initialized = True
        logger.info("RiskCommitteeEngine started")
    
    async def stop(self) -> None:
        """Stop the committee engine."""
        self._close_session()
        self._initialized = False
        logger.info("RiskCommitteeEngine stopped")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status."""
        return {
            "status": "healthy" if self._initialized else "not_started",
            "module": "risk_committee",
        }
    
    # ============================================================
    # MAIN REVIEW METHOD
    # ============================================================
    
    def convene_committee(
        self,
        correlation_id: str,
        cycle_id: Optional[str] = None,
    ) -> CommitteeReport:
        """
        Convene the risk committee and produce a decision.
        
        All four reviewers are consulted:
        1. Data Integrity Reviewer
        2. Market Risk Reviewer
        3. Execution Quality Reviewer
        4. Capital Preservation Reviewer
        
        Args:
            correlation_id: Current cycle correlation ID
            cycle_id: Optional cycle identifier
            
        Returns:
            CommitteeReport with full decision and reasoning
        """
        start_time = time.time()
        session = self._get_session()
        
        logger.info(
            f"=== RISK COMMITTEE CONVENED === | "
            f"correlation_id={correlation_id} | cycle_id={cycle_id}"
        )
        
        # Initialize report
        report = CommitteeReport(
            correlation_id=correlation_id,
            cycle_id=cycle_id or "",
        )
        
        try:
            # 1. Data Integrity Review
            data_reviewer = DataIntegrityReviewer(
                session=session,
                max_data_age_seconds=self._max_data_age,
                expected_sources=self._expected_sources,
            )
            report.data_integrity = data_reviewer.review(correlation_id)
            
            # 2. Market Risk Review
            market_reviewer = MarketRiskReviewer(
                session=session,
                high_volatility_threshold=self._high_volatility_threshold,
            )
            report.market_risk = market_reviewer.review(correlation_id)
            
            # 3. Execution Quality Review
            execution_reviewer = ExecutionQualityReviewer(
                session=session,
                max_slippage_bps=self._max_slippage_bps,
            )
            report.execution_quality = execution_reviewer.review(correlation_id)
            
            # 4. Capital Preservation Review
            capital_reviewer = CapitalPreservationReviewer(
                session=session,
                max_drawdown_pct=self._max_drawdown_pct,
            )
            report.capital_safety = capital_reviewer.review(correlation_id)
            
            # 5. Committee Decision
            self._make_committee_decision(report)
            
            # Calculate duration
            report.review_duration_ms = (time.time() - start_time) * 1000
            
            # 6. Persist report
            self._persist_report(report, session)
            
            # Log decision
            logger.info(
                f"=== COMMITTEE DECISION: {report.decision.value} === | "
                f"correlation_id={correlation_id} | "
                f"critical={report.critical_count} | "
                f"warning={report.warning_count} | "
                f"ok={report.ok_count} | "
                f"duration={report.review_duration_ms:.0f}ms"
            )
            
            if report.decision != CommitteeDecision.APPROVE:
                logger.warning(
                    f"COMMITTEE {report.decision.value}: {report.decision_reason}"
                )
            
            return report
            
        except Exception as e:
            logger.error(f"Committee review failed: {e}", exc_info=True)
            
            # On error, default to BLOCK for safety
            report.decision = CommitteeDecision.BLOCK
            report.decision_reason = f"REVIEW FAILED: {str(e)}"
            report.decision_details = ["Exception during committee review"]
            report.review_duration_ms = (time.time() - start_time) * 1000
            
            return report
    
    # ============================================================
    # DECISION LOGIC
    # ============================================================
    
    def _make_committee_decision(self, report: CommitteeReport) -> None:
        """
        Apply committee decision logic.
        
        EXPLICIT LOGIC:
        - If ANY = FAIL / BREACH / UNACCEPTABLE / HIGH → BLOCK
        - If 2+ WARNINGS/WARN/DEGRADED/MEDIUM → HOLD
        - If ALL PASS/SAFE/GOOD/LOW → APPROVE
        """
        verdicts = report.get_all_verdicts()
        
        critical_count = 0
        warning_count = 0
        ok_count = 0
        
        critical_details = []
        warning_details = []
        
        for verdict in verdicts:
            if verdict.is_critical():
                critical_count += 1
                critical_details.append(
                    f"{verdict.reviewer_type.value}: {verdict.status} - {verdict.reason}"
                )
            elif verdict.is_warning():
                warning_count += 1
                warning_details.append(
                    f"{verdict.reviewer_type.value}: {verdict.status} - {verdict.reason}"
                )
            else:
                ok_count += 1
        
        report.critical_count = critical_count
        report.warning_count = warning_count
        report.ok_count = ok_count
        
        # Apply decision logic
        if critical_count > 0:
            # ANY critical failure → BLOCK
            report.decision = CommitteeDecision.BLOCK
            report.decision_reason = (
                f"CRITICAL FAILURE: {critical_count} reviewer(s) reported critical issues"
            )
            report.decision_details = critical_details + warning_details
            
        elif warning_count >= 2:
            # 2+ warnings → HOLD
            report.decision = CommitteeDecision.HOLD
            report.decision_reason = (
                f"ELEVATED RISK: {warning_count} reviewer(s) reported warnings"
            )
            report.decision_details = warning_details
            
        elif warning_count == 1:
            # 1 warning → APPROVE with caution
            report.decision = CommitteeDecision.APPROVE
            report.decision_reason = (
                f"APPROVED WITH CAUTION: 1 warning noted"
            )
            report.decision_details = warning_details + [
                "Trading may continue with enhanced monitoring"
            ]
            
        else:
            # All OK → APPROVE
            report.decision = CommitteeDecision.APPROVE
            report.decision_reason = "All reviewers report acceptable conditions"
            report.decision_details = [
                f"Data Integrity: {report.data_integrity.verdict.status if report.data_integrity else 'N/A'}",
                f"Market Risk: {report.market_risk.verdict.status if report.market_risk else 'N/A'}",
                f"Execution Quality: {report.execution_quality.verdict.status if report.execution_quality else 'N/A'}",
                f"Capital Safety: {report.capital_safety.verdict.status if report.capital_safety else 'N/A'}",
            ]
    
    # ============================================================
    # PERSISTENCE
    # ============================================================
    
    def _persist_report(self, report: CommitteeReport, session: Session) -> None:
        """Persist committee report to database."""
        try:
            db_report = DBReport(
                report_id=report.report_id,
                correlation_id=report.correlation_id,
                cycle_id=report.cycle_id,
                created_at=report.timestamp,
                review_duration_ms=report.review_duration_ms,
                
                decision=CommitteeDecisionEnum(report.decision.value.lower()),
                decision_reason=report.decision_reason,
                decision_details=report.decision_details,
                
                critical_count=report.critical_count,
                warning_count=report.warning_count,
                ok_count=report.ok_count,
                
                data_integrity_status=(
                    DataIntegrityStatusEnum(report.data_integrity.verdict.status.lower())
                    if report.data_integrity else None
                ),
                market_risk_level=(
                    MarketRiskLevelEnum(report.market_risk.verdict.status.lower())
                    if report.market_risk else None
                ),
                execution_quality_status=(
                    ExecutionQualityEnum(report.execution_quality.verdict.status.lower())
                    if report.execution_quality else None
                ),
                capital_safety_status=(
                    CapitalSafetyEnum(report.capital_safety.verdict.status.lower())
                    if report.capital_safety else None
                ),
                
                data_integrity_report=(
                    report.data_integrity.to_dict() if report.data_integrity else None
                ),
                market_risk_report=(
                    report.market_risk.to_dict() if report.market_risk else None
                ),
                execution_quality_report=(
                    report.execution_quality.to_dict() if report.execution_quality else None
                ),
                capital_safety_report=(
                    report.capital_safety.to_dict() if report.capital_safety else None
                ),
            )
            
            session.add(db_report)
            session.commit()
            
            logger.debug(f"Persisted committee report: {report.report_id[:8]}")
            
        except Exception as e:
            logger.error(f"Failed to persist committee report: {e}")
            session.rollback()
    
    # ============================================================
    # QUERY METHODS
    # ============================================================
    
    def get_latest_report(self) -> Optional[CommitteeReport]:
        """Get the most recent committee report."""
        session = self._get_session()
        
        db_report = (
            session.query(DBReport)
            .order_by(DBReport.created_at.desc())
            .first()
        )
        
        if not db_report:
            return None
        
        return self._db_to_report(db_report)
    
    def get_reports_by_decision(
        self,
        decision: CommitteeDecision,
        limit: int = 10,
    ) -> List[CommitteeReport]:
        """Get recent reports with specific decision."""
        session = self._get_session()
        
        db_reports = (
            session.query(DBReport)
            .filter(DBReport.decision == CommitteeDecisionEnum(decision.value.lower()))
            .order_by(DBReport.created_at.desc())
            .limit(limit)
            .all()
        )
        
        return [self._db_to_report(r) for r in db_reports]
    
    def _db_to_report(self, db_report: DBReport) -> CommitteeReport:
        """Convert database report to CommitteeReport."""
        # Simplified conversion - returns basic report
        # Full report reconstruction would require deserializing JSONB fields
        report = CommitteeReport(
            report_id=db_report.report_id,
            correlation_id=db_report.correlation_id,
            cycle_id=db_report.cycle_id or "",
            timestamp=db_report.created_at,
            decision=CommitteeDecision(db_report.decision.value.upper()),
            decision_reason=db_report.decision_reason,
            decision_details=db_report.decision_details or [],
            critical_count=db_report.critical_count,
            warning_count=db_report.warning_count,
            ok_count=db_report.ok_count,
            review_duration_ms=db_report.review_duration_ms,
        )
        
        return report
    
    # ============================================================
    # INTEGRATION HELPERS
    # ============================================================
    
    def should_allow_trading(self) -> bool:
        """
        Quick check if trading should be allowed.
        
        Based on most recent committee decision.
        """
        latest = self.get_latest_report()
        
        if not latest:
            # No report yet - conservative default
            logger.warning("No committee report available - defaulting to BLOCK")
            return False
        
        # Only APPROVE allows trading
        return latest.decision == CommitteeDecision.APPROVE
    
    def get_decision_for_system_risk_controller(self) -> Dict[str, Any]:
        """
        Get decision in format for System Risk Controller.
        
        Returns:
            Dict with decision and metadata for SRC integration
        """
        latest = self.get_latest_report()
        
        if not latest:
            return {
                "decision": "BLOCK",
                "reason": "No committee report available",
                "source": "risk_committee",
                "report_id": None,
            }
        
        # Map committee decision to SRC action
        action_map = {
            CommitteeDecision.APPROVE: "CONTINUE",
            CommitteeDecision.HOLD: "PAUSE_NEW_TRADES",
            CommitteeDecision.BLOCK: "HALT",
        }
        
        return {
            "decision": action_map[latest.decision],
            "reason": latest.decision_reason,
            "source": "risk_committee",
            "report_id": latest.report_id,
            "critical_count": latest.critical_count,
            "warning_count": latest.warning_count,
            "timestamp": latest.timestamp.isoformat(),
        }


# ============================================================
# FACTORY FUNCTION
# ============================================================

def create_risk_committee(
    config: Optional[Dict[str, Any]] = None,
) -> RiskCommitteeEngine:
    """
    Factory function to create Risk Committee Engine.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Configured RiskCommitteeEngine instance
    """
    return RiskCommitteeEngine(config=config)
