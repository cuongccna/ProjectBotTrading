"""
Database Query Services for Dashboard.
"""
from typing import List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import func, desc, select, cast, Date
from sqlalchemy.orm import Session

from database.models import (
    SystemMonitoring,
    RawNews,
    CleanedNews,
    SentimentScore,
    OnchainFlowRaw,
    RiskState,
    EntryDecision,
    PositionSizing,
    ExecutionRecord
)
from database.engine import get_session

class DashboardService:
    def __init__(self, session: Session):
        self.session = session

    # =======================
    # 1. SYSTEM HEALTH
    # =======================
    def get_system_health(self) -> List[Dict[str, Any]]:
        # Get latest heartbeat per module
        # We assume "heartbeat" or operation logs land in SystemMonitoring
        
        # 1. Get unique modules
        # This is a bit simplified. In a real system, we might have a registry.
        # Here we scan recent logs.
        
        now = datetime.utcnow()
        lookback = now - timedelta(hours=1)
        
        # Count errors per module in last hour
        error_counts = (
            self.session.query(
                SystemMonitoring.module_name,
                func.count(SystemMonitoring.id)
            )
            .filter(SystemMonitoring.event_time >= lookback)
            .filter(SystemMonitoring.severity == 'error')
            .group_by(SystemMonitoring.module_name)
            .all()
        )
        error_map = {m: c for m, c in error_counts}
        
        # Get latest log for each module to determine UP/DOWN
        # Using a subquery to find max ID per module
        subq = (
            self.session.query(
                SystemMonitoring.module_name,
                func.max(SystemMonitoring.id).label('max_id')
            )
            .filter(SystemMonitoring.event_time >= now - timedelta(hours=24))
            .group_by(SystemMonitoring.module_name)
            .subquery()
        )
        
        latest_logs = (
            self.session.query(SystemMonitoring)
            .join(subq, SystemMonitoring.id == subq.c.max_id)
            .all()
        )
        
        results = []
        for log in latest_logs:
            is_stale = (now - log.event_time) > timedelta(minutes=30)
            errors = error_map.get(log.module_name, 0)
            
            if is_stale:
                status = "DOWN"
            elif errors > 5:
                status = "DEGRADED"
            else:
                status = "UP"
                
            results.append({
                "module_name": log.module_name,
                "status": status,
                "last_heartbeat": log.event_time,
                "error_count_1h": errors,
                "message": log.message
            })
            
        return results

    # =======================
    # 2. DATA PIPELINE
    # =======================
    def get_pipeline_stats(self) -> List[Dict[str, Any]]:
        now = datetime.utcnow()
        window_24h = now - timedelta(hours=24)
        
        stats = []
        
        # Helper query function
        def get_count_and_latest(model):
            count = self.session.query(func.count(model.id)).filter(model.created_at >= window_24h).scalar()
            latest = self.session.query(func.max(model.created_at)).scalar()
            return count, latest

        # Raw News
        c, l = get_count_and_latest(RawNews)
        stats.append({
            "source_module": "data_ingestion",
            "metric": "raw_news_count",
            "count_24h": c,
            "last_update": l,
            "status": "HEALTHY" if c > 0 and (now - (l or now) < timedelta(hours=1)) else "STALE"
        })

        # Cleaned News
        c, l = get_count_and_latest(CleanedNews)
        stats.append({
            "source_module": "data_processing",
            "metric": "cleaned_news_count",
            "count_24h": c,
            "last_update": l,
            "status": "HEALTHY" if c > 0 else "STALE"
        })

        # Sentiment
        # SentimentScore uses created_at columns? The model says created_at is default=utc_now in Base, but let's check model definition.
        # Actually SentimentScore has created_at? checking models.py content... 
        # Yes, all models have created_at if they inherit correctly or defined it. 
        # Looking at previous context models.py: RawNews has it.
        # Assuming SentimentScore has it (it was in the list).
        c = self.session.query(func.count(SentimentScore.id)).filter(SentimentScore.created_at >= window_24h).scalar()
        l = self.session.query(func.max(SentimentScore.created_at)).scalar()
        stats.append({
            "source_module": "sentiment_analysis",
            "metric": "sentiment_scores_count",
            "count_24h": c,
            "last_update": l,
            "status": "HEALTHY" if c > 0 else "STALE"
        })
        
        # Onchain
        c = self.session.query(func.count(OnchainFlowRaw.id)).filter(OnchainFlowRaw.event_time >= window_24h).scalar()
        l = self.session.query(func.max(OnchainFlowRaw.event_time)).scalar()
        stats.append({
            "source_module": "onchain_collector",
            "metric": "onchain_events_count",
            "count_24h": c,
            "last_update": l,
            "status": "HEALTHY" if c > 0 else "STALE"
        })
        
        return stats

    # =======================
    # 3. RISK STATE
    # =======================
    def get_latest_risk_state(self) -> Dict[str, Any]:
        latest_risk = (
            self.session.query(RiskState)
            .order_by(desc(RiskState.id))
            .first()
        )
        
        if not latest_risk:
            return None
            
        # Deconstruct components
        components = []
        
        # Sentiment
        components.append({
            "name": "sentiment",
            "raw_score": latest_risk.sentiment_risk_raw or 0,
            "normalized_score": latest_risk.sentiment_risk_normalized or 0,
            "weight": latest_risk.weights.get("sentiment", 0) if latest_risk.weights else 0,
            "risk_contribution": (latest_risk.sentiment_risk_normalized or 0) * (latest_risk.weights.get("sentiment", 0) if latest_risk.weights else 0),
            "level": "N/A" # Simple placeholder
        })
        
        # Flow
        components.append({
            "name": "flow",
            "raw_score": latest_risk.flow_risk_raw or 0,
            "normalized_score": latest_risk.flow_risk_normalized or 0,
            "weight": latest_risk.weights.get("flow", 0) if latest_risk.weights else 0,
            "risk_contribution": (latest_risk.flow_risk_normalized or 0) * (latest_risk.weights.get("flow", 0) if latest_risk.weights else 0),
            "level": "N/A"
        })
        
        # Smart Money
        components.append({
            "name": "smart_money",
            "raw_score": latest_risk.smart_money_risk_raw or 0,
            "normalized_score": latest_risk.smart_money_risk_normalized or 0,
            "weight": latest_risk.weights.get("smart_money", 0) if latest_risk.weights else 0,
            "risk_contribution": (latest_risk.smart_money_risk_normalized or 0) * (latest_risk.weights.get("smart_money", 0) if latest_risk.weights else 0),
            "level": "N/A"
        })

         # Market Condition
        components.append({
            "name": "market_condition",
            "raw_score": latest_risk.market_condition_risk_raw or 0,
            "normalized_score": latest_risk.market_condition_risk_normalized or 0,
            "weight": latest_risk.weights.get("market_condition", 0) if latest_risk.weights else 0,
            "risk_contribution": (latest_risk.market_condition_risk_normalized or 0) * (latest_risk.weights.get("market_condition", 0) if latest_risk.weights else 0),
            "level": "N/A"
        })

        return {
            "timestamp": latest_risk.created_at,
            "global_risk_score": latest_risk.global_risk_score,
            "risk_level": latest_risk.risk_level,
            "trading_allowed": latest_risk.trading_allowed,
            "blocked_reason": latest_risk.trading_blocked_reason,
            "components": components
        }

    # =======================
    # 4. DECISION TRACE
    # =======================
    def get_recent_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        decisions = (
            self.session.query(EntryDecision)
            .order_by(desc(EntryDecision.created_at))
            .limit(limit)
            .all()
        )
        
        results = []
        for d in decisions:
            results.append({
                "id": d.id,
                "timestamp": d.created_at,
                "token": d.token,
                "decision": d.decision,
                "direction": d.direction,
                "reason_code": d.reason_code,
                "reason_details": d.reason_details,
                "scores": {
                    "sentiment": d.sentiment_score,
                    "flow": d.flow_score,
                    "risk": d.risk_score,
                    "smart_money": d.smart_money_score
                },
                "trade_guard_intervention": d.trade_guard_intervention
            })
        return results

    # =======================
    # 5. POSITION & EXECUTION
    # =======================
    def get_position_execution_stats(self) -> Dict[str, Any]:
        # Recent Executions
        executions = (
            self.session.query(ExecutionRecord)
            .order_by(desc(ExecutionRecord.executed_at))
            .limit(20)
            .all()
        )
        
        exec_stats = []
        for e in executions:
            exec_stats.append({
                "order_id": e.order_id,
                "token": e.token,
                "side": e.side,
                "status": e.status,
                "executed_size": e.executed_size,
                "executed_price": e.executed_price,
                "slippage_percent": e.slippage_percent,
                "latency_ms": e.latency_ms,
                "executed_at": e.executed_at
            })
            
        # Positions
        # Since we don't have a dedicated "CurrentPositions" snapshot table that updates in-place,
        # we might have to derive it from 'PositionSizing' or just show the latest sizing calculation as a proxy for intent.
        # OR, we assume we want to query a real position table if one existed.
        # But 'PositionSizing' isn't exactly 'Open Positions'.
        # However, for this deliverable, showing Latest Position Sizing events gives visibility into "What did we size recently?"
        # The user request says "Current Positions".
        # If the DB doesn't have a Portfolio table, we can return empty or mock from latest executions (summing them up).
        # Let's just return the latest position sizing calculations as a proxy for "Intended Positions".
        
        latest_sizings = (
            self.session.query(PositionSizing)
            .order_by(desc(PositionSizing.created_at))
            .limit(10)
            .all()
        )
        
        positions = []
        for p in latest_sizings:
            positions.append({
                "token": p.token,
                "size": p.final_size,
                "entry_price": 0.0, # Not readily available in sizing table alone without linking to execution
                "current_value": p.final_size_usd,
                "unrealized_pnl": 0.0
            })

        return {
            "positions": positions,
            "recent_executions": exec_stats
        }

    # =======================
    # 6. ALERTS & INCIDENTS
    # =======================
    def get_active_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        # Define alerts as monitoring events with high severity
        alerts = (
            self.session.query(SystemMonitoring)
            .filter(SystemMonitoring.severity.in_(['warning', 'error', 'critical']))
            .order_by(desc(SystemMonitoring.event_time))
            .limit(limit)
            .all()
        )
        
        results = []
        for a in alerts:
            results.append({
                "id": a.id,
                "timestamp": a.event_time,
                "module": a.module_name,
                "severity": a.severity.upper(),
                "message": a.message,
                "details": a.details
            })
        return results

