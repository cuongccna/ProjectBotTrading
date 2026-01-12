"""
System Integration Hooks for Chaos Testing.

============================================================
PURPOSE
============================================================
Provides integration hooks between the chaos testing framework
and the trading system components.

This module:
1. Wires chaos testing to Orchestrator
2. Wires chaos testing to Trade Guard
3. Wires chaos testing to Monitoring
4. Provides mock implementations for testing

============================================================
INTEGRATION ARCHITECTURE
============================================================

                    ┌─────────────────┐
                    │  Chaos Testing  │
                    │    Executor     │
                    └────────┬────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
           ▼                 ▼                 ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │ Orchestrator │  │ Trade Guard  │  │  Monitoring  │
    │   Adapter    │  │   Adapter    │  │   Adapter    │
    └──────────────┘  └──────────────┘  └──────────────┘

============================================================
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from .models import (
    RunMode,
    FaultCategory,
    ChaosTestCase,
    ChaosTestResult,
    ExpectedSystemState,
    ExpectedTradeGuardDecision,
)
from .validator import (
    SystemStateMonitor,
    TradeGuardMonitor,
    AlertMonitor,
    BehaviorMonitor,
)


logger = logging.getLogger(__name__)


# ============================================================
# ABSTRACT ADAPTERS
# ============================================================

class OrchestratorAdapter(ABC):
    """Abstract adapter for Orchestrator integration."""
    
    @abstractmethod
    async def get_system_state(self) -> ExpectedSystemState:
        """Get current system state from Orchestrator."""
        pass
    
    @abstractmethod
    async def trigger_emergency_stop(self, reason: str) -> bool:
        """Trigger emergency stop."""
        pass
    
    @abstractmethod
    async def pause_trading(self, reason: str) -> bool:
        """Pause trading operations."""
        pass
    
    @abstractmethod
    async def resume_trading(self) -> bool:
        """Resume trading operations."""
        pass
    
    @abstractmethod
    async def get_active_modules(self) -> List[str]:
        """Get list of active trading modules."""
        pass
    
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Perform system health check."""
        pass


class TradeGuardAdapter(ABC):
    """Abstract adapter for Trade Guard integration."""
    
    @abstractmethod
    async def get_last_decision(self) -> Optional[ExpectedTradeGuardDecision]:
        """Get last Trade Guard decision."""
        pass
    
    @abstractmethod
    async def is_trading_allowed(self) -> bool:
        """Check if trading is currently allowed."""
        pass
    
    @abstractmethod
    async def get_active_blocks(self) -> List[Dict[str, Any]]:
        """Get list of active trading blocks."""
        pass
    
    @abstractmethod
    async def register_decision_callback(
        self,
        callback: Callable[[ExpectedTradeGuardDecision, str], None],
    ) -> None:
        """Register callback for Trade Guard decisions."""
        pass


class MonitoringAdapter(ABC):
    """Abstract adapter for Monitoring integration."""
    
    @abstractmethod
    async def get_recent_alerts(
        self,
        since: datetime,
    ) -> List[Dict[str, Any]]:
        """Get alerts generated since timestamp."""
        pass
    
    @abstractmethod
    async def send_alert(
        self,
        tier: str,
        message: str,
        metadata: Dict[str, Any] = None,
    ) -> bool:
        """Send an alert."""
        pass
    
    @abstractmethod
    async def register_alert_callback(
        self,
        callback: Callable[[str, str], None],
    ) -> None:
        """Register callback for alert notifications."""
        pass


# ============================================================
# MOCK IMPLEMENTATIONS
# ============================================================

class MockOrchestratorAdapter(OrchestratorAdapter):
    """Mock Orchestrator for testing."""
    
    def __init__(self):
        self._state = ExpectedSystemState.RUNNING
        self._modules = ["signal_generator", "risk_controller", "execution_engine"]
        self._is_paused = False
    
    async def get_system_state(self) -> ExpectedSystemState:
        return self._state
    
    def set_state(self, state: ExpectedSystemState) -> None:
        """Set mock state (for testing)."""
        self._state = state
    
    async def trigger_emergency_stop(self, reason: str) -> bool:
        logger.info(f"[MOCK] Emergency stop triggered: {reason}")
        self._state = ExpectedSystemState.EMERGENCY_STOP
        return True
    
    async def pause_trading(self, reason: str) -> bool:
        logger.info(f"[MOCK] Trading paused: {reason}")
        self._is_paused = True
        self._state = ExpectedSystemState.PAUSED
        return True
    
    async def resume_trading(self) -> bool:
        logger.info("[MOCK] Trading resumed")
        self._is_paused = False
        self._state = ExpectedSystemState.RUNNING
        return True
    
    async def get_active_modules(self) -> List[str]:
        return self._modules
    
    async def health_check(self) -> Dict[str, Any]:
        return {
            "healthy": not self._is_paused,
            "state": self._state.value,
            "modules": {m: "healthy" for m in self._modules},
        }


class MockTradeGuardAdapter(TradeGuardAdapter):
    """Mock Trade Guard for testing."""
    
    def __init__(self):
        self._last_decision: Optional[ExpectedTradeGuardDecision] = None
        self._trading_allowed = True
        self._active_blocks: List[Dict[str, Any]] = []
        self._callbacks: List[Callable] = []
    
    async def get_last_decision(self) -> Optional[ExpectedTradeGuardDecision]:
        return self._last_decision
    
    def set_decision(
        self,
        decision: ExpectedTradeGuardDecision,
        reason: str = "",
    ) -> None:
        """Set mock decision (for testing)."""
        self._last_decision = decision
        for callback in self._callbacks:
            try:
                callback(decision, reason)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    async def is_trading_allowed(self) -> bool:
        return self._trading_allowed
    
    def set_trading_allowed(self, allowed: bool) -> None:
        """Set mock trading allowed state."""
        self._trading_allowed = allowed
    
    async def get_active_blocks(self) -> List[Dict[str, Any]]:
        return self._active_blocks
    
    def add_block(self, block: Dict[str, Any]) -> None:
        """Add a mock block."""
        self._active_blocks.append(block)
    
    async def register_decision_callback(
        self,
        callback: Callable[[ExpectedTradeGuardDecision, str], None],
    ) -> None:
        self._callbacks.append(callback)


class MockMonitoringAdapter(MonitoringAdapter):
    """Mock Monitoring for testing."""
    
    def __init__(self):
        self._alerts: List[Dict[str, Any]] = []
        self._callbacks: List[Callable] = []
    
    async def get_recent_alerts(
        self,
        since: datetime,
    ) -> List[Dict[str, Any]]:
        return [a for a in self._alerts if a["timestamp"] >= since]
    
    async def send_alert(
        self,
        tier: str,
        message: str,
        metadata: Dict[str, Any] = None,
    ) -> bool:
        alert = {
            "timestamp": datetime.utcnow(),
            "tier": tier,
            "message": message,
            "metadata": metadata or {},
        }
        self._alerts.append(alert)
        logger.info(f"[MOCK] Alert sent: [{tier}] {message}")
        
        for callback in self._callbacks:
            try:
                callback(tier, message)
            except Exception as e:
                logger.error(f"Callback error: {e}")
        
        return True
    
    async def register_alert_callback(
        self,
        callback: Callable[[str, str], None],
    ) -> None:
        self._callbacks.append(callback)
    
    def clear_alerts(self) -> None:
        """Clear mock alerts."""
        self._alerts.clear()


# ============================================================
# INTEGRATION MANAGER
# ============================================================

class ChaosIntegrationManager:
    """
    Manages integration between chaos testing and system components.
    
    Wires the chaos testing validators to system components so that
    system state changes, Trade Guard decisions, and alerts are
    captured during chaos testing.
    """
    
    def __init__(
        self,
        orchestrator: OrchestratorAdapter,
        trade_guard: TradeGuardAdapter,
        monitoring: MonitoringAdapter,
        state_monitor: SystemStateMonitor,
        trade_guard_monitor: TradeGuardMonitor,
        alert_monitor: AlertMonitor,
        behavior_monitor: BehaviorMonitor,
    ):
        self._orchestrator = orchestrator
        self._trade_guard = trade_guard
        self._monitoring = monitoring
        
        self._state_monitor = state_monitor
        self._trade_guard_monitor = trade_guard_monitor
        self._alert_monitor = alert_monitor
        self._behavior_monitor = behavior_monitor
        
        self._is_wired = False
    
    async def wire(self) -> None:
        """Wire up all integrations."""
        if self._is_wired:
            logger.warning("Already wired")
            return
        
        # Wire Trade Guard
        await self._trade_guard.register_decision_callback(
            self._on_trade_guard_decision
        )
        
        # Wire Monitoring
        await self._monitoring.register_alert_callback(
            self._on_alert
        )
        
        # Get initial state
        initial_state = await self._orchestrator.get_system_state()
        self._state_monitor.update_state(initial_state)
        
        self._is_wired = True
        logger.info("Chaos integration wired")
    
    def _on_trade_guard_decision(
        self,
        decision: ExpectedTradeGuardDecision,
        reason: str,
    ) -> None:
        """Handle Trade Guard decision."""
        self._trade_guard_monitor.record_decision(decision, reason)
    
    def _on_alert(self, tier: str, message: str) -> None:
        """Handle alert."""
        self._alert_monitor.record_alert(tier, message)
    
    async def poll_state(self) -> ExpectedSystemState:
        """Poll and update system state."""
        state = await self._orchestrator.get_system_state()
        self._state_monitor.update_state(state)
        return state
    
    async def record_trade_event(self, trade_data: Dict[str, Any]) -> None:
        """Record a trade event."""
        self._behavior_monitor.record_event("trade", trade_data)
    
    async def record_retry_event(self, operation: str, attempt: int) -> None:
        """Record a retry event."""
        self._behavior_monitor.record_event("retry", {
            "operation": operation,
            "attempt": attempt,
        })
    
    async def record_reconciliation(self) -> None:
        """Record a reconciliation event."""
        self._behavior_monitor.record_event("reconciliation", {})
    
    async def record_audit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Record an audit event."""
        self._behavior_monitor.record_event("audit", {
            "event_type": event_type,
            **data,
        })


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_mock_integration_manager(
    state_monitor: SystemStateMonitor,
    trade_guard_monitor: TradeGuardMonitor,
    alert_monitor: AlertMonitor,
    behavior_monitor: BehaviorMonitor,
) -> ChaosIntegrationManager:
    """
    Create an integration manager with mock adapters.
    
    Use this for isolated chaos testing without real system components.
    """
    return ChaosIntegrationManager(
        orchestrator=MockOrchestratorAdapter(),
        trade_guard=MockTradeGuardAdapter(),
        monitoring=MockMonitoringAdapter(),
        state_monitor=state_monitor,
        trade_guard_monitor=trade_guard_monitor,
        alert_monitor=alert_monitor,
        behavior_monitor=behavior_monitor,
    )


def create_integration_manager(
    orchestrator: OrchestratorAdapter,
    trade_guard: TradeGuardAdapter,
    monitoring: MonitoringAdapter,
    state_monitor: SystemStateMonitor,
    trade_guard_monitor: TradeGuardMonitor,
    alert_monitor: AlertMonitor,
    behavior_monitor: BehaviorMonitor,
) -> ChaosIntegrationManager:
    """
    Create an integration manager with real adapters.
    
    Use this for integration testing with real system components.
    """
    return ChaosIntegrationManager(
        orchestrator=orchestrator,
        trade_guard=trade_guard,
        monitoring=monitoring,
        state_monitor=state_monitor,
        trade_guard_monitor=trade_guard_monitor,
        alert_monitor=alert_monitor,
        behavior_monitor=behavior_monitor,
    )
