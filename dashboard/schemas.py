"""
Pydantic schemas for Dashboard API responses.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, ConfigDict

# =======================
# COMMON
# =======================

class BaseResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    timestamp: datetime = datetime.utcnow()

# =======================
# 1. SYSTEM HEALTH
# =======================

class ModuleStatus(BaseModel):
    module_name: str
    status: str  # UP, DEGRADED, DOWN
    last_heartbeat: datetime
    error_count_1h: int
    message: Optional[str] = None

class SystemHealthResponse(BaseResponse):
    data: List[ModuleStatus]

# =======================
# 2. DATA PIPELINE
# =======================

class PipelineStats(BaseModel):
    source_module: str
    metric: str
    count_24h: int
    last_update: Optional[datetime]
    status: str  # HEALTHY, STALE, INACTIVE

class PipelineVisibilityResponse(BaseResponse):
    data: List[PipelineStats]

# =======================
# 3. RISK STATE
# =======================

class RiskComponent(BaseModel):
    name: str # e.g., "sentiment", "flow"
    raw_score: float
    normalized_score: float
    weight: float
    risk_contribution: float
    level: str # low, medium, high

class RiskStateDetail(BaseModel):
    timestamp: datetime
    global_risk_score: float
    risk_level: str
    trading_allowed: bool
    blocked_reason: Optional[str] = None
    components: List[RiskComponent]

class RiskStateResponse(BaseResponse):
    data: RiskStateDetail

# =======================
# 4. DECISION TRACE
# =======================

class DecisionRecord(BaseModel):
    id: int
    timestamp: datetime
    token: str
    decision: str  # ALLOW / BLOCK
    direction: Optional[str] = None
    reason_code: str
    reason_details: Optional[str] = None
    scores: Dict[str, Optional[float]]
    trade_guard_intervention: bool

class DecisionTraceResponse(BaseResponse):
    data: List[DecisionRecord]

# =======================
# 5. POSITION & EXECUTION
# =======================

class ExecutionStats(BaseModel):
    order_id: str
    token: str
    side: str
    status: str
    executed_size: Optional[float]
    executed_price: Optional[float]
    slippage_percent: Optional[float]
    latency_ms: Optional[int]
    executed_at: datetime

class PositionRecord(BaseModel):
    token: str
    size: float
    entry_price: float
    current_value: float
    unrealized_pnl: float

class PositionExecutionResponse(BaseResponse):
    positions: List[PositionRecord]
    recent_executions: List[ExecutionStats]

# =======================
# 6. ALERTS & INCIDENTS
# =======================

class AlertRecord(BaseModel):
    id: int
    timestamp: datetime
    module: str
    severity: str # INFO, WARNING, CRITICAL
    message: str
    details: Optional[Dict[str, Any]] = None

class AlertsResponse(BaseResponse):
    data: List[AlertRecord]
