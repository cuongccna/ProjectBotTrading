"""
Dashboard Database Models - System Health.

============================================================
SYSTEM HEALTH TABLES
============================================================

Tables for tracking module status, health checks, and errors.

Source: System logs, health check processes
Update Frequency: Every 30 seconds
Retention: 7 days for detailed, 90 days for aggregated

============================================================
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field


class ModuleStatus(str, Enum):
    """Module operational status."""
    UP = "up"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class HealthCheckType(str, Enum):
    """Type of health check performed."""
    HEARTBEAT = "heartbeat"
    CONNECTIVITY = "connectivity"
    DATA_FRESHNESS = "data_freshness"
    ERROR_RATE = "error_rate"
    LATENCY = "latency"
    RESOURCE_USAGE = "resource_usage"


@dataclass
class ModuleHealth:
    """
    Current health status of a system module.
    
    Table: module_health
    Primary Key: module_name
    """
    module_name: str
    status: ModuleStatus
    last_heartbeat: datetime
    last_successful_run: Optional[datetime]
    error_count_1h: int
    error_count_24h: int
    avg_latency_ms: float
    data_freshness_seconds: Optional[int]
    memory_usage_mb: Optional[float]
    cpu_usage_pct: Optional[float]
    
    # Metadata
    version: Optional[str] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "health_monitor"
    update_frequency_seconds: int = 30
    
    def to_dict(self) -> dict:
        return {
            "module_name": self.module_name,
            "status": self.status.value,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "last_successful_run": self.last_successful_run.isoformat() if self.last_successful_run else None,
            "error_count_1h": self.error_count_1h,
            "error_count_24h": self.error_count_24h,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "data_freshness_seconds": self.data_freshness_seconds,
            "memory_usage_mb": round(self.memory_usage_mb, 2) if self.memory_usage_mb else None,
            "cpu_usage_pct": round(self.cpu_usage_pct, 2) if self.cpu_usage_pct else None,
            "version": self.version,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class HealthCheckRecord:
    """
    Individual health check record.
    
    Table: health_check_log
    Primary Key: id (auto-increment)
    Indexes: module_name, check_type, timestamp
    """
    id: Optional[int]
    module_name: str
    check_type: HealthCheckType
    passed: bool
    message: Optional[str]
    value: Optional[float]  # Metric value if applicable
    threshold: Optional[float]  # Expected threshold
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "health_monitor"
    retention_days: int = 7


@dataclass
class DataSourceFreshness:
    """
    Data freshness per external data source.
    
    Table: data_source_freshness
    Primary Key: source_name
    """
    source_name: str
    last_successful_fetch: Optional[datetime]
    last_attempt: datetime
    records_fetched_1h: int
    records_fetched_24h: int
    error_rate_1h: float  # 0.0 - 1.0
    avg_fetch_latency_ms: float
    is_healthy: bool
    status_message: Optional[str]
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "data_source_health"
    update_frequency_seconds: int = 60
    
    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "last_successful_fetch": self.last_successful_fetch.isoformat() if self.last_successful_fetch else None,
            "last_attempt": self.last_attempt.isoformat(),
            "records_fetched_1h": self.records_fetched_1h,
            "records_fetched_24h": self.records_fetched_24h,
            "error_rate_1h": round(self.error_rate_1h, 4),
            "avg_fetch_latency_ms": round(self.avg_fetch_latency_ms, 2),
            "is_healthy": self.is_healthy,
            "status_message": self.status_message,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class SystemError:
    """
    System error record.
    
    Table: system_errors
    Primary Key: id
    Indexes: module_name, severity, timestamp
    """
    id: Optional[int]
    module_name: str
    error_type: str
    severity: str  # ERROR, WARNING, CRITICAL
    message: str
    stack_trace: Optional[str]
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Source traceability
    source_module: str = "error_handler"
    retention_days: int = 30


# =============================================================
# SQL TABLE DEFINITIONS
# =============================================================

MODULE_HEALTH_TABLE = """
CREATE TABLE IF NOT EXISTS module_health (
    module_name VARCHAR(100) PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    last_heartbeat TIMESTAMP NOT NULL,
    last_successful_run TIMESTAMP,
    error_count_1h INTEGER DEFAULT 0,
    error_count_24h INTEGER DEFAULT 0,
    avg_latency_ms FLOAT DEFAULT 0,
    data_freshness_seconds INTEGER,
    memory_usage_mb FLOAT,
    cpu_usage_pct FLOAT,
    version VARCHAR(50),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'health_monitor',
    update_frequency_seconds INTEGER DEFAULT 30
);

CREATE INDEX IF NOT EXISTS idx_module_health_status ON module_health(status);
CREATE INDEX IF NOT EXISTS idx_module_health_updated ON module_health(updated_at);
"""

HEALTH_CHECK_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS health_check_log (
    id SERIAL PRIMARY KEY,
    module_name VARCHAR(100) NOT NULL,
    check_type VARCHAR(50) NOT NULL,
    passed BOOLEAN NOT NULL,
    message TEXT,
    value FLOAT,
    threshold FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'health_monitor'
);

CREATE INDEX IF NOT EXISTS idx_health_check_module ON health_check_log(module_name);
CREATE INDEX IF NOT EXISTS idx_health_check_type ON health_check_log(check_type);
CREATE INDEX IF NOT EXISTS idx_health_check_time ON health_check_log(timestamp);
"""

DATA_SOURCE_FRESHNESS_TABLE = """
CREATE TABLE IF NOT EXISTS data_source_freshness (
    source_name VARCHAR(100) PRIMARY KEY,
    last_successful_fetch TIMESTAMP,
    last_attempt TIMESTAMP NOT NULL,
    records_fetched_1h INTEGER DEFAULT 0,
    records_fetched_24h INTEGER DEFAULT 0,
    error_rate_1h FLOAT DEFAULT 0,
    avg_fetch_latency_ms FLOAT DEFAULT 0,
    is_healthy BOOLEAN DEFAULT true,
    status_message TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'data_source_health',
    update_frequency_seconds INTEGER DEFAULT 60
);

CREATE INDEX IF NOT EXISTS idx_source_freshness_healthy ON data_source_freshness(is_healthy);
"""

SYSTEM_ERRORS_TABLE = """
CREATE TABLE IF NOT EXISTS system_errors (
    id SERIAL PRIMARY KEY,
    module_name VARCHAR(100) NOT NULL,
    error_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    stack_trace TEXT,
    resolved BOOLEAN DEFAULT false,
    resolved_at TIMESTAMP,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_module VARCHAR(100) DEFAULT 'error_handler'
);

CREATE INDEX IF NOT EXISTS idx_errors_module ON system_errors(module_name);
CREATE INDEX IF NOT EXISTS idx_errors_severity ON system_errors(severity);
CREATE INDEX IF NOT EXISTS idx_errors_resolved ON system_errors(resolved);
CREATE INDEX IF NOT EXISTS idx_errors_time ON system_errors(timestamp);
"""

ALL_HEALTH_TABLES = [
    MODULE_HEALTH_TABLE,
    HEALTH_CHECK_LOG_TABLE,
    DATA_SOURCE_FRESHNESS_TABLE,
    SYSTEM_ERRORS_TABLE,
]
