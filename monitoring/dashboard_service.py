"""
Dashboard Service.

============================================================
PURPOSE
============================================================
Central service for dashboard data aggregation.

PRINCIPLES:
- READ-ONLY: No state mutation
- No predictions or derived analytics
- Show UNKNOWN when data unavailable
- Mirror, not brain

============================================================
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List

from .models import (
    SystemMode,
    ModuleStatus,
    AlertTier,
    DataFreshness,
    SystemStateSnapshot,
    DataSourceStatus,
    PositionSnapshot,
    RiskExposureSnapshot,
    SignalRecord,
    OrderRecord,
    ModuleHealth,
    Alert,
    DashboardOverview,
    ExecutionView,
    SignalView,
    AuditTrail,
    ReadOnlyAccess,
)
from .collectors import (
    SystemStateCollector,
    DataPipelineCollector,
    ModuleHealthCollector,
    RiskExposureCollector,
    PositionCollector,
    SignalCollector,
    OrderCollector,
    ExecutionMetricsCollector,
)
from .alerts import AlertManager


logger = logging.getLogger(__name__)


# ============================================================
# DASHBOARD SERVICE
# ============================================================

class DashboardService(ReadOnlyAccess):
    """
    Central service for dashboard data.
    
    This is a READ-ONLY service.
    It aggregates data from all collectors.
    It does NOT make trading decisions.
    It does NOT modify system state.
    
    The dashboard is a MIRROR, not a BRAIN.
    """
    
    def __init__(
        self,
        # Collectors
        system_collector: Optional[SystemStateCollector] = None,
        data_pipeline_collector: Optional[DataPipelineCollector] = None,
        module_health_collector: Optional[ModuleHealthCollector] = None,
        risk_collector: Optional[RiskExposureCollector] = None,
        position_collector: Optional[PositionCollector] = None,
        signal_collector: Optional[SignalCollector] = None,
        order_collector: Optional[OrderCollector] = None,
        execution_metrics_collector: Optional[ExecutionMetricsCollector] = None,
        
        # Alert manager (read-only access)
        alert_manager: Optional[AlertManager] = None,
    ):
        """Initialize dashboard service."""
        self._system_collector = system_collector
        self._data_pipeline_collector = data_pipeline_collector
        self._module_health_collector = module_health_collector
        self._risk_collector = risk_collector
        self._position_collector = position_collector
        self._signal_collector = signal_collector
        self._order_collector = order_collector
        self._execution_metrics_collector = execution_metrics_collector
        self._alert_manager = alert_manager
        
        # Cache for expensive operations
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, datetime] = {}
        self._default_ttl = 5  # seconds
    
    # --------------------------------------------------------
    # MAIN DASHBOARD VIEW
    # --------------------------------------------------------
    
    async def get_overview(self) -> DashboardOverview:
        """
        Get complete dashboard overview.
        
        This is the main entry point for dashboard data.
        """
        # Collect all data in parallel
        results = await asyncio.gather(
            self._get_system_state(),
            self._get_risk_exposure(),
            self._get_active_positions(),
            self._get_recent_errors(),
            self._get_module_health(),
            self._get_data_sources(),
            return_exceptions=True,
        )
        
        # Handle exceptions gracefully
        system_state = results[0] if not isinstance(results[0], Exception) else self._empty_system_state()
        risk_exposure = results[1] if not isinstance(results[1], Exception) else self._empty_risk_exposure()
        positions = results[2] if not isinstance(results[2], Exception) else []
        errors = results[3] if not isinstance(results[3], Exception) else []
        module_health = results[4] if not isinstance(results[4], Exception) else {}
        data_sources = results[5] if not isinstance(results[5], Exception) else []
        
        return DashboardOverview(
            system_state=system_state,
            risk_exposure=risk_exposure,
            active_positions=positions,
            recent_errors=errors,
            module_health=module_health,
            data_sources=data_sources,
            generated_at=datetime.utcnow(),
        )
    
    # --------------------------------------------------------
    # EXECUTION VIEW
    # --------------------------------------------------------
    
    async def get_execution_view(
        self,
        limit: int = 100,
    ) -> ExecutionView:
        """Get execution-focused view."""
        # Collect data
        results = await asyncio.gather(
            self._get_active_orders(),
            self._get_recent_orders(limit),
            self._get_execution_metrics(),
            return_exceptions=True,
        )
        
        active_orders = results[0] if not isinstance(results[0], Exception) else []
        recent_orders = results[1] if not isinstance(results[1], Exception) else []
        metrics = results[2] if not isinstance(results[2], Exception) else {}
        
        return ExecutionView(
            active_orders=active_orders,
            recent_orders=recent_orders,
            fill_rate=metrics.get("fill_rate"),
            avg_slippage=metrics.get("avg_slippage"),
            avg_fill_time_ms=metrics.get("avg_fill_time_ms"),
            metrics_by_exchange=metrics.get("by_exchange", {}),
            generated_at=datetime.utcnow(),
        )
    
    # --------------------------------------------------------
    # SIGNAL VIEW
    # --------------------------------------------------------
    
    async def get_signal_view(
        self,
        limit: int = 100,
    ) -> SignalView:
        """Get signal-focused view."""
        results = await asyncio.gather(
            self._get_pending_signals(),
            self._get_recent_signals(limit),
            return_exceptions=True,
        )
        
        pending = results[0] if not isinstance(results[0], Exception) else []
        recent = results[1] if not isinstance(results[1], Exception) else []
        
        # Calculate simple stats (no predictions)
        total = len(recent)
        resulted_in_orders = sum(1 for s in recent if s.resulted_in_order)
        rejected = sum(1 for s in recent if s.rejection_reason)
        
        return SignalView(
            pending_signals=pending,
            recent_signals=recent,
            signals_generated_count=total,
            signals_executed_count=resulted_in_orders,
            signals_rejected_count=rejected,
            execution_rate=Decimal(str(resulted_in_orders / total)) if total > 0 else None,
            generated_at=datetime.utcnow(),
        )
    
    # --------------------------------------------------------
    # AUDIT TRAIL
    # --------------------------------------------------------
    
    async def get_audit_trail(
        self,
        signal_id: Optional[str] = None,
        order_id: Optional[str] = None,
        position_id: Optional[str] = None,
    ) -> Optional[AuditTrail]:
        """
        Get complete audit trail for a trade.
        
        Traces from signal -> order -> fills -> position.
        """
        # Find the starting point
        signal = None
        order = None
        position = None
        
        if signal_id and self._signal_collector:
            signal = await self._signal_collector.get_signal(signal_id)
            if signal and signal.order_id:
                order_id = signal.order_id
        
        if order_id and self._order_collector:
            order = await self._order_collector.get_order(order_id)
            if order and not signal and order.source_signal_id:
                signal = await self._signal_collector.get_signal(order.source_signal_id)
        
        if position_id and self._position_collector:
            position = await self._position_collector.get_position(position_id)
        
        if not any([signal, order, position]):
            return None
        
        return AuditTrail(
            trace_id=signal_id or order_id or position_id or "unknown",
            signal=signal,
            order=order,
            position=position,
            fills=order.fills if order else [],
            source_data_timestamp=signal.source_data_timestamp if signal else None,
            source_data_hash=signal.source_data_hash if signal else None,
            generated_at=datetime.utcnow(),
        )
    
    # --------------------------------------------------------
    # ALERT CONTEXT (for alert evaluation)
    # --------------------------------------------------------
    
    async def get_alert_context(self) -> Dict[str, Any]:
        """
        Get context for alert evaluation.
        
        This provides the data needed by alert rules.
        """
        results = await asyncio.gather(
            self._get_system_state(),
            self._get_risk_exposure(),
            self._get_module_health(),
            self._get_data_sources(),
            return_exceptions=True,
        )
        
        return {
            "system_state": results[0] if not isinstance(results[0], Exception) else None,
            "risk_exposure": results[1] if not isinstance(results[1], Exception) else None,
            "module_health": results[2] if not isinstance(results[2], Exception) else {},
            "data_sources": results[3] if not isinstance(results[3], Exception) else [],
        }
    
    # --------------------------------------------------------
    # HELPER METHODS
    # --------------------------------------------------------
    
    async def _get_system_state(self) -> SystemStateSnapshot:
        """Get system state."""
        if self._system_collector:
            result = await self._system_collector.safe_collect()
            if result:
                return result
        return self._empty_system_state()
    
    async def _get_risk_exposure(self) -> RiskExposureSnapshot:
        """Get risk exposure."""
        if self._risk_collector:
            result = await self._risk_collector.safe_collect()
            if result:
                return result
        return self._empty_risk_exposure()
    
    async def _get_active_positions(self) -> List[PositionSnapshot]:
        """Get active positions."""
        if self._position_collector:
            result = await self._position_collector.safe_collect()
            if result:
                return result
        return []
    
    async def _get_recent_errors(self) -> List[Alert]:
        """Get recent error alerts."""
        if self._alert_manager:
            return self._alert_manager.get_active_alerts()
        return []
    
    async def _get_module_health(self) -> Dict[str, ModuleHealth]:
        """Get module health."""
        if self._module_health_collector:
            result = await self._module_health_collector.safe_collect()
            if result:
                return result
        return {}
    
    async def _get_data_sources(self) -> List[DataSourceStatus]:
        """Get data source status."""
        if self._data_pipeline_collector:
            result = await self._data_pipeline_collector.safe_collect()
            if result:
                return result
        return []
    
    async def _get_active_orders(self) -> List[OrderRecord]:
        """Get active orders."""
        if self._order_collector:
            return await self._order_collector.get_active_orders()
        return []
    
    async def _get_recent_orders(self, limit: int) -> List[OrderRecord]:
        """Get recent orders."""
        if self._order_collector:
            return await self._order_collector.collect(limit=limit)
        return []
    
    async def _get_execution_metrics(self) -> Dict[str, Any]:
        """Get execution metrics."""
        if self._execution_metrics_collector:
            result = await self._execution_metrics_collector.safe_collect()
            if result:
                return result
        return {}
    
    async def _get_pending_signals(self) -> List[SignalRecord]:
        """Get pending signals."""
        if self._signal_collector:
            return await self._signal_collector.get_pending_signals()
        return []
    
    async def _get_recent_signals(self, limit: int) -> List[SignalRecord]:
        """Get recent signals."""
        if self._signal_collector:
            return await self._signal_collector.collect(limit=limit)
        return []
    
    def _empty_system_state(self) -> SystemStateSnapshot:
        """Create empty system state."""
        return SystemStateSnapshot(
            mode=SystemMode.INITIALIZING,
            mode_changed_at=datetime.utcnow(),
            mode_changed_by="UNKNOWN",
            mode_reason="No data available",
            snapshot_time=datetime.utcnow(),
            system_uptime_seconds=0,
            healthy_modules=0,
            degraded_modules=0,
            unhealthy_modules=0,
            trading_enabled=False,
            active_orders_count=0,
            open_positions_count=0,
        )
    
    def _empty_risk_exposure(self) -> RiskExposureSnapshot:
        """Create empty risk exposure."""
        return RiskExposureSnapshot(
            snapshot_time=datetime.utcnow(),
            total_equity=None,
            total_balance=None,
            available_balance=None,
            margin_used=None,
            margin_ratio=None,
            total_exposure=None,
            exposure_ratio=None,
            long_exposure=None,
            short_exposure=None,
            net_exposure=None,
            current_drawdown=None,
            max_drawdown_today=None,
            daily_pnl=None,
            realized_pnl=None,
            unrealized_pnl=None,
            position_count=0,
            long_count=0,
            short_count=0,
            risk_budget_used_pct=None,
            risk_budget_remaining=None,
            max_position_size=None,
            max_leverage=None,
            current_leverage=None,
            balance_data_fresh=False,
            position_data_fresh=False,
        )


# ============================================================
# DASHBOARD FACTORY
# ============================================================

def create_dashboard_service(
    state_store: Any = None,
    data_source_registry: Any = None,
    module_registry: Any = None,
    risk_store: Any = None,
    position_store: Any = None,
    balance_reader: Any = None,
    signal_store: Any = None,
    order_store: Any = None,
    alert_manager: Optional[AlertManager] = None,
) -> DashboardService:
    """
    Factory function to create a DashboardService.
    
    All stores/registries should be READ-ONLY or provide
    read-only access.
    """
    return DashboardService(
        system_collector=SystemStateCollector(state_store),
        data_pipeline_collector=DataPipelineCollector(data_source_registry),
        module_health_collector=ModuleHealthCollector(module_registry),
        risk_collector=RiskExposureCollector(
            risk_store=risk_store,
            position_store=position_store,
            balance_reader=balance_reader,
        ),
        position_collector=PositionCollector(position_store),
        signal_collector=SignalCollector(signal_store),
        order_collector=OrderCollector(order_store),
        execution_metrics_collector=ExecutionMetricsCollector(order_store),
        alert_manager=alert_manager,
    )
