"""
Telegram Notification Handler.

============================================================
PURPOSE
============================================================
Send alerts to Telegram channels/chats.

PRINCIPLES:
- Notification-only, NO control commands
- Rate limiting to prevent spam
- Clear, actionable messages
- Tiered formatting

============================================================
"""

import asyncio
import logging
import html
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List, TYPE_CHECKING

import aiohttp

from ..models import Alert, AlertTier

if TYPE_CHECKING:
    from strategy_engine.types import StrategySignal, SignalBundle


logger = logging.getLogger(__name__)


# ============================================================
# TELEGRAM MESSAGE FORMATTER
# ============================================================

class TelegramFormatter:
    """
    Formats alerts for Telegram.
    
    Uses HTML formatting for clarity.
    """
    
    # Tier icons
    TIER_ICONS = {
        AlertTier.INFO: "ℹ️",
        AlertTier.WARNING: "⚠️",
        AlertTier.CRITICAL: "🚨",
    }
    
    # Category icons
    CATEGORY_ICONS = {
        "system": "⚙️",
        "risk": "📊",
        "execution": "📈",
        "data": "📡",
        "module": "🔧",
        "position": "💰",
    }
    
    @classmethod
    def format_alert(cls, alert: Alert) -> str:
        """Format alert for Telegram."""
        tier_icon = cls.TIER_ICONS.get(alert.tier, "📌")
        category_icon = cls.CATEGORY_ICONS.get(alert.category, "📋")
        
        # Header
        header = f"{tier_icon} <b>{html.escape(alert.title)}</b> {category_icon}"
        
        # Body
        message = html.escape(alert.message)
        
        # Tier badge
        tier_badge = f"<code>[{alert.tier.value}]</code>"
        
        # Time
        time_str = alert.triggered_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Build message
        lines = [
            header,
            "",
            message,
            "",
            f"🏷 {tier_badge}",
            f"🕐 {time_str}",
        ]
        
        # Add data if present and not too large
        if alert.data:
            data_lines = cls._format_data(alert.data)
            if data_lines:
                lines.append("")
                lines.append("<b>Details:</b>")
                lines.extend(data_lines)
        
        return "\n".join(lines)
    
    @classmethod
    def _format_data(cls, data: Dict[str, Any], max_items: int = 5) -> List[str]:
        """Format alert data."""
        lines = []
        count = 0
        
        for key, value in data.items():
            if count >= max_items:
                lines.append(f"<i>... and {len(data) - count} more</i>")
                break
            
            # Format value
            if isinstance(value, Decimal):
                value_str = f"{value:.4f}"
            elif isinstance(value, float):
                value_str = f"{value:.4f}"
            elif isinstance(value, list):
                if len(value) <= 3:
                    value_str = ", ".join(str(v) for v in value)
                else:
                    value_str = f"{', '.join(str(v) for v in value[:3])}, ..."
            else:
                value_str = str(value)
            
            lines.append(f"• <code>{key}</code>: {html.escape(value_str)}")
            count += 1
        
        return lines
    
    @classmethod
    def format_summary(cls, alerts: List[Alert]) -> str:
        """Format alert summary."""
        if not alerts:
            return "✅ No active alerts"
        
        critical = sum(1 for a in alerts if a.tier == AlertTier.CRITICAL)
        warning = sum(1 for a in alerts if a.tier == AlertTier.WARNING)
        info = sum(1 for a in alerts if a.tier == AlertTier.INFO)
        
        lines = [
            "<b>📋 Alert Summary</b>",
            "",
            f"🚨 Critical: {critical}",
            f"⚠️ Warning: {warning}",
            f"ℹ️ Info: {info}",
            "",
            f"Total Active: {len(alerts)}",
        ]
        
        # List critical alerts
        if critical > 0:
            lines.append("")
            lines.append("<b>Critical Alerts:</b>")
            for alert in alerts:
                if alert.tier == AlertTier.CRITICAL:
                    lines.append(f"• {html.escape(alert.title)}")
        
        return "\n".join(lines)
    
    @classmethod
    def format_system_status(
        cls,
        status: Dict[str, Any],
    ) -> str:
        """Format system status message."""
        mode = status.get("mode", "UNKNOWN")
        trading = "✅ Enabled" if status.get("trading_enabled") else "❌ Disabled"
        uptime = status.get("uptime_hours", 0)
        
        lines = [
            "<b>🖥 System Status</b>",
            "",
            f"Mode: <code>{mode}</code>",
            f"Trading: {trading}",
            f"Uptime: {uptime:.1f} hours",
            "",
        ]
        
        # Module health
        healthy = status.get("healthy_modules", 0)
        degraded = status.get("degraded_modules", 0)
        unhealthy = status.get("unhealthy_modules", 0)
        
        lines.append("<b>Module Health:</b>")
        lines.append(f"🟢 Healthy: {healthy}")
        if degraded > 0:
            lines.append(f"🟡 Degraded: {degraded}")
        if unhealthy > 0:
            lines.append(f"🔴 Unhealthy: {unhealthy}")
        
        return "\n".join(lines)
    
    # --------------------------------------------------------
    # STRATEGY SIGNAL FORMATTING
    # --------------------------------------------------------
    
    # Direction icons
    DIRECTION_ICONS = {
        "LONG": "🟢 LONG",
        "SHORT": "🔴 SHORT",
        "NEUTRAL": "⚪ NEUTRAL",
    }
    
    # Confidence level icons
    CONFIDENCE_ICONS = {
        "very_low": "⬜",
        "low": "🟨",
        "medium": "🟧",
        "high": "🟩",
        "very_high": "💎",
    }
    
    @classmethod
    def format_strategy_signal(cls, signal: "StrategySignal") -> str:
        """
        Format a StrategySignal for Telegram notification.
        
        Includes:
        - Symbol and direction
        - Confidence score with visual indicator
        - Market context summary from supporting_features
        """
        # Direction with icon
        direction_str = cls.DIRECTION_ICONS.get(
            signal.direction.value, f"❓ {signal.direction.value}"
        )
        
        # Confidence bar (visual representation)
        conf_pct = int(signal.confidence_score * 100)
        filled = int(signal.confidence_score * 10)
        conf_bar = "▓" * filled + "░" * (10 - filled)
        
        # Confidence level icon
        conf_level_name = signal.confidence_level.name.lower() if hasattr(signal.confidence_level, 'name') else "medium"
        conf_icon = cls.CONFIDENCE_ICONS.get(conf_level_name, "🟨")
        
        # Header
        lines = [
            f"📊 <b>Strategy Signal</b>",
            "",
            f"<b>{html.escape(signal.symbol)}</b> ({signal.timeframe})",
            f"Direction: {direction_str}",
            f"Signal Type: <code>{signal.signal_type.value}</code>",
            "",
            f"{conf_icon} Confidence: <b>{conf_pct}%</b>",
            f"<code>[{conf_bar}]</code>",
            "",
        ]
        
        # Market context summary from supporting_features
        features = signal.supporting_features or {}
        if features:
            lines.append("<b>📈 Market Context:</b>")
            
            # Trend
            trend = features.get("trend_state", "unknown")
            trend_icon = "📈" if "up" in str(trend).lower() else "📉" if "down" in str(trend).lower() else "➡️"
            lines.append(f"{trend_icon} Trend: <code>{html.escape(str(trend))}</code>")
            
            # Volatility
            volatility = features.get("volatility_level", "unknown")
            vol_raw = features.get("volatility_raw")
            vol_str = f"{volatility}"
            if vol_raw is not None:
                vol_str += f" ({vol_raw:.2%})" if isinstance(vol_raw, (int, float)) else ""
            lines.append(f"📊 Volatility: <code>{html.escape(vol_str)}</code>")
            
            # Liquidity
            liquidity = features.get("liquidity_score")
            liq_grade = features.get("liquidity_grade", "unknown")
            if liquidity is not None:
                liq_str = f"{liq_grade} ({liquidity:.0%})" if isinstance(liquidity, (int, float)) else str(liq_grade)
            else:
                liq_str = str(liq_grade)
            lines.append(f"💧 Liquidity: <code>{html.escape(liq_str)}</code>")
            
            # Price change if available
            price_change = features.get("price_change_pct")
            if price_change is not None and isinstance(price_change, (int, float)):
                change_icon = "🔺" if price_change > 0 else "🔻" if price_change < 0 else "➖"
                lines.append(f"{change_icon} Price Change: <code>{price_change:+.2%}</code>")
            
            lines.append("")
        
        # Reason/explanation
        if signal.explanation:
            # Truncate long explanations
            explanation = signal.explanation
            if len(explanation) > 150:
                explanation = explanation[:147] + "..."
            lines.append(f"💡 <i>{html.escape(explanation)}</i>")
            lines.append("")
        
        # Timestamp
        time_str = signal.generated_at.strftime("%Y-%m-%d %H:%M:%S UTC") if signal.generated_at else "N/A"
        lines.append(f"🕐 {time_str}")
        
        return "\n".join(lines)
    
    @classmethod
    def format_signal_bundle_summary(
        cls,
        signals: List["StrategySignal"],
        title: str = "Strategy Signals",
    ) -> str:
        """
        Format a summary of multiple actionable signals.
        
        Only includes actionable signals.
        """
        actionable = [s for s in signals if s.is_actionable]
        
        if not actionable:
            return "✅ No actionable signals at this time."
        
        # Sort by confidence
        actionable.sort(key=lambda s: s.confidence_score, reverse=True)
        
        lines = [
            f"📊 <b>{html.escape(title)}</b>",
            f"<i>{len(actionable)} actionable signal(s)</i>",
            "",
        ]
        
        for sig in actionable[:5]:  # Limit to top 5
            direction_str = cls.DIRECTION_ICONS.get(
                sig.direction.value, sig.direction.value
            )
            conf_pct = int(sig.confidence_score * 100)
            
            lines.append(
                f"<b>{sig.symbol}</b> {direction_str} "
                f"<code>{sig.signal_type.value}</code> ({conf_pct}%)"
            )
        
        if len(actionable) > 5:
            lines.append(f"<i>... and {len(actionable) - 5} more</i>")
        
        return "\n".join(lines)


# ============================================================
# RATE LIMITER
# ============================================================

class TelegramRateLimiter:
    """
    Rate limiter for Telegram messages.
    
    Prevents excessive message sending.
    """
    
    def __init__(
        self,
        max_per_minute: int = 20,
        max_per_hour: int = 100,
    ):
        """Initialize rate limiter."""
        self._max_per_minute = max_per_minute
        self._max_per_hour = max_per_hour
        self._minute_window: List[datetime] = []
        self._hour_window: List[datetime] = []
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> bool:
        """Try to acquire a send slot."""
        async with self._lock:
            now = datetime.utcnow()
            
            # Clean old entries
            minute_ago = now - timedelta(minutes=1)
            hour_ago = now - timedelta(hours=1)
            
            self._minute_window = [t for t in self._minute_window if t > minute_ago]
            self._hour_window = [t for t in self._hour_window if t > hour_ago]
            
            # Check limits
            if len(self._minute_window) >= self._max_per_minute:
                return False
            if len(self._hour_window) >= self._max_per_hour:
                return False
            
            # Record this send
            self._minute_window.append(now)
            self._hour_window.append(now)
            
            return True
    
    @property
    def remaining_minute(self) -> int:
        """Remaining sends in current minute."""
        now = datetime.utcnow()
        minute_ago = now - timedelta(minutes=1)
        count = sum(1 for t in self._minute_window if t > minute_ago)
        return max(0, self._max_per_minute - count)
    
    @property
    def remaining_hour(self) -> int:
        """Remaining sends in current hour."""
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        count = sum(1 for t in self._hour_window if t > hour_ago)
        return max(0, self._max_per_hour - count)


# ============================================================
# TELEGRAM NOTIFIER
# ============================================================

class TelegramNotifier:
    """
    Sends notifications to Telegram.
    
    This is a notification-only client.
    NO control commands are processed.
    """
    
    _is_placeholder: bool = False  # Real implementation
    
    BASE_URL = "https://api.telegram.org/bot"
    
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_ids: Optional[List[str]] = None,
        rate_limiter: Optional[TelegramRateLimiter] = None,
        min_tier: AlertTier = AlertTier.INFO,
        **kwargs,  # For orchestrator compatibility
    ):
        """
        Initialize Telegram notifier.
        
        Args:
            bot_token: Telegram bot token
            chat_ids: List of chat IDs to send to
            rate_limiter: Optional rate limiter
            min_tier: Minimum alert tier to send
        """
        # Load from environment if not provided
        self._bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        
        # Handle chat_ids from env (can be comma-separated)
        if chat_ids:
            self._chat_ids = chat_ids
        else:
            env_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            env_alert_chat_id = os.getenv("TELEGRAM_ALERT_CHAT_ID", "")
            self._chat_ids = []
            if env_chat_id:
                self._chat_ids.append(env_chat_id)
            if env_alert_chat_id and env_alert_chat_id != env_chat_id:
                self._chat_ids.append(env_alert_chat_id)
        
        self._rate_limiter = rate_limiter or TelegramRateLimiter()
        self._min_tier = min_tier
        self._formatter = TelegramFormatter()
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._enabled = bool(self._bot_token and self._chat_ids)  # Only enabled if configured
        
        if self._enabled:
            logger.info(f"TelegramNotifier enabled with {len(self._chat_ids)} chat(s)")
        else:
            logger.warning("TelegramNotifier NOT configured - check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self) -> None:
        """Close the notifier."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    def enable(self) -> None:
        """Enable notifications."""
        self._enabled = True
    
    def disable(self) -> None:
        """Disable notifications."""
        self._enabled = False
    
    async def send_alert(self, alert: Alert) -> bool:
        """
        Send an alert notification.
        
        Returns True if sent successfully.
        """
        if not self._enabled:
            return False
        
        # Check tier
        tier_order = {AlertTier.INFO: 0, AlertTier.WARNING: 1, AlertTier.CRITICAL: 2}
        if tier_order.get(alert.tier, 0) < tier_order.get(self._min_tier, 0):
            return False
        
        # Format message
        message = self._formatter.format_alert(alert)
        
        # Send to all chats
        return await self._send_to_all(message)
    
    async def send_summary(self, alerts: List[Alert]) -> bool:
        """Send alert summary."""
        if not self._enabled:
            return False
        
        message = self._formatter.format_summary(alerts)
        return await self._send_to_all(message)
    
    async def send_status(self, status: Dict[str, Any]) -> bool:
        """Send system status."""
        if not self._enabled:
            return False
        
        message = self._formatter.format_system_status(status)
        return await self._send_to_all(message)
    
    async def send_text(self, text: str) -> bool:
        """Send plain text message."""
        if not self._enabled:
            return False
        
        return await self._send_to_all(html.escape(text))
    
    # --------------------------------------------------------
    # STRATEGY SIGNAL ALERTS
    # --------------------------------------------------------
    
    async def send_strategy_signal(
        self,
        signal: "StrategySignal",
    ) -> bool:
        """
        Send alert for a single actionable strategy signal.
        
        Only sends if the signal is actionable (has direction,
        sufficient confidence, and valid signal type).
        
        Args:
            signal: StrategySignal from StrategyEngine
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self._enabled:
            return False
        
        # Only send for actionable signals
        if not signal.is_actionable:
            logger.debug(
                f"Signal for {signal.symbol} not actionable, skipping notification"
            )
            return False
        
        message = self._formatter.format_strategy_signal(signal)
        return await self._send_to_all(message)
    
    async def send_actionable_signals(
        self,
        signals: List["StrategySignal"],
        send_individual: bool = False,
        send_summary: bool = True,
    ) -> bool:
        """
        Send alerts for actionable signals from a bundle.
        
        By default sends a summary. Can optionally send
        individual alerts for each actionable signal.
        
        Args:
            signals: List of StrategySignal objects
            send_individual: If True, send individual alert per signal
            send_summary: If True, send a summary of all actionable signals
            
        Returns:
            True if any message sent successfully
        """
        if not self._enabled:
            return False
        
        # Filter to actionable only
        actionable = [s for s in signals if s.is_actionable]
        
        if not actionable:
            logger.debug("No actionable signals to notify")
            return False
        
        success = False
        
        # Send individual alerts if requested
        if send_individual:
            for sig in actionable:
                if await self.send_strategy_signal(sig):
                    success = True
        
        # Send summary
        if send_summary:
            message = self._formatter.format_signal_bundle_summary(actionable)
            if await self._send_to_all(message):
                success = True
        
        return success
    
    async def send_signal_bundle(
        self,
        bundle: "SignalBundle",
        send_individual: bool = False,
        send_summary: bool = True,
    ) -> bool:
        """
        Send alerts for actionable signals from a SignalBundle.
        
        Convenience method that extracts signals from bundle.
        
        Args:
            bundle: SignalBundle from StrategyEngine
            send_individual: If True, send individual alert per signal
            send_summary: If True, send a summary of all actionable signals
            
        Returns:
            True if any message sent successfully
        """
        return await self.send_actionable_signals(
            bundle.signals,
            send_individual=send_individual,
            send_summary=send_summary,
        )
    
    async def _send_to_all(self, message: str) -> bool:
        """Send message to all configured chats."""
        if not await self._rate_limiter.acquire():
            logger.warning("Telegram rate limit reached, message not sent")
            return False
        
        success = True
        for chat_id in self._chat_ids:
            if not await self._send_message(chat_id, message):
                success = False
        
        return success
    
    async def _send_message(
        self,
        chat_id: str,
        message: str,
        parse_mode: str = "HTML",
    ) -> bool:
        """Send message to a specific chat."""
        try:
            session = await self._get_session()
            
            url = f"{self.BASE_URL}{self._bot_token}/sendMessage"
            
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    return True
                else:
                    body = await response.text()
                    logger.error(
                        f"Telegram API error: {response.status} - {body}"
                    )
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False


# ============================================================
# NOTIFICATION HANDLER FACTORY
# ============================================================

def create_telegram_handler(
    bot_token: str,
    chat_ids: List[str],
    min_tier: AlertTier = AlertTier.INFO,
) -> "TelegramNotifier":
    """
    Create a Telegram notification handler.
    
    Returns a handler function compatible with AlertManager.
    """
    notifier = TelegramNotifier(
        bot_token=bot_token,
        chat_ids=chat_ids,
        min_tier=min_tier,
    )
    return notifier


async def telegram_alert_handler(
    notifier: TelegramNotifier,
    alert: Alert,
) -> bool:
    """
    Alert handler function for AlertManager.
    
    Usage:
        notifier = create_telegram_handler(...)
        manager.add_handler(lambda a: telegram_alert_handler(notifier, a))
    """
    return await notifier.send_alert(alert)
