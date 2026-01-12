"""
Parity Validation Notifications.

============================================================
PURPOSE
============================================================
Sends notifications for parity validation events.

Notification channels:
1. Telegram - Critical mismatches, drift detection, trading blocks
2. Logging - All events

All notifications are rate-limited to prevent spam.

============================================================
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .models import (
    ValidationMode,
    MismatchSeverity,
    FailureCondition,
    SystemReaction,
    CycleParityReport,
    DailyParitySummary,
    DriftReport,
)
from .reporter import ParityReportGenerator


logger = logging.getLogger(__name__)


# ============================================================
# NOTIFICATION TYPES
# ============================================================

class NotificationType(Enum):
    """Types of notifications."""
    PARITY_MISMATCH = "parity_mismatch"
    DRIFT_DETECTED = "drift_detected"
    TRADING_BLOCKED = "trading_blocked"
    RISK_ESCALATED = "risk_escalated"
    DAILY_SUMMARY = "daily_summary"
    FATAL_CONDITION = "fatal_condition"
    REPEATED_MISMATCH = "repeated_mismatch"


class NotificationPriority(Enum):
    """Notification priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================
# RATE LIMITER
# ============================================================

class NotificationRateLimiter:
    """Rate limits notifications to prevent spam."""
    
    # Default limits (notifications per window)
    DEFAULT_LIMITS = {
        NotificationType.PARITY_MISMATCH: (10, timedelta(minutes=5)),
        NotificationType.DRIFT_DETECTED: (5, timedelta(minutes=10)),
        NotificationType.TRADING_BLOCKED: (1, timedelta(minutes=1)),  # Always send
        NotificationType.RISK_ESCALATED: (3, timedelta(minutes=5)),
        NotificationType.DAILY_SUMMARY: (1, timedelta(hours=1)),
        NotificationType.FATAL_CONDITION: (1, timedelta(seconds=10)),  # Always send quickly
        NotificationType.REPEATED_MISMATCH: (5, timedelta(minutes=15)),
    }
    
    def __init__(self, limits: Optional[Dict[NotificationType, tuple]] = None):
        self._limits = limits or self.DEFAULT_LIMITS
        self._sent: Dict[str, List[datetime]] = {}
    
    def should_send(
        self,
        notification_type: NotificationType,
        key: Optional[str] = None,
    ) -> bool:
        """Check if notification should be sent based on rate limits."""
        limit, window = self._limits.get(
            notification_type,
            (10, timedelta(minutes=5))
        )
        
        cache_key = f"{notification_type.value}:{key or 'default'}"
        now = datetime.utcnow()
        
        # Clean old entries
        if cache_key in self._sent:
            self._sent[cache_key] = [
                t for t in self._sent[cache_key]
                if now - t < window
            ]
        else:
            self._sent[cache_key] = []
        
        # Check limit
        if len(self._sent[cache_key]) >= limit:
            return False
        
        # Record this notification
        self._sent[cache_key].append(now)
        return True
    
    def reset(self, notification_type: Optional[NotificationType] = None) -> None:
        """Reset rate limits."""
        if notification_type:
            prefix = notification_type.value
            self._sent = {
                k: v for k, v in self._sent.items()
                if not k.startswith(prefix)
            }
        else:
            self._sent.clear()


# ============================================================
# TELEGRAM NOTIFIER
# ============================================================

class TelegramNotifier:
    """Sends notifications via Telegram."""
    
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        enabled: bool = True,
        rate_limiter: Optional[NotificationRateLimiter] = None,
    ):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._enabled = enabled
        self._rate_limiter = rate_limiter or NotificationRateLimiter()
        self._report_generator = ParityReportGenerator()
    
    async def _send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a message via Telegram API."""
        if not self._enabled:
            logger.debug("Telegram notifications disabled, skipping")
            return False
        
        try:
            # Placeholder for actual Telegram API call
            # import aiohttp
            # async with aiohttp.ClientSession() as session:
            #     url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
            #     payload = {
            #         "chat_id": self._chat_id,
            #         "text": text,
            #         "parse_mode": parse_mode,
            #     }
            #     async with session.post(url, json=payload) as resp:
            #         return resp.status == 200
            
            logger.info(f"[TELEGRAM] Would send: {text[:100]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False
    
    async def notify_parity_mismatch(
        self,
        report: CycleParityReport,
    ) -> bool:
        """Notify about a parity mismatch."""
        # Only notify for WARNING or higher
        if report.highest_severity in [MismatchSeverity.INFO]:
            return False
        
        # Rate limit
        if not self._rate_limiter.should_send(
            NotificationType.PARITY_MISMATCH,
            report.cycle_id,
        ):
            logger.debug(f"Rate limited: parity mismatch for {report.cycle_id}")
            return False
        
        message = self._format_mismatch_message(report)
        return await self._send_message(message)
    
    def _format_mismatch_message(self, report: CycleParityReport) -> str:
        """Format parity mismatch message."""
        severity_emoji = {
            MismatchSeverity.INFO: "ℹ️",
            MismatchSeverity.WARNING: "⚠️",
            MismatchSeverity.CRITICAL: "🔴",
            MismatchSeverity.FATAL: "🚨",
        }
        
        emoji = severity_emoji.get(report.highest_severity, "❓")
        
        lines = [
            f"{emoji} <b>PARITY MISMATCH</b>",
            f"",
            f"<b>Cycle:</b> {report.cycle_id}",
            f"<b>Severity:</b> {report.highest_severity.value}",
            f"<b>Mode:</b> {report.validation_mode.value}",
        ]
        
        if report.failure_conditions:
            lines.append("")
            lines.append("<b>Failures:</b>")
            for fc in report.failure_conditions[:5]:
                lines.append(f"  • {fc.value}")
        
        lines.append("")
        lines.append(f"<b>Reaction:</b> {report.recommended_reaction.value}")
        
        return "\n".join(lines)
    
    async def notify_drift_detected(
        self,
        report: DriftReport,
    ) -> bool:
        """Notify about detected drift."""
        if report.significant_drift_count == 0:
            return False
        
        if not self._rate_limiter.should_send(NotificationType.DRIFT_DETECTED):
            logger.debug("Rate limited: drift detection")
            return False
        
        message = self._format_drift_message(report)
        return await self._send_message(message)
    
    def _format_drift_message(self, report: DriftReport) -> str:
        """Format drift detection message."""
        lines = [
            "📈 <b>DRIFT DETECTED</b>",
            "",
            f"<b>Significant Drifts:</b> {report.significant_drift_count}",
            f"<b>Window:</b> {report.analysis_window_start.strftime('%H:%M')} - {report.analysis_window_end.strftime('%H:%M')}",
        ]
        
        # Add drift summaries
        drift_counts = {
            "Parameter": len(report.parameter_drifts),
            "Behavior": len(report.behavior_drifts),
            "Execution": len(report.execution_drifts),
            "Risk Tolerance": len(report.risk_tolerance_drifts),
        }
        
        for name, count in drift_counts.items():
            if count > 0:
                lines.append(f"  • {name}: {count}")
        
        # Add hints
        if report.root_cause_hints:
            lines.append("")
            lines.append("<b>Root Cause Hints:</b>")
            for hint in report.root_cause_hints[:3]:
                lines.append(f"💡 {hint}")
        
        return "\n".join(lines)
    
    async def notify_trading_blocked(
        self,
        reason: str,
        report: Optional[CycleParityReport] = None,
    ) -> bool:
        """Notify that trading has been blocked."""
        # Always send trading blocked notifications
        if not self._rate_limiter.should_send(NotificationType.TRADING_BLOCKED):
            logger.debug("Rate limited: trading blocked")
            return False
        
        message = self._format_blocked_message(reason, report)
        return await self._send_message(message)
    
    def _format_blocked_message(
        self,
        reason: str,
        report: Optional[CycleParityReport],
    ) -> str:
        """Format trading blocked message."""
        lines = [
            "🛑 <b>TRADING BLOCKED</b>",
            "",
            f"<b>Reason:</b> {reason}",
        ]
        
        if report:
            lines.append(f"<b>Cycle:</b> {report.cycle_id}")
            if report.failure_conditions:
                lines.append("<b>Failures:</b>")
                for fc in report.failure_conditions[:3]:
                    lines.append(f"  • {fc.value}")
        
        lines.append("")
        lines.append("<b>Action Required:</b> Manual review before resuming")
        
        return "\n".join(lines)
    
    async def notify_risk_escalated(
        self,
        current_level: str,
        new_level: str,
        reason: str,
    ) -> bool:
        """Notify that risk level has been escalated."""
        if not self._rate_limiter.should_send(NotificationType.RISK_ESCALATED):
            logger.debug("Rate limited: risk escalated")
            return False
        
        lines = [
            "⚡ <b>RISK ESCALATED</b>",
            "",
            f"<b>Level:</b> {current_level} → {new_level}",
            f"<b>Reason:</b> {reason}",
        ]
        
        return await self._send_message("\n".join(lines))
    
    async def notify_fatal_condition(
        self,
        condition: FailureCondition,
        report: CycleParityReport,
    ) -> bool:
        """Notify about a fatal condition."""
        if not self._rate_limiter.should_send(
            NotificationType.FATAL_CONDITION,
            condition.value,
        ):
            return False
        
        lines = [
            "🚨 <b>FATAL PARITY CONDITION</b>",
            "",
            f"<b>Condition:</b> {condition.value}",
            f"<b>Cycle:</b> {report.cycle_id}",
            "",
            "<b>IMMEDIATE ACTION REQUIRED</b>",
        ]
        
        return await self._send_message("\n".join(lines))
    
    async def notify_daily_summary(
        self,
        summary: DailyParitySummary,
    ) -> bool:
        """Send daily parity summary."""
        if not self._rate_limiter.should_send(NotificationType.DAILY_SUMMARY):
            return False
        
        message = self._format_summary_message(summary)
        return await self._send_message(message)
    
    def _format_summary_message(self, summary: DailyParitySummary) -> str:
        """Format daily summary message."""
        status_emoji = "✅" if summary.match_rate >= 99 else "⚠️" if summary.match_rate >= 95 else "🔴"
        
        lines = [
            f"{status_emoji} <b>DAILY PARITY SUMMARY</b>",
            f"<b>Date:</b> {summary.date.strftime('%Y-%m-%d')}",
            "",
            f"<b>Cycles:</b> {summary.total_cycles}",
            f"<b>Match Rate:</b> {summary.match_rate:.2f}%",
            f"<b>Matched:</b> {summary.matched_cycles}",
            f"<b>Mismatched:</b> {summary.mismatched_cycles}",
        ]
        
        # Severity breakdown
        if summary.warning_count or summary.critical_count or summary.fatal_count:
            lines.append("")
            lines.append("<b>Severity Breakdown:</b>")
            if summary.warning_count:
                lines.append(f"  ⚠️ Warning: {summary.warning_count}")
            if summary.critical_count:
                lines.append(f"  🔴 Critical: {summary.critical_count}")
            if summary.fatal_count:
                lines.append(f"  🚨 Fatal: {summary.fatal_count}")
        
        if summary.drift_detected:
            lines.append("")
            lines.append("📈 <b>Drift detected during this period</b>")
        
        return "\n".join(lines)
    
    async def notify_repeated_mismatch(
        self,
        field_name: str,
        occurrence_count: int,
        window_minutes: int,
    ) -> bool:
        """Notify about repeated mismatches on same field."""
        if not self._rate_limiter.should_send(
            NotificationType.REPEATED_MISMATCH,
            field_name,
        ):
            return False
        
        lines = [
            "🔄 <b>REPEATED MISMATCH</b>",
            "",
            f"<b>Field:</b> {field_name}",
            f"<b>Occurrences:</b> {occurrence_count}",
            f"<b>Window:</b> Last {window_minutes} minutes",
            "",
            "This may indicate a systematic issue.",
        ]
        
        return await self._send_message("\n".join(lines))


# ============================================================
# NOTIFICATION MANAGER
# ============================================================

class ParityNotificationManager:
    """Manages all parity validation notifications."""
    
    def __init__(
        self,
        telegram_notifier: Optional[TelegramNotifier] = None,
        rate_limiter: Optional[NotificationRateLimiter] = None,
    ):
        self._telegram = telegram_notifier
        self._rate_limiter = rate_limiter or NotificationRateLimiter()
        
        # Track repeated mismatches
        self._mismatch_history: Dict[str, List[datetime]] = {}
        self._repeated_threshold = 5
        self._repeated_window = timedelta(minutes=15)
    
    async def on_cycle_validated(
        self,
        report: CycleParityReport,
    ) -> None:
        """Handle cycle validation completion."""
        # Always log
        if report.overall_match:
            logger.debug(f"Parity OK: {report.cycle_id}")
        else:
            logger.warning(
                f"Parity mismatch: {report.cycle_id} "
                f"severity={report.highest_severity.value}"
            )
        
        # Track mismatches for repeated detection
        if not report.overall_match:
            await self._track_mismatches(report)
        
        # Notify based on severity
        if report.highest_severity == MismatchSeverity.FATAL:
            for fc in report.failure_conditions:
                if self._telegram:
                    await self._telegram.notify_fatal_condition(fc, report)
        elif report.highest_severity in [MismatchSeverity.WARNING, MismatchSeverity.CRITICAL]:
            if self._telegram:
                await self._telegram.notify_parity_mismatch(report)
        
        # Notify if trading blocked
        if report.recommended_reaction == SystemReaction.BLOCK_TRADING:
            if self._telegram:
                await self._telegram.notify_trading_blocked(
                    reason="Parity validation failure",
                    report=report,
                )
    
    async def _track_mismatches(self, report: CycleParityReport) -> None:
        """Track mismatches for repeated detection."""
        now = datetime.utcnow()
        
        # Get all mismatched fields
        for comparison in [
            report.data_parity,
            report.feature_parity,
            report.decision_parity,
            report.execution_parity,
            report.accounting_parity,
        ]:
            if comparison and not comparison.is_match:
                for mismatch in comparison.mismatches:
                    if not mismatch.within_tolerance:
                        field_key = f"{comparison.domain.value}.{mismatch.field_name}"
                        
                        if field_key not in self._mismatch_history:
                            self._mismatch_history[field_key] = []
                        
                        # Clean old entries
                        self._mismatch_history[field_key] = [
                            t for t in self._mismatch_history[field_key]
                            if now - t < self._repeated_window
                        ]
                        
                        # Add current
                        self._mismatch_history[field_key].append(now)
                        
                        # Check threshold
                        if len(self._mismatch_history[field_key]) >= self._repeated_threshold:
                            if self._telegram:
                                await self._telegram.notify_repeated_mismatch(
                                    field_name=field_key,
                                    occurrence_count=len(self._mismatch_history[field_key]),
                                    window_minutes=int(self._repeated_window.total_seconds() / 60),
                                )
                            # Reset after notification
                            self._mismatch_history[field_key] = []
    
    async def on_drift_detected(
        self,
        report: DriftReport,
    ) -> None:
        """Handle drift detection."""
        if report.significant_drift_count > 0:
            logger.warning(
                f"Drift detected: {report.significant_drift_count} significant drifts"
            )
            
            if self._telegram:
                await self._telegram.notify_drift_detected(report)
    
    async def on_risk_escalated(
        self,
        current_level: str,
        new_level: str,
        reason: str,
    ) -> None:
        """Handle risk escalation."""
        logger.warning(f"Risk escalated: {current_level} -> {new_level}")
        
        if self._telegram:
            await self._telegram.notify_risk_escalated(
                current_level, new_level, reason
            )
    
    async def on_trading_blocked(
        self,
        reason: str,
        report: Optional[CycleParityReport] = None,
    ) -> None:
        """Handle trading block."""
        logger.critical(f"Trading blocked: {reason}")
        
        if self._telegram:
            await self._telegram.notify_trading_blocked(reason, report)
    
    async def send_daily_summary(
        self,
        summary: DailyParitySummary,
    ) -> None:
        """Send daily summary notification."""
        logger.info(
            f"Daily parity summary: {summary.matched_cycles}/{summary.total_cycles} "
            f"({summary.match_rate:.2f}% match rate)"
        )
        
        if self._telegram:
            await self._telegram.notify_daily_summary(summary)


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_rate_limiter(
    limits: Optional[Dict[NotificationType, tuple]] = None,
) -> NotificationRateLimiter:
    """Create a NotificationRateLimiter."""
    return NotificationRateLimiter(limits)


def create_telegram_notifier(
    bot_token: str,
    chat_id: str,
    enabled: bool = True,
    rate_limiter: Optional[NotificationRateLimiter] = None,
) -> TelegramNotifier:
    """Create a TelegramNotifier."""
    return TelegramNotifier(
        bot_token=bot_token,
        chat_id=chat_id,
        enabled=enabled,
        rate_limiter=rate_limiter,
    )


def create_notification_manager(
    telegram_bot_token: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
    telegram_enabled: bool = True,
) -> ParityNotificationManager:
    """Create a ParityNotificationManager."""
    telegram = None
    if telegram_bot_token and telegram_chat_id:
        telegram = create_telegram_notifier(
            bot_token=telegram_bot_token,
            chat_id=telegram_chat_id,
            enabled=telegram_enabled,
        )
    
    return ParityNotificationManager(telegram_notifier=telegram)
