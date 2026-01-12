"""
Parity Validation Orchestrator.

============================================================
PURPOSE
============================================================
Main orchestrator for live vs backtest parity validation.

Coordinates:
1. Data collection from both sources
2. Comparison across all domains
3. Drift detection
4. Report generation
5. System reaction triggering

============================================================
STRICT PROHIBITIONS
============================================================
This module must NEVER:
- Modify trading logic
- Modify backtest logic
- Adjust parameters automatically
- Ignore mismatches

============================================================
"""

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import (
    ValidationMode,
    ParityDomain,
    MismatchSeverity,
    FailureCondition,
    SystemReaction,
    ToleranceConfig,
    CycleParityReport,
    DailyParitySummary,
    ParityAuditRecord,
    ParityComparisonResult,
)
from .collectors import (
    LiveDataCollector,
    BacktestDataCollector,
    SynchronizedCollector,
    create_live_collector,
    create_backtest_collector,
    create_synchronized_collector,
)
from .comparators import (
    BaseComparator,
    DataComparator,
    FeatureComparator,
    DecisionComparator,
    ExecutionComparator,
    AccountingComparator,
    create_comparators,
)
from .drift_detector import (
    DriftDetector,
    ContinuousDriftMonitor,
    create_drift_detector,
    create_drift_monitor,
)


logger = logging.getLogger(__name__)


# ============================================================
# VERSION INFO
# ============================================================

def get_code_version() -> str:
    """Get current code version."""
    return "1.0.0"


def get_code_commit_hash() -> str:
    """Get current git commit hash."""
    # In production, this would be injected at build time
    return "unknown"


def compute_config_hash(config: Dict[str, Any]) -> str:
    """Compute hash of configuration."""
    import json
    config_str = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(config_str.encode()).hexdigest()[:16]


# ============================================================
# REACTION HANDLER
# ============================================================

class ReactionHandler:
    """Handles system reactions to parity failures."""
    
    def __init__(
        self,
        trade_guard: Any = None,
        risk_escalator: Any = None,
        alert_service: Any = None,
    ):
        self._trade_guard = trade_guard
        self._risk_escalator = risk_escalator
        self._alert_service = alert_service
        self._reaction_history: List[Tuple[datetime, SystemReaction, str]] = []
    
    async def handle_reaction(
        self,
        reaction: SystemReaction,
        report: CycleParityReport,
    ) -> bool:
        """Execute a system reaction."""
        success = True
        reason = self._build_reaction_reason(report)
        
        logger.info(f"Executing reaction: {reaction.value} - {reason}")
        
        try:
            if reaction == SystemReaction.LOG_ONLY:
                # Just log
                pass
            
            elif reaction == SystemReaction.ESCALATE_RISK:
                if self._risk_escalator:
                    await self._risk_escalator.escalate(
                        reason=f"Parity failure: {reason}",
                        severity=report.highest_severity.value,
                    )
            
            elif reaction == SystemReaction.NOTIFY_TRADE_GUARD:
                if self._trade_guard:
                    await self._trade_guard.notify_parity_failure(
                        cycle_id=report.cycle_id,
                        failures=report.failure_conditions,
                    )
            
            elif reaction == SystemReaction.BLOCK_TRADING:
                if self._trade_guard:
                    await self._trade_guard.block_trading(
                        reason=f"Parity validation failure: {reason}",
                        duration_seconds=3600,  # 1 hour block
                    )
            
            elif reaction == SystemReaction.REQUIRE_MANUAL_REVIEW:
                if self._alert_service:
                    await self._alert_service.send_critical(
                        title="Manual Review Required",
                        message=f"Parity validation requires manual review: {reason}",
                        data={"cycle_id": report.cycle_id},
                    )
            
            self._reaction_history.append((datetime.utcnow(), reaction, reason))
            
        except Exception as e:
            logger.error(f"Reaction execution failed: {e}")
            success = False
        
        return success
    
    def _build_reaction_reason(self, report: CycleParityReport) -> str:
        """Build reason string from report."""
        failures = [fc.value for fc in report.failure_conditions]
        return f"Severity={report.highest_severity.value}, Failures={failures}"
    
    def determine_reaction(
        self,
        report: CycleParityReport,
    ) -> SystemReaction:
        """Determine appropriate reaction based on report."""
        severity = report.highest_severity
        
        if severity == MismatchSeverity.FATAL:
            return SystemReaction.BLOCK_TRADING
        
        if severity == MismatchSeverity.CRITICAL:
            # Check specific failure conditions
            fatal_failures = {
                FailureCondition.TRADE_ALLOWED_LIVE_BLOCKED_BACKTEST,
                FailureCondition.TRADE_BLOCKED_LIVE_ALLOWED_BACKTEST,
            }
            
            if any(fc in fatal_failures for fc in report.failure_conditions):
                return SystemReaction.BLOCK_TRADING
            
            return SystemReaction.NOTIFY_TRADE_GUARD
        
        if severity == MismatchSeverity.WARNING:
            return SystemReaction.ESCALATE_RISK
        
        return SystemReaction.LOG_ONLY
    
    def get_reaction_history(
        self,
        since: datetime,
    ) -> List[Tuple[datetime, SystemReaction, str]]:
        """Get reaction history since timestamp."""
        return [r for r in self._reaction_history if r[0] >= since]


# ============================================================
# PARITY VALIDATOR
# ============================================================

class ParityValidator:
    """
    Main parity validation orchestrator.
    
    Coordinates all validation activities and enforces
    the parity validation policy.
    """
    
    def __init__(
        self,
        mode: ValidationMode,
        tolerance_config: Optional[ToleranceConfig] = None,
        live_collector: Optional[LiveDataCollector] = None,
        backtest_collector: Optional[BacktestDataCollector] = None,
        comparators: Optional[Dict[ParityDomain, BaseComparator]] = None,
        drift_detector: Optional[DriftDetector] = None,
        reaction_handler: Optional[ReactionHandler] = None,
    ):
        self._mode = mode
        self._tolerance = tolerance_config or ToleranceConfig()
        
        # Initialize collectors
        self._live_collector = live_collector or create_live_collector()
        self._backtest_collector = backtest_collector or create_backtest_collector()
        self._sync_collector = create_synchronized_collector(
            self._live_collector,
            self._backtest_collector,
        )
        
        # Initialize comparators
        self._comparators = comparators or create_comparators(self._tolerance)
        
        # Initialize drift detection
        self._drift_detector = drift_detector or create_drift_detector()
        self._drift_monitor = create_drift_monitor(
            detector=self._drift_detector,
            alert_callback=self._on_drift_detected,
        )
        
        # Reaction handler
        self._reaction_handler = reaction_handler or ReactionHandler()
        
        # State
        self._is_running = False
        self._cycle_reports: List[CycleParityReport] = []
        self._daily_summaries: List[DailyParitySummary] = []
        
        # Callbacks
        self._on_mismatch_callbacks: List[Callable] = []
        self._on_drift_callbacks: List[Callable] = []
        
        logger.info(f"ParityValidator initialized in {mode.value} mode")
    
    @property
    def mode(self) -> ValidationMode:
        return self._mode
    
    @property
    def tolerance_config(self) -> ToleranceConfig:
        return self._tolerance
    
    def register_mismatch_callback(self, callback: Callable) -> None:
        """Register callback for mismatch events."""
        self._on_mismatch_callbacks.append(callback)
    
    def register_drift_callback(self, callback: Callable) -> None:
        """Register callback for drift events."""
        self._on_drift_callbacks.append(callback)
    
    async def validate_cycle(
        self,
        symbol: str,
        cycle_id: str,
        timestamp: datetime,
        backtest_state: Optional[Dict[str, Any]] = None,
    ) -> CycleParityReport:
        """
        Validate parity for a single trading cycle.
        
        Args:
            symbol: Trading symbol
            cycle_id: Unique cycle identifier
            timestamp: Cycle timestamp
            backtest_state: Optional backtest state for replay
            
        Returns:
            CycleParityReport with all comparison results
        """
        logger.info(f"Validating parity for cycle {cycle_id}")
        
        # Set backtest state if provided
        if backtest_state:
            self._backtest_collector.set_replay_state(backtest_state)
        
        # Create report
        report = CycleParityReport(
            report_id=f"parity_{uuid.uuid4().hex[:12]}",
            cycle_id=cycle_id,
            timestamp=timestamp,
            validation_mode=self._mode,
            tolerance_config_version=get_code_version(),
            code_version=get_code_version(),
            config_version=compute_config_hash({"tolerance": str(self._tolerance)}),
        )
        
        try:
            # Collect all data pairs
            snapshots = await self._sync_collector.collect_full_cycle(
                symbol=symbol,
                cycle_id=cycle_id,
                timestamp=timestamp,
            )
            
            # Data parity
            live_market, backtest_market = snapshots["market"]
            data_result = self._comparators[ParityDomain.DATA].compare(
                live_market, backtest_market, cycle_id
            )
            report.add_comparison(data_result)
            
            # Feature parity
            live_features, backtest_features = snapshots["feature"]
            feature_result = self._comparators[ParityDomain.FEATURE].compare(
                live_features, backtest_features, cycle_id
            )
            report.add_comparison(feature_result)
            
            # Decision parity
            live_decision, backtest_decision = snapshots["decision"]
            decision_result = self._comparators[ParityDomain.DECISION].compare(
                live_decision, backtest_decision, cycle_id
            )
            report.add_comparison(decision_result)
            
            # Execution parity (if trade was executed)
            live_execution, backtest_execution = snapshots["execution"]
            if live_execution.order_type or backtest_execution.order_type:
                execution_result = self._comparators[ParityDomain.EXECUTION].compare(
                    live_execution, backtest_execution, cycle_id
                )
                report.add_comparison(execution_result)
            
            # Determine recommended reaction
            report.recommended_reaction = self._reaction_handler.determine_reaction(report)
            
            # Process for drift detection
            self._drift_monitor.process_cycle_report(report)
            
            # Store report
            self._cycle_reports.append(report)
            
            # Notify callbacks if mismatch
            if not report.overall_match:
                await self._notify_mismatch(report)
            
            # Execute reaction if needed
            if report.recommended_reaction != SystemReaction.LOG_ONLY:
                await self._reaction_handler.handle_reaction(
                    report.recommended_reaction,
                    report,
                )
            
        except Exception as e:
            logger.exception(f"Parity validation failed for cycle {cycle_id}: {e}")
            report.overall_match = False
        
        return report
    
    async def _notify_mismatch(self, report: CycleParityReport) -> None:
        """Notify registered callbacks of mismatch."""
        for callback in self._on_mismatch_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(report)
                else:
                    callback(report)
            except Exception as e:
                logger.error(f"Mismatch callback failed: {e}")
    
    def _on_drift_detected(self, drift_metric: Any) -> None:
        """Handle drift detection event."""
        logger.warning(f"Drift detected: {drift_metric.metric_name}")
        
        for callback in self._on_drift_callbacks:
            try:
                callback(drift_metric)
            except Exception as e:
                logger.error(f"Drift callback failed: {e}")
    
    def create_audit_record(
        self,
        cycle_id: str,
        report: CycleParityReport,
        input_data_hash: str = "",
    ) -> ParityAuditRecord:
        """Create an audit record for a parity validation."""
        return ParityAuditRecord(
            audit_id=f"audit_{uuid.uuid4().hex[:12]}",
            timestamp=datetime.utcnow(),
            cycle_id=cycle_id,
            validation_mode=self._mode,
            code_version=get_code_version(),
            code_commit_hash=get_code_commit_hash(),
            config_version=report.config_version,
            config_hash=compute_config_hash({"tolerance": str(self._tolerance)}),
            tolerance_config=self._tolerance,
            parity_report=report,
            input_data_hash=input_data_hash,
        )
    
    def generate_daily_summary(
        self,
        date: datetime,
    ) -> DailyParitySummary:
        """Generate daily parity summary."""
        # Filter reports for the date
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        
        day_reports = [
            r for r in self._cycle_reports
            if start <= r.timestamp < end
        ]
        
        summary = DailyParitySummary(
            summary_id=f"daily_{date.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}",
            date=date,
            total_cycles=len(day_reports),
            matched_cycles=sum(1 for r in day_reports if r.overall_match),
            mismatched_cycles=sum(1 for r in day_reports if not r.overall_match),
        )
        
        # Severity breakdown
        for report in day_reports:
            if report.highest_severity == MismatchSeverity.INFO:
                summary.info_count += 1
            elif report.highest_severity == MismatchSeverity.WARNING:
                summary.warning_count += 1
            elif report.highest_severity == MismatchSeverity.CRITICAL:
                summary.critical_count += 1
            elif report.highest_severity == MismatchSeverity.FATAL:
                summary.fatal_count += 1
        
        # Failure condition counts
        for report in day_reports:
            for fc in report.failure_conditions:
                fc_key = fc.value
                summary.failure_condition_counts[fc_key] = (
                    summary.failure_condition_counts.get(fc_key, 0) + 1
                )
        
        # Domain mismatch counts
        for report in day_reports:
            for comparison in [
                report.data_parity,
                report.feature_parity,
                report.decision_parity,
                report.execution_parity,
            ]:
                if comparison and not comparison.is_match:
                    domain_key = comparison.domain.value
                    summary.domain_mismatch_counts[domain_key] = (
                        summary.domain_mismatch_counts.get(domain_key, 0) + 1
                    )
        
        # Reactions taken
        for r in self._reaction_handler.get_reaction_history(since=start):
            if r[0] < end:
                summary.reactions_taken.append(r[1])
        
        # Drift info
        drift_report = self._drift_detector.generate_report(start, end)
        if drift_report.significant_drift_count > 0:
            summary.drift_detected = True
            summary.drift_metrics = (
                drift_report.parameter_drifts +
                drift_report.behavior_drifts +
                drift_report.execution_drifts +
                drift_report.risk_tolerance_drifts
            )
        
        self._daily_summaries.append(summary)
        return summary
    
    def get_cycle_reports(
        self,
        since: datetime,
        limit: int = 100,
    ) -> List[CycleParityReport]:
        """Get cycle reports since timestamp."""
        reports = [r for r in self._cycle_reports if r.timestamp >= since]
        return reports[:limit]
    
    def get_daily_summaries(
        self,
        since: datetime,
    ) -> List[DailyParitySummary]:
        """Get daily summaries since date."""
        return [s for s in self._daily_summaries if s.date >= since]
    
    def get_current_drift_status(self) -> Dict[str, Any]:
        """Get current drift status."""
        return self._drift_monitor.get_current_drift_summary()


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_parity_validator(
    mode: ValidationMode = ValidationMode.SHADOW_MODE,
    tolerance_config: Optional[ToleranceConfig] = None,
    live_collector: Optional[LiveDataCollector] = None,
    backtest_collector: Optional[BacktestDataCollector] = None,
    trade_guard: Any = None,
    risk_escalator: Any = None,
    alert_service: Any = None,
) -> ParityValidator:
    """
    Create a fully configured ParityValidator.
    
    Args:
        mode: Validation mode
        tolerance_config: Tolerance thresholds
        live_collector: Live data collector
        backtest_collector: Backtest data collector
        trade_guard: Trade Guard instance for reactions
        risk_escalator: Risk escalator for reactions
        alert_service: Alert service for notifications
        
    Returns:
        Configured ParityValidator
    """
    reaction_handler = ReactionHandler(
        trade_guard=trade_guard,
        risk_escalator=risk_escalator,
        alert_service=alert_service,
    )
    
    return ParityValidator(
        mode=mode,
        tolerance_config=tolerance_config,
        live_collector=live_collector,
        backtest_collector=backtest_collector,
        reaction_handler=reaction_handler,
    )
