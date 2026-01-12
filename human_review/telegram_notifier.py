"""
Telegram Notification Service for Human Review Events.

Sends formatted review notifications to Telegram for human oversight.
"""

import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any

from database.models_review import ReviewEvent

logger = logging.getLogger(__name__)


class TelegramReviewNotifier:
    """Send review event notifications to Telegram."""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.bot_token and self.chat_id)
    
    def format_review_notification(self, event: ReviewEvent) -> str:
        """
        Format a review event as a Telegram message.
        
        Returns structured, scannable message format.
        """
        priority_emoji = {
            "low": "🔵",
            "normal": "🟡",
            "high": "🟠",
            "critical": "🔴"
        }
        
        trigger_emoji = {
            "trade_guard_block": "🛡️",
            "drawdown_threshold": "📉",
            "consecutive_losses": "❌",
            "risk_oscillation": "⚠️",
            "data_source_degraded": "📡",
            "signal_contradiction": "🔀",
            "backtest_divergence": "📊",
            "manual_request": "👤"
        }
        
        priority = event.priority or "normal"
        trigger_type = event.trigger_type or "unknown"
        
        # Build message
        lines = [
            f"{priority_emoji.get(priority, '🟡')} {trigger_emoji.get(trigger_type, '📋')} **REVIEW REQUIRED**",
            "",
            f"📌 **Trigger:** {trigger_type.replace('_', ' ').title()}",
            f"🔢 **Event ID:** #{event.id}",
            f"⏰ **Time:** {event.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
            f"🎯 **Priority:** {priority.upper()}",
            "",
            f"📝 **Reason:**",
            f"_{event.trigger_reason}_",
        ]
        
        # Add trigger value if present
        if event.trigger_value is not None:
            threshold_str = f" (threshold: {event.trigger_threshold})" if event.trigger_threshold else ""
            lines.append(f"📊 **Value:** {event.trigger_value}{threshold_str}")
        
        # Add market context summary if present
        if event.market_context:
            mc = event.market_context
            token = mc.get("token", "?")
            price = mc.get("price", "?")
            change = mc.get("price_change_24h")
            change_str = f" ({change:+.1%})" if change else ""
            lines.extend([
                "",
                f"📈 **Market:** {token} @ ${price}{change_str}",
            ])
        
        # Add risk summary if present
        if event.risk_state_snapshot:
            rs = event.risk_state_snapshot
            risk_score = rs.get("global_risk_score", "?")
            risk_level = rs.get("risk_level", "?")
            trading = "✅ Allowed" if rs.get("trading_allowed") else "🚫 Blocked"
            lines.extend([
                "",
                f"⚡ **Risk:** {risk_score}/100 ({risk_level}) - {trading}",
            ])
        
        # Add Trade Guard rules if present
        if event.trade_guard_rules:
            rules = event.trade_guard_rules
            triggered_rules = [r.get("rule_name", r.get("rule_id", "?")) for r in rules if r.get("triggered")]
            if triggered_rules:
                lines.extend([
                    "",
                    f"🛡️ **Trade Guard:** {', '.join(triggered_rules[:3])}",
                ])
        
        # Action required
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━━",
            "🔍 **Action Required:**",
            "Open Dashboard → Review Panel",
            f"Event ID: #{event.id}",
        ])
        
        return "\n".join(lines)
    
    def format_critical_alert(self, event: ReviewEvent) -> str:
        """Format critical priority events with extra emphasis."""
        base_message = self.format_review_notification(event)
        
        return f"""
🚨🚨🚨 **CRITICAL REVIEW** 🚨🚨🚨

{base_message}

⚠️ **IMMEDIATE ATTENTION REQUIRED**
"""
    
    async def send_review_notification(self, event: ReviewEvent) -> Optional[str]:
        """
        Send review notification to Telegram.
        
        Returns message_id if successful, None otherwise.
        """
        if not self.enabled:
            logger.warning("Telegram notifications not configured")
            return None
        
        try:
            import aiohttp
            
            if event.priority == "critical":
                message = self.format_critical_alert(event)
            else:
                message = self.format_review_notification(event)
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        message_id = str(data.get("result", {}).get("message_id", ""))
                        logger.info(f"Telegram notification sent for event {event.id}")
                        return message_id
                    else:
                        logger.error(f"Telegram API error: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return None
    
    def send_review_notification_sync(self, event: ReviewEvent) -> Optional[str]:
        """
        Synchronous version for non-async contexts.
        """
        if not self.enabled:
            logger.warning("Telegram notifications not configured")
            return None
        
        try:
            import requests
            
            if event.priority == "critical":
                message = self.format_critical_alert(event)
            else:
                message = self.format_review_notification(event)
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                message_id = str(data.get("result", {}).get("message_id", ""))
                logger.info(f"Telegram notification sent for event {event.id}")
                return message_id
            else:
                logger.error(f"Telegram API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return None


# =============================================================
# MESSAGE TEMPLATES
# =============================================================

REVIEW_TEMPLATES = {
    "trade_guard_block": """
🛡️ **TRADE GUARD BLOCK REVIEW**

Trading has been blocked for {blocked_hours:.1f} hours.

**Blocking Rules:**
{rules_list}

**Current Risk State:**
- Risk Score: {risk_score}/100
- Risk Level: {risk_level}

Please review whether to:
- Adjust risk thresholds
- Disable a data source
- Mark as anomaly
""",

    "drawdown_threshold": """
📉 **DRAWDOWN THRESHOLD REVIEW**

Current drawdown: **{drawdown:.1%}**
Threshold: {threshold:.1%}

**Market Context:**
- Token: {token}
- Price: ${price}
- 24h Change: {change_24h:+.1%}

Please review whether to:
- Reduce position limits
- Pause strategy
- Continue with caution
""",

    "consecutive_losses": """
❌ **CONSECUTIVE LOSSES REVIEW**

Consecutive losing trades: **{loss_count}**

**Recent Trades:**
{trades_summary}

Please review whether to:
- Pause strategy
- Reduce position limits
- Mark as regime change
""",
}


def format_template(template_key: str, **kwargs) -> str:
    """Format a message template with provided values."""
    template = REVIEW_TEMPLATES.get(template_key, "")
    try:
        return template.format(**kwargs)
    except KeyError as e:
        logger.warning(f"Missing template key: {e}")
        return template
