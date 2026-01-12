"""
Risk & Exposure Collector.

============================================================
PURPOSE
============================================================
Read-only collector for risk metrics and exposure data.

PRINCIPLES:
- ALL data is read directly from source systems
- NO derived calculations beyond simple aggregation
- NO assumptions about missing data
- Show UNKNOWN when data unavailable

============================================================
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, List

from ..models import (
    RiskExposureSnapshot,
    PositionSnapshot,
    AlertTier,
)
from .base import BaseCollector


logger = logging.getLogger(__name__)


# ============================================================
# RISK EXPOSURE COLLECTOR
# ============================================================

class RiskExposureCollector(BaseCollector):
    """
    Collects risk and exposure metrics.
    
    READ-ONLY: Only reads from risk stores and exchanges.
    """
    
    def __init__(
        self,
        risk_store: Any = None,  # Read-only risk data store
        position_store: Any = None,  # Read-only position data store
        balance_reader: Any = None,  # Read-only balance reader
    ):
        """Initialize risk exposure collector."""
        super().__init__("risk_exposure")
        self._risk_store = risk_store
        self._position_store = position_store
        self._balance_reader = balance_reader
    
    async def collect(self) -> RiskExposureSnapshot:
        """Collect current risk exposure."""
        
        # Collect balances
        balances = await self._collect_balances()
        
        # Collect positions
        positions = await self._collect_positions()
        
        # Get risk metrics from risk store
        risk_metrics = await self._collect_risk_metrics()
        
        # Calculate simple aggregates (no predictions)
        total_equity = balances.get("total_equity")
        total_exposure = self._calculate_total_exposure(positions)
        
        return RiskExposureSnapshot(
            snapshot_time=datetime.utcnow(),
            
            # Balance data
            total_equity=total_equity,
            total_balance=balances.get("total_balance"),
            available_balance=balances.get("available_balance"),
            margin_used=balances.get("margin_used"),
            margin_ratio=balances.get("margin_ratio"),
            
            # Exposure data
            total_exposure=total_exposure,
            exposure_ratio=self._safe_divide(total_exposure, total_equity),
            long_exposure=self._calculate_directional_exposure(positions, "long"),
            short_exposure=self._calculate_directional_exposure(positions, "short"),
            net_exposure=self._calculate_net_exposure(positions),
            
            # Risk metrics (read from risk store)
            current_drawdown=risk_metrics.get("current_drawdown"),
            max_drawdown_today=risk_metrics.get("max_drawdown_today"),
            daily_pnl=risk_metrics.get("daily_pnl"),
            realized_pnl=risk_metrics.get("realized_pnl"),
            unrealized_pnl=risk_metrics.get("unrealized_pnl"),
            
            # Position counts
            position_count=len(positions),
            long_count=sum(1 for p in positions if p.side == "long"),
            short_count=sum(1 for p in positions if p.side == "short"),
            
            # Risk budget (from risk store)
            risk_budget_used_pct=risk_metrics.get("risk_budget_used_pct"),
            risk_budget_remaining=risk_metrics.get("risk_budget_remaining"),
            
            # Limits
            max_position_size=risk_metrics.get("max_position_size"),
            max_leverage=risk_metrics.get("max_leverage"),
            current_leverage=risk_metrics.get("current_leverage"),
            
            # Data quality flags
            balance_data_fresh=balances.get("is_fresh", False),
            position_data_fresh=await self._check_position_freshness(),
        )
    
    async def _collect_balances(self) -> Dict[str, Any]:
        """Collect balance data."""
        if self._balance_reader is None:
            return {"is_fresh": False}
        
        try:
            # Get balance from reader (read-only)
            balance = await self._balance_reader.get_balance()
            if balance is None:
                return {"is_fresh": False}
            
            return {
                "total_equity": balance.get("total_equity"),
                "total_balance": balance.get("total_balance"),
                "available_balance": balance.get("available_balance"),
                "margin_used": balance.get("margin_used"),
                "margin_ratio": balance.get("margin_ratio"),
                "is_fresh": balance.get("is_fresh", False),
            }
        except Exception as e:
            logger.error(f"Error collecting balances: {e}")
            return {"is_fresh": False}
    
    async def _collect_positions(self) -> List[PositionSnapshot]:
        """Collect position data."""
        if self._position_store is None:
            return []
        
        try:
            positions = await self._position_store.get_all_positions()
            if positions is None:
                return []
            
            snapshots = []
            for pos in positions:
                snapshots.append(PositionSnapshot(
                    position_id=pos.get("id", "unknown"),
                    symbol=pos.get("symbol", "unknown"),
                    exchange=pos.get("exchange", "unknown"),
                    side=pos.get("side", "unknown"),
                    size=pos.get("size"),
                    notional_value=pos.get("notional_value"),
                    entry_price=pos.get("entry_price"),
                    current_price=pos.get("current_price"),
                    liquidation_price=pos.get("liquidation_price"),
                    unrealized_pnl=pos.get("unrealized_pnl"),
                    realized_pnl=pos.get("realized_pnl"),
                    leverage=pos.get("leverage"),
                    margin_used=pos.get("margin_used"),
                    opened_at=pos.get("opened_at"),
                    updated_at=pos.get("updated_at"),
                    associated_strategy=pos.get("strategy"),
                    stop_loss=pos.get("stop_loss"),
                    take_profit=pos.get("take_profit"),
                ))
            
            return snapshots
        except Exception as e:
            logger.error(f"Error collecting positions: {e}")
            return []
    
    async def _collect_risk_metrics(self) -> Dict[str, Any]:
        """Collect risk metrics from risk store."""
        if self._risk_store is None:
            return {}
        
        try:
            return await self._risk_store.get_current_metrics() or {}
        except Exception as e:
            logger.error(f"Error collecting risk metrics: {e}")
            return {}
    
    def _calculate_total_exposure(
        self,
        positions: List[PositionSnapshot],
    ) -> Optional[Decimal]:
        """Calculate total absolute exposure."""
        if not positions:
            return Decimal("0")
        
        total = Decimal("0")
        for pos in positions:
            if pos.notional_value is not None:
                total += abs(pos.notional_value)
        
        return total
    
    def _calculate_directional_exposure(
        self,
        positions: List[PositionSnapshot],
        direction: str,
    ) -> Optional[Decimal]:
        """Calculate exposure for a direction."""
        if not positions:
            return Decimal("0")
        
        total = Decimal("0")
        for pos in positions:
            if pos.side == direction and pos.notional_value is not None:
                total += abs(pos.notional_value)
        
        return total
    
    def _calculate_net_exposure(
        self,
        positions: List[PositionSnapshot],
    ) -> Optional[Decimal]:
        """Calculate net exposure (long - short)."""
        if not positions:
            return Decimal("0")
        
        net = Decimal("0")
        for pos in positions:
            if pos.notional_value is not None:
                if pos.side == "long":
                    net += abs(pos.notional_value)
                elif pos.side == "short":
                    net -= abs(pos.notional_value)
        
        return net
    
    def _safe_divide(
        self,
        numerator: Optional[Decimal],
        denominator: Optional[Decimal],
    ) -> Optional[Decimal]:
        """Safe division returning None if impossible."""
        if numerator is None or denominator is None:
            return None
        if denominator == 0:
            return None
        return numerator / denominator
    
    async def _check_position_freshness(self) -> bool:
        """Check if position data is fresh."""
        if self._position_store is None:
            return False
        
        try:
            last_update = await self._position_store.get_last_update_time()
            if last_update is None:
                return False
            
            age = (datetime.utcnow() - last_update).total_seconds()
            return age < 60  # Fresh if updated within 60 seconds
        except Exception:
            return False


# ============================================================
# POSITION SNAPSHOT COLLECTOR
# ============================================================

class PositionCollector(BaseCollector):
    """
    Dedicated collector for position snapshots.
    
    READ-ONLY: Only reads position data.
    """
    
    def __init__(self, position_store: Any = None):
        """Initialize position collector."""
        super().__init__("positions")
        self._position_store = position_store
    
    async def collect(self) -> List[PositionSnapshot]:
        """Collect all positions."""
        if self._position_store is None:
            return []
        
        try:
            positions = await self._position_store.get_all_positions()
            if positions is None:
                return []
            
            snapshots = []
            for pos in positions:
                snapshots.append(self._to_snapshot(pos))
            
            return snapshots
        except Exception as e:
            logger.error(f"Error collecting positions: {e}")
            return []
    
    def _to_snapshot(self, pos: Dict[str, Any]) -> PositionSnapshot:
        """Convert position dict to snapshot."""
        return PositionSnapshot(
            position_id=pos.get("id", "unknown"),
            symbol=pos.get("symbol", "unknown"),
            exchange=pos.get("exchange", "unknown"),
            side=pos.get("side", "unknown"),
            size=pos.get("size"),
            notional_value=pos.get("notional_value"),
            entry_price=pos.get("entry_price"),
            current_price=pos.get("current_price"),
            liquidation_price=pos.get("liquidation_price"),
            unrealized_pnl=pos.get("unrealized_pnl"),
            realized_pnl=pos.get("realized_pnl"),
            leverage=pos.get("leverage"),
            margin_used=pos.get("margin_used"),
            opened_at=pos.get("opened_at"),
            updated_at=pos.get("updated_at"),
            associated_strategy=pos.get("strategy"),
            stop_loss=pos.get("stop_loss"),
            take_profit=pos.get("take_profit"),
        )
    
    async def get_position(self, position_id: str) -> Optional[PositionSnapshot]:
        """Get a single position by ID."""
        if self._position_store is None:
            return None
        
        try:
            pos = await self._position_store.get_position(position_id)
            if pos is None:
                return None
            return self._to_snapshot(pos)
        except Exception as e:
            logger.error(f"Error getting position {position_id}: {e}")
            return None
