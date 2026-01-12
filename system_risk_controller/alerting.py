"""
System Risk Controller - Alerting.

============================================================
PURPOSE
============================================================
Send immediate alerts for halt events via Telegram.

ON ANY HALT EVENT:
1. Persist halt reason (repository)
2. Send immediate Telegram alert (this module)

ALERT LEVELS:
- SOFT: Warning notification
- HARD: Critical alert with details
- EMERGENCY: URGENT alert with all details + action required

============================================================
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum

from .types import (
    SystemState,
    HaltLevel,
    HaltTrigger,
    HaltEvent,
    StateTransition,
)
from .config import AlertingConfig


logger = logging.getLogger(__name__)


# ============================================================
# ALERT TYPES
# ============================================================

class AlertPriority(Enum):
    """Alert priority levels."""
    
    LOW = "low"
    """Informational only."""
    
    MEDIUM = "medium"
    """Warning, requires attention."""
    
    HIGH = "high"
    """Critical, requires immediate attention."""
    
    URGENT = "urgent"
    """Emergency, requires immediate action."""


@dataclass
class Alert:
    """Alert to be sent."""
    
    priority: AlertPriority
    """Alert priority."""
    
    title: str
    """Alert title."""
    
    message: str
    """Alert message."""
    
    details: Dict[str, Any] = field(default_factory=dict)
    """Additional details."""
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """When alert was created."""
    
    halt_event: Optional[HaltEvent] = None
    """Related halt event."""
    
    state_transition: Optional[StateTransition] = None
    """Related state transition."""


# ============================================================
# ALERT FORMATTERS
# ============================================================

def format_halt_event_alert(event: HaltEvent) -> Alert:
    """
    Format a halt event as an alert.
    
    Args:
        event: Halt event
        
    Returns:
        Formatted alert
    """
    # Determine priority
    priority_map = {
        HaltLevel.SOFT: AlertPriority.MEDIUM,
        HaltLevel.HARD: AlertPriority.HIGH,
        HaltLevel.EMERGENCY: AlertPriority.URGENT,
    }
    priority = priority_map.get(event.halt_level, AlertPriority.HIGH)
    
    # Format title
    emoji_map = {
        HaltLevel.SOFT: "⚠️",
        HaltLevel.HARD: "🛑",
        HaltLevel.EMERGENCY: "🚨",
    }
    emoji = emoji_map.get(event.halt_level, "⚠️")
    title = f"{emoji} HALT: {event.halt_level.name}"
    
    # Format message
    lines = [
        f"**Trigger:** `{event.trigger.value}`",
        f"**Level:** {event.halt_level.name}",
        f"**Time:** {event.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"**Source:** {event.source_monitor}",
        f"",
        f"**Message:**",
        event.message,
    ]
    
    if event.details:
        lines.append("")
        lines.append("**Details:**")
        for key, value in event.details.items():
            lines.append(f"• {key}: {value}")
    
    message = "\n".join(lines)
    
    return Alert(
        priority=priority,
        title=title,
        message=message,
        details=event.details or {},
        timestamp=event.timestamp,
        halt_event=event,
    )


def format_state_transition_alert(transition: StateTransition) -> Alert:
    """
    Format a state transition as an alert.
    
    Args:
        transition: State transition
        
    Returns:
        Formatted alert
    """
    # Determine priority based on target state
    priority_map = {
        SystemState.RUNNING: AlertPriority.LOW,
        SystemState.DEGRADED: AlertPriority.MEDIUM,
        SystemState.HALTED_SOFT: AlertPriority.MEDIUM,
        SystemState.HALTED_HARD: AlertPriority.HIGH,
        SystemState.EMERGENCY_LOCKDOWN: AlertPriority.URGENT,
    }
    priority = priority_map.get(transition.to_state, AlertPriority.HIGH)
    
    # Format title
    if transition.to_state == SystemState.RUNNING:
        emoji = "✅"
        title = f"{emoji} SYSTEM RESUMED"
    elif transition.to_state == SystemState.EMERGENCY_LOCKDOWN:
        emoji = "🚨"
        title = f"{emoji} EMERGENCY LOCKDOWN"
    elif transition.to_state in {SystemState.HALTED_SOFT, SystemState.HALTED_HARD}:
        emoji = "🛑"
        title = f"{emoji} SYSTEM HALTED"
    else:
        emoji = "ℹ️"
        title = f"{emoji} STATE CHANGE"
    
    # Format message
    lines = [
        f"**From:** {transition.from_state.value}",
        f"**To:** {transition.to_state.value}",
        f"**Time:** {transition.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"**Automatic:** {'Yes' if transition.is_automatic else 'No'}",
        f"",
        f"**Reason:**",
        transition.reason,
    ]
    
    if transition.trigger:
        lines.insert(3, f"**Trigger:** `{transition.trigger.value}`")
    
    message = "\n".join(lines)
    
    return Alert(
        priority=priority,
        title=title,
        message=message,
        details={
            "from_state": transition.from_state.value,
            "to_state": transition.to_state.value,
            "trigger": transition.trigger.value if transition.trigger else None,
        },
        timestamp=transition.timestamp,
        state_transition=transition,
    )


def format_resume_alert(
    operator: str,
    from_state: SystemState,
    success: bool,
    error: Optional[str] = None,
) -> Alert:
    """
    Format a resume attempt as an alert.
    
    Args:
        operator: Operator name
        from_state: State before resume
        success: Whether resume succeeded
        error: Error message if failed
        
    Returns:
        Formatted alert
    """
    if success:
        priority = AlertPriority.LOW
        emoji = "✅"
        title = f"{emoji} RESUME SUCCESSFUL"
        message = f"**Operator:** {operator}\n**From:** {from_state.value}\n**To:** RUNNING"
    else:
        priority = AlertPriority.HIGH
        emoji = "❌"
        title = f"{emoji} RESUME FAILED"
        message = f"**Operator:** {operator}\n**From:** {from_state.value}\n**Error:** {error}"
    
    return Alert(
        priority=priority,
        title=title,
        message=message,
        details={
            "operator": operator,
            "from_state": from_state.value,
            "success": success,
            "error": error,
        },
    )


# ============================================================
# ALERT SENDER INTERFACE
# ============================================================

class AlertSender(ABC):
    """Abstract interface for sending alerts."""
    
    @abstractmethod
    async def send(self, alert: Alert) -> bool:
        """
        Send an alert.
        
        Args:
            alert: Alert to send
            
        Returns:
            True if sent successfully
        """
        pass


# ============================================================
# TELEGRAM ALERT SENDER
# ============================================================

class TelegramAlertSender(AlertSender):
    """
    Sends alerts via Telegram.
    
    Uses the Telegram Bot API to send messages.
    """
    
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        parse_mode: str = "Markdown",
    ):
        """
        Initialize Telegram sender.
        
        Args:
            bot_token: Telegram bot token
            chat_id: Chat ID to send to
            parse_mode: Message parse mode
        """
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._parse_mode = parse_mode
        self._api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    async def send(self, alert: Alert) -> bool:
        """Send alert via Telegram."""
        try:
            import aiohttp
            
            # Format message
            text = f"*{alert.title}*\n\n{alert.message}"
            
            # Truncate if too long
            max_length = 4096
            if len(text) > max_length:
                text = text[:max_length - 3] + "..."
            
            payload = {
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": self._parse_mode,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self._api_url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Telegram alert sent: {alert.title}")
                        return True
                    else:
                        error = await response.text()
                        logger.error(f"Telegram send failed: {error}")
                        return False
                        
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False


# ============================================================
# CONSOLE ALERT SENDER (for testing)
# ============================================================

class ConsoleAlertSender(AlertSender):
    """
    Sends alerts to console (for testing/development).
    """
    
    async def send(self, alert: Alert) -> bool:
        """Print alert to console."""
        separator = "=" * 60
        print(f"\n{separator}")
        print(f"ALERT: {alert.priority.value.upper()}")
        print(separator)
        print(f"Title: {alert.title}")
        print(f"Time: {alert.timestamp}")
        print(f"Message:\n{alert.message}")
        if alert.details:
            print(f"Details: {alert.details}")
        print(separator)
        return True


# ============================================================
# ALERTING SERVICE
# ============================================================

class AlertingService:
    """
    Alerting service for System Risk Controller.
    
    Manages alert sending with:
    - Rate limiting
    - Deduplication
    - Priority handling
    - Retry logic
    """
    
    def __init__(
        self,
        config: AlertingConfig,
        senders: Optional[List[AlertSender]] = None,
    ):
        """
        Initialize alerting service.
        
        Args:
            config: Alerting configuration
            senders: List of alert senders
        """
        self._config = config
        self._senders = senders or []
        
        # Deduplication: track recent alerts
        self._recent_alerts: Dict[str, datetime] = {}
        
        # Rate limiting
        self._last_alert_time: Optional[datetime] = None
    
    def add_sender(self, sender: AlertSender) -> None:
        """Add an alert sender."""
        self._senders.append(sender)
    
    async def alert_halt_event(self, event: HaltEvent) -> None:
        """
        Send alert for a halt event.
        
        Args:
            event: Halt event to alert
        """
        if not self._config.telegram_enabled:
            return
        
        alert = format_halt_event_alert(event)
        await self._send_alert(alert)
    
    async def alert_state_transition(self, transition: StateTransition) -> None:
        """
        Send alert for a state transition.
        
        Args:
            transition: State transition to alert
        """
        if not self._config.telegram_enabled:
            return
        
        # Don't alert for minor transitions
        if (
            transition.from_state == SystemState.RUNNING
            and transition.to_state == SystemState.DEGRADED
            and not self._config.alert_on_degraded
        ):
            return
        
        alert = format_state_transition_alert(transition)
        await self._send_alert(alert)
    
    async def alert_resume(
        self,
        operator: str,
        from_state: SystemState,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """
        Send alert for a resume attempt.
        
        Args:
            operator: Operator name
            from_state: State before resume
            success: Whether resume succeeded
            error: Error message if failed
        """
        if not self._config.telegram_enabled:
            return
        
        alert = format_resume_alert(operator, from_state, success, error)
        await self._send_alert(alert)
    
    async def _send_alert(self, alert: Alert) -> None:
        """Send alert through all configured senders."""
        # Check deduplication
        alert_key = f"{alert.title}:{alert.message[:100]}"
        now = datetime.utcnow()
        
        if alert_key in self._recent_alerts:
            last_sent = self._recent_alerts[alert_key]
            min_interval = timedelta(minutes=self._config.repeat_critical_alert_minutes)
            
            if now - last_sent < min_interval:
                logger.debug(f"Skipping duplicate alert: {alert.title}")
                return
        
        # Send through all senders
        for sender in self._senders:
            try:
                await sender.send(alert)
            except Exception as e:
                logger.error(f"Alert sender failed: {e}")
        
        # Update deduplication cache
        self._recent_alerts[alert_key] = now
        
        # Cleanup old entries
        self._cleanup_recent_alerts()
    
    def _cleanup_recent_alerts(self) -> None:
        """Remove old entries from deduplication cache."""
        now = datetime.utcnow()
        expiry = timedelta(hours=1)
        
        expired = [
            key for key, timestamp in self._recent_alerts.items()
            if now - timestamp > expiry
        ]
        
        for key in expired:
            del self._recent_alerts[key]
