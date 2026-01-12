"""
Parity Validation Reporting.

============================================================
PURPOSE
============================================================
Generates and persists parity validation reports.

Report types:
1. Per-cycle parity report
2. Daily parity summary
3. Drift statistics
4. Root cause hints

All reports are stored in database for auditability.

============================================================
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .models import (
    ValidationMode,
    ParityDomain,
    MismatchSeverity,
    FailureCondition,
    SystemReaction,
    CycleParityReport,
    DailyParitySummary,
    DriftReport,
    ParityAuditRecord,
    ParityComparisonResult,
    FieldMismatch,
)


logger = logging.getLogger(__name__)


# ============================================================
# REPORT FORMATTER
# ============================================================

class ReportFormatter:
    """Formats parity reports for various outputs."""
    
    def format_cycle_report(
        self,
        report: CycleParityReport,
        include_snapshots: bool = False,
    ) -> Dict[str, Any]:
        """Format a cycle parity report as JSON-serializable dict."""
        result = {
            "report_id": report.report_id,
            "cycle_id": report.cycle_id,
            "timestamp": report.timestamp.isoformat(),
            "validation_mode": report.validation_mode.value,
            "overall_match": report.overall_match,
            "highest_severity": report.highest_severity.value,
            "failure_conditions": [fc.value for fc in report.failure_conditions],
            "recommended_reaction": report.recommended_reaction.value,
            "code_version": report.code_version,
            "config_version": report.config_version,
            "domains": {},
        }
        
        # Add domain results
        for domain, comparison in [
            ("data", report.data_parity),
            ("feature", report.feature_parity),
            ("decision", report.decision_parity),
            ("execution", report.execution_parity),
            ("accounting", report.accounting_parity),
        ]:
            if comparison:
                result["domains"][domain] = self._format_comparison(
                    comparison, include_snapshots
                )
        
        return result
    
    def _format_comparison(
        self,
        comparison: ParityComparisonResult,
        include_snapshots: bool,
    ) -> Dict[str, Any]:
        """Format a comparison result."""
        formatted = {
            "comparison_id": comparison.comparison_id,
            "domain": comparison.domain.value,
            "is_match": comparison.is_match,
            "severity": comparison.severity.value,
            "mismatches": [
                self._format_mismatch(m) for m in comparison.mismatches
            ],
            "failure_conditions": [fc.value for fc in comparison.failure_conditions],
        }
        
        if comparison.category:
            formatted["category"] = comparison.category.value
        if comparison.explanation:
            formatted["explanation"] = comparison.explanation
        
        if include_snapshots:
            formatted["live_snapshot"] = self._serialize_snapshot(comparison.live_snapshot)
            formatted["backtest_snapshot"] = self._serialize_snapshot(comparison.backtest_snapshot)
        
        return formatted
    
    def _format_mismatch(self, mismatch: FieldMismatch) -> Dict[str, Any]:
        """Format a field mismatch."""
        return {
            "field": mismatch.field_name,
            "live_value": self._serialize_value(mismatch.live_value),
            "backtest_value": self._serialize_value(mismatch.backtest_value),
            "deviation": str(mismatch.deviation) if mismatch.deviation else None,
            "deviation_pct": str(mismatch.deviation_pct) if mismatch.deviation_pct else None,
            "within_tolerance": mismatch.within_tolerance,
            "tolerance_used": str(mismatch.tolerance_used) if mismatch.tolerance_used else None,
        }
    
    def _serialize_value(self, value: Any) -> Any:
        """Serialize a value for JSON."""
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if hasattr(value, "__dict__"):
            return {k: self._serialize_value(v) for k, v in value.__dict__.items() if not k.startswith("_")}
        return value
    
    def _serialize_snapshot(self, snapshot: Any) -> Optional[Dict[str, Any]]:
        """Serialize a snapshot."""
        if snapshot is None:
            return None
        if isinstance(snapshot, dict):
            return {k: self._serialize_value(v) for k, v in snapshot.items()}
        if hasattr(snapshot, "to_dict"):
            return snapshot.to_dict()
        return self._serialize_value(snapshot)
    
    def format_daily_summary(
        self,
        summary: DailyParitySummary,
    ) -> Dict[str, Any]:
        """Format a daily summary."""
        return {
            "summary_id": summary.summary_id,
            "date": summary.date.isoformat(),
            "total_cycles": summary.total_cycles,
            "matched_cycles": summary.matched_cycles,
            "mismatched_cycles": summary.mismatched_cycles,
            "match_rate": f"{summary.match_rate:.2f}%",
            "severity_breakdown": {
                "info": summary.info_count,
                "warning": summary.warning_count,
                "critical": summary.critical_count,
                "fatal": summary.fatal_count,
            },
            "failure_condition_counts": summary.failure_condition_counts,
            "domain_mismatch_counts": summary.domain_mismatch_counts,
            "drift_detected": summary.drift_detected,
            "reactions_taken": [r.value for r in summary.reactions_taken],
        }
    
    def format_drift_report(
        self,
        report: DriftReport,
    ) -> Dict[str, Any]:
        """Format a drift report."""
        return {
            "report_id": report.report_id,
            "generated_at": report.generated_at.isoformat(),
            "analysis_window": {
                "start": report.analysis_window_start.isoformat(),
                "end": report.analysis_window_end.isoformat(),
            },
            "total_drift_count": report.total_drift_count,
            "significant_drift_count": report.significant_drift_count,
            "parameter_drifts": [self._format_drift_metric(d) for d in report.parameter_drifts],
            "behavior_drifts": [self._format_drift_metric(d) for d in report.behavior_drifts],
            "execution_drifts": [self._format_drift_metric(d) for d in report.execution_drifts],
            "risk_tolerance_drifts": [self._format_drift_metric(d) for d in report.risk_tolerance_drifts],
            "root_cause_hints": report.root_cause_hints,
        }
    
    def _format_drift_metric(self, metric: Any) -> Dict[str, Any]:
        """Format a drift metric."""
        return {
            "drift_id": metric.drift_id,
            "drift_type": metric.drift_type.value,
            "metric_name": metric.metric_name,
            "current_value": str(metric.current_value),
            "baseline_value": str(metric.baseline_value),
            "deviation": str(metric.deviation),
            "deviation_pct": str(metric.deviation_pct),
            "trend_direction": metric.trend_direction,
            "is_significant": metric.is_significant,
        }
    
    def format_text_summary(
        self,
        report: CycleParityReport,
    ) -> str:
        """Format a human-readable text summary."""
        lines = [
            f"=== Parity Report: {report.cycle_id} ===",
            f"Timestamp: {report.timestamp.isoformat()}",
            f"Mode: {report.validation_mode.value}",
            f"Overall Match: {'✓' if report.overall_match else '✗'}",
            f"Severity: {report.highest_severity.value}",
        ]
        
        if report.failure_conditions:
            lines.append(f"Failures: {', '.join(fc.value for fc in report.failure_conditions)}")
        
        lines.append(f"Reaction: {report.recommended_reaction.value}")
        
        # Domain summaries
        for name, comparison in [
            ("Data", report.data_parity),
            ("Feature", report.feature_parity),
            ("Decision", report.decision_parity),
            ("Execution", report.execution_parity),
        ]:
            if comparison:
                status = "✓" if comparison.is_match else "✗"
                mismatch_count = len([m for m in comparison.mismatches if not m.within_tolerance])
                lines.append(f"  {name}: {status} ({mismatch_count} mismatches)")
        
        return "\n".join(lines)


# ============================================================
# REPORT REPOSITORY
# ============================================================

class ReportRepository:
    """Persists parity reports to database."""
    
    def __init__(self, db_connection: Any = None):
        self._db = db_connection
        self._formatter = ReportFormatter()
    
    async def save_cycle_report(
        self,
        report: CycleParityReport,
    ) -> str:
        """Save a cycle parity report."""
        logger.info(f"Saving cycle report: {report.report_id}")
        
        data = self._formatter.format_cycle_report(report, include_snapshots=True)
        
        # Placeholder for actual database insert
        # await self._db.execute(
        #     "INSERT INTO parity_cycle_reports (...) VALUES (...)",
        #     data
        # )
        
        return report.report_id
    
    async def save_daily_summary(
        self,
        summary: DailyParitySummary,
    ) -> str:
        """Save a daily summary."""
        logger.info(f"Saving daily summary: {summary.summary_id}")
        
        data = self._formatter.format_daily_summary(summary)
        
        # Placeholder for actual database insert
        # await self._db.execute(
        #     "INSERT INTO parity_daily_summaries (...) VALUES (...)",
        #     data
        # )
        
        return summary.summary_id
    
    async def save_audit_record(
        self,
        record: ParityAuditRecord,
    ) -> str:
        """Save an audit record."""
        logger.info(f"Saving audit record: {record.audit_id}")
        
        data = record.to_dict()
        
        # Placeholder for actual database insert
        # await self._db.execute(
        #     "INSERT INTO parity_audit_records (...) VALUES (...)",
        #     data
        # )
        
        return record.audit_id
    
    async def get_cycle_reports(
        self,
        since: datetime,
        until: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get cycle reports from database."""
        logger.info(f"Querying cycle reports since {since}")
        
        # Placeholder for actual database query
        return []
    
    async def get_daily_summaries(
        self,
        since: datetime,
        until: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get daily summaries from database."""
        logger.info(f"Querying daily summaries since {since}")
        
        # Placeholder for actual database query
        return []
    
    async def get_audit_records(
        self,
        cycle_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get audit records from database."""
        logger.info(f"Querying audit records")
        
        # Placeholder for actual database query
        return []


# ============================================================
# REPORT EXPORTER
# ============================================================

class ReportExporter:
    """Exports reports to various formats."""
    
    def __init__(self):
        self._formatter = ReportFormatter()
    
    def export_to_json(
        self,
        report: CycleParityReport,
        file_path: str,
        include_snapshots: bool = True,
    ) -> None:
        """Export cycle report to JSON file."""
        data = self._formatter.format_cycle_report(report, include_snapshots)
        
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"Exported report to {file_path}")
    
    def export_daily_to_json(
        self,
        summary: DailyParitySummary,
        file_path: str,
    ) -> None:
        """Export daily summary to JSON file."""
        data = self._formatter.format_daily_summary(summary)
        
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"Exported daily summary to {file_path}")
    
    def export_to_csv_row(
        self,
        report: CycleParityReport,
    ) -> Dict[str, Any]:
        """Export cycle report as CSV row data."""
        return {
            "report_id": report.report_id,
            "cycle_id": report.cycle_id,
            "timestamp": report.timestamp.isoformat(),
            "mode": report.validation_mode.value,
            "overall_match": report.overall_match,
            "severity": report.highest_severity.value,
            "failure_count": len(report.failure_conditions),
            "reaction": report.recommended_reaction.value,
            "data_match": report.data_parity.is_match if report.data_parity else None,
            "feature_match": report.feature_parity.is_match if report.feature_parity else None,
            "decision_match": report.decision_parity.is_match if report.decision_parity else None,
            "execution_match": report.execution_parity.is_match if report.execution_parity else None,
        }


# ============================================================
# REPORT GENERATOR
# ============================================================

class ParityReportGenerator:
    """Generates comprehensive parity reports."""
    
    def __init__(
        self,
        repository: Optional[ReportRepository] = None,
        exporter: Optional[ReportExporter] = None,
    ):
        self._repository = repository or ReportRepository()
        self._exporter = exporter or ReportExporter()
        self._formatter = ReportFormatter()
    
    async def generate_and_save_cycle_report(
        self,
        report: CycleParityReport,
    ) -> str:
        """Generate formatted report and save to database."""
        return await self._repository.save_cycle_report(report)
    
    async def generate_and_save_daily_summary(
        self,
        summary: DailyParitySummary,
    ) -> str:
        """Generate and save daily summary."""
        return await self._repository.save_daily_summary(summary)
    
    def get_text_summary(
        self,
        report: CycleParityReport,
    ) -> str:
        """Get human-readable text summary."""
        return self._formatter.format_text_summary(report)
    
    def get_alert_message(
        self,
        report: CycleParityReport,
    ) -> str:
        """Generate alert message for notifications."""
        if report.overall_match:
            return f"✓ Parity OK: {report.cycle_id}"
        
        lines = [
            f"⚠️ PARITY MISMATCH: {report.cycle_id}",
            f"Severity: {report.highest_severity.value}",
        ]
        
        if report.failure_conditions:
            lines.append(f"Failures: {len(report.failure_conditions)}")
            for fc in report.failure_conditions[:3]:  # Show first 3
                lines.append(f"  • {fc.value}")
        
        lines.append(f"Reaction: {report.recommended_reaction.value}")
        
        return "\n".join(lines)
    
    def get_drift_alert_message(
        self,
        report: DriftReport,
    ) -> str:
        """Generate alert message for drift detection."""
        if report.significant_drift_count == 0:
            return "✓ No significant drift detected"
        
        lines = [
            f"⚠️ DRIFT DETECTED",
            f"Significant drifts: {report.significant_drift_count}",
        ]
        
        # Add hints
        for hint in report.root_cause_hints[:2]:  # Show first 2
            lines.append(f"💡 {hint}")
        
        return "\n".join(lines)


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_report_formatter() -> ReportFormatter:
    """Create a ReportFormatter."""
    return ReportFormatter()


def create_report_repository(db_connection: Any = None) -> ReportRepository:
    """Create a ReportRepository."""
    return ReportRepository(db_connection)


def create_report_exporter() -> ReportExporter:
    """Create a ReportExporter."""
    return ReportExporter()


def create_report_generator(
    repository: Optional[ReportRepository] = None,
    exporter: Optional[ReportExporter] = None,
) -> ParityReportGenerator:
    """Create a ParityReportGenerator."""
    return ParityReportGenerator(
        repository=repository,
        exporter=exporter,
    )
