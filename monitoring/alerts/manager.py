"""
Alert Manager.

============================================================
PURPOSE
============================================================
Manages alert evaluation, lifecycle, and dispatch.

PRINCIPLES:
- Deterministic rule evaluation
- Clear alert lifecycle (trigger -> acknowledge -> resolve)
- NO automatic corrections
- Notification-only

============================================================
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable, Awaitable

from ..models import Alert, AlertTier
from .rules import AlertRule, get_default_rules


logger = logging.getLogger(__name__)


# ============================================================
# ALERT HISTORY
# ============================================================

class AlertHistory:
    """
    Maintains alert history.
    
    READ-ONLY: Only stores alert records.
    """
    
    def __init__(self, max_history: int = 10000):
        """Initialize alert history."""
        self._alerts: List[Alert] = []
        self._max_history = max_history
        self._alerts_by_id: Dict[str, Alert] = {}
    
    def add(self, alert: Alert) -> None:
        """Add alert to history."""
        self._alerts.append(alert)
        self._alerts_by_id[alert.alert_id] = alert
        
        # Trim history if needed
        if len(self._alerts) > self._max_history:
            removed = self._alerts[:-self._max_history]
            self._alerts = self._alerts[-self._max_history:]
            for alert in removed:
                self._alerts_by_id.pop(alert.alert_id, None)
    
    def get(self, alert_id: str) -> Optional[Alert]:
        """Get alert by ID."""
        return self._alerts_by_id.get(alert_id)
    
    def get_recent(self, limit: int = 100) -> List[Alert]:
        """Get recent alerts."""
        return self._alerts[-limit:][::-1]  # Newest first
    
    def get_unacknowledged(self) -> List[Alert]:
        """Get unacknowledged alerts."""
        return [a for a in self._alerts if not a.acknowledged]
    
    def get_active(self) -> List[Alert]:
        """Get active (unresolved) alerts."""
        return [a for a in self._alerts if not a.resolved]
    
    def get_by_tier(self, tier: AlertTier) -> List[Alert]:
        """Get alerts by tier."""
        return [a for a in self._alerts if a.tier == tier]
    
    def get_by_category(self, category: str) -> List[Alert]:
        """Get alerts by category."""
        return [a for a in self._alerts if a.category == category]
    
    def get_since(self, since: datetime) -> List[Alert]:
        """Get alerts since a timestamp."""
        return [a for a in self._alerts if a.triggered_at >= since]
    
    def acknowledge(
        self,
        alert_id: str,
        acknowledged_by: str,
    ) -> bool:
        """Acknowledge an alert."""
        alert = self._alerts_by_id.get(alert_id)
        if alert is None:
            return False
        
        alert.acknowledged = True
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = acknowledged_by
        return True
    
    def stats(self) -> Dict[str, Any]:
        """Get alert statistics."""
        now = datetime.utcnow()
        last_hour = now - timedelta(hours=1)
        last_day = now - timedelta(days=1)
        
        alerts_1h = [a for a in self._alerts if a.triggered_at >= last_hour]
        alerts_24h = [a for a in self._alerts if a.triggered_at >= last_day]
        
        return {
            "total_alerts": len(self._alerts),
            "active_alerts": len(self.get_active()),
            "unacknowledged": len(self.get_unacknowledged()),
            "alerts_last_hour": len(alerts_1h),
            "alerts_last_24h": len(alerts_24h),
            "by_tier": {
                tier.value: len(self.get_by_tier(tier))
                for tier in AlertTier
            },
        }


# ============================================================
# ALERT MANAGER
# ============================================================

# Type for notification handlers
NotificationHandler = Callable[[Alert], Awaitable[bool]]


class AlertManager:
    """
    Manages alert rules and dispatches alerts.
    
    This is the central alert coordination point.
    """
    
    def __init__(
        self,
        rules: Optional[List[AlertRule]] = None,
        notification_handlers: Optional[List[NotificationHandler]] = None,
    ):
        """Initialize alert manager."""
        self._rules = rules or get_default_rules()
        self._handlers = notification_handlers or []
        self._history = AlertHistory()
        self._enabled = True
        
        # Rule lookup
        self._rules_by_id = {r.rule_id: r for r in self._rules}
        
        # Evaluation lock
        self._eval_lock = asyncio.Lock()
    
    @property
    def history(self) -> AlertHistory:
        """Get alert history."""
        return self._history
    
    @property
    def rules(self) -> List[AlertRule]:
        """Get all rules."""
        return self._rules
    
    def add_rule(self, rule: AlertRule) -> None:
        """Add a rule."""
        self._rules.append(rule)
        self._rules_by_id[rule.rule_id] = rule
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule."""
        rule = self._rules_by_id.pop(rule_id, None)
        if rule:
            self._rules.remove(rule)
            return True
        return False
    
    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Get a rule by ID."""
        return self._rules_by_id.get(rule_id)
    
    def enable_rule(self, rule_id: str) -> bool:
        """Enable a rule."""
        rule = self._rules_by_id.get(rule_id)
        if rule:
            rule.config.enabled = True
            return True
        return False
    
    def disable_rule(self, rule_id: str) -> bool:
        """Disable a rule."""
        rule = self._rules_by_id.get(rule_id)
        if rule:
            rule.config.enabled = False
            return True
        return False
    
    def add_handler(self, handler: NotificationHandler) -> None:
        """Add a notification handler."""
        self._handlers.append(handler)
    
    def remove_handler(self, handler: NotificationHandler) -> None:
        """Remove a notification handler."""
        if handler in self._handlers:
            self._handlers.remove(handler)
    
    def enable(self) -> None:
        """Enable alert manager."""
        self._enabled = True
    
    def disable(self) -> None:
        """Disable alert manager."""
        self._enabled = False
    
    async def evaluate(self, context: Dict[str, Any]) -> List[Alert]:
        """
        Evaluate all rules against the context.
        
        This is the main evaluation loop.
        Returns list of triggered alerts.
        """
        if not self._enabled:
            return []
        
        async with self._eval_lock:
            triggered = []
            
            for rule in self._rules:
                if not rule.config.enabled:
                    continue
                
                try:
                    alert = rule.evaluate(context)
                    if alert:
                        triggered.append(alert)
                        self._history.add(alert)
                        logger.info(
                            f"Alert triggered: {alert.title} "
                            f"[{alert.tier.value}] ({rule.rule_id})"
                        )
                except Exception as e:
                    logger.error(f"Error evaluating rule {rule.rule_id}: {e}")
            
            # Dispatch notifications
            if triggered:
                await self._dispatch_notifications(triggered)
            
            return triggered
    
    async def _dispatch_notifications(self, alerts: List[Alert]) -> None:
        """Dispatch alerts to notification handlers."""
        for alert in alerts:
            for handler in self._handlers:
                try:
                    await handler(alert)
                except Exception as e:
                    logger.error(f"Notification handler error: {e}")
    
    def acknowledge(
        self,
        alert_id: str,
        acknowledged_by: str,
    ) -> bool:
        """Acknowledge an alert."""
        return self._history.acknowledge(alert_id, acknowledged_by)
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active (unresolved) alerts."""
        return self._history.get_active()
    
    def get_critical_alerts(self) -> List[Alert]:
        """Get all critical alerts."""
        return [
            a for a in self._history.get_active()
            if a.tier == AlertTier.CRITICAL
        ]
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get alert summary for dashboard."""
        active = self._history.get_active()
        
        return {
            "active_count": len(active),
            "critical_count": sum(1 for a in active if a.tier == AlertTier.CRITICAL),
            "warning_count": sum(1 for a in active if a.tier == AlertTier.WARNING),
            "info_count": sum(1 for a in active if a.tier == AlertTier.INFO),
            "unacknowledged_count": len(self._history.get_unacknowledged()),
            "stats": self._history.stats(),
        }


# ============================================================
# ALERT DISPATCHER
# ============================================================

class AlertDispatcher:
    """
    Coordinates alert evaluation and dispatch.
    
    Runs as a background task.
    """
    
    def __init__(
        self,
        manager: AlertManager,
        context_provider: Callable[[], Awaitable[Dict[str, Any]]],
        evaluation_interval: float = 5.0,
    ):
        """Initialize dispatcher."""
        self._manager = manager
        self._context_provider = context_provider
        self._interval = evaluation_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the dispatcher."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Alert dispatcher started")
    
    async def stop(self) -> None:
        """Stop the dispatcher."""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        logger.info("Alert dispatcher stopped")
    
    async def _run(self) -> None:
        """Main run loop."""
        while self._running:
            try:
                # Get context
                context = await self._context_provider()
                
                # Evaluate rules
                await self._manager.evaluate(context)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert evaluation error: {e}")
            
            await asyncio.sleep(self._interval)
