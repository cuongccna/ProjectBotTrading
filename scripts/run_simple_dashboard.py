#!/usr/bin/env python3
"""
Simple Dashboard Server - Direct JSON API.

============================================================
USAGE
============================================================
    python scripts/run_simple_dashboard.py
    python scripts/run_simple_dashboard.py --port 8080

============================================================
PURPOSE
============================================================
This is a SIMPLE dashboard that reads directly from JSON files
without going through the complex collector/model system.

It provides a clean REST API for monitoring the trading system.

============================================================
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from aiohttp import web

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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

logger = logging.getLogger(__name__)


# ============================================================
# DATA READER
# ============================================================

class LiveDataReader:
    """
    Simple reader that loads data directly from JSON files.
    
    This bypasses the complex collector/model system and
    provides direct access to live data.
    """
    
    def __init__(self, data_dir: Path):
        """Initialize data reader."""
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
    
    def _read_json(self, filename: str) -> Any:
        """Read JSON file safely."""
        filepath = self._data_dir / filename
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error reading {filename}: {e}")
            return None
    
    async def get_system_state(self) -> Dict[str, Any]:
        """Get current system state."""
        data = self._read_json("orchestrator_state.json")
        
        if data is None:
            return {
                "state": "UNKNOWN",
                "trading_enabled": False,
                "message": "No state file found",
            }
        
        return {
            "state": data.get("state", "UNKNOWN"),
            "reason": data.get("reason", ""),
            "triggered_by": data.get("triggered_by", ""),
            "timestamp": data.get("timestamp", ""),
            "transition_count": data.get("transition_count", 0),
            "trading_enabled": data.get("state", "").lower() == "running",
        }
    
    async def get_module_health(self) -> Dict[str, Any]:
        """Get module health status."""
        data = self._read_json("module_health.json")
        
        if data is None:
            return {"modules": {}, "summary": {"healthy": 0, "degraded": 0, "unhealthy": 0}}
        
        summary = {"healthy": 0, "degraded": 0, "unhealthy": 0}
        for name, health in data.items():
            status = health.get("status", "UNKNOWN")
            if status == "HEALTHY":
                summary["healthy"] += 1
            elif status == "DEGRADED":
                summary["degraded"] += 1
            else:
                summary["unhealthy"] += 1
        
        return {"modules": data, "summary": summary}
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get open positions."""
        data = self._read_json("positions.json")
        return data if data is not None else []
    
    async def get_orders(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get order history."""
        data = self._read_json("orders.json")
        if data is None:
            return []
        return data[-limit:]
    
    async def get_signals(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get signal history."""
        data = self._read_json("signals.json")
        if data is None:
            return []
        return data[-limit:]
    
    async def get_balance(self) -> Dict[str, Any]:
        """Get account balance."""
        data = self._read_json("balance.json")
        
        if data is None:
            return {"available": False, "message": "No balance data"}
        
        # Check freshness
        timestamp = data.get("timestamp")
        is_fresh = False
        if timestamp:
            try:
                ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                age = (datetime.utcnow() - ts.replace(tzinfo=None)).total_seconds()
                is_fresh = age < 300  # 5 minutes
            except Exception:
                pass
        
        data["is_fresh"] = is_fresh
        data["available"] = True
        return data
    
    async def get_risk_metrics(self) -> Dict[str, Any]:
        """Get risk metrics."""
        data = self._read_json("risk_metrics.json")
        
        if data is None:
            return {"available": False, "message": "No risk data"}
        
        data["available"] = True
        return data
    
    async def get_data_sources(self) -> Dict[str, Any]:
        """Get data source status."""
        data = self._read_json("data_sources.json")
        
        if data is None:
            return {}
        
        return data
    
    async def get_overview(self) -> Dict[str, Any]:
        """Get complete system overview."""
        system = await self.get_system_state()
        health = await self.get_module_health()
        positions = await self.get_positions()
        balance = await self.get_balance()
        risk = await self.get_risk_metrics()
        sources = await self.get_data_sources()
        
        # Calculate position summary
        total_pnl = 0.0
        total_exposure = 0.0
        for pos in positions:
            try:
                total_pnl += float(pos.get("unrealized_pnl", 0))
                total_exposure += float(pos.get("notional_value", 0))
            except (ValueError, TypeError):
                pass
        
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "system": system,
            "module_health": health,
            "positions": {
                "count": len(positions),
                "total_pnl": total_pnl,
                "total_exposure": total_exposure,
                "details": positions,
            },
            "balance": balance,
            "risk": risk,
            "data_sources": sources,
        }


# ============================================================
# SAMPLE DATA
# ============================================================

def initialize_sample_data(data_dir: Path) -> None:
    """Initialize sample data files if they don't exist."""
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
                "cpu_usage_pct": 5.0,
                "memory_usage_mb": 100.0,
                "memory_limit_mb": 1024.0,
                "queue_backlog": 0,
                "queue_max_size": 1000,
                "last_heartbeat": datetime.utcnow().isoformat(),
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
                    "side": "LONG",
                    "quantity": "0.1",
                    "notional_value": "4550.00",
                    "entry_price": "45000.00",
                    "current_price": "45500.00",
                    "liquidation_price": "38000.00",
                    "unrealized_pnl": "50.00",
                    "leverage": 5,
                    "margin_used": "910.00",
                    "opened_at": datetime.utcnow().isoformat(),
                    "strategy": "momentum",
                },
                {
                    "id": "pos_002",
                    "symbol": "ETHUSDT",
                    "exchange": "binance",
                    "side": "LONG",
                    "quantity": "1.0",
                    "notional_value": "2520.00",
                    "entry_price": "2500.00",
                    "current_price": "2520.00",
                    "liquidation_price": "1800.00",
                    "unrealized_pnl": "20.00",
                    "leverage": 3,
                    "margin_used": "840.00",
                    "opened_at": datetime.utcnow().isoformat(),
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
                "current_drawdown_pct": "0.50",
                "max_drawdown_today_pct": "1.20",
                "daily_pnl": "70.00",
                "realized_pnl": "0.00",
                "unrealized_pnl": "70.00",
                "risk_budget_used_pct": "15.00",
                "risk_budget_remaining": "4250.00",
                "max_position_size": "10000.00",
                "max_leverage": 10,
                "current_leverage": 2.5,
                "risk_level": "LOW",
            }, f, indent=2)
    
    # Data sources
    sources_file = data_dir / "data_sources.json"
    if not sources_file.exists():
        with open(sources_file, "w") as f:
            json.dump({
                "binance": {
                    "type": "exchange",
                    "status": "connected",
                    "last_update": datetime.utcnow().isoformat(),
                    "latency_ms": 45.0,
                },
                "bybit": {
                    "type": "exchange",
                    "status": "connected",
                    "last_update": datetime.utcnow().isoformat(),
                    "latency_ms": 52.0,
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
                    "symbol": "BTCUSDT",
                    "direction": "BUY",
                    "strength": 0.75,
                    "generated_at": datetime.utcnow().isoformat(),
                    "status": "executed",
                    "order_id": "ord_001",
                },
            ], f, indent=2)
    
    # Orders
    orders_file = data_dir / "orders.json"
    if not orders_file.exists():
        with open(orders_file, "w") as f:
            json.dump([
                {
                    "id": "ord_001",
                    "symbol": "BTCUSDT",
                    "exchange": "binance",
                    "side": "BUY",
                    "type": "LIMIT",
                    "status": "FILLED",
                    "quantity": "0.1",
                    "price": "45000.00",
                    "filled_quantity": "0.1",
                    "filled_price": "44990.00",
                    "created_at": datetime.utcnow().isoformat(),
                },
            ], f, indent=2)
    
    logger.info(f"Sample data initialized in {data_dir}")


# ============================================================
# API HANDLERS
# ============================================================

class DashboardAPI:
    """Simple dashboard API handlers."""
    
    def __init__(self, reader: LiveDataReader):
        """Initialize API."""
        self._reader = reader
    
    async def health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat(),
            "service": "dashboard",
        })
    
    async def overview(self, request: web.Request) -> web.Response:
        """Get complete overview."""
        try:
            data = await self._reader.get_overview()
            return web.json_response({"status": "ok", "data": data})
        except Exception as e:
            logger.error(f"Error getting overview: {e}")
            return web.json_response({"status": "error", "error": str(e)}, status=500)
    
    async def system(self, request: web.Request) -> web.Response:
        """Get system state."""
        try:
            data = await self._reader.get_system_state()
            return web.json_response({"status": "ok", "data": data})
        except Exception as e:
            logger.error(f"Error getting system: {e}")
            return web.json_response({"status": "error", "error": str(e)}, status=500)
    
    async def modules(self, request: web.Request) -> web.Response:
        """Get module health."""
        try:
            data = await self._reader.get_module_health()
            return web.json_response({"status": "ok", "data": data})
        except Exception as e:
            logger.error(f"Error getting modules: {e}")
            return web.json_response({"status": "error", "error": str(e)}, status=500)
    
    async def positions(self, request: web.Request) -> web.Response:
        """Get positions."""
        try:
            data = await self._reader.get_positions()
            return web.json_response({"status": "ok", "data": data, "count": len(data)})
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return web.json_response({"status": "error", "error": str(e)}, status=500)
    
    async def orders(self, request: web.Request) -> web.Response:
        """Get orders."""
        try:
            limit = int(request.query.get("limit", 100))
            data = await self._reader.get_orders(limit=limit)
            return web.json_response({"status": "ok", "data": data, "count": len(data)})
        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            return web.json_response({"status": "error", "error": str(e)}, status=500)
    
    async def signals(self, request: web.Request) -> web.Response:
        """Get signals."""
        try:
            limit = int(request.query.get("limit", 100))
            data = await self._reader.get_signals(limit=limit)
            return web.json_response({"status": "ok", "data": data, "count": len(data)})
        except Exception as e:
            logger.error(f"Error getting signals: {e}")
            return web.json_response({"status": "error", "error": str(e)}, status=500)
    
    async def balance(self, request: web.Request) -> web.Response:
        """Get balance."""
        try:
            data = await self._reader.get_balance()
            return web.json_response({"status": "ok", "data": data})
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return web.json_response({"status": "error", "error": str(e)}, status=500)
    
    async def risk(self, request: web.Request) -> web.Response:
        """Get risk metrics."""
        try:
            data = await self._reader.get_risk_metrics()
            return web.json_response({"status": "ok", "data": data})
        except Exception as e:
            logger.error(f"Error getting risk: {e}")
            return web.json_response({"status": "error", "error": str(e)}, status=500)
    
    async def data_sources(self, request: web.Request) -> web.Response:
        """Get data sources."""
        try:
            data = await self._reader.get_data_sources()
            return web.json_response({"status": "ok", "data": data})
        except Exception as e:
            logger.error(f"Error getting data sources: {e}")
            return web.json_response({"status": "error", "error": str(e)}, status=500)


# ============================================================
# MAIN
# ============================================================

async def run_dashboard(host: str, port: int, data_dir: Path) -> None:
    """Run dashboard server."""
    # Initialize sample data if needed
    initialize_sample_data(data_dir)
    
    # Create reader and API
    reader = LiveDataReader(data_dir)
    api = DashboardAPI(reader)
    
    # Create app
    app = web.Application()
    
    # Add routes
    app.router.add_get("/api/health", api.health)
    app.router.add_get("/api/overview", api.overview)
    app.router.add_get("/api/system", api.system)
    app.router.add_get("/api/modules", api.modules)
    app.router.add_get("/api/positions", api.positions)
    app.router.add_get("/api/orders", api.orders)
    app.router.add_get("/api/signals", api.signals)
    app.router.add_get("/api/balance", api.balance)
    app.router.add_get("/api/risk", api.risk)
    app.router.add_get("/api/data-sources", api.data_sources)
    
    # Add root handler with UI
    async def root_handler(request):
        return web.Response(
            text=f"""
<!DOCTYPE html>
<html>
<head>
    <title>Crypto Trading Dashboard</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px; background: #0a0e17; color: #e4e4e7; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #00d4ff; margin-bottom: 5px; }}
        h2 {{ color: #a1a1aa; font-size: 14px; margin-top: 0; }}
        .status {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
        .status.running {{ background: #22c55e; color: white; }}
        .status.stopped {{ background: #ef4444; color: white; }}
        .status.unknown {{ background: #71717a; color: white; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 20px; }}
        .card {{ background: #1a1f2e; border-radius: 8px; padding: 20px; }}
        .card h3 {{ margin-top: 0; color: #00d4ff; font-size: 14px; text-transform: uppercase; }}
        .metric {{ margin: 15px 0; }}
        .metric .label {{ color: #71717a; font-size: 12px; }}
        .metric .value {{ font-size: 24px; font-weight: bold; }}
        .metric .value.positive {{ color: #22c55e; }}
        .metric .value.negative {{ color: #ef4444; }}
        .endpoints {{ background: #1a1f2e; padding: 20px; border-radius: 8px; margin-top: 20px; }}
        .endpoint {{ display: inline-block; margin: 5px; padding: 8px 16px; background: #0f3460; border-radius: 4px; color: #00d4ff; text-decoration: none; font-size: 13px; }}
        .endpoint:hover {{ background: #1e4976; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #2a2f3e; }}
        th {{ color: #71717a; font-weight: normal; }}
        .tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
        .tag.long {{ background: #22c55e33; color: #22c55e; }}
        .tag.short {{ background: #ef444433; color: #ef4444; }}
        .tag.healthy {{ background: #22c55e33; color: #22c55e; }}
        #overview-data {{ white-space: pre-wrap; font-family: monospace; font-size: 12px; background: #0f1319; padding: 15px; border-radius: 4px; max-height: 400px; overflow: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Crypto Trading Dashboard</h1>
        <h2>Institutional-Grade Monitoring | Data: {data_dir}</h2>
        
        <div id="status-bar" style="margin: 20px 0;">
            Loading...
        </div>
        
        <div class="grid">
            <div class="card">
                <h3>💰 Balance</h3>
                <div id="balance-data">Loading...</div>
            </div>
            <div class="card">
                <h3>📊 Risk</h3>
                <div id="risk-data">Loading...</div>
            </div>
            <div class="card">
                <h3>🔧 Modules</h3>
                <div id="modules-data">Loading...</div>
            </div>
        </div>
        
        <div class="card" style="margin-top: 20px;">
            <h3>📈 Positions</h3>
            <div id="positions-data">Loading...</div>
        </div>
        
        <div class="endpoints">
            <h3 style="margin-top: 0;">API Endpoints</h3>
            <a class="endpoint" href="/api/health">/api/health</a>
            <a class="endpoint" href="/api/overview">/api/overview</a>
            <a class="endpoint" href="/api/system">/api/system</a>
            <a class="endpoint" href="/api/modules">/api/modules</a>
            <a class="endpoint" href="/api/positions">/api/positions</a>
            <a class="endpoint" href="/api/orders">/api/orders</a>
            <a class="endpoint" href="/api/signals">/api/signals</a>
            <a class="endpoint" href="/api/balance">/api/balance</a>
            <a class="endpoint" href="/api/risk">/api/risk</a>
            <a class="endpoint" href="/api/data-sources">/api/data-sources</a>
        </div>
    </div>
    
    <script>
        async function fetchData() {{
            try {{
                // Fetch overview
                const overview = await fetch('/api/overview').then(r => r.json());
                
                if (overview.status === 'ok') {{
                    const data = overview.data;
                    
                    // Status bar
                    const state = data.system.state.toUpperCase();
                    const stateClass = state === 'RUNNING' ? 'running' : (state === 'UNKNOWN' ? 'unknown' : 'stopped');
                    document.getElementById('status-bar').innerHTML = `
                        <span class="status ${{stateClass}}">${{state}}</span>
                        <span style="margin-left: 15px; color: #71717a;">Trading: ${{data.system.trading_enabled ? '✅ Enabled' : '❌ Disabled'}}</span>
                        <span style="margin-left: 15px; color: #71717a;">Updated: ${{new Date().toLocaleTimeString()}}</span>
                    `;
                    
                    // Balance
                    const balance = data.balance;
                    if (balance.available) {{
                        document.getElementById('balance-data').innerHTML = `
                            <div class="metric">
                                <div class="label">Total Equity</div>
                                <div class="value">$${{parseFloat(balance.total_equity || 0).toLocaleString()}}</div>
                            </div>
                            <div class="metric">
                                <div class="label">Available</div>
                                <div class="value">$${{parseFloat(balance.available_balance || 0).toLocaleString()}}</div>
                            </div>
                            <div class="metric">
                                <div class="label">Margin Used</div>
                                <div class="value">$${{parseFloat(balance.margin_used || 0).toLocaleString()}}</div>
                            </div>
                        `;
                    }} else {{
                        document.getElementById('balance-data').innerHTML = '<div style="color: #71717a;">No data</div>';
                    }}
                    
                    // Risk
                    const risk = data.risk;
                    if (risk.available) {{
                        const pnlClass = parseFloat(risk.daily_pnl || 0) >= 0 ? 'positive' : 'negative';
                        document.getElementById('risk-data').innerHTML = `
                            <div class="metric">
                                <div class="label">Daily P&L</div>
                                <div class="value ${{pnlClass}}">$${{parseFloat(risk.daily_pnl || 0).toLocaleString()}}</div>
                            </div>
                            <div class="metric">
                                <div class="label">Risk Level</div>
                                <div class="value">${{risk.risk_level || 'N/A'}}</div>
                            </div>
                            <div class="metric">
                                <div class="label">Drawdown</div>
                                <div class="value">${{risk.current_drawdown_pct || 0}}%</div>
                            </div>
                        `;
                    }} else {{
                        document.getElementById('risk-data').innerHTML = '<div style="color: #71717a;">No data</div>';
                    }}
                    
                    // Modules
                    const modules = data.module_health;
                    document.getElementById('modules-data').innerHTML = `
                        <div class="metric">
                            <div class="label">Healthy</div>
                            <div class="value positive">${{modules.summary.healthy}}</div>
                        </div>
                        <div class="metric">
                            <div class="label">Degraded</div>
                            <div class="value" style="color: #eab308;">${{modules.summary.degraded}}</div>
                        </div>
                        <div class="metric">
                            <div class="label">Unhealthy</div>
                            <div class="value negative">${{modules.summary.unhealthy}}</div>
                        </div>
                    `;
                    
                    // Positions
                    const positions = data.positions.details;
                    if (positions.length > 0) {{
                        let table = `<table>
                            <tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th><th>Current</th><th>P&L</th></tr>`;
                        for (const pos of positions) {{
                            const pnl = parseFloat(pos.unrealized_pnl || 0);
                            const pnlClass = pnl >= 0 ? 'positive' : 'negative';
                            const sideClass = pos.side.toLowerCase();
                            table += `<tr>
                                <td><strong>${{pos.symbol}}</strong></td>
                                <td><span class="tag ${{sideClass}}">${{pos.side}}</span></td>
                                <td>${{pos.quantity}}</td>
                                <td>$${{parseFloat(pos.entry_price).toLocaleString()}}</td>
                                <td>$${{parseFloat(pos.current_price).toLocaleString()}}</td>
                                <td class="${{pnlClass}}">$${{pnl.toFixed(2)}}</td>
                            </tr>`;
                        }}
                        table += '</table>';
                        table += `<div style="margin-top: 15px; color: #71717a;">Total Exposure: $${{data.positions.total_exposure.toLocaleString()}} | Total P&L: <span class="${{data.positions.total_pnl >= 0 ? 'positive' : 'negative'}}">${{data.positions.total_pnl.toFixed(2)}}</span></div>`;
                        document.getElementById('positions-data').innerHTML = table;
                    }} else {{
                        document.getElementById('positions-data').innerHTML = '<div style="color: #71717a;">No open positions</div>';
                    }}
                }}
            }} catch (e) {{
                console.error('Error fetching data:', e);
            }}
        }}
        
        // Initial fetch
        fetchData();
        
        // Refresh every 10 seconds
        setInterval(fetchData, 10000);
    </script>
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
    
    print(f"""
============================================================
  SIMPLE DASHBOARD SERVER - LIVE DATA
============================================================
  URL:       http://{host}:{port}
  Data Dir:  {data_dir}
  
  API Endpoints:
    /api/health        - Health check
    /api/overview      - Complete overview
    /api/system        - System state
    /api/modules       - Module health
    /api/positions     - Open positions
    /api/orders        - Order history
    /api/signals       - Signal history
    /api/balance       - Account balance
    /api/risk          - Risk metrics
    /api/data-sources  - Data source status
============================================================
  Press Ctrl+C to stop
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
        description="Run the simple trading dashboard",
    )
    
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "storage" / "state", help="Data directory")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    
    args = parser.parse_args()
    
    setup_logging(args.log_level)
    
    try:
        asyncio.run(run_dashboard(args.host, args.port, args.data_dir))
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
