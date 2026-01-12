"""
Risk Scoring Engine - Alerting.

============================================================
PURPOSE
============================================================
Alerting integration for risk state changes.

Provides:
- Telegram notifications on risk escalation
- Alert formatting with context
- Rate limiting to prevent spam
- Alert tracking for persistence

============================================================
ALERT PHILOSOPHY
============================================================
- Alert on escalation to HIGH or CRITICAL
- Include actionable context
- Rate limit to prevent alert fatigue
- Track sent alerts for audit

============================================================
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Protocol
from dataclasses import dataclass, field

from .types import (
    RiskScoringOutput,
    RiskStateChange,
    RiskLevel,
    RiskDimension,
    RiskState,
)
from .config import AlertingConfig


# ============================================================
# ALERT MESSAGE DATACLASS
# ============================================================


@dataclass(frozen=True)
class RiskAlert:
    """
    Structured alert message for risk events.
    
    ============================================================
    FIELDS
    ============================================================
    - alert_type: Type of alert (ESCALATION, DE_ESCALATION, LEVEL_CHANGE)
    - severity: HIGH, CRITICAL
    - title: Short title
    - message: Detailed message
    - timestamp: When the alert was created
    - context: Additional structured data
    
    ============================================================
    """
    
    alert_type: str
    severity: str
    title: str
    message: str
    timestamp: datetime
    risk_level: RiskLevel
    total_score: int
    state_changes: List[RiskStateChange] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_telegram_message(self, include_details: bool = True) -> str:
        """
        Format alert for Telegram.
        
        Args:
            include_details: Whether to include detailed breakdown
        
        Returns:
            Formatted message string with Telegram markdown
        """
        # Emoji based on severity
        emoji = "🔴" if self.severity == "CRITICAL" else "🟠" if self.severity == "HIGH" else "🟡"
        
        lines = [
            f"{emoji} *RISK ALERT*",
            f"",
            f"*Level:* {self.risk_level.name}",
            f"*Score:* {self.total_score}/8",
            f"*Time:* {self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ]
        
        if include_details and self.state_changes:
            lines.append("")
            lines.append("*Changes:*")
            for change in self.state_changes:
                direction = "⬆️" if change.new_state.value > change.old_state.value else "⬇️"
                lines.append(
                    f"  {direction} {change.dimension.name}: "
                    f"{change.old_state.name} → {change.new_state.name}"
                )
        
        if include_details:
            lines.append("")
            lines.append(f"*Reason:* {self.message}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "alert_type": self.alert_type,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "risk_level": self.risk_level.name,
            "total_score": self.total_score,
            "state_changes": [
                {
                    "dimension": c.dimension.name,
                    "old_state": c.old_state.name,
                    "new_state": c.new_state.name,
                    "reason": c.reason,
                }
                for c in self.state_changes
            ],
            "context": self.context,
        }


# ============================================================
# ALERT SENDER PROTOCOL
# ============================================================


class AlertSender(Protocol):
    """
    Protocol for alert sending implementations.
    
    Allows for different alert destinations:
    - Telegram
    - Slack
    - Email
    - Webhook
    """
    
    async def send(self, alert: RiskAlert) -> bool:
        """
        Send an alert.
        
        Args:
            alert: The alert to send
        
        Returns:
            True if sent successfully
        """
        ...


# ============================================================
# TELEGRAM ALERT SENDER
# ============================================================


class TelegramAlertSender:
    """
    Send risk alerts via Telegram.
    
    ============================================================
    USAGE
    ============================================================
    Requires a Telegram bot token and chat ID.
    The bot must be added to the chat.
    
    ============================================================
    """
    
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        include_details: bool = True
    ):
        """
        Initialize Telegram sender.
        
        Args:
            bot_token: Telegram bot token
            chat_id: Target chat/channel ID
            include_details: Include detailed breakdown in messages
        """
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._include_details = include_details
    
    async def send(self, alert: RiskAlert) -> bool:
        """
        Send alert via Telegram.
        
        Args:
            alert: The alert to send
        
        Returns:
            True if sent successfully
        """
        try:
            import httpx
            
            message = alert.to_telegram_message(include_details=self._include_details)
            
            url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
            payload = {
                "chat_id": self._chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)
                return response.status_code == 200
                
        except Exception:
            # Log error but don't crash
            return False


# ============================================================
# CONSOLE ALERT SENDER (FOR TESTING)
# ============================================================


class ConsoleAlertSender:
    """
    Print alerts to console (for development/testing).
    """
    
    async def send(self, alert: RiskAlert) -> bool:
        """Print alert to console."""
        print("=" * 50)
        print("RISK ALERT")
        print("=" * 50)
        print(f"Severity: {alert.severity}")
        print(f"Level: {alert.risk_level.name}")
        print(f"Score: {alert.total_score}/8")
        print(f"Message: {alert.message}")
        print("=" * 50)
        return True


# ============================================================
# RATE LIMITER
# ============================================================


class AlertRateLimiter:
    """
    Rate limits alerts to prevent spam.
    
    ============================================================
    LOGIC
    ============================================================
    - Track last alert time per dimension
    - Enforce minimum interval between alerts
    - Always allow CRITICAL alerts
    
    ============================================================
    """
    
    def __init__(self, min_interval_seconds: float = 300.0):
        """
        Initialize rate limiter.
        
        Args:
            min_interval_seconds: Minimum seconds between alerts
        """
        self._min_interval = timedelta(seconds=min_interval_seconds)
        self._last_alerts: Dict[str, datetime] = {}
    
    def should_send(
        self,
        dimension: RiskDimension,
        severity: str,
        now: Optional[datetime] = None
    ) -> bool:
        """
        Check if an alert should be sent.
        
        Args:
            dimension: Risk dimension
            severity: Alert severity
            now: Current time (defaults to utcnow)
        
        Returns:
            True if alert should be sent
        """
        now = now or datetime.utcnow()
        
        # Always send CRITICAL alerts
        if severity == "CRITICAL":
            return True
        
        # Check rate limit for this dimension
        key = dimension.name
        last_alert = self._last_alerts.get(key)
        
        if last_alert is None:
            return True
        
        return (now - last_alert) >= self._min_interval
    
    def record_sent(
        self,
        dimension: RiskDimension,
        now: Optional[datetime] = None
    ) -> None:
        """
        Record that an alert was sent.
        
        Args:
            dimension: Risk dimension
            now: Current time (defaults to utcnow)
        """
        self._last_alerts[dimension.name] = now or datetime.utcnow()
    
    def reset(self) -> None:
        """Clear all rate limit state."""
        self._last_alerts.clear()


# ============================================================
# RISK ALERTING SERVICE
# ============================================================


class RiskAlertingService:
    """
    Main service for processing and sending risk alerts.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    1. Determine if alert should be sent
    2. Build alert messages
    3. Rate limit alerts
    4. Send via configured senders
    
    ============================================================
    """
    
    def __init__(
        self,
        config: Optional[AlertingConfig] = None,
        senders: Optional[List[AlertSender]] = None
    ):
        """
        Initialize alerting service.
        
        Args:
            config: Alerting configuration
            senders: List of alert senders
        """
        self._config = config or AlertingConfig()
        self._senders = senders or []
        self._rate_limiter = AlertRateLimiter(
            min_interval_seconds=self._config.min_seconds_between_alerts
        )
    
    def add_sender(self, sender: AlertSender) -> None:
        """Add an alert sender."""
        self._senders.append(sender)
    
    def should_alert(self, output: RiskScoringOutput) -> bool:
        """
        Determine if this output warrants an alert.
        
        Args:
            output: Risk scoring output
        
        Returns:
            True if alert should be sent
        """
        # Check if we alert on this level
        if output.risk_level == RiskLevel.CRITICAL:
            return self._config.alert_on_critical
        elif output.risk_level == RiskLevel.HIGH:
            return self._config.alert_on_high
        
        # Check for state changes
        if output.state_changes:
            # Check for escalations
            for change in output.state_changes:
                if change.new_state.value > change.old_state.value:
                    return True
            
            # Check for de-escalations if configured
            if self._config.alert_on_de_escalation:
                for change in output.state_changes:
                    if change.new_state.value < change.old_state.value:
                        return True
        
        return False
    
    def build_alert(
        self,
        output: RiskScoringOutput,
        previous_level: Optional[RiskLevel] = None
    ) -> RiskAlert:
        """
        Build an alert from a risk scoring output.
        
        Args:
            output: Risk scoring output
            previous_level: Previous risk level (for comparison)
        
        Returns:
            RiskAlert ready to send
        """
        # Determine severity
        if output.risk_level == RiskLevel.CRITICAL:
            severity = "CRITICAL"
        elif output.risk_level == RiskLevel.HIGH:
            severity = "HIGH"
        else:
            severity = "MEDIUM"
        
        # Determine alert type
        if previous_level and output.risk_level.value > previous_level.value:
            alert_type = "ESCALATION"
        elif previous_level and output.risk_level.value < previous_level.value:
            alert_type = "DE_ESCALATION"
        else:
            alert_type = "LEVEL_CHANGE"
        
        # Build message
        if output.state_changes:
            primary_change = output.state_changes[0]
            message = primary_change.reason
        else:
            # Build message from assessments
            dangerous_dimensions = []
            for assessment in [
                output.market_assessment,
                output.liquidity_assessment,
                output.volatility_assessment,
                output.system_integrity_assessment,
            ]:
                if assessment.state == RiskState.DANGEROUS:
                    dangerous_dimensions.append(assessment.dimension.name)
            
            if dangerous_dimensions:
                message = f"Dangerous state in: {', '.join(dangerous_dimensions)}"
            else:
                message = f"Risk level at {output.risk_level.name}"
        
        return RiskAlert(
            alert_type=alert_type,
            severity=severity,
            title=f"Risk {alert_type}: {output.risk_level.name}",
            message=message,
            timestamp=output.timestamp or datetime.utcnow(),
            risk_level=output.risk_level,
            total_score=output.total_score,
            state_changes=output.state_changes or [],
            context={
                "market_state": output.market_assessment.state.name,
                "liquidity_state": output.liquidity_assessment.state.name,
                "volatility_state": output.volatility_assessment.state.name,
                "system_integrity_state": output.system_integrity_assessment.state.name,
            }
        )
    
    async def process_output(
        self,
        output: RiskScoringOutput,
        previous_level: Optional[RiskLevel] = None
    ) -> Optional[RiskAlert]:
        """
        Process a risk scoring output and send alerts if needed.
        
        Args:
            output: Risk scoring output
            previous_level: Previous risk level
        
        Returns:
            RiskAlert if sent, None otherwise
        """
        if not self.should_alert(output):
            return None
        
        # Build alert
        alert = self.build_alert(output, previous_level)
        
        # Check rate limiting
        severity = alert.severity
        
        # Find primary dimension for rate limiting
        if output.state_changes:
            primary_dimension = output.state_changes[0].dimension
        else:
            primary_dimension = RiskDimension.SYSTEM_INTEGRITY
        
        if not self._rate_limiter.should_send(primary_dimension, severity):
            return None
        
        # Send to all senders
        sent = False
        for sender in self._senders:
            try:
                if await sender.send(alert):
                    sent = True
            except Exception:
                # Log but continue
                pass
        
        if sent:
            self._rate_limiter.record_sent(primary_dimension)
            return alert
        
        return None


# ============================================================
# FACTORY FUNCTIONS
# ============================================================


def create_telegram_alerting_service(
    bot_token: str,
    chat_id: str,
    config: Optional[AlertingConfig] = None
) -> RiskAlertingService:
    """
    Create an alerting service configured for Telegram.
    
    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        config: Optional alerting configuration
    
    Returns:
        Configured RiskAlertingService
    """
    service = RiskAlertingService(config=config)
    service.add_sender(TelegramAlertSender(
        bot_token=bot_token,
        chat_id=chat_id,
        include_details=config.telegram_include_details if config else True
    ))
    return service


def create_console_alerting_service(
    config: Optional[AlertingConfig] = None
) -> RiskAlertingService:
    """
    Create an alerting service that prints to console.
    
    Useful for development and testing.
    
    Args:
        config: Optional alerting configuration
    
    Returns:
        Configured RiskAlertingService
    """
    service = RiskAlertingService(config=config)
    service.add_sender(ConsoleAlertSender())
    return service
