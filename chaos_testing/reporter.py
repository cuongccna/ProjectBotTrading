"""
Chaos Testing Report Generator.

============================================================
PURPOSE
============================================================
Generates comprehensive chaos testing reports.

Reports include:
- Summary statistics
- Detailed test results
- Forbidden behavior violations
- Recommendations
- Trend analysis

============================================================
REPORT TYPES
============================================================

1. ChaosReport - Full detailed report (database persistence)
2. Summary Report - Compact overview
3. Failure Report - Failed tests only
4. Violation Report - Forbidden behavior violations

============================================================
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from .models import (
    RunMode,
    FaultCategory,
    ChaosTestCase,
    ChaosTestResult,
    ChaosTestRun,
    ChaosReport,
    ForbiddenBehavior,
    ForbiddenBehaviorViolation,
    ExpectedSystemState,
    ExpectedTradeGuardDecision,
)


logger = logging.getLogger(__name__)


# ============================================================
# REPORT STATISTICS
# ============================================================

class ReportStatistics:
    """Statistics for chaos test runs."""
    
    def __init__(self, results: List[ChaosTestResult]):
        self.results = results
        self._compute_stats()
    
    def _compute_stats(self) -> None:
        """Compute statistics from results."""
        self.total_tests = len(self.results)
        self.passed_tests = sum(1 for r in self.results if r.passed)
        self.failed_tests = self.total_tests - self.passed_tests
        self.pass_rate = (
            (self.passed_tests / self.total_tests * 100)
            if self.total_tests > 0
            else 0.0
        )
        
        # Duration statistics
        durations = [
            (r.ended_at - r.started_at).total_seconds()
            for r in self.results
            if r.started_at and r.ended_at
        ]
        self.total_duration = sum(durations)
        self.avg_duration = (
            self.total_duration / len(durations) if durations else 0.0
        )
        self.max_duration = max(durations) if durations else 0.0
        self.min_duration = min(durations) if durations else 0.0
        
        # Violations
        all_violations = []
        for r in self.results:
            all_violations.extend(r.forbidden_behavior_violations)
        
        self.total_violations = len(all_violations)
        self.violation_by_type: Dict[ForbiddenBehavior, int] = {}
        for v in all_violations:
            self.violation_by_type[v.behavior] = (
                self.violation_by_type.get(v.behavior, 0) + 1
            )
        
        # Category breakdown
        self.results_by_category: Dict[FaultCategory, List[ChaosTestResult]] = {}
        for r in self.results:
            cat = r.test_case.fault_definition.category
            if cat not in self.results_by_category:
                self.results_by_category[cat] = []
            self.results_by_category[cat].append(r)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "pass_rate": round(self.pass_rate, 2),
            "total_duration_seconds": round(self.total_duration, 2),
            "avg_duration_seconds": round(self.avg_duration, 2),
            "max_duration_seconds": round(self.max_duration, 2),
            "min_duration_seconds": round(self.min_duration, 2),
            "total_violations": self.total_violations,
            "violations_by_type": {
                v.value: count
                for v, count in self.violation_by_type.items()
            },
            "results_by_category": {
                cat.value: {
                    "total": len(results),
                    "passed": sum(1 for r in results if r.passed),
                }
                for cat, results in self.results_by_category.items()
            },
        }


# ============================================================
# REPORT GENERATOR
# ============================================================

class ReportGenerator:
    """Generates chaos testing reports."""
    
    def __init__(self):
        self._recommendations_engine = RecommendationsEngine()
    
    def generate_report(
        self,
        test_run: ChaosTestRun,
        include_recommendations: bool = True,
    ) -> ChaosReport:
        """
        Generate a full chaos testing report.
        
        Args:
            test_run: The completed test run
            include_recommendations: Include actionable recommendations
            
        Returns:
            Complete ChaosReport
        """
        stats = ReportStatistics(test_run.test_results)
        
        # Get all violations
        all_violations = []
        for result in test_run.test_results:
            all_violations.extend(result.forbidden_behavior_violations)
        
        # Get all failed tests
        failed_tests = [r for r in test_run.test_results if not r.passed]
        
        # Generate summary
        summary = self._generate_summary(test_run, stats)
        
        # Generate recommendations
        recommendations = []
        if include_recommendations:
            recommendations = self._recommendations_engine.generate(
                test_run,
                stats,
            )
        
        report = ChaosReport(
            report_id=f"report_{test_run.run_id}",
            test_run=test_run,
            generated_at=datetime.utcnow(),
            summary=summary,
            recommendations=recommendations,
            passed=test_run.failed_tests == 0,
        )
        
        logger.info(
            f"Generated chaos report: {report.report_id} "
            f"(passed={report.passed}, violations={len(all_violations)})"
        )
        
        return report
    
    def _generate_summary(
        self,
        test_run: ChaosTestRun,
        stats: ReportStatistics,
    ) -> Dict[str, Any]:
        """Generate report summary."""
        return {
            "run_name": test_run.name,
            "run_mode": test_run.run_mode.value,
            "started_at": test_run.started_at.isoformat(),
            "ended_at": test_run.ended_at.isoformat() if test_run.ended_at else None,
            "duration_seconds": (
                (test_run.ended_at - test_run.started_at).total_seconds()
                if test_run.ended_at
                else None
            ),
            "statistics": stats.to_dict(),
            "overall_status": "PASS" if test_run.failed_tests == 0 else "FAIL",
            "critical_failures": self._get_critical_failures(test_run),
        }
    
    def _get_critical_failures(
        self,
        test_run: ChaosTestRun,
    ) -> List[Dict[str, Any]]:
        """Get critical failures from test run."""
        critical = []
        
        for result in test_run.test_results:
            if not result.passed:
                if result.test_case.priority == 1:
                    critical.append({
                        "test_name": result.test_case.name,
                        "category": result.test_case.fault_definition.category.value,
                        "error": result.error_message,
                        "violations": [
                            v.behavior.value
                            for v in result.forbidden_behavior_violations
                        ],
                    })
        
        return critical
    
    def generate_summary_report(
        self,
        test_run: ChaosTestRun,
    ) -> Dict[str, Any]:
        """Generate a compact summary report."""
        stats = ReportStatistics(test_run.test_results)
        
        return {
            "run_id": test_run.run_id,
            "name": test_run.name,
            "mode": test_run.run_mode.value,
            "passed": test_run.failed_tests == 0,
            "total": test_run.total_tests,
            "passed_count": test_run.passed_tests,
            "failed_count": test_run.failed_tests,
            "pass_rate": f"{stats.pass_rate:.1f}%",
            "duration": f"{stats.total_duration:.1f}s",
            "violations": stats.total_violations,
        }
    
    def generate_failure_report(
        self,
        test_run: ChaosTestRun,
    ) -> Dict[str, Any]:
        """Generate a report focusing on failures."""
        failed_results = [r for r in test_run.test_results if not r.passed]
        
        failures = []
        for result in failed_results:
            failures.append({
                "test_name": result.test_case.name,
                "test_id": result.test_case.test_id,
                "category": result.test_case.fault_definition.category.value,
                "fault_type": result.test_case.fault_definition.fault_type,
                "expected_state": result.test_case.expected_system_state.value,
                "actual_state": (
                    result.actual_system_state.value
                    if result.actual_system_state
                    else None
                ),
                "expected_decision": result.test_case.expected_trade_guard_decision.value,
                "actual_decision": (
                    result.actual_trade_guard_decision.value
                    if result.actual_trade_guard_decision
                    else None
                ),
                "error": result.error_message,
                "violations": [
                    {
                        "behavior": v.behavior.value,
                        "description": v.description,
                        "evidence": v.evidence,
                    }
                    for v in result.forbidden_behavior_violations
                ],
            })
        
        return {
            "run_id": test_run.run_id,
            "total_failures": len(failures),
            "failures": failures,
        }
    
    def generate_violation_report(
        self,
        test_run: ChaosTestRun,
    ) -> Dict[str, Any]:
        """Generate a report focusing on forbidden behavior violations."""
        violations_by_type: Dict[str, List[Dict[str, Any]]] = {}
        
        for result in test_run.test_results:
            for violation in result.forbidden_behavior_violations:
                behavior = violation.behavior.value
                if behavior not in violations_by_type:
                    violations_by_type[behavior] = []
                
                violations_by_type[behavior].append({
                    "test_name": result.test_case.name,
                    "description": violation.description,
                    "detected_at": violation.detected_at.isoformat(),
                    "evidence": violation.evidence,
                })
        
        total_violations = sum(
            len(v) for v in violations_by_type.values()
        )
        
        return {
            "run_id": test_run.run_id,
            "total_violations": total_violations,
            "violations_by_type": violations_by_type,
            "unique_violation_types": list(violations_by_type.keys()),
        }
    
    def export_json(
        self,
        report: ChaosReport,
        file_path: str,
    ) -> None:
        """Export report to JSON file."""
        
        def serialize(obj: Any) -> Any:
            if hasattr(obj, "__dict__"):
                return {
                    k: serialize(v)
                    for k, v in obj.__dict__.items()
                    if not k.startswith("_")
                }
            elif isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, (list, tuple)):
                return [serialize(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: serialize(v) for k, v in obj.items()}
            elif hasattr(obj, "value"):  # Enum
                return obj.value
            elif isinstance(obj, Decimal):
                return float(obj)
            else:
                return obj
        
        with open(file_path, "w") as f:
            json.dump(serialize(report), f, indent=2)
        
        logger.info(f"Exported report to {file_path}")


# ============================================================
# RECOMMENDATIONS ENGINE
# ============================================================

class RecommendationsEngine:
    """Generates recommendations based on test results."""
    
    def generate(
        self,
        test_run: ChaosTestRun,
        stats: ReportStatistics,
    ) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []
        
        # Check overall pass rate
        if stats.pass_rate < 100:
            recommendations.append(
                f"CRITICAL: {stats.failed_tests} tests failed. "
                "Review failure report for details."
            )
        
        # Check for violations
        for behavior, count in stats.violation_by_type.items():
            rec = self._get_recommendation_for_violation(behavior, count)
            if rec:
                recommendations.append(rec)
        
        # Check category-specific failures
        for category, results in stats.results_by_category.items():
            failed = [r for r in results if not r.passed]
            if failed:
                rec = self._get_recommendation_for_category(category, failed)
                if rec:
                    recommendations.append(rec)
        
        # General recommendations
        if stats.total_violations == 0 and stats.failed_tests == 0:
            recommendations.append(
                "All chaos tests passed. Consider adding more test cases "
                "or increasing fault intensity."
            )
        
        if stats.avg_duration > 30:
            recommendations.append(
                f"Average test duration is {stats.avg_duration:.1f}s. "
                "Consider optimizing system response times."
            )
        
        return recommendations
    
    def _get_recommendation_for_violation(
        self,
        behavior: ForbiddenBehavior,
        count: int,
    ) -> Optional[str]:
        """Get recommendation for a specific violation type."""
        recommendations = {
            ForbiddenBehavior.TRADE_WITH_STALE_DATA: (
                f"CRITICAL: {count} instances of trading with stale data. "
                "Implement stricter data freshness checks before order execution."
            ),
            ForbiddenBehavior.IGNORE_TRADE_GUARD: (
                f"CRITICAL: {count} instances of ignoring Trade Guard. "
                "Review order execution path to ensure Trade Guard is always consulted."
            ),
            ForbiddenBehavior.INFINITE_RETRY: (
                f"WARNING: {count} instances of excessive retries. "
                "Implement exponential backoff with maximum retry limits."
            ),
            ForbiddenBehavior.SILENT_CRASH: (
                f"CRITICAL: {count} silent crashes detected. "
                "Add proper exception handling with alerting."
            ),
            ForbiddenBehavior.CONTINUE_AFTER_CRITICAL: (
                f"CRITICAL: {count} instances of operation after critical failure. "
                "Implement proper emergency stop mechanism."
            ),
            ForbiddenBehavior.MISSING_AUDIT_TRAIL: (
                f"WARNING: {count} missing audit trail events. "
                "Ensure all security-relevant actions are logged."
            ),
            ForbiddenBehavior.IGNORE_RATE_LIMIT: (
                f"WARNING: {count} rate limit violations. "
                "Implement proper rate limit tracking and back-off."
            ),
            ForbiddenBehavior.SKIP_RECONCILIATION: (
                f"WARNING: {count} reconciliation gaps. "
                "Ensure periodic position reconciliation runs."
            ),
        }
        
        return recommendations.get(behavior)
    
    def _get_recommendation_for_category(
        self,
        category: FaultCategory,
        failed_results: List[ChaosTestResult],
    ) -> Optional[str]:
        """Get recommendation for category failures."""
        recommendations = {
            FaultCategory.DATA: (
                f"{len(failed_results)} data fault tests failed. "
                "Review data validation and freshness checking."
            ),
            FaultCategory.API: (
                f"{len(failed_results)} API fault tests failed. "
                "Improve error handling for external API calls."
            ),
            FaultCategory.PROCESS: (
                f"{len(failed_results)} process fault tests failed. "
                "Add proper health checks and circuit breakers."
            ),
            FaultCategory.EXECUTION: (
                f"{len(failed_results)} execution fault tests failed. "
                "Review order state machine and recovery logic."
            ),
            FaultCategory.SYSTEM: (
                f"{len(failed_results)} system fault tests failed. "
                "Improve infrastructure resilience and failover."
            ),
        }
        
        return recommendations.get(category)


# ============================================================
# DATABASE PERSISTENCE
# ============================================================

class ReportRepository:
    """Persists chaos testing reports to database."""
    
    def __init__(self, db_connection: Any = None):
        """
        Initialize repository.
        
        Args:
            db_connection: Database connection (implementation-specific)
        """
        self._db = db_connection
    
    async def save_report(self, report: ChaosReport) -> str:
        """
        Save a chaos report to database.
        
        Args:
            report: The report to save
            
        Returns:
            Saved report ID
        """
        # This is a placeholder - actual implementation depends on database
        logger.info(f"Saving report {report.report_id} to database")
        
        # Example structure for database insert
        record = {
            "report_id": report.report_id,
            "run_id": report.test_run.run_id,
            "run_mode": report.test_run.run_mode.value,
            "run_name": report.test_run.name,
            "started_at": report.test_run.started_at,
            "ended_at": report.test_run.ended_at,
            "total_tests": report.test_run.total_tests,
            "passed_tests": report.test_run.passed_tests,
            "failed_tests": report.test_run.failed_tests,
            "passed": report.passed,
            "summary": report.summary,
            "recommendations": report.recommendations,
            "generated_at": report.generated_at,
        }
        
        # Save to database (placeholder)
        # await self._db.execute(
        #     "INSERT INTO chaos_reports (...) VALUES (...)",
        #     record
        # )
        
        return report.report_id
    
    async def get_report(self, report_id: str) -> Optional[ChaosReport]:
        """Load a report from database."""
        logger.info(f"Loading report {report_id} from database")
        # Placeholder - actual implementation depends on database
        return None
    
    async def list_reports(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List recent reports."""
        logger.info(f"Listing reports (limit={limit}, offset={offset})")
        # Placeholder - actual implementation depends on database
        return []


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_report_generator() -> ReportGenerator:
    """Create a ReportGenerator instance."""
    return ReportGenerator()


def create_report_repository(db_connection: Any = None) -> ReportRepository:
    """Create a ReportRepository instance."""
    return ReportRepository(db_connection)
