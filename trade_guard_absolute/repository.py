"""
Trade Guard Absolute - Repository.

============================================================
PURPOSE
============================================================
Database operations for guard decision logging.

Provides:
- Decision logging
- Alert logging
- Statistics aggregation
- Query operations

============================================================
"""

from datetime import datetime, timedelta
from typing import List, Optional
import logging

from sqlalchemy import select, func, and_, desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .types import (
    GuardDecisionOutput,
    GuardDecision,
    BlockReason,
    BlockSeverity,
    BlockCategory,
)
from .models import (
    GuardDecisionLog,
    GuardBlockAlertLog,
    GuardDailyStats,
)


logger = logging.getLogger(__name__)


class GuardRepository:
    """
    Repository for guard decision persistence.
    
    All database operations go through this class.
    """
    
    def __init__(self, session: Session):
        """
        Initialize repository.
        
        Args:
            session: SQLAlchemy database session
        """
        self._session = session
    
    # ============================================================
    # DECISION LOGGING
    # ============================================================
    
    def log_decision(
        self,
        decision_output: GuardDecisionOutput,
    ) -> GuardDecisionLog:
        """
        Log a guard decision to the database.
        
        Args:
            decision_output: The decision output to log
            
        Returns:
            Created GuardDecisionLog record
        """
        try:
            # Extract block message from details
            block_message = None
            if decision_output.details:
                block_message = decision_output.details.get("message")
            
            # Serialize validation results
            validation_results_data = None
            if decision_output.validation_results:
                validation_results_data = [
                    {
                        "validator_name": r.validator_name,
                        "is_valid": r.is_valid,
                        "reason": r.reason.value if r.reason else None,
                        "severity": r.severity.name if r.severity else None,
                        "details": r.details,
                        "validation_time_ms": r.validation_time_ms,
                    }
                    for r in decision_output.validation_results
                ]
            
            record = GuardDecisionLog(
                evaluation_id=decision_output.evaluation_id,
                request_id=decision_output.trade_intent.request_id if decision_output.trade_intent else "UNKNOWN",
                symbol=decision_output.trade_intent.symbol if decision_output.trade_intent else "UNKNOWN",
                direction=decision_output.trade_intent.direction if decision_output.trade_intent else None,
                decision=decision_output.decision.value,
                block_reason=decision_output.reason.value if decision_output.reason else None,
                block_severity=decision_output.severity.name if decision_output.severity else None,
                block_category=decision_output.category.value if decision_output.category else None,
                block_message=block_message,
                details=decision_output.details,
                validation_results=validation_results_data,
                evaluation_time_ms=decision_output.evaluation_time_ms,
                timestamp=decision_output.timestamp,
            )
            
            self._session.add(record)
            self._session.commit()
            
            logger.debug(f"Logged guard decision: {decision_output.evaluation_id}")
            
            return record
        
        except SQLAlchemyError as e:
            self._session.rollback()
            logger.error(f"Failed to log guard decision: {e}")
            raise
    
    def get_decision_by_evaluation_id(
        self,
        evaluation_id: str,
    ) -> Optional[GuardDecisionLog]:
        """
        Get a decision by evaluation ID.
        
        Args:
            evaluation_id: The evaluation ID
            
        Returns:
            GuardDecisionLog or None
        """
        stmt = select(GuardDecisionLog).where(
            GuardDecisionLog.evaluation_id == evaluation_id
        )
        return self._session.execute(stmt).scalar_one_or_none()
    
    def get_decisions_by_request_id(
        self,
        request_id: str,
    ) -> List[GuardDecisionLog]:
        """
        Get all decisions for a request ID.
        
        Args:
            request_id: The request ID
            
        Returns:
            List of GuardDecisionLog records
        """
        stmt = (
            select(GuardDecisionLog)
            .where(GuardDecisionLog.request_id == request_id)
            .order_by(desc(GuardDecisionLog.timestamp))
        )
        return list(self._session.execute(stmt).scalars().all())
    
    def get_recent_blocks(
        self,
        hours: int = 24,
        limit: int = 100,
        category: Optional[str] = None,
    ) -> List[GuardDecisionLog]:
        """
        Get recent BLOCK decisions.
        
        Args:
            hours: Look back period
            limit: Maximum records to return
            category: Optional filter by category
            
        Returns:
            List of blocked decisions
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        
        conditions = [
            GuardDecisionLog.decision == "BLOCK",
            GuardDecisionLog.timestamp >= since,
        ]
        
        if category:
            conditions.append(GuardDecisionLog.block_category == category)
        
        stmt = (
            select(GuardDecisionLog)
            .where(and_(*conditions))
            .order_by(desc(GuardDecisionLog.timestamp))
            .limit(limit)
        )
        
        return list(self._session.execute(stmt).scalars().all())
    
    def get_block_count_by_reason(
        self,
        hours: int = 24,
    ) -> dict:
        """
        Get block counts grouped by reason.
        
        Args:
            hours: Look back period
            
        Returns:
            Dict of reason -> count
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        
        stmt = (
            select(
                GuardDecisionLog.block_reason,
                func.count(GuardDecisionLog.id),
            )
            .where(
                and_(
                    GuardDecisionLog.decision == "BLOCK",
                    GuardDecisionLog.timestamp >= since,
                    GuardDecisionLog.block_reason.isnot(None),
                )
            )
            .group_by(GuardDecisionLog.block_reason)
        )
        
        results = self._session.execute(stmt).all()
        return {reason: count for reason, count in results}
    
    # ============================================================
    # ALERT LOGGING
    # ============================================================
    
    def log_alert(
        self,
        evaluation_id: str,
        alert_type: str,
        alert_severity: str,
        alert_title: str,
        alert_message: str,
        sent: bool = False,
        send_error: Optional[str] = None,
        rate_limited: bool = False,
    ) -> GuardBlockAlertLog:
        """
        Log an alert.
        
        Args:
            evaluation_id: Reference to decision
            alert_type: Type of alert (TELEGRAM, etc.)
            alert_severity: Severity level
            alert_title: Alert title
            alert_message: Full message
            sent: Whether successfully sent
            send_error: Error if failed
            rate_limited: Whether rate limited
            
        Returns:
            Created alert record
        """
        try:
            record = GuardBlockAlertLog(
                evaluation_id=evaluation_id,
                alert_type=alert_type,
                alert_severity=alert_severity,
                alert_title=alert_title,
                alert_message=alert_message,
                sent=sent,
                send_error=send_error,
                rate_limited=rate_limited,
                sent_at=datetime.utcnow() if sent else None,
            )
            
            self._session.add(record)
            self._session.commit()
            
            return record
        
        except SQLAlchemyError as e:
            self._session.rollback()
            logger.error(f"Failed to log alert: {e}")
            raise
    
    def get_recent_alerts(
        self,
        hours: int = 24,
        limit: int = 50,
    ) -> List[GuardBlockAlertLog]:
        """
        Get recent alerts.
        
        Args:
            hours: Look back period
            limit: Maximum records
            
        Returns:
            List of alert records
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        
        stmt = (
            select(GuardBlockAlertLog)
            .where(GuardBlockAlertLog.created_at >= since)
            .order_by(desc(GuardBlockAlertLog.created_at))
            .limit(limit)
        )
        
        return list(self._session.execute(stmt).scalars().all())
    
    def count_alerts_in_window(
        self,
        minutes: int = 60,
    ) -> int:
        """
        Count alerts sent in time window.
        
        For rate limiting checks.
        
        Args:
            minutes: Look back period
            
        Returns:
            Number of alerts sent
        """
        since = datetime.utcnow() - timedelta(minutes=minutes)
        
        stmt = (
            select(func.count(GuardBlockAlertLog.id))
            .where(
                and_(
                    GuardBlockAlertLog.sent == True,
                    GuardBlockAlertLog.sent_at >= since,
                )
            )
        )
        
        return self._session.execute(stmt).scalar() or 0
    
    # ============================================================
    # STATISTICS
    # ============================================================
    
    def get_or_create_daily_stats(
        self,
        date: Optional[datetime] = None,
    ) -> GuardDailyStats:
        """
        Get or create daily stats record.
        
        Args:
            date: Date for stats (defaults to today)
            
        Returns:
            GuardDailyStats record
        """
        if date is None:
            date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        stmt = select(GuardDailyStats).where(
            GuardDailyStats.stat_date == date
        )
        stats = self._session.execute(stmt).scalar_one_or_none()
        
        if stats is None:
            stats = GuardDailyStats(stat_date=date)
            self._session.add(stats)
            self._session.commit()
        
        return stats
    
    def update_stats_for_decision(
        self,
        decision_output: GuardDecisionOutput,
    ) -> None:
        """
        Update daily stats for a decision.
        
        Args:
            decision_output: The decision to record
        """
        try:
            stats = self.get_or_create_daily_stats()
            
            # Update counts
            stats.total_evaluations += 1
            
            if decision_output.decision == GuardDecision.EXECUTE:
                stats.execute_count += 1
            else:
                stats.block_count += 1
                
                # Update category breakdown
                if decision_output.category:
                    category = decision_output.category
                    if category == BlockCategory.SYSTEM_INTEGRITY:
                        stats.blocks_system_integrity += 1
                    elif category == BlockCategory.EXECUTION_SAFETY:
                        stats.blocks_execution_safety += 1
                    elif category == BlockCategory.STATE_CONSISTENCY:
                        stats.blocks_state_consistency += 1
                    elif category == BlockCategory.RULE_VIOLATION:
                        stats.blocks_rule_violation += 1
                    elif category == BlockCategory.ENVIRONMENTAL:
                        stats.blocks_environmental += 1
                    elif category == BlockCategory.INTERNAL_ERROR:
                        stats.blocks_internal_error += 1
                
                # Update severity breakdown
                if decision_output.severity:
                    severity = decision_output.severity
                    if severity == BlockSeverity.LOW:
                        stats.severity_low += 1
                    elif severity == BlockSeverity.MEDIUM:
                        stats.severity_medium += 1
                    elif severity == BlockSeverity.HIGH:
                        stats.severity_high += 1
                    elif severity == BlockSeverity.CRITICAL:
                        stats.severity_critical += 1
                    elif severity == BlockSeverity.EMERGENCY:
                        stats.severity_emergency += 1
            
            # Update timing
            if stats.total_evaluations == 1:
                stats.avg_evaluation_time_ms = decision_output.evaluation_time_ms
                stats.max_evaluation_time_ms = decision_output.evaluation_time_ms
            else:
                # Incremental average
                stats.avg_evaluation_time_ms = (
                    (stats.avg_evaluation_time_ms * (stats.total_evaluations - 1) 
                     + decision_output.evaluation_time_ms) 
                    / stats.total_evaluations
                )
                stats.max_evaluation_time_ms = max(
                    stats.max_evaluation_time_ms,
                    decision_output.evaluation_time_ms,
                )
            
            self._session.commit()
        
        except SQLAlchemyError as e:
            self._session.rollback()
            logger.error(f"Failed to update stats: {e}")
    
    def get_stats_range(
        self,
        days: int = 7,
    ) -> List[GuardDailyStats]:
        """
        Get stats for date range.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of daily stats records
        """
        since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
        
        stmt = (
            select(GuardDailyStats)
            .where(GuardDailyStats.stat_date >= since)
            .order_by(desc(GuardDailyStats.stat_date))
        )
        
        return list(self._session.execute(stmt).scalars().all())
    
    # ============================================================
    # CLEANUP
    # ============================================================
    
    def cleanup_old_records(
        self,
        retention_days: int = 90,
    ) -> int:
        """
        Delete records older than retention period.
        
        Args:
            retention_days: Days to retain
            
        Returns:
            Number of records deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        deleted = 0
        
        try:
            # Delete old decisions
            result = self._session.query(GuardDecisionLog).filter(
                GuardDecisionLog.timestamp < cutoff
            ).delete()
            deleted += result
            
            # Delete old alerts
            result = self._session.query(GuardBlockAlertLog).filter(
                GuardBlockAlertLog.created_at < cutoff
            ).delete()
            deleted += result
            
            # Delete old stats
            result = self._session.query(GuardDailyStats).filter(
                GuardDailyStats.stat_date < cutoff
            ).delete()
            deleted += result
            
            self._session.commit()
            logger.info(f"Cleaned up {deleted} old guard records")
            
            return deleted
        
        except SQLAlchemyError as e:
            self._session.rollback()
            logger.error(f"Failed to cleanup old records: {e}")
            raise
