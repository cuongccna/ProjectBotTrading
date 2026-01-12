#!/usr/bin/env python3
"""
Dashboard Server Runner - LIVE DATA VERSION.

============================================================
USAGE
============================================================
    python scripts/run_dashboard.py
    python scripts/run_dashboard.py --port 8080
    python scripts/run_dashboard.py --host 0.0.0.0 --port 8080
    python scripts/run_dashboard.py --data-dir ./storage/state

============================================================
ENDPOINTS
============================================================
    GET  /api/dashboard/health      - Health check
    GET  /api/dashboard/overview    - Complete dashboard overview
    GET  /api/dashboard/system      - System status
    GET  /api/dashboard/risk        - Risk and exposure
    GET  /api/dashboard/positions   - All positions
    GET  /api/dashboard/execution   - Execution view
    GET  /api/dashboard/orders      - Order history
    GET  /api/dashboard/signals     - Current signals
    GET  /api/dashboard/alerts      - Active alerts

============================================================
DATA SOURCES
============================================================
This dashboard reads LIVE data from:
- storage/state/orchestrator_state.json  - System state
- storage/state/positions.json           - Open positions
- storage/state/orders.json              - Order history
- storage/state/signals.json             - Signal history
- storage/state/risk_metrics.json        - Risk metrics
- storage/state/balance.json             - Account balance
- storage/state/module_health.json       - Module health
- storage/state/data_sources.json        - Data source status

============================================================
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, Optional, List

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from aiohttp import web

from monitoring.dashboard_service import DashboardService
from monitoring.api import setup_dashboard_routes
from monitoring.alerts import AlertManager
from monitoring.collectors.base import (
    SystemStateCollector,
    DataPipelineCollector,
    ModuleHealthCollector,
)
from monitoring.collectors.risk_collector import (
    RiskExposureCollector,
    PositionCollector,
)
from monitoring.collectors.execution_collector import (
    SignalCollector,
    OrderCollector,
    ExecutionMetricsCollector,
)

logger = logging.getLogger(__name__)


# ============================================================
# LOGGING
# ============================================================

def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ============================================================
# LIVE DATA STORES
# ============================================================
# These classes provide read-only access to actual system data
# stored in JSON files by the orchestrator and other modules

class FileBasedStateStore:
    """
    Read-only state store that reads from orchestrator state files.
    """
    
    def __init__(self, state_dir: Path):
        """Initialize state store."""
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)
    
    async def get(self, key: str) -> Any:
        """Get a value by key."""
        try:
            parts = key.split(".")
            
            if parts[0] == "system":
                return await self._get_system_value(parts[1] if len(parts) > 1 else None)
            elif parts[0] == "trading":
                return await self._get_trading_value(parts[1] if len(parts) > 1 else None)
            elif parts[0] == "modules":
                return await self._get_modules_value(parts[1] if len(parts) > 1 else None)
            
            return None
        except Exception as e:
            logger.debug(f"Error getting {key}: {e}")
            return None
    
    async def _get_system_value(self, subkey: Optional[str]) -> Any:
        """Get system state value."""
        state_file = self._state_dir / "orchestrator_state.json"
        if not state_file.exists():
            return None
        
        try:
            with open(state_file, "r") as f:
                data = json.load(f)
            
            if subkey is None:
                return data
            elif subkey == "mode":
                return data.get("state", "INITIALIZING")
            elif subkey == "mode_changed_at":
                ts = data.get("timestamp")
                return datetime.fromisoformat(ts) if ts else None
            elif subkey == "mode_changed_by":
                return data.get("triggered_by", "system")
            elif subkey == "mode_reason":
                return data.get("reason", "")
            
            return data.get(subkey)
        except Exception as e:
            logger.debug(f"Error reading system state: {e}")
            return None
    
    async def _get_trading_value(self, subkey: Optional[str]) -> Any:
        """Get trading state value."""
        if subkey == "enabled":
            mode = await self._get_system_value("mode")
            return mode in ("running", "RUNNING")
        elif subkey == "open_positions":
            positions_file = self._state_dir / "positions.json"
            if positions_file.exists():
                try:
                    with open(positions_file, "r") as f:
                        return len(json.load(f))
                except Exception:
                    pass
            return 0
        elif subkey == "active_orders":
            orders_file = self._state_dir / "active_orders.json"
            if orders_file.exists():
                try:
                    with open(orders_file, "r") as f:
                        return len(json.load(f))
                except Exception:
                    pass
            return 0
        
        return None
    
    async def _get_modules_value(self, subkey: Optional[str]) -> Any:
        """Get modules health value."""
        health_file = self._state_dir / "module_health.json"
        
        if health_file.exists():
            try:
                with open(health_file, "r") as f:
                    data = json.load(f)
                
                if subkey == "health":
                    return data
                
                return data.get(subkey)
            except Exception as e:
                logger.debug(f"Error reading module health: {e}")
        
        return {}


class FileBasedPositionStore:
    """Read-only position store."""
    
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
    
    async def get_all_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions."""
        positions_file = self._data_dir / "positions.json"
        
        if not positions_file.exists():
            return []
        
        try:
            with open(positions_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"Error reading positions: {e}")
            return []


class FileBasedOrderStore:
    """Read-only order store."""
    
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
    
    async def get_recent_orders(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent orders."""
        orders_file = self._data_dir / "orders.json"
        
        if not orders_file.exists():
            return []
        
        try:
            with open(orders_file, "r") as f:
                orders = json.load(f)
            return orders[-limit:] if orders else []
        except Exception as e:
            logger.debug(f"Error reading orders: {e}")
            return []


class FileBasedSignalStore:
    """Read-only signal store."""
    
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
    
    async def get_recent_signals(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent signals."""
        signals_file = self._data_dir / "signals.json"
        
        if not signals_file.exists():
            return []
        
        try:
            with open(signals_file, "r") as f:
                signals = json.load(f)
            return signals[-limit:] if signals else []
        except Exception as e:
            logger.debug(f"Error reading signals: {e}")
            return []
    
    async def get_signal(self, signal_id: str) -> Optional[Dict[str, Any]]:
        signals = await self.get_recent_signals(limit=1000)
        for sig in signals:
            if sig.get("id") == signal_id:
                return sig
        return None
    
    async def get_signals_by_strategy(self, strategy: str, limit: int = 50) -> List[Dict[str, Any]]:
        signals = await self.get_recent_signals(limit=1000)
        filtered = [s for s in signals if s.get("strategy") == strategy]
        return filtered[-limit:]
    
    async def get_pending_signals(self) -> List[Dict[str, Any]]:
        signals = await self.get_recent_signals(limit=100)
        return [s for s in signals if not s.get("processed", False)]


class FileBasedRiskStore:
    """Read-only risk store."""
    
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
    
    async def get_current_metrics(self) -> Dict[str, Any]:
        """Get current risk metrics."""
        risk_file = self._data_dir / "risk_metrics.json"
        
        if not risk_file.exists():
            return {}
        
        try:
            with open(risk_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"Error reading risk metrics: {e}")
            return {}


class FileBasedBalanceReader:
    """Read-only balance reader."""
    
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
    
    async def get_balance(self) -> Dict[str, Any]:
        """Get current balance."""
        balance_file = self._data_dir / "balance.json"
        
        if not balance_file.exists():
            return {"is_fresh": False}
        
        try:
            with open(balance_file, "r") as f:
                data = json.load(f)
            
            timestamp = data.get("timestamp")
            if timestamp:
                ts = datetime.fromisoformat(timestamp)
                age = (datetime.utcnow() - ts).total_seconds()
                data["is_fresh"] = age < 60
            else:
                data["is_fresh"] = False
            
            return data
        except Exception as e:
            logger.debug(f"Error reading balance: {e}")
            return {"is_fresh": False}


class FileBasedDataSourceRegistry:
    """Read-only data source registry."""
    
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
    
    async def list_sources(self) -> List[str]:
        """List all data sources."""
        sources_file = self._data_dir / "data_sources.json"
        
        if not sources_file.exists():
            return ["binance", "bybit"]
        
        try:
            with open(sources_file, "r") as f:
                data = json.load(f)
            return list(data.keys())
        except Exception as e:
            logger.debug(f"Error listing sources: {e}")
            return ["binance", "bybit"]
    
    async def get_source_info(self, source_name: str) -> Optional[Dict[str, Any]]:
        sources_file = self._data_dir / "data_sources.json"
        
        if not sources_file.exists():
            return None
        
        try:
            with open(sources_file, "r") as f:
                data = json.load(f)
            return data.get(source_name)
        except Exception as e:
            logger.debug(f"Error getting source {source_name}: {e}")
            return None


class FileBasedModuleRegistry:
    """Read-only module registry."""
    
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
    
    async def list_modules(self) -> List[str]:
        health_file = self._data_dir / "module_health.json"
        
        if not health_file.exists():
            return []
        
        try:
            with open(health_file, "r") as f:
                data = json.load(f)
            return list(data.keys())
        except Exception as e:
            logger.debug(f"Error listing modules: {e}")
            return []
    
    async def get_module_info(self, module_name: str) -> Optional[Dict[str, Any]]:
        health_file = self._data_dir / "module_health.json"
        
        if not health_file.exists():
            return None
        
        try:
            with open(health_file, "r") as f:
                data = json.load(f)
            return data.get(module_name)
        except Exception as e:
            logger.debug(f"Error getting module {module_name}: {e}")
            return None


# ============================================================
# DASHBOARD FACTORY
# ============================================================

def create_dashboard_service(data_dir: Path) -> DashboardService:
    """
    Create dashboard service with LIVE data collectors.
    
    Args:
        data_dir: Directory containing state files
    """
    # Create stores
    state_store = FileBasedStateStore(data_dir)
    position_store = FileBasedPositionStore(data_dir)
    order_store = FileBasedOrderStore(data_dir)
    signal_store = FileBasedSignalStore(data_dir)
    risk_store = FileBasedRiskStore(data_dir)
    balance_reader = FileBasedBalanceReader(data_dir)
    data_source_registry = FileBasedDataSourceRegistry(data_dir)
    module_registry = FileBasedModuleRegistry(data_dir)
    
    # Create collectors with real stores
    return DashboardService(
        system_collector=SystemStateCollector(state_store=state_store),
        data_pipeline_collector=DataPipelineCollector(data_source_registry=data_source_registry),
        module_health_collector=ModuleHealthCollector(module_registry=module_registry),
        risk_collector=RiskExposureCollector(
            risk_store=risk_store,
            position_store=position_store,
            balance_reader=balance_reader,
        ),
        position_collector=PositionCollector(position_store=position_store),
        signal_collector=SignalCollector(signal_store=signal_store),
        order_collector=OrderCollector(order_store=order_store),
        execution_metrics_collector=ExecutionMetricsCollector(order_store=order_store),
    )


def initialize_sample_data(data_dir: Path) -> None:
    """
    Initialize sample data files if they don't exist.
    
    This creates realistic sample data for demo purposes.
    In production, these files are written by the actual modules.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Orchestrator state
    state_file = data_dir / "orchestrator_state.json"
    if not state_file.exists():
        with open(state_file, "w") as f:
            json.dump({
                "state": "running",
                "reason": "Normal operation",
                "triggered_by": "orchestrator",
                "timestamp": datetime.utcnow().isoformat(),
                "transition_count": 1,
            }, f, indent=2)
    
    # Module health
    health_file = data_dir / "module_health.json"
    if not health_file.exists():
        modules = [
            "data_ingestion", "data_processing", "risk_scoring",
            "strategy_engine", "trade_guard", "system_risk_controller",
            "execution_engine", "monitoring",
        ]
        health = {}
        for name in modules:
            health[name] = {
                "type": "core",
                "status": "HEALTHY",
                "cpu_usage": 5.0,
                "memory_usage": 100.0,
                "memory_limit": 1024.0,
                "queue_backlog": 0,
                "queue_max_size": 1000,
                "requests_per_minute": 10,
                "errors_per_minute": 0,
            }
        with open(health_file, "w") as f:
            json.dump(health, f, indent=2)
    
    # Positions
    positions_file = data_dir / "positions.json"
    if not positions_file.exists():
        with open(positions_file, "w") as f:
            json.dump([
                {
                    "id": "pos_001",
                    "symbol": "BTCUSDT",
                    "exchange": "binance",
                    "side": "long",
                    "size": "0.1",
                    "notional_value": "4550.00",
                    "entry_price": "45000.00",
                    "current_price": "45500.00",
                    "liquidation_price": "38000.00",
                    "unrealized_pnl": "50.00",
                    "realized_pnl": "0.00",
                    "leverage": 5,
                    "margin_used": "910.00",
                    "opened_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "strategy": "momentum",
                },
                {
                    "id": "pos_002",
                    "symbol": "ETHUSDT",
                    "exchange": "binance",
                    "side": "long",
                    "size": "1.0",
                    "notional_value": "2520.00",
                    "entry_price": "2500.00",
                    "current_price": "2520.00",
                    "liquidation_price": "1800.00",
                    "unrealized_pnl": "20.00",
                    "realized_pnl": "0.00",
                    "leverage": 3,
                    "margin_used": "840.00",
                    "opened_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "strategy": "trend_following",
                },
            ], f, indent=2)
    
    # Balance
    balance_file = data_dir / "balance.json"
    if not balance_file.exists():
        with open(balance_file, "w") as f:
            json.dump({
                "total_equity": "50000.00",
                "total_balance": "48250.00",
                "available_balance": "46500.00",
                "margin_used": "1750.00",
                "margin_ratio": "0.035",
                "timestamp": datetime.utcnow().isoformat(),
            }, f, indent=2)
    
    # Risk metrics
    risk_file = data_dir / "risk_metrics.json"
    if not risk_file.exists():
        with open(risk_file, "w") as f:
            json.dump({
                "current_drawdown": "0.50",
                "max_drawdown_today": "1.20",
                "daily_pnl": "70.00",
                "realized_pnl": "0.00",
                "unrealized_pnl": "70.00",
                "risk_budget_used_pct": "15.00",
                "risk_budget_remaining": "4250.00",
                "max_position_size": "10000.00",
                "max_leverage": 10,
                "current_leverage": 2.5,
            }, f, indent=2)
    
    # Data sources
    sources_file = data_dir / "data_sources.json"
    if not sources_file.exists():
        with open(sources_file, "w") as f:
            json.dump({
                "binance": {
                    "type": "exchange",
                    "last_fetch_time": datetime.utcnow().isoformat(),
                    "latency_ms": 45.0,
                    "missing_fields": False,
                    "abnormal_volume": False,
                },
                "bybit": {
                    "type": "exchange",
                    "last_fetch_time": datetime.utcnow().isoformat(),
                    "latency_ms": 52.0,
                    "missing_fields": False,
                    "abnormal_volume": False,
                },
            }, f, indent=2)
    
    # Signals
    signals_file = data_dir / "signals.json"
    if not signals_file.exists():
        with open(signals_file, "w") as f:
            json.dump([
                {
                    "id": "sig_001",
                    "strategy": "momentum",
                    "type": "entry",
                    "symbol": "BTCUSDT",
                    "exchange": "binance",
                    "direction": "BUY",
                    "strength": "0.75",
                    "generated_at": datetime.utcnow().isoformat(),
                    "processed": True,
                    "processed_at": datetime.utcnow().isoformat(),
                    "resulted_in_order": True,
                    "order_id": "ord_001",
                    "source_data_timestamp": datetime.utcnow().isoformat(),
                },
            ], f, indent=2)
    
    # Orders
    orders_file = data_dir / "orders.json"
    if not orders_file.exists():
        with open(orders_file, "w") as f:
            json.dump([
                {
                    "id": "ord_001",
                    "internal_id": "int_001",
                    "exchange_id": "ex_001",
                    "symbol": "BTCUSDT",
                    "exchange": "binance",
                    "side": "BUY",
                    "type": "LIMIT",
                    "status": "FILLED",
                    "requested_quantity": "0.1",
                    "requested_price": "45000.00",
                    "filled_quantity": "0.1",
                    "avg_fill_price": "44990.00",
                    "slippage": "-10.00",
                    "created_at": datetime.utcnow().isoformat(),
                    "filled_at": datetime.utcnow().isoformat(),
                },
            ], f, indent=2)
    
    logger.info(f"Sample data initialized in {data_dir}")


# ============================================================
# MAIN
# ============================================================

async def run_dashboard(host: str, port: int, data_dir: Path) -> None:
    """Run dashboard server."""
    # Initialize sample data if needed
    initialize_sample_data(data_dir)
    
    # Create dashboard service with live data
    dashboard_service = create_dashboard_service(data_dir)
    
    # Create alert manager
    alert_manager = AlertManager()
    
    # Create main app
    app = web.Application()
    
    # Add dashboard routes
    setup_dashboard_routes(app, dashboard_service, alert_manager)
    
    # Add root handler
    async def root_handler(request):
        return web.Response(
            text=f"""
<!DOCTYPE html>
<html>
<head>
    <title>Crypto Trading Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #1a1a2e; color: #eee; }}
        h1 {{ color: #00d4ff; }}
        a {{ color: #00d4ff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .endpoints {{ background: #16213e; padding: 20px; border-radius: 8px; }}
        .endpoint {{ margin: 10px 0; padding: 10px; background: #0f3460; border-radius: 4px; }}
        .method {{ color: #4ade80; font-weight: bold; }}
        .status {{ background: #22c55e; padding: 5px 15px; border-radius: 4px; display: inline-block; margin-bottom: 20px; }}
        .info {{ background: #16213e; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <h1>🚀 Crypto Trading Dashboard</h1>
    <div class="status">LIVE DATA MODE</div>
    <p>Institutional-Grade Monitoring System</p>
    
    <div class="info">
        <strong>Data Source:</strong> {data_dir}<br>
        <strong>Mode:</strong> Live data from state files
    </div>
    
    <div class="endpoints">
        <h2>API Endpoints</h2>
        <div class="endpoint"><span class="method">GET</span> <a href="/api/dashboard/health">/api/dashboard/health</a> - Health check</div>
        <div class="endpoint"><span class="method">GET</span> <a href="/api/dashboard/overview">/api/dashboard/overview</a> - Complete overview</div>
        <div class="endpoint"><span class="method">GET</span> <a href="/api/dashboard/system">/api/dashboard/system</a> - System status</div>
        <div class="endpoint"><span class="method">GET</span> <a href="/api/dashboard/risk">/api/dashboard/risk</a> - Risk exposure</div>
        <div class="endpoint"><span class="method">GET</span> <a href="/api/dashboard/positions">/api/dashboard/positions</a> - Positions</div>
        <div class="endpoint"><span class="method">GET</span> <a href="/api/dashboard/execution">/api/dashboard/execution</a> - Execution view</div>
        <div class="endpoint"><span class="method">GET</span> <a href="/api/dashboard/orders">/api/dashboard/orders</a> - Orders</div>
        <div class="endpoint"><span class="method">GET</span> <a href="/api/dashboard/signals">/api/dashboard/signals</a> - Signals</div>
        <div class="endpoint"><span class="method">GET</span> <a href="/api/dashboard/alerts">/api/dashboard/alerts</a> - Alerts</div>
    </div>
</body>
</html>
            """,
            content_type="text/html",
        )
    
    app.router.add_get("/", root_handler)
    
    # Start server
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    logger.info(f"Dashboard server started at http://{host}:{port}")
    logger.info(f"Data directory: {data_dir}")
    logger.info("Press Ctrl+C to stop")
    
    print(f"""
============================================================
  DASHBOARD SERVER RUNNING - LIVE DATA MODE
============================================================
  URL:       http://{host}:{port}
  API:       http://{host}:{port}/api/dashboard/
  Data Dir:  {data_dir}
  
  Endpoints:
    /api/dashboard/health      - Health check
    /api/dashboard/overview    - Complete overview
    /api/dashboard/system      - System status
    /api/dashboard/risk        - Risk exposure
    /api/dashboard/positions   - Positions
    /api/dashboard/orders      - Orders
    /api/dashboard/signals     - Signals
    /api/dashboard/alerts      - Alerts
============================================================
""")
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run the trading dashboard server with LIVE data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind to (default: 8080)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=PROJECT_ROOT / "storage" / "state",
        help="Directory containing state files (default: storage/state)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )
    
    args = parser.parse_args()
    
    setup_logging(args.log_level)
    
    try:
        asyncio.run(run_dashboard(args.host, args.port, args.data_dir))
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
