"""
Data Collectors for Parity Validation.

============================================================
PURPOSE
============================================================
Collects data from live and backtest sources for comparison.

Collectors ensure:
- Same timestamps
- Same aggregation windows
- Same missing-data handling

============================================================
"""

import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid

from ..models import (
    MarketSnapshot,
    FeatureSnapshot,
    DecisionSnapshot,
    ExecutionSnapshot,
    OHLCVData,
)


logger = logging.getLogger(__name__)


# ============================================================
# BASE COLLECTOR
# ============================================================

class BaseDataCollector(ABC):
    """Abstract base class for data collectors."""
    
    def __init__(self, source_name: str):
        self._source_name = source_name
        self._collection_count = 0
    
    @property
    def source_name(self) -> str:
        return self._source_name
    
    @abstractmethod
    async def collect_market_snapshot(
        self,
        symbol: str,
        timestamp: datetime,
    ) -> MarketSnapshot:
        """Collect market data snapshot."""
        pass
    
    @abstractmethod
    async def collect_feature_snapshot(
        self,
        symbol: str,
        timestamp: datetime,
    ) -> FeatureSnapshot:
        """Collect feature calculation snapshot."""
        pass
    
    @abstractmethod
    async def collect_decision_snapshot(
        self,
        cycle_id: str,
        timestamp: datetime,
    ) -> DecisionSnapshot:
        """Collect decision state snapshot."""
        pass
    
    @abstractmethod
    async def collect_execution_snapshot(
        self,
        cycle_id: str,
        timestamp: datetime,
    ) -> ExecutionSnapshot:
        """Collect execution state snapshot."""
        pass
    
    def _generate_snapshot_id(self) -> str:
        """Generate unique snapshot ID."""
        self._collection_count += 1
        return f"{self._source_name}_{uuid.uuid4().hex[:12]}"


# ============================================================
# LIVE DATA COLLECTOR
# ============================================================

class LiveDataCollector(BaseDataCollector):
    """Collects data from live trading system."""
    
    def __init__(
        self,
        data_service: Any = None,
        feature_service: Any = None,
        trade_guard: Any = None,
        execution_engine: Any = None,
    ):
        super().__init__("live")
        self._data_service = data_service
        self._feature_service = feature_service
        self._trade_guard = trade_guard
        self._execution_engine = execution_engine
    
    async def collect_market_snapshot(
        self,
        symbol: str,
        timestamp: datetime,
    ) -> MarketSnapshot:
        """Collect live market data."""
        snapshot = MarketSnapshot(
            snapshot_id=self._generate_snapshot_id(),
            timestamp=timestamp,
            symbol=symbol,
            source="live",
        )
        
        if self._data_service:
            try:
                # Get OHLCV
                ohlcv_data = await self._data_service.get_ohlcv(symbol, timestamp)
                if ohlcv_data:
                    snapshot.ohlcv = OHLCVData(
                        timestamp=ohlcv_data.get("timestamp", timestamp),
                        open=Decimal(str(ohlcv_data.get("open", 0))),
                        high=Decimal(str(ohlcv_data.get("high", 0))),
                        low=Decimal(str(ohlcv_data.get("low", 0))),
                        close=Decimal(str(ohlcv_data.get("close", 0))),
                        volume=Decimal(str(ohlcv_data.get("volume", 0))),
                        symbol=symbol,
                        timeframe=ohlcv_data.get("timeframe", "1m"),
                    )
                
                # Get derived metrics
                metrics = await self._data_service.get_derived_metrics(symbol)
                if metrics:
                    snapshot.volume_24h = Decimal(str(metrics.get("volume_24h", 0)))
                    snapshot.market_condition = metrics.get("market_condition")
                    snapshot.sentiment_score = Decimal(str(metrics.get("sentiment_score", 0)))
                    snapshot.flow_score = Decimal(str(metrics.get("flow_score", 0)))
                    snapshot.aggregated_risk_level = Decimal(str(metrics.get("risk_level", 0)))
                    
            except Exception as e:
                logger.error(f"Error collecting live market data: {e}")
        
        return snapshot
    
    async def collect_feature_snapshot(
        self,
        symbol: str,
        timestamp: datetime,
    ) -> FeatureSnapshot:
        """Collect live feature calculations."""
        snapshot = FeatureSnapshot(
            snapshot_id=self._generate_snapshot_id(),
            timestamp=timestamp,
            symbol=symbol,
            source="live",
        )
        
        if self._feature_service:
            try:
                features = await self._feature_service.get_features(symbol, timestamp)
                if features:
                    snapshot.features = {
                        k: Decimal(str(v)) for k, v in features.items()
                    }
                    snapshot.calculation_version = features.get("_version", "")
            except Exception as e:
                logger.error(f"Error collecting live features: {e}")
        
        return snapshot
    
    async def collect_decision_snapshot(
        self,
        cycle_id: str,
        timestamp: datetime,
    ) -> DecisionSnapshot:
        """Collect live decision state."""
        snapshot = DecisionSnapshot(
            snapshot_id=self._generate_snapshot_id(),
            timestamp=timestamp,
            cycle_id=cycle_id,
            source="live",
        )
        
        if self._trade_guard:
            try:
                decision = await self._trade_guard.get_current_decision()
                if decision:
                    snapshot.trade_guard_decision = decision.get("decision", "")
                    snapshot.guard_state = decision.get("state", "")
                    snapshot.reason_codes = decision.get("reasons", [])
                    snapshot.entry_permitted = decision.get("entry_permitted", False)
                    snapshot.entry_reason = decision.get("entry_reason", "")
                    
                    if decision.get("position_size"):
                        snapshot.position_size = Decimal(str(decision["position_size"]))
                    if decision.get("position_size_pct"):
                        snapshot.position_size_pct = Decimal(str(decision["position_size_pct"]))
                    if decision.get("risk_level"):
                        snapshot.risk_level = Decimal(str(decision["risk_level"]))
                        
            except Exception as e:
                logger.error(f"Error collecting live decision: {e}")
        
        return snapshot
    
    async def collect_execution_snapshot(
        self,
        cycle_id: str,
        timestamp: datetime,
    ) -> ExecutionSnapshot:
        """Collect live execution state."""
        snapshot = ExecutionSnapshot(
            snapshot_id=self._generate_snapshot_id(),
            timestamp=timestamp,
            cycle_id=cycle_id,
            source="live",
        )
        
        if self._execution_engine:
            try:
                execution = await self._execution_engine.get_cycle_execution(cycle_id)
                if execution:
                    snapshot.order_type = execution.get("order_type", "")
                    snapshot.order_side = execution.get("order_side", "")
                    
                    if execution.get("order_size"):
                        snapshot.order_size = Decimal(str(execution["order_size"]))
                    if execution.get("entry_price"):
                        snapshot.entry_price = Decimal(str(execution["entry_price"]))
                    if execution.get("expected_price"):
                        snapshot.expected_price = Decimal(str(execution["expected_price"]))
                    if execution.get("slippage"):
                        snapshot.slippage = Decimal(str(execution["slippage"]))
                    if execution.get("fill_ratio"):
                        snapshot.fill_ratio = Decimal(str(execution["fill_ratio"]))
                    if execution.get("fill_time_seconds"):
                        snapshot.fill_time_seconds = execution["fill_time_seconds"]
                    if execution.get("fees"):
                        snapshot.fees = Decimal(str(execution["fees"]))
                    if execution.get("fee_rate"):
                        snapshot.fee_rate = Decimal(str(execution["fee_rate"]))
                        
            except Exception as e:
                logger.error(f"Error collecting live execution: {e}")
        
        return snapshot


# ============================================================
# BACKTEST DATA COLLECTOR
# ============================================================

class BacktestDataCollector(BaseDataCollector):
    """Collects data from backtest replay."""
    
    def __init__(
        self,
        backtest_engine: Any = None,
        historical_data_source: Any = None,
    ):
        super().__init__("backtest")
        self._backtest_engine = backtest_engine
        self._historical_data = historical_data_source
        self._replay_state: Dict[str, Any] = {}
    
    def set_replay_state(self, state: Dict[str, Any]) -> None:
        """Set the current replay state for collection."""
        self._replay_state = state
    
    async def collect_market_snapshot(
        self,
        symbol: str,
        timestamp: datetime,
    ) -> MarketSnapshot:
        """Collect backtest market data."""
        snapshot = MarketSnapshot(
            snapshot_id=self._generate_snapshot_id(),
            timestamp=timestamp,
            symbol=symbol,
            source="backtest",
        )
        
        # Use replay state if available
        if self._replay_state:
            market_data = self._replay_state.get("market_data", {})
            if market_data:
                snapshot.ohlcv = OHLCVData(
                    timestamp=timestamp,
                    open=Decimal(str(market_data.get("open", 0))),
                    high=Decimal(str(market_data.get("high", 0))),
                    low=Decimal(str(market_data.get("low", 0))),
                    close=Decimal(str(market_data.get("close", 0))),
                    volume=Decimal(str(market_data.get("volume", 0))),
                    symbol=symbol,
                    timeframe=market_data.get("timeframe", "1m"),
                )
                
                snapshot.volume_24h = Decimal(str(market_data.get("volume_24h", 0)))
                snapshot.market_condition = market_data.get("market_condition")
                snapshot.sentiment_score = Decimal(str(market_data.get("sentiment_score", 0)))
                snapshot.flow_score = Decimal(str(market_data.get("flow_score", 0)))
                snapshot.aggregated_risk_level = Decimal(str(market_data.get("risk_level", 0)))
        
        elif self._historical_data:
            try:
                data = await self._historical_data.get_at_timestamp(symbol, timestamp)
                if data:
                    snapshot.ohlcv = OHLCVData(
                        timestamp=timestamp,
                        open=Decimal(str(data.get("open", 0))),
                        high=Decimal(str(data.get("high", 0))),
                        low=Decimal(str(data.get("low", 0))),
                        close=Decimal(str(data.get("close", 0))),
                        volume=Decimal(str(data.get("volume", 0))),
                        symbol=symbol,
                        timeframe="1m",
                    )
            except Exception as e:
                logger.error(f"Error collecting backtest market data: {e}")
        
        return snapshot
    
    async def collect_feature_snapshot(
        self,
        symbol: str,
        timestamp: datetime,
    ) -> FeatureSnapshot:
        """Collect backtest feature calculations."""
        snapshot = FeatureSnapshot(
            snapshot_id=self._generate_snapshot_id(),
            timestamp=timestamp,
            symbol=symbol,
            source="backtest",
        )
        
        if self._replay_state:
            features = self._replay_state.get("features", {})
            if features:
                snapshot.features = {
                    k: Decimal(str(v)) for k, v in features.items()
                    if not k.startswith("_")
                }
                snapshot.calculation_version = features.get("_version", "")
        
        elif self._backtest_engine:
            try:
                features = await self._backtest_engine.calculate_features(symbol, timestamp)
                if features:
                    snapshot.features = {
                        k: Decimal(str(v)) for k, v in features.items()
                    }
            except Exception as e:
                logger.error(f"Error collecting backtest features: {e}")
        
        return snapshot
    
    async def collect_decision_snapshot(
        self,
        cycle_id: str,
        timestamp: datetime,
    ) -> DecisionSnapshot:
        """Collect backtest decision state."""
        snapshot = DecisionSnapshot(
            snapshot_id=self._generate_snapshot_id(),
            timestamp=timestamp,
            cycle_id=cycle_id,
            source="backtest",
        )
        
        if self._replay_state:
            decision = self._replay_state.get("decision", {})
            if decision:
                snapshot.trade_guard_decision = decision.get("decision", "")
                snapshot.guard_state = decision.get("state", "")
                snapshot.reason_codes = decision.get("reasons", [])
                snapshot.entry_permitted = decision.get("entry_permitted", False)
                snapshot.entry_reason = decision.get("entry_reason", "")
                
                if decision.get("position_size"):
                    snapshot.position_size = Decimal(str(decision["position_size"]))
                if decision.get("position_size_pct"):
                    snapshot.position_size_pct = Decimal(str(decision["position_size_pct"]))
                if decision.get("risk_level"):
                    snapshot.risk_level = Decimal(str(decision["risk_level"]))
        
        return snapshot
    
    async def collect_execution_snapshot(
        self,
        cycle_id: str,
        timestamp: datetime,
    ) -> ExecutionSnapshot:
        """Collect backtest execution state."""
        snapshot = ExecutionSnapshot(
            snapshot_id=self._generate_snapshot_id(),
            timestamp=timestamp,
            cycle_id=cycle_id,
            source="backtest",
        )
        
        if self._replay_state:
            execution = self._replay_state.get("execution", {})
            if execution:
                snapshot.order_type = execution.get("order_type", "")
                snapshot.order_side = execution.get("order_side", "")
                
                if execution.get("order_size"):
                    snapshot.order_size = Decimal(str(execution["order_size"]))
                if execution.get("entry_price"):
                    snapshot.entry_price = Decimal(str(execution["entry_price"]))
                if execution.get("expected_price"):
                    snapshot.expected_price = Decimal(str(execution["expected_price"]))
                if execution.get("slippage"):
                    snapshot.slippage = Decimal(str(execution["slippage"]))
                if execution.get("fill_ratio"):
                    snapshot.fill_ratio = Decimal(str(execution["fill_ratio"]))
                if execution.get("fill_time_seconds"):
                    snapshot.fill_time_seconds = execution["fill_time_seconds"]
                if execution.get("fees"):
                    snapshot.fees = Decimal(str(execution["fees"]))
                if execution.get("fee_rate"):
                    snapshot.fee_rate = Decimal(str(execution["fee_rate"]))
        
        return snapshot


# ============================================================
# SYNCHRONIZED COLLECTOR
# ============================================================

class SynchronizedCollector:
    """
    Coordinates collection from both live and backtest sources.
    
    Ensures:
    - Same timestamps
    - Same aggregation windows
    - Consistent snapshot pairing
    """
    
    def __init__(
        self,
        live_collector: LiveDataCollector,
        backtest_collector: BacktestDataCollector,
    ):
        self._live = live_collector
        self._backtest = backtest_collector
    
    async def collect_market_pair(
        self,
        symbol: str,
        timestamp: datetime,
    ) -> tuple[MarketSnapshot, MarketSnapshot]:
        """Collect paired market snapshots."""
        live_snapshot, backtest_snapshot = await asyncio.gather(
            self._live.collect_market_snapshot(symbol, timestamp),
            self._backtest.collect_market_snapshot(symbol, timestamp),
        )
        return live_snapshot, backtest_snapshot
    
    async def collect_feature_pair(
        self,
        symbol: str,
        timestamp: datetime,
    ) -> tuple[FeatureSnapshot, FeatureSnapshot]:
        """Collect paired feature snapshots."""
        live_snapshot, backtest_snapshot = await asyncio.gather(
            self._live.collect_feature_snapshot(symbol, timestamp),
            self._backtest.collect_feature_snapshot(symbol, timestamp),
        )
        return live_snapshot, backtest_snapshot
    
    async def collect_decision_pair(
        self,
        cycle_id: str,
        timestamp: datetime,
    ) -> tuple[DecisionSnapshot, DecisionSnapshot]:
        """Collect paired decision snapshots."""
        live_snapshot, backtest_snapshot = await asyncio.gather(
            self._live.collect_decision_snapshot(cycle_id, timestamp),
            self._backtest.collect_decision_snapshot(cycle_id, timestamp),
        )
        return live_snapshot, backtest_snapshot
    
    async def collect_execution_pair(
        self,
        cycle_id: str,
        timestamp: datetime,
    ) -> tuple[ExecutionSnapshot, ExecutionSnapshot]:
        """Collect paired execution snapshots."""
        live_snapshot, backtest_snapshot = await asyncio.gather(
            self._live.collect_execution_snapshot(cycle_id, timestamp),
            self._backtest.collect_execution_snapshot(cycle_id, timestamp),
        )
        return live_snapshot, backtest_snapshot
    
    async def collect_full_cycle(
        self,
        symbol: str,
        cycle_id: str,
        timestamp: datetime,
    ) -> Dict[str, tuple]:
        """Collect all snapshot pairs for a cycle."""
        market_pair = await self.collect_market_pair(symbol, timestamp)
        feature_pair = await self.collect_feature_pair(symbol, timestamp)
        decision_pair = await self.collect_decision_pair(cycle_id, timestamp)
        execution_pair = await self.collect_execution_pair(cycle_id, timestamp)
        
        return {
            "market": market_pair,
            "feature": feature_pair,
            "decision": decision_pair,
            "execution": execution_pair,
        }
    
    def compute_input_hash(self, snapshots: Dict[str, tuple]) -> str:
        """Compute hash of input data for reproducibility."""
        data = {}
        for key, (live, backtest) in snapshots.items():
            if hasattr(live, "to_dict"):
                data[f"live_{key}"] = live.to_dict()
            if hasattr(backtest, "to_dict"):
                data[f"backtest_{key}"] = backtest.to_dict()
        
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_live_collector(
    data_service: Any = None,
    feature_service: Any = None,
    trade_guard: Any = None,
    execution_engine: Any = None,
) -> LiveDataCollector:
    """Create a LiveDataCollector."""
    return LiveDataCollector(
        data_service=data_service,
        feature_service=feature_service,
        trade_guard=trade_guard,
        execution_engine=execution_engine,
    )


def create_backtest_collector(
    backtest_engine: Any = None,
    historical_data_source: Any = None,
) -> BacktestDataCollector:
    """Create a BacktestDataCollector."""
    return BacktestDataCollector(
        backtest_engine=backtest_engine,
        historical_data_source=historical_data_source,
    )


def create_synchronized_collector(
    live_collector: LiveDataCollector,
    backtest_collector: BacktestDataCollector,
) -> SynchronizedCollector:
    """Create a SynchronizedCollector."""
    return SynchronizedCollector(
        live_collector=live_collector,
        backtest_collector=backtest_collector,
    )
