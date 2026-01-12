"""
Risk Budget Manager - Alerting Integration.

============================================================
PURPOSE
============================================================
Integration with Telegram alerting system for risk notifications.

Provides:
- Alert formatting for different severity levels
- Rate limiting to prevent spam
- Alert deduplication
- Message construction for Telegram

============================================================
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable, Any
import logging
from collections import defaultdict

from .types import AlertSeverity, RiskBudgetSnapshot
from .config import AlertingConfig


logger = logging.getLogger(__name__)


@dataclass
class AlertMessage:
    """
    Structured alert message.
    """
    
    severity: AlertSeverity
    """Alert severity level."""
    
    title: str
    """Alert title."""
    
    message: str
    """Alert body message."""
    
    alert_type: Optional[str] = None
    """Type for categorization."""
    
    symbol: Optional[str] = None
    """Related symbol if applicable."""
    
    position_id: Optional[str] = None
    """Related position if applicable."""
    
    snapshot: Optional[RiskBudgetSnapshot] = None
    """Risk state snapshot."""
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """When alert was created."""
    
    def format_telegram(self) -> str:
        """
        Format message for Telegram.
        
        Returns:
            Formatted message string
        """
        emoji = self._get_severity_emoji()
        
        lines = [
            f"{emoji} *{self.title}*",
            "",
            self.message,
        ]
        
        if self.symbol:
            lines.append(f"\n📊 Symbol: `{self.symbol}`")
        
        if self.snapshot:
            lines.extend([
                "",
                "━━━━━━━━━━━━━━━",
                f"💰 Equity: ${self.snapshot.account_equity:,.2f}",
                f"📉 Drawdown: {self.snapshot.current_drawdown_pct:.1f}%",
                f"📅 Daily Used: {self.snapshot.daily_used_pct:.2f}%/{self.snapshot.daily_limit_pct:.2f}%",
                f"📈 Open Risk: {self.snapshot.open_used_pct:.2f}%/{self.snapshot.open_limit_pct:.2f}%",
                f"🔢 Positions: {self.snapshot.open_positions}/{self.snapshot.max_positions}",
            ])
        
        lines.extend([
            "",
            f"🕐 {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ])
        
        return "\n".join(lines)
    
    def _get_severity_emoji(self) -> str:
        """Get emoji for severity level."""
        return {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🚨",
            AlertSeverity.EMERGENCY: "🆘",
        }.get(self.severity, "📢")


class RiskAlertManager:
    """
    Manages risk-related alerts and notifications.
    
    ============================================================
    FEATURES
    ============================================================
    - Rate limiting to prevent alert spam
    - Alert deduplication within time window
    - Multiple output channels (Telegram, logging)
    - Alert history tracking
    
    ============================================================
    """
    
    def __init__(
        self,
        config: AlertingConfig,
        telegram_sender: Optional[Callable[[str], Any]] = None,
    ):
        """
        Initialize alert manager.
        
        Args:
            config: Alerting configuration
            telegram_sender: Optional async function to send Telegram messages
                            Signature: async (message: str) -> message_id
        """
        self._config = config
        self._telegram_sender = telegram_sender
        
        # Rate limiting state
        self._alert_counts: Dict[str, int] = defaultdict(int)
        self._last_alert_times: Dict[str, datetime] = {}
        self._hour_start: datetime = datetime.utcnow()
        self._alerts_this_hour: int = 0
        
        # Alert history
        self._recent_alerts: List[AlertMessage] = []
        self._max_history = 100
    
    # --------------------------------------------------------
    # MAIN ALERT METHOD
    # --------------------------------------------------------
    
    async def send_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        alert_type: Optional[str] = None,
        symbol: Optional[str] = None,
        position_id: Optional[str] = None,
        snapshot: Optional[RiskBudgetSnapshot] = None,
        force: bool = False,
    ) -> Optional[str]:
        """
        Send an alert.
        
        Args:
            severity: Alert severity
            title: Alert title
            message: Alert message
            alert_type: Type for categorization
            symbol: Related symbol
            position_id: Related position
            snapshot: Current risk state
            force: Force send even if rate limited
        
        Returns:
            Message ID if sent, None if rate limited
        """
        if not self._config.enabled:
            logger.debug(f"Alerting disabled, skipping: {title}")
            return None
        
        alert = AlertMessage(
            severity=severity,
            title=title,
            message=message,
            alert_type=alert_type,
            symbol=symbol,
            position_id=position_id,
            snapshot=snapshot,
        )
        
        # Check rate limits (unless forced)
        if not force:
            if not self._check_rate_limits(alert):
                logger.debug(f"Alert rate limited: {title}")
                return None
        
        # Add to history
        self._add_to_history(alert)
        
        # Log the alert
        self._log_alert(alert)
        
        # Send to Telegram if enabled
        message_id = None
        if self._config.telegram_enabled and self._telegram_sender:
            try:
                formatted = alert.format_telegram()
                message_id = await self._telegram_sender(formatted)
                logger.info(f"Telegram alert sent: {title} (ID: {message_id})")
            except Exception as e:
                logger.error(f"Failed to send Telegram alert: {e}")
        
        return message_id
    
    # --------------------------------------------------------
    # PREDEFINED ALERTS
    # --------------------------------------------------------
    
    async def alert_daily_budget_warning(
        self,
        usage_pct: float,
        daily_used: float,
        daily_limit: float,
        snapshot: Optional[RiskBudgetSnapshot] = None,
    ) -> Optional[str]:
        """Send daily budget warning."""
        return await self.send_alert(
            severity=AlertSeverity.WARNING,
            title="Daily Budget Warning",
            message=(
                f"Daily risk budget is {usage_pct:.0f}% utilized.\n"
                f"Used: {daily_used:.2f}% of {daily_limit:.2f}% limit."
            ),
            alert_type="DAILY_BUDGET_WARNING",
            snapshot=snapshot,
        )
    
    async def alert_drawdown_warning(
        self,
        current_drawdown: float,
        warning_threshold: float,
        max_drawdown: float,
        snapshot: Optional[RiskBudgetSnapshot] = None,
    ) -> Optional[str]:
        """Send drawdown warning."""
        return await self.send_alert(
            severity=AlertSeverity.WARNING,
            title="Drawdown Warning",
            message=(
                f"Current drawdown: {current_drawdown:.1f}%\n"
                f"Warning threshold: {warning_threshold:.1f}%\n"
                f"Halt threshold: {max_drawdown:.1f}%"
            ),
            alert_type="DRAWDOWN_WARNING",
            snapshot=snapshot,
        )
    
    async def alert_drawdown_halt(
        self,
        current_drawdown: float,
        max_drawdown: float,
        equity: float,
        peak_equity: float,
        snapshot: Optional[RiskBudgetSnapshot] = None,
    ) -> Optional[str]:
        """Send drawdown halt alert."""
        loss_amount = peak_equity - equity
        
        return await self.send_alert(
            severity=AlertSeverity.EMERGENCY,
            title="TRADING HALTED - Drawdown Limit",
            message=(
                f"❌ Trading has been HALTED.\n\n"
                f"Drawdown: {current_drawdown:.1f}%\n"
                f"Limit: {max_drawdown:.1f}%\n"
                f"Loss from peak: ${loss_amount:,.2f}\n\n"
                f"Manual intervention required to resume."
            ),
            alert_type="DRAWDOWN_HALT",
            snapshot=snapshot,
            force=True,  # Always send halt alerts
        )
    
    async def alert_stale_equity_data(
        self,
        last_update: Optional[datetime],
        max_age_seconds: int,
    ) -> Optional[str]:
        """Send stale equity data alert."""
        age_str = "unknown"
        if last_update:
            age = (datetime.utcnow() - last_update).total_seconds()
            age_str = f"{age:.0f} seconds"
        
        return await self.send_alert(
            severity=AlertSeverity.CRITICAL,
            title="Stale Equity Data",
            message=(
                f"Equity data is stale ({age_str} old).\n"
                f"Maximum allowed: {max_age_seconds} seconds.\n\n"
                f"All trades will be rejected until data is refreshed."
            ),
            alert_type="STALE_EQUITY",
            force=True,
        )
    
    async def alert_consecutive_rejections(
        self,
        rejection_count: int,
        recent_reasons: List[str],
        snapshot: Optional[RiskBudgetSnapshot] = None,
    ) -> Optional[str]:
        """Send consecutive rejection alert."""
        reasons_str = ", ".join(set(recent_reasons[-5:]))
        
        return await self.send_alert(
            severity=AlertSeverity.WARNING,
            title="Multiple Trade Rejections",
            message=(
                f"{rejection_count} trades rejected consecutively.\n"
                f"Recent reasons: {reasons_str}"
            ),
            alert_type="CONSECUTIVE_REJECTIONS",
            snapshot=snapshot,
        )
    
    async def alert_trade_allowed(
        self,
        symbol: str,
        direction: str,
        risk_pct: float,
        position_size: float,
        snapshot: Optional[RiskBudgetSnapshot] = None,
    ) -> Optional[str]:
        """Send trade allowed notification (info level)."""
        return await self.send_alert(
            severity=AlertSeverity.INFO,
            title="Trade Allowed",
            message=(
                f"Trade approved for {symbol}\n"
                f"Direction: {direction}\n"
                f"Risk: {risk_pct:.2f}%\n"
                f"Size: {position_size:.4f}"
            ),
            alert_type="TRADE_ALLOWED",
            symbol=symbol,
            snapshot=snapshot,
        )
    
    async def alert_trade_rejected(
        self,
        symbol: str,
        reason: str,
        proposed_risk: float,
        snapshot: Optional[RiskBudgetSnapshot] = None,
    ) -> Optional[str]:
        """Send trade rejected notification."""
        return await self.send_alert(
            severity=AlertSeverity.WARNING,
            title="Trade Rejected",
            message=(
                f"Trade rejected for {symbol}\n"
                f"Reason: {reason}\n"
                f"Proposed risk: {proposed_risk:.2f}%"
            ),
            alert_type="TRADE_REJECTED",
            symbol=symbol,
            snapshot=snapshot,
        )
    
    async def alert_trading_resumed(
        self,
        resumed_by: str,
        snapshot: Optional[RiskBudgetSnapshot] = None,
    ) -> Optional[str]:
        """Send trading resumed notification."""
        return await self.send_alert(
            severity=AlertSeverity.INFO,
            title="Trading Resumed",
            message=(
                f"✅ Trading has been resumed.\n"
                f"Resumed by: {resumed_by}"
            ),
            alert_type="TRADING_RESUMED",
            snapshot=snapshot,
            force=True,
        )
    
    async def alert_position_opened(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        risk_pct: float,
        snapshot: Optional[RiskBudgetSnapshot] = None,
    ) -> Optional[str]:
        """Send position opened notification."""
        return await self.send_alert(
            severity=AlertSeverity.INFO,
            title="Position Opened",
            message=(
                f"New position: {symbol} {direction}\n"
                f"Entry: ${entry_price:,.2f}\n"
                f"Stop Loss: ${stop_loss:,.2f}\n"
                f"Risk: {risk_pct:.2f}%"
            ),
            alert_type="POSITION_OPENED",
            symbol=symbol,
            snapshot=snapshot,
        )
    
    async def alert_position_closed(
        self,
        symbol: str,
        direction: str,
        realized_pnl: float,
        pnl_pct: float,
        snapshot: Optional[RiskBudgetSnapshot] = None,
    ) -> Optional[str]:
        """Send position closed notification."""
        pnl_emoji = "🟢" if realized_pnl >= 0 else "🔴"
        
        return await self.send_alert(
            severity=AlertSeverity.INFO,
            title="Position Closed",
            message=(
                f"{pnl_emoji} {symbol} {direction} closed\n"
                f"P&L: ${realized_pnl:+,.2f} ({pnl_pct:+.2f}%)"
            ),
            alert_type="POSITION_CLOSED",
            symbol=symbol,
            snapshot=snapshot,
        )
    
    # --------------------------------------------------------
    # RATE LIMITING
    # --------------------------------------------------------
    
    def _check_rate_limits(self, alert: AlertMessage) -> bool:
        """
        Check if alert should be sent based on rate limits.
        
        Returns:
            True if alert should be sent
        """
        now = datetime.utcnow()
        
        # Reset hourly counter if needed
        if (now - self._hour_start).total_seconds() >= 3600:
            self._hour_start = now
            self._alerts_this_hour = 0
        
        # Check hourly limit
        if self._alerts_this_hour >= self._config.max_alerts_per_hour:
            return False
        
        # Check per-alert-type interval
        alert_key = f"{alert.alert_type}:{alert.symbol or 'global'}"
        last_time = self._last_alert_times.get(alert_key)
        
        if last_time:
            elapsed = (now - last_time).total_seconds()
            if elapsed < self._config.min_alert_interval_seconds:
                return False
        
        # Update tracking
        self._last_alert_times[alert_key] = now
        self._alerts_this_hour += 1
        
        return True
    
    def _add_to_history(self, alert: AlertMessage) -> None:
        """Add alert to history."""
        self._recent_alerts.append(alert)
        
        # Trim history
        if len(self._recent_alerts) > self._max_history:
            self._recent_alerts = self._recent_alerts[-self._max_history:]
    
    def _log_alert(self, alert: AlertMessage) -> None:
        """Log alert at appropriate level."""
        log_message = f"[{alert.severity.value}] {alert.title}: {alert.message}"
        
        if alert.severity == AlertSeverity.EMERGENCY:
            logger.critical(log_message)
        elif alert.severity == AlertSeverity.CRITICAL:
            logger.error(log_message)
        elif alert.severity == AlertSeverity.WARNING:
            logger.warning(log_message)
        else:
            logger.info(log_message)
    
    # --------------------------------------------------------
    # HISTORY ACCESS
    # --------------------------------------------------------
    
    def get_recent_alerts(
        self,
        count: int = 10,
        severity: Optional[AlertSeverity] = None,
    ) -> List[AlertMessage]:
        """Get recent alerts."""
        alerts = self._recent_alerts
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        return alerts[-count:]
    
    def get_alert_count_by_severity(
        self,
        hours: int = 24,
    ) -> Dict[str, int]:
        """Get count of alerts by severity in time period."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        counts = defaultdict(int)
        for alert in self._recent_alerts:
            if alert.timestamp >= cutoff:
                counts[alert.severity.value] += 1
        
        return dict(counts)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def create_telegram_callback(
    bot_token: str,
    chat_id: str,
) -> Callable[[str], Any]:
    """
    Create a Telegram sender callback.
    
    This is a factory function that creates the async sender
    function for use with RiskAlertManager.
    
    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
    
    Returns:
        Async function that sends messages
    """
    async def send_telegram_message(message: str) -> Optional[str]:
        """Send message to Telegram."""
        try:
            import aiohttp
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return str(data.get("result", {}).get("message_id"))
                    else:
                        logger.error(f"Telegram API error: {response.status}")
                        return None
                        
        except ImportError:
            logger.warning("aiohttp not installed, Telegram alerts disabled")
            return None
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return None
    
    return send_telegram_message
