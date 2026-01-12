"""
Dashboard API Endpoints.

============================================================
PURPOSE
============================================================
HTTP API for dashboard data access.

PRINCIPLES:
- ALL endpoints are READ-ONLY
- NO control endpoints
- NO state mutation
- Pure data retrieval

============================================================
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, List

from aiohttp import web

from .models import AlertTier
from .dashboard_service import DashboardService
from .alerts import AlertManager


logger = logging.getLogger(__name__)


# ============================================================
# JSON ENCODER
# ============================================================

class DashboardEncoder(json.JSONEncoder):
    """JSON encoder for dashboard data."""
    
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        if hasattr(obj, '__dict__'):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
        if hasattr(obj, 'value'):  # Enums
            return obj.value
        return super().default(obj)


def json_response(data: Any, status: int = 200) -> web.Response:
    """Create JSON response."""
    return web.Response(
        text=json.dumps(data, cls=DashboardEncoder, indent=2),
        status=status,
        content_type="application/json",
    )


# ============================================================
# API HANDLERS
# ============================================================

class DashboardAPI:
    """
    HTTP API for dashboard.
    
    ALL endpoints are READ-ONLY.
    NO control endpoints exist in this class.
    """
    
    def __init__(
        self,
        dashboard_service: DashboardService,
        alert_manager: Optional[AlertManager] = None,
    ):
        """Initialize API."""
        self._service = dashboard_service
        self._alert_manager = alert_manager
    
    # --------------------------------------------------------
    # OVERVIEW ENDPOINTS
    # --------------------------------------------------------
    
    async def get_overview(self, request: web.Request) -> web.Response:
        """
        GET /api/dashboard/overview
        
        Get complete dashboard overview.
        """
        try:
            overview = await self._service.get_overview()
            return json_response({
                "status": "ok",
                "data": overview,
            })
        except Exception as e:
            logger.error(f"Error getting overview: {e}")
            return json_response({
                "status": "error",
                "error": str(e),
            }, status=500)
    
    async def get_system_status(self, request: web.Request) -> web.Response:
        """
        GET /api/dashboard/system
        
        Get system status only.
        """
        try:
            overview = await self._service.get_overview()
            return json_response({
                "status": "ok",
                "data": {
                    "system_state": overview.system_state,
                    "module_health": overview.module_health,
                    "data_sources": overview.data_sources,
                },
            })
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return json_response({
                "status": "error",
                "error": str(e),
            }, status=500)
    
    # --------------------------------------------------------
    # RISK ENDPOINTS
    # --------------------------------------------------------
    
    async def get_risk(self, request: web.Request) -> web.Response:
        """
        GET /api/dashboard/risk
        
        Get risk and exposure data.
        """
        try:
            overview = await self._service.get_overview()
            return json_response({
                "status": "ok",
                "data": {
                    "risk_exposure": overview.risk_exposure,
                    "positions": overview.active_positions,
                },
            })
        except Exception as e:
            logger.error(f"Error getting risk: {e}")
            return json_response({
                "status": "error",
                "error": str(e),
            }, status=500)
    
    async def get_positions(self, request: web.Request) -> web.Response:
        """
        GET /api/dashboard/positions
        
        Get all positions.
        """
        try:
            overview = await self._service.get_overview()
            return json_response({
                "status": "ok",
                "data": overview.active_positions,
            })
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return json_response({
                "status": "error",
                "error": str(e),
            }, status=500)
    
    # --------------------------------------------------------
    # EXECUTION ENDPOINTS
    # --------------------------------------------------------
    
    async def get_execution(self, request: web.Request) -> web.Response:
        """
        GET /api/dashboard/execution
        
        Get execution view.
        """
        try:
            limit = int(request.query.get("limit", 100))
            view = await self._service.get_execution_view(limit=limit)
            return json_response({
                "status": "ok",
                "data": view,
            })
        except Exception as e:
            logger.error(f"Error getting execution: {e}")
            return json_response({
                "status": "error",
                "error": str(e),
            }, status=500)
    
    async def get_orders(self, request: web.Request) -> web.Response:
        """
        GET /api/dashboard/orders
        
        Get orders.
        """
        try:
            limit = int(request.query.get("limit", 100))
            view = await self._service.get_execution_view(limit=limit)
            return json_response({
                "status": "ok",
                "data": {
                    "active_orders": view.active_orders,
                    "recent_orders": view.recent_orders,
                },
            })
        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            return json_response({
                "status": "error",
                "error": str(e),
            }, status=500)
    
    # --------------------------------------------------------
    # SIGNAL ENDPOINTS
    # --------------------------------------------------------
    
    async def get_signals(self, request: web.Request) -> web.Response:
        """
        GET /api/dashboard/signals
        
        Get signal view.
        """
        try:
            limit = int(request.query.get("limit", 100))
            view = await self._service.get_signal_view(limit=limit)
            return json_response({
                "status": "ok",
                "data": view,
            })
        except Exception as e:
            logger.error(f"Error getting signals: {e}")
            return json_response({
                "status": "error",
                "error": str(e),
            }, status=500)
    
    # --------------------------------------------------------
    # AUDIT ENDPOINTS
    # --------------------------------------------------------
    
    async def get_audit_trail(self, request: web.Request) -> web.Response:
        """
        GET /api/dashboard/audit
        
        Get audit trail for a trade.
        
        Query params:
        - signal_id: Signal ID
        - order_id: Order ID
        - position_id: Position ID
        """
        try:
            signal_id = request.query.get("signal_id")
            order_id = request.query.get("order_id")
            position_id = request.query.get("position_id")
            
            if not any([signal_id, order_id, position_id]):
                return json_response({
                    "status": "error",
                    "error": "Must provide signal_id, order_id, or position_id",
                }, status=400)
            
            trail = await self._service.get_audit_trail(
                signal_id=signal_id,
                order_id=order_id,
                position_id=position_id,
            )
            
            if trail is None:
                return json_response({
                    "status": "error",
                    "error": "Audit trail not found",
                }, status=404)
            
            return json_response({
                "status": "ok",
                "data": trail,
            })
        except Exception as e:
            logger.error(f"Error getting audit trail: {e}")
            return json_response({
                "status": "error",
                "error": str(e),
            }, status=500)
    
    # --------------------------------------------------------
    # ALERT ENDPOINTS (READ-ONLY)
    # --------------------------------------------------------
    
    async def get_alerts(self, request: web.Request) -> web.Response:
        """
        GET /api/dashboard/alerts
        
        Get alerts.
        
        Query params:
        - tier: Filter by tier (INFO, WARNING, CRITICAL)
        - active_only: Only show active alerts
        - limit: Max number of alerts
        """
        try:
            if self._alert_manager is None:
                return json_response({
                    "status": "ok",
                    "data": {
                        "alerts": [],
                        "summary": {},
                    },
                })
            
            tier = request.query.get("tier")
            active_only = request.query.get("active_only", "false").lower() == "true"
            limit = int(request.query.get("limit", 100))
            
            if active_only:
                alerts = self._alert_manager.get_active_alerts()
            else:
                alerts = self._alert_manager.history.get_recent(limit)
            
            if tier:
                try:
                    tier_enum = AlertTier(tier)
                    alerts = [a for a in alerts if a.tier == tier_enum]
                except ValueError:
                    pass
            
            summary = self._alert_manager.get_alert_summary()
            
            return json_response({
                "status": "ok",
                "data": {
                    "alerts": alerts,
                    "summary": summary,
                },
            })
        except Exception as e:
            logger.error(f"Error getting alerts: {e}")
            return json_response({
                "status": "error",
                "error": str(e),
            }, status=500)
    
    async def acknowledge_alert(self, request: web.Request) -> web.Response:
        """
        POST /api/dashboard/alerts/{alert_id}/acknowledge
        
        Acknowledge an alert.
        
        NOTE: This is the ONLY non-read endpoint.
        It does NOT affect trading - only marks alert as acknowledged.
        """
        try:
            if self._alert_manager is None:
                return json_response({
                    "status": "error",
                    "error": "Alert manager not available",
                }, status=500)
            
            alert_id = request.match_info.get("alert_id")
            
            # Get acknowledger from request body
            body = await request.json()
            acknowledged_by = body.get("acknowledged_by", "unknown")
            
            success = self._alert_manager.acknowledge(alert_id, acknowledged_by)
            
            if success:
                return json_response({
                    "status": "ok",
                    "message": f"Alert {alert_id} acknowledged",
                })
            else:
                return json_response({
                    "status": "error",
                    "error": f"Alert {alert_id} not found",
                }, status=404)
                
        except Exception as e:
            logger.error(f"Error acknowledging alert: {e}")
            return json_response({
                "status": "error",
                "error": str(e),
            }, status=500)
    
    # --------------------------------------------------------
    # HEALTH CHECK
    # --------------------------------------------------------
    
    async def health(self, request: web.Request) -> web.Response:
        """
        GET /api/dashboard/health
        
        Dashboard health check.
        """
        return json_response({
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat(),
            "service": "dashboard",
        })


# ============================================================
# ROUTER FACTORY
# ============================================================

def create_dashboard_router(
    dashboard_service: DashboardService,
    alert_manager: Optional[AlertManager] = None,
) -> web.Application:
    """
    Create dashboard API application.
    
    Returns an aiohttp Application with all routes configured.
    """
    api = DashboardAPI(dashboard_service, alert_manager)
    
    app = web.Application()
    
    # Add routes - ALL are READ-ONLY except acknowledge
    app.router.add_get("/health", api.health)
    app.router.add_get("/overview", api.get_overview)
    app.router.add_get("/system", api.get_system_status)
    app.router.add_get("/risk", api.get_risk)
    app.router.add_get("/positions", api.get_positions)
    app.router.add_get("/execution", api.get_execution)
    app.router.add_get("/orders", api.get_orders)
    app.router.add_get("/signals", api.get_signals)
    app.router.add_get("/audit", api.get_audit_trail)
    app.router.add_get("/alerts", api.get_alerts)
    
    # Only non-read endpoint - does NOT affect trading
    app.router.add_post("/alerts/{alert_id}/acknowledge", api.acknowledge_alert)
    
    return app


def setup_dashboard_routes(
    app: web.Application,
    dashboard_service: DashboardService,
    alert_manager: Optional[AlertManager] = None,
    prefix: str = "/api/dashboard",
) -> None:
    """
    Add dashboard routes to an existing application.
    
    All routes are READ-ONLY except acknowledge.
    """
    dashboard_app = create_dashboard_router(dashboard_service, alert_manager)
    app.add_subapp(prefix, dashboard_app)
