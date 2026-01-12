"""
Dashboard Database Models - Alerts & Incidents.

============================================================
ALERTS & INCIDENTS TABLES
============================================================

Tables for tracking alerts, incidents, and their resolution.

Source: Trade Guard, System Risk Controller, Data Source Health
Update Frequency: On event
Retention: 90 days

============================================================
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from dataclasses import dataclass, field


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Alert status."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class AlertCategory(str, Enum):
    """Alert category."""
    SYSTEM_HEALTH = "system_health"
    DATA_QUALITY = "data_quality"
    RISK_BREACH = "risk_breach"
    TRADE_GUARD = "trade_guard"
    EXECUTION = "execution"
    POSITION = "position"
    CONNECTIVITY = "connectivity"
    SECURITY = "security"


@dataclass
class Alert:
    """
    System alert.
    
    Table: alerts
    Primary Key: alert_id
    """
    alert_id: str
    timestamp: datetime
    
    # Classification
    severity: AlertSeverity
    category: AlertCategory
    alert_type: str  # Specific alert type within category
    
    # Content
    title: str
    message: str
    details: Optional[dict] = None
    
    # Affected components
    affected_modules: List[str] = field(default_factory=list)
    affected_assets: List[str] = field(default_factory=list)
    
    # Status
    status: AlertStatus = AlertStatus.ACTIVE
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None
    
    # Auto-resolution
    auto_resolve: bool = False
    auto_resolve_condition: Optional[str] = None
    
    # Suppression
    is_suppressed: bool = False
    suppress_until: Optional[datetime] = None
    
    # Escalation
    escalation_level: int = 0
    escalated_at: Optional[datetime] = None
    
    # Source traceability
    source_module: str = ""
    source_rule_id: Optional[str] = None
    retention_days: int = 90
    
    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "category": self.category.value,
            "alert_type": self.alert_type,
            "title": self.title,
            "message": self.message,
            "affected_modules": self.affected_modules,
            "affected_assets": self.affected_assets,
            "status": self.status.value,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "source_module": self.source_module,
            "is_active": self.status == AlertStatus.ACTIVE,
            "duration_minutes": self._calculate_duration(),
        }
    
    def _calculate_duration(self) -> int:
        """Calculate alert duration in minutes."""
        end_time = self.resolved_at or datetime.utcnow()
        return int((end_time - self.timestamp).total_seconds() / 60)


@dataclass
class Incident:
    """
    Incident record (escalated or grouped alerts).
    
    Table: incidents
    Primary Key: incident_id
    """
    incident_id: str
    created_at: datetime
    
    # Classification
    severity: AlertSeverity
    category: AlertCategory
    title: str
    description: str
    
    # Status
    status: str  # open, investigating, mitigating, resolved
    
    # Related alerts
    alert_ids: List[str] = field(default_factory=list)
    
    # Impact
    impact_description: str = ""
    affected_modules: List[str] = field(default_factory=list)
    trading_impact: str = ""  # none, reduced, paused, blocked
    
    # Timeline
    detected_at: datetime = field(default_factory=datetime.utcnow)
    investigation_started_at: Optional[datetime] = None
    mitigation_started_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    # Resolution
    root_cause: Optional[str] = None
    resolution_actions: List[str] = field(default_factory=list)
    
    # Ownership
    assigned_to: Optional[str] = None
    
    # Post-mortem
    post_mortem_required: bool = False
    post_mortem_url: Optional[str] = None
    
    # Source traceability
    source_module: str = "incident_manager"
    retention_days: int = 365
    
    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "created_at": self.created_at.isoformat(),
            "severity": self.severity.value,
            "category": self.category.value,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "alert_count": len(self.alert_ids),
            "impact_description": self.impact_description,
            "trading_impact": self.trading_impact,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "duration_minutes": self._calculate_duration(),
        }
    
    def _calculate_duration(self) -> int:
        """Calculate incident duration in minutes."""
        end_time = self.resolved_at or datetime.utcnow()
        return int((end_time - self.created_at).total_seconds() / 60)


@dataclass
class AlertRule:
    """
    Alert rule configuration.
    
    Table: alert_rules
    Primary Key: rule_id
    """
    rule_id: str
    rule_name: str
    category: AlertCategory
    severity: AlertSeverity
    
    # Condition
    condition_type: str  # threshold, comparison, pattern
    condition_config: dict = field(default_factory=dict)
    
    # Monitoring
    monitored_metric: str
    check_interval_seconds: int = 60
    
    # Thresholds
    warning_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None
    
    # Behavior
    is_enabled: bool = True
    auto_resolve: bool = False
    suppress_duplicate_minutes: int = 5
    escalation_after_minutes: int = 30
    
    # Stats
    triggers_24h: int = 0
    last_triggered: Optional[datetime] = None
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AlertSummary:
    """
    Alert summary for dashboard display.
    
    Not persisted - calculated on query.
    """
    total_active: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    
    by_category: dict = field(default_factory=dict)
    oldest_unresolved_minutes: int = 0
    avg_resolution_time_minutes: float = 0
    
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "total_active": self.total_active,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "by_category": self.by_category,
            "oldest_unresolved_minutes": self.oldest_unresolved_minutes,
            "avg_resolution_time_minutes": round(self.avg_resolution_time_minutes, 1),
            "last_updated": self.last_updated.isoformat(),
        }


# =============================================================
# SQL TABLE DEFINITIONS
# =============================================================

ALERTS_TABLE = """
CREATE TABLE IF NOT EXISTS alerts (
    alert_id VARCHAR(100) PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    severity VARCHAR(20) NOT NULL,
    category VARCHAR(50) NOT NULL,
    alert_type VARCHAR(100) NOT NULL,
    title VARCHAR(500) NOT NULL,
    message TEXT NOT NULL,
    details JSONB,
    affected_modules JSONB,
    affected_assets JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    acknowledged_at TIMESTAMP,
    acknowledged_by VARCHAR(100),
    resolved_at TIMESTAMP,
    resolved_by VARCHAR(100),
    resolution_note TEXT,
    auto_resolve BOOLEAN DEFAULT false,
    auto_resolve_condition TEXT,
    is_suppressed BOOLEAN DEFAULT false,
    suppress_until TIMESTAMP,
    escalation_level INTEGER DEFAULT 0,
    escalated_at TIMESTAMP,
    source_module VARCHAR(100) NOT NULL,
    source_rule_id VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_category ON alerts(category);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(status) WHERE status = 'active';
"""

INCIDENTS_TABLE = """
CREATE TABLE IF NOT EXISTS incidents (
    incident_id VARCHAR(100) PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    severity VARCHAR(20) NOT NULL,
    category VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'open',
    alert_ids JSONB,
    impact_description TEXT,
    affected_modules JSONB,
    trading_impact VARCHAR(50),
    detected_at TIMESTAMP NOT NULL,
    investigation_started_at TIMESTAMP,
    mitigation_started_at TIMESTAMP,
    resolved_at TIMESTAMP,
    root_cause TEXT,
    resolution_actions JSONB,
    assigned_to VARCHAR(100),
    post_mortem_required BOOLEAN DEFAULT false,
    post_mortem_url TEXT,
    source_module VARCHAR(100) DEFAULT 'incident_manager'
);

CREATE INDEX IF NOT EXISTS idx_incidents_time ON incidents(created_at);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
"""

ALERT_RULES_TABLE = """
CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id VARCHAR(100) PRIMARY KEY,
    rule_name VARCHAR(200) NOT NULL,
    category VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    condition_type VARCHAR(50) NOT NULL,
    condition_config JSONB,
    monitored_metric VARCHAR(200) NOT NULL,
    check_interval_seconds INTEGER DEFAULT 60,
    warning_threshold FLOAT,
    critical_threshold FLOAT,
    is_enabled BOOLEAN DEFAULT true,
    auto_resolve BOOLEAN DEFAULT false,
    suppress_duplicate_minutes INTEGER DEFAULT 5,
    escalation_after_minutes INTEGER DEFAULT 30,
    triggers_24h INTEGER DEFAULT 0,
    last_triggered TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_category ON alert_rules(category);
CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(is_enabled);
"""

ALERT_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS alert_history (
    id SERIAL PRIMARY KEY,
    alert_id VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    action_by VARCHAR(100),
    action_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    old_status VARCHAR(20),
    new_status VARCHAR(20),
    notes TEXT,
    FOREIGN KEY (alert_id) REFERENCES alerts(alert_id)
);

CREATE INDEX IF NOT EXISTS idx_alert_history_alert ON alert_history(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_history_time ON alert_history(action_at);
"""

ALL_ALERT_TABLES = [
    ALERTS_TABLE,
    INCIDENTS_TABLE,
    ALERT_RULES_TABLE,
    ALERT_HISTORY_TABLE,
]
