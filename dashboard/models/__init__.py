"""
Dashboard Database Models Package.

Institutional-Grade Monitoring & Decision Dashboard Models.

All models follow the Data Contract Rules:
- Every field has source_module traceability
- Update frequency is specified
- Retention policy is defined
- SQL table definitions are included

Panels:
1. System Health - Module status, health checks, data freshness
2. Data Pipeline - Ingestion metrics, processing status, data quality
3. Risk State - Global risk, components, market conditions
4. Decision Trace - Trade decisions, guard interventions, audit log
5. Position Monitor - Current positions, open orders, execution metrics
6. Alerts & Incidents - Active alerts, incidents, resolution tracking
"""

from .system_health import (
    ModuleStatus,
    HealthCheckType,
    ModuleHealth,
    HealthCheckRecord,
    DataSourceFreshness,
    SystemError,
    ALL_HEALTH_TABLES,
)

from .data_pipeline import (
    PipelineStage,
    BatchStatus,
    PipelineMetrics,
    IngestionCount,
    SentimentBatchStatus,
    DataQualityMetrics,
    OnChainEventCount,
    SmartMoneyEventCount,
    ALL_PIPELINE_TABLES,
)

from .risk_state import (
    RiskLevel,
    TradingState,
    GlobalRiskState,
    RiskComponent,
    RiskHistory,
    MarketConditionState,
    SentimentState,
    ALL_RISK_TABLES,
)

from .decisions import (
    DecisionType,
    BlockReason,
    TradeGuardRuleType,
    TradeDecision,
    TradeGuardIntervention,
    TradeGuardRule,
    DecisionAuditLog,
    ALL_DECISION_TABLES,
)

from .positions import (
    PositionSide,
    OrderStatus,
    OrderType,
    CurrentPosition,
    OpenOrder,
    ExecutionMetrics,
    PortfolioSnapshot,
    ALL_POSITION_TABLES,
)

from .alerts import (
    AlertSeverity,
    AlertStatus,
    AlertCategory,
    Alert,
    Incident,
    AlertRule,
    AlertSummary,
    ALL_ALERT_TABLES,
)


# All SQL table definitions
ALL_TABLES = (
    ALL_HEALTH_TABLES
    + ALL_PIPELINE_TABLES
    + ALL_RISK_TABLES
    + ALL_DECISION_TABLES
    + ALL_POSITION_TABLES
    + ALL_ALERT_TABLES
)

__all__ = [
    # System Health
    "ModuleStatus",
    "HealthCheckType",
    "ModuleHealth",
    "HealthCheckRecord",
    "DataSourceFreshness",
    "SystemError",
    "ALL_HEALTH_TABLES",
    
    # Data Pipeline
    "PipelineStage",
    "BatchStatus",
    "PipelineMetrics",
    "IngestionCount",
    "SentimentBatchStatus",
    "DataQualityMetrics",
    "OnChainEventCount",
    "SmartMoneyEventCount",
    "ALL_PIPELINE_TABLES",
    
    # Risk State
    "RiskLevel",
    "TradingState",
    "GlobalRiskState",
    "RiskComponent",
    "RiskHistory",
    "MarketConditionState",
    "SentimentState",
    "ALL_RISK_TABLES",
    
    # Decisions
    "DecisionType",
    "BlockReason",
    "TradeGuardRuleType",
    "TradeDecision",
    "TradeGuardIntervention",
    "TradeGuardRule",
    "DecisionAuditLog",
    "ALL_DECISION_TABLES",
    
    # Positions
    "PositionSide",
    "OrderStatus",
    "OrderType",
    "CurrentPosition",
    "OpenOrder",
    "ExecutionMetrics",
    "PortfolioSnapshot",
    "ALL_POSITION_TABLES",
    
    # Alerts
    "AlertSeverity",
    "AlertStatus",
    "AlertCategory",
    "Alert",
    "Incident",
    "AlertRule",
    "AlertSummary",
    "ALL_ALERT_TABLES",
    
    # All tables
    "ALL_TABLES",
]
