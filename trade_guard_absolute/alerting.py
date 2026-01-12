"""
Trade Guard Absolute - Alerting.

============================================================
PURPOSE
============================================================
Telegram alerting for BLOCK decisions.

Every BLOCK decision triggers an immediate alert.
Alerts are rate-limited to prevent spam.

============================================================
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from dataclasses import dataclass

from .types import (
    GuardDecisionOutput,
    GuardDecision,
    BlockSeverity,
)
from .config import GuardAlertingConfig


logger = logging.getLogger(__name__)


# ============================================================
# ALERT MESSAGE TYPES
# ============================================================

@dataclass
class GuardAlert:
    """
    Alert message structure.
    """
    evaluation_id: str
    """Reference to the decision."""
    
    severity: BlockSeverity
    """Alert severity."""
    
    title: str
    """Alert title."""
    
    message: str
    """Full alert message."""
    
    symbol: str
    """Trading symbol."""
    
    reason_code: str
    """Block reason code."""
    
    timestamp: datetime
    """When the block occurred."""


# ============================================================
# ALERT FORMATTER
# ============================================================

class GuardAlertFormatter:
    """
    Formats guard decisions into alert messages.
    """
    
    # Severity emojis
    SEVERITY_EMOJI = {
        BlockSeverity.LOW: "⚠️",
        BlockSeverity.MEDIUM: "🟡",
        BlockSeverity.HIGH: "🟠",
        BlockSeverity.CRITICAL: "🔴",
        BlockSeverity.EMERGENCY: "🚨",
    }
    
    def format_alert(
        self,
        decision_output: GuardDecisionOutput,
    ) -> GuardAlert:
        """
        Format a decision into an alert.
        
        Args:
            decision_output: The BLOCK decision
            
        Returns:
            Formatted GuardAlert
        """
        severity = decision_output.severity or BlockSeverity.HIGH
        emoji = self.SEVERITY_EMOJI.get(severity, "⚠️")
        
        symbol = (
            decision_output.trade_intent.symbol
            if decision_output.trade_intent
            else "UNKNOWN"
        )
        
        reason_code = (
            decision_output.reason.value
            if decision_output.reason
            else "UNKNOWN"
        )
        
        category = (
            decision_output.category.value
            if decision_output.category
            else "UNKNOWN"
        )
        
        # Build title
        title = f"{emoji} TRADE BLOCKED [{severity.name}]"
        
        # Build message
        lines = [
            f"**🛡️ TRADE GUARD ABSOLUTE**",
            f"",
            f"**Decision:** BLOCK",
            f"**Symbol:** {symbol}",
            f"**Reason:** `{reason_code}`",
            f"**Category:** {category}",
            f"**Severity:** {severity.name}",
            f"",
        ]
        
        # Add details message
        if decision_output.details:
            detail_msg = decision_output.details.get("message", "")
            if detail_msg:
                lines.append(f"**Message:** {detail_msg}")
                lines.append("")
        
        # Add direction if available
        if decision_output.trade_intent and decision_output.trade_intent.direction:
            lines.append(f"**Direction:** {decision_output.trade_intent.direction}")
        
        # Add timing
        lines.append(f"**Eval Time:** {decision_output.evaluation_time_ms:.2f}ms")
        lines.append(f"**Time:** {decision_output.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        lines.append("")
        lines.append(f"ID: `{decision_output.evaluation_id}`")
        
        message = "\n".join(lines)
        
        return GuardAlert(
            evaluation_id=decision_output.evaluation_id,
            severity=severity,
            title=title,
            message=message,
            symbol=symbol,
            reason_code=reason_code,
            timestamp=decision_output.timestamp,
        )


# ============================================================
# RATE LIMITER
# ============================================================

class AlertRateLimiter:
    """
    Rate limits alerts to prevent spam.
    """
    
    def __init__(
        self,
        min_interval_seconds: int = 60,
        max_per_hour: int = 30,
    ):
        """
        Initialize rate limiter.
        
        Args:
            min_interval_seconds: Minimum time between similar alerts
            max_per_hour: Maximum alerts per hour
        """
        self._min_interval = timedelta(seconds=min_interval_seconds)
        self._max_per_hour = max_per_hour
        
        # Track alerts by reason code
        self._last_alert_by_reason: Dict[str, datetime] = {}
        
        # Track total alerts
        self._alert_timestamps: list = []
    
    def should_send(
        self,
        reason_code: str,
    ) -> bool:
        """
        Check if alert should be sent.
        
        Args:
            reason_code: The block reason code
            
        Returns:
            True if alert should be sent
        """
        now = datetime.utcnow()
        
        # Check total rate limit
        self._cleanup_old_timestamps()
        if len(self._alert_timestamps) >= self._max_per_hour:
            logger.warning("Alert rate limit exceeded")
            return False
        
        # Check per-reason rate limit
        last_alert = self._last_alert_by_reason.get(reason_code)
        if last_alert:
            if now - last_alert < self._min_interval:
                logger.debug(f"Rate limiting alert for {reason_code}")
                return False
        
        return True
    
    def record_sent(
        self,
        reason_code: str,
    ) -> None:
        """
        Record that an alert was sent.
        
        Args:
            reason_code: The block reason code
        """
        now = datetime.utcnow()
        self._last_alert_by_reason[reason_code] = now
        self._alert_timestamps.append(now)
    
    def _cleanup_old_timestamps(self) -> None:
        """Remove timestamps older than 1 hour."""
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=1)
        self._alert_timestamps = [
            ts for ts in self._alert_timestamps
            if ts > cutoff
        ]


# ============================================================
# TELEGRAM SENDER
# ============================================================

class TelegramAlertSender:
    """
    Sends alerts via Telegram.
    
    Uses the same Telegram infrastructure as other modules.
    """
    
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
    ):
        """
        Initialize Telegram sender.
        
        Args:
            bot_token: Telegram bot token
            chat_id: Telegram chat ID
        """
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._api_url = f"https://api.telegram.org/bot{bot_token}"
    
    async def send_alert_async(
        self,
        alert: GuardAlert,
    ) -> bool:
        """
        Send alert asynchronously.
        
        Args:
            alert: The alert to send
            
        Returns:
            True if sent successfully
        """
        try:
            import aiohttp
            
            url = f"{self._api_url}/sendMessage"
            payload = {
                "chat_id": self._chat_id,
                "text": alert.message,
                "parse_mode": "Markdown",
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"Sent guard alert: {alert.evaluation_id}")
                        return True
                    else:
                        text = await response.text()
                        logger.error(f"Telegram API error: {response.status} - {text}")
                        return False
        
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False
    
    def send_alert_sync(
        self,
        alert: GuardAlert,
    ) -> bool:
        """
        Send alert synchronously.
        
        Args:
            alert: The alert to send
            
        Returns:
            True if sent successfully
        """
        try:
            import requests
            
            url = f"{self._api_url}/sendMessage"
            payload = {
                "chat_id": self._chat_id,
                "text": alert.message,
                "parse_mode": "Markdown",
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Sent guard alert: {alert.evaluation_id}")
                return True
            else:
                logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                return False
        
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False


# ============================================================
# GUARD ALERTER
# ============================================================

class GuardAlerter:
    """
    Main alerting class for Trade Guard Absolute.
    
    Combines formatting, rate limiting, and sending.
    """
    
    def __init__(
        self,
        config: GuardAlertingConfig,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        """
        Initialize alerter.
        
        Args:
            config: Alerting configuration
            bot_token: Telegram bot token
            chat_id: Telegram chat ID
        """
        self._config = config
        self._formatter = GuardAlertFormatter()
        self._rate_limiter = AlertRateLimiter(
            min_interval_seconds=config.min_alert_interval_seconds,
            max_per_hour=config.max_alerts_per_hour,
        )
        
        self._telegram_sender: Optional[TelegramAlertSender] = None
        if config.telegram_enabled and bot_token and chat_id:
            self._telegram_sender = TelegramAlertSender(
                bot_token=bot_token,
                chat_id=chat_id,
            )
    
    def alert_on_block(
        self,
        decision_output: GuardDecisionOutput,
    ) -> bool:
        """
        Send alert for a BLOCK decision.
        
        Args:
            decision_output: The BLOCK decision
            
        Returns:
            True if alert was sent (or rate limited), False on error
        """
        # Skip if alerting disabled
        if not self._config.enabled:
            return True
        
        # Skip if not a BLOCK
        if decision_output.decision != GuardDecision.BLOCK:
            return True
        
        # Skip if not alerting on blocks
        if not self._config.alert_on_block:
            return True
        
        # Check severity threshold
        severity = decision_output.severity or BlockSeverity.LOW
        if severity.value < self._config.min_severity_for_alert:
            logger.debug(f"Skipping alert - severity {severity.name} below threshold")
            return True
        
        # Format alert
        alert = self._formatter.format_alert(decision_output)
        
        # Check rate limit
        if not self._rate_limiter.should_send(alert.reason_code):
            logger.debug(f"Alert rate limited: {alert.reason_code}")
            return True  # Rate limited is not an error
        
        # Send alert
        sent = False
        
        if self._telegram_sender:
            sent = self._telegram_sender.send_alert_sync(alert)
            if sent:
                self._rate_limiter.record_sent(alert.reason_code)
        else:
            # No sender configured - log only
            logger.warning(f"Guard BLOCK (no sender configured): {alert.message}")
            sent = True
        
        return sent
    
    async def alert_on_block_async(
        self,
        decision_output: GuardDecisionOutput,
    ) -> bool:
        """
        Send alert asynchronously.
        
        Args:
            decision_output: The BLOCK decision
            
        Returns:
            True if alert was sent
        """
        # Skip checks same as sync version
        if not self._config.enabled:
            return True
        
        if decision_output.decision != GuardDecision.BLOCK:
            return True
        
        if not self._config.alert_on_block:
            return True
        
        severity = decision_output.severity or BlockSeverity.LOW
        if severity.value < self._config.min_severity_for_alert:
            return True
        
        alert = self._formatter.format_alert(decision_output)
        
        if not self._rate_limiter.should_send(alert.reason_code):
            return True
        
        sent = False
        
        if self._telegram_sender:
            sent = await self._telegram_sender.send_alert_async(alert)
            if sent:
                self._rate_limiter.record_sent(alert.reason_code)
        else:
            logger.warning(f"Guard BLOCK (no sender): {alert.message}")
            sent = True
        
        return sent
