"""
Execution Engine - Alerting.

============================================================
PURPOSE
============================================================
Sends alerts for execution events via Telegram.

ALERT TYPES:
- Execution failures
- Reconciliation mismatches
- Slippage warnings
- System state changes
- Critical errors

SAFETY REQUIREMENTS:
- All abnormal events must be alerted immediately
- No silent failures
- Rate limiting to prevent spam

============================================================
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

import aiohttp


logger = logging.getLogger(__name__)


# ============================================================
# ALERT TYPES
# ============================================================

class AlertSeverity(Enum):
    """Alert severity levels."""
    
    INFO = "INFO"
    """Informational."""
    
    WARNING = "WARNING"
    """Warning, needs attention."""
    
    ERROR = "ERROR"
    """Error condition."""
    
    CRITICAL = "CRITICAL"
    """Critical, immediate attention required."""


class AlertType(Enum):
    """Types of alerts."""
    
    EXECUTION_FAILED = "EXECUTION_FAILED"
    """Order execution failed."""
    
    EXECUTION_REJECTED = "EXECUTION_REJECTED"
    """Order rejected by exchange."""
    
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    """Order execution timed out."""
    
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    """State mismatch detected."""
    
    SLIPPAGE_WARNING = "SLIPPAGE_WARNING"
    """Excessive slippage detected."""
    
    PARTIAL_FILL = "PARTIAL_FILL"
    """Order partially filled."""
    
    RATE_LIMITED = "RATE_LIMITED"
    """Rate limit hit."""
    
    CONNECTION_ERROR = "CONNECTION_ERROR"
    """Exchange connection error."""
    
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    """Authentication failed."""
    
    SYSTEM_ERROR = "SYSTEM_ERROR"
    """Internal system error."""


@dataclass
class Alert:
    """An alert to be sent."""
    
    alert_type: AlertType
    """Type of alert."""
    
    severity: AlertSeverity
    """Severity level."""
    
    message: str
    """Alert message."""
    
    details: Dict[str, Any] = field(default_factory=dict)
    """Additional details."""
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """When alert was created."""
    
    order_id: Optional[str] = None
    """Related order ID."""
    
    symbol: Optional[str] = None
    """Related symbol."""


# ============================================================
# ALERT CONFIGURATION
# ============================================================

@dataclass
class ExecutionAlertingConfig:
    """Configuration for execution alerting."""
    
    enabled: bool = True
    """Whether alerting is enabled."""
    
    telegram_bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    """Environment variable for Telegram bot token."""
    
    telegram_chat_id_env: str = "TELEGRAM_CHAT_ID"
    """Environment variable for Telegram chat ID."""
    
    # Rate limiting
    min_interval_seconds: float = 5.0
    """Minimum interval between alerts."""
    
    max_alerts_per_minute: int = 10
    """Maximum alerts per minute."""
    
    # Severity filters
    min_severity: AlertSeverity = AlertSeverity.WARNING
    """Minimum severity to alert."""
    
    # Aggregation
    aggregate_similar: bool = True
    """Whether to aggregate similar alerts."""
    
    aggregation_window_seconds: float = 60.0
    """Window for aggregating similar alerts."""


# ============================================================
# TELEGRAM ALERTER
# ============================================================

class TelegramAlerter:
    """
    Sends alerts via Telegram.
    
    Features:
    - Rate limiting
    - Alert aggregation
    - Severity filtering
    """
    
    def __init__(self, config: ExecutionAlertingConfig):
        """
        Initialize Telegram alerter.
        
        Args:
            config: Alerting configuration
        """
        self._config = config
        
        # Get credentials
        self._bot_token = os.environ.get(config.telegram_bot_token_env, "")
        self._chat_id = os.environ.get(config.telegram_chat_id_env, "")
        
        # Rate limiting
        self._last_alert_time: Optional[datetime] = None
        self._alerts_this_minute: List[datetime] = []
        
        # Aggregation
        self._pending_alerts: Dict[str, List[Alert]] = {}
        
        # HTTP session
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Alert history
        self._history: List[Alert] = []
        self._max_history = 100
    
    @property
    def is_configured(self) -> bool:
        """Check if Telegram is configured."""
        return bool(self._bot_token and self._chat_id)
    
    async def send_alert(self, alert: Alert) -> bool:
        """
        Send an alert.
        
        Args:
            alert: Alert to send
            
        Returns:
            Whether alert was sent
        """
        if not self._config.enabled:
            return False
        
        # Check severity
        if self._severity_value(alert.severity) < self._severity_value(self._config.min_severity):
            return False
        
        # Store in history
        self._history.append(alert)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        
        # Check rate limiting
        if not self._can_send():
            logger.warning(f"Alert rate limited: {alert.message}")
            return False
        
        # Check aggregation
        if self._config.aggregate_similar:
            key = self._get_aggregation_key(alert)
            if key in self._pending_alerts:
                self._pending_alerts[key].append(alert)
                return False  # Will be sent with aggregation
            else:
                self._pending_alerts[key] = [alert]
                # Schedule aggregated send
                asyncio.create_task(self._send_aggregated(key))
                return True
        else:
            return await self._send_telegram(alert)
    
    async def _send_aggregated(self, key: str) -> None:
        """Send aggregated alerts after delay."""
        await asyncio.sleep(self._config.aggregation_window_seconds)
        
        alerts = self._pending_alerts.pop(key, [])
        if not alerts:
            return
        
        if len(alerts) == 1:
            await self._send_telegram(alerts[0])
        else:
            # Send aggregated
            first = alerts[0]
            message = f"🔔 {len(alerts)}x {first.alert_type.value}\n"
            message += f"Severity: {first.severity.value}\n"
            message += f"First: {first.message}\n"
            message += f"Count: {len(alerts)} in last {self._config.aggregation_window_seconds}s"
            
            aggregated = Alert(
                alert_type=first.alert_type,
                severity=first.severity,
                message=message,
            )
            await self._send_telegram(aggregated)
    
    async def _send_telegram(self, alert: Alert) -> bool:
        """Send alert via Telegram API."""
        if not self.is_configured:
            logger.debug(f"Telegram not configured, logging alert: {alert.message}")
            return False
        
        # Build message
        emoji = self._get_severity_emoji(alert.severity)
        message = self._format_message(alert, emoji)
        
        try:
            if self._session is None:
                self._session = aiohttp.ClientSession()
            
            url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
            payload = {
                "chat_id": self._chat_id,
                "text": message,
                "parse_mode": "HTML",
            }
            
            async with self._session.post(url, json=payload) as response:
                if response.status == 200:
                    self._record_sent()
                    logger.info(f"Alert sent: {alert.alert_type.value}")
                    return True
                else:
                    body = await response.text()
                    logger.error(f"Telegram API error {response.status}: {body}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False
    
    def _format_message(self, alert: Alert, emoji: str) -> str:
        """Format alert message for Telegram."""
        lines = [
            f"{emoji} <b>{alert.alert_type.value}</b>",
            f"<b>Severity:</b> {alert.severity.value}",
            f"<b>Time:</b> {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC",
            "",
            alert.message,
        ]
        
        if alert.order_id:
            lines.append(f"\n<b>Order:</b> <code>{alert.order_id[:8]}...</code>")
        
        if alert.symbol:
            lines.append(f"<b>Symbol:</b> {alert.symbol}")
        
        if alert.details:
            lines.append("\n<b>Details:</b>")
            for key, value in alert.details.items():
                lines.append(f"  • {key}: {value}")
        
        return "\n".join(lines)
    
    def _get_severity_emoji(self, severity: AlertSeverity) -> str:
        """Get emoji for severity level."""
        return {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.ERROR: "❌",
            AlertSeverity.CRITICAL: "🚨",
        }.get(severity, "📢")
    
    def _severity_value(self, severity: AlertSeverity) -> int:
        """Get numeric value for severity."""
        return {
            AlertSeverity.INFO: 0,
            AlertSeverity.WARNING: 1,
            AlertSeverity.ERROR: 2,
            AlertSeverity.CRITICAL: 3,
        }.get(severity, 0)
    
    def _get_aggregation_key(self, alert: Alert) -> str:
        """Get aggregation key for alert."""
        return f"{alert.alert_type.value}:{alert.severity.value}:{alert.symbol or ''}"
    
    def _can_send(self) -> bool:
        """Check if we can send an alert (rate limiting)."""
        now = datetime.utcnow()
        
        # Check minimum interval
        if self._last_alert_time:
            elapsed = (now - self._last_alert_time).total_seconds()
            if elapsed < self._config.min_interval_seconds:
                return False
        
        # Check alerts per minute
        minute_ago = now - timedelta(minutes=1)
        self._alerts_this_minute = [
            t for t in self._alerts_this_minute if t > minute_ago
        ]
        
        if len(self._alerts_this_minute) >= self._config.max_alerts_per_minute:
            return False
        
        return True
    
    def _record_sent(self) -> None:
        """Record that an alert was sent."""
        now = datetime.utcnow()
        self._last_alert_time = now
        self._alerts_this_minute.append(now)
    
    def get_history(self, limit: int = 10) -> List[Alert]:
        """Get alert history."""
        return self._history[-limit:]
    
    async def close(self) -> None:
        """Close HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None


# ============================================================
# ALERT HELPER FUNCTIONS
# ============================================================

def create_execution_failed_alert(
    order_id: str,
    symbol: str,
    error_message: str,
    error_code: str = None,
) -> Alert:
    """Create an execution failed alert."""
    return Alert(
        alert_type=AlertType.EXECUTION_FAILED,
        severity=AlertSeverity.ERROR,
        message=f"Order execution failed: {error_message}",
        order_id=order_id,
        symbol=symbol,
        details={
            "error_code": error_code or "UNKNOWN",
        },
    )


def create_execution_rejected_alert(
    order_id: str,
    symbol: str,
    reason: str,
) -> Alert:
    """Create an execution rejected alert."""
    return Alert(
        alert_type=AlertType.EXECUTION_REJECTED,
        severity=AlertSeverity.WARNING,
        message=f"Order rejected: {reason}",
        order_id=order_id,
        symbol=symbol,
    )


def create_slippage_alert(
    order_id: str,
    symbol: str,
    expected_price: str,
    actual_price: str,
    slippage_pct: float,
) -> Alert:
    """Create a slippage warning alert."""
    severity = AlertSeverity.CRITICAL if slippage_pct > 2.0 else AlertSeverity.WARNING
    
    return Alert(
        alert_type=AlertType.SLIPPAGE_WARNING,
        severity=severity,
        message=f"Excessive slippage: {slippage_pct:.2f}%",
        order_id=order_id,
        symbol=symbol,
        details={
            "expected_price": expected_price,
            "actual_price": actual_price,
            "slippage_pct": f"{slippage_pct:.2f}%",
        },
    )


def create_reconciliation_alert(
    mismatch_type: str,
    order_id: str,
    symbol: str,
    message: str,
    severity: AlertSeverity = AlertSeverity.WARNING,
) -> Alert:
    """Create a reconciliation mismatch alert."""
    return Alert(
        alert_type=AlertType.RECONCILIATION_MISMATCH,
        severity=severity,
        message=message,
        order_id=order_id,
        symbol=symbol,
        details={
            "mismatch_type": mismatch_type,
        },
    )


def create_system_error_alert(
    error_message: str,
    component: str = "ExecutionEngine",
) -> Alert:
    """Create a system error alert."""
    return Alert(
        alert_type=AlertType.SYSTEM_ERROR,
        severity=AlertSeverity.CRITICAL,
        message=f"System error in {component}: {error_message}",
        details={
            "component": component,
        },
    )
