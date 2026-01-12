"""
Risk Committee - Database Models.

============================================================
PERSISTENCE
============================================================
Store committee reports and individual reviewer decisions
for audit trail and analysis.

============================================================
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Float, Boolean,
    DateTime, Index, Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB

from database.engine import Base


# =============================================================
# ENUMS FOR DATABASE
# =============================================================

class CommitteeDecisionEnum(str, enum.Enum):
    """Committee decision enum for database."""
    APPROVE = "approve"
    HOLD = "hold"
    BLOCK = "block"


class DataIntegrityStatusEnum(str, enum.Enum):
    """Data integrity status for database."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class MarketRiskLevelEnum(str, enum.Enum):
    """Market risk level for database."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExecutionQualityEnum(str, enum.Enum):
    """Execution quality for database."""
    GOOD = "good"
    DEGRADED = "degraded"
    UNACCEPTABLE = "unacceptable"


class CapitalSafetyEnum(str, enum.Enum):
    """Capital safety status for database."""
    SAFE = "safe"
    WARNING = "warning"
    BREACH = "breach"


# =============================================================
# RISK COMMITTEE REPORT TABLE
# =============================================================

class RiskCommitteeReport(Base):
    """
    Risk Committee Report table.
    
    Stores full committee reports with all reviewer verdicts.
    Source: risk_committee.engine
    Retention: Permanent (audit trail)
    """
    __tablename__ = "risk_committee_reports"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    report_id = Column(String(36), nullable=False, unique=True, index=True)
    correlation_id = Column(String(36), nullable=False, index=True)
    cycle_id = Column(String(100), nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    review_duration_ms = Column(Float, nullable=False, default=0.0)
    
    # Committee decision
    decision = Column(
        SQLEnum(CommitteeDecisionEnum),
        nullable=False,
        default=CommitteeDecisionEnum.BLOCK
    )
    decision_reason = Column(Text, nullable=False)
    decision_details = Column(JSONB, nullable=True)
    
    # Vote summary
    critical_count = Column(Integer, nullable=False, default=0)
    warning_count = Column(Integer, nullable=False, default=0)
    ok_count = Column(Integer, nullable=False, default=0)
    
    # Individual reviewer statuses (denormalized for quick queries)
    data_integrity_status = Column(
        SQLEnum(DataIntegrityStatusEnum),
        nullable=True
    )
    market_risk_level = Column(
        SQLEnum(MarketRiskLevelEnum),
        nullable=True
    )
    execution_quality_status = Column(
        SQLEnum(ExecutionQualityEnum),
        nullable=True
    )
    capital_safety_status = Column(
        SQLEnum(CapitalSafetyEnum),
        nullable=True
    )
    
    # Full reports as JSONB (for detailed audit)
    data_integrity_report = Column(JSONB, nullable=True)
    market_risk_report = Column(JSONB, nullable=True)
    execution_quality_report = Column(JSONB, nullable=True)
    capital_safety_report = Column(JSONB, nullable=True)
    
    # Source module
    source_module = Column(String(100), nullable=False, default="risk_committee")
    
    __table_args__ = (
        Index("idx_committee_decision_time", "decision", "created_at"),
        Index("idx_committee_correlation", "correlation_id", "created_at"),
        Index("idx_committee_cycle", "cycle_id"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<RiskCommitteeReport("
            f"id={self.id}, "
            f"report_id={self.report_id[:8]}, "
            f"decision={self.decision.value}, "
            f"critical={self.critical_count}, "
            f"warning={self.warning_count}, "
            f"ok={self.ok_count}"
            f")>"
        )


# =============================================================
# CREATE TABLE SQL (for reference)
# =============================================================

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS risk_committee_reports (
    id BIGSERIAL PRIMARY KEY,
    report_id VARCHAR(36) NOT NULL UNIQUE,
    correlation_id VARCHAR(36) NOT NULL,
    cycle_id VARCHAR(100),
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    review_duration_ms FLOAT NOT NULL DEFAULT 0.0,
    
    decision VARCHAR(20) NOT NULL DEFAULT 'block',
    decision_reason TEXT NOT NULL,
    decision_details JSONB,
    
    critical_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    ok_count INTEGER NOT NULL DEFAULT 0,
    
    data_integrity_status VARCHAR(20),
    market_risk_level VARCHAR(20),
    execution_quality_status VARCHAR(20),
    capital_safety_status VARCHAR(20),
    
    data_integrity_report JSONB,
    market_risk_report JSONB,
    execution_quality_report JSONB,
    capital_safety_report JSONB,
    
    source_module VARCHAR(100) NOT NULL DEFAULT 'risk_committee'
);

CREATE INDEX IF NOT EXISTS idx_committee_decision_time 
    ON risk_committee_reports (decision, created_at);
CREATE INDEX IF NOT EXISTS idx_committee_correlation 
    ON risk_committee_reports (correlation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_committee_cycle 
    ON risk_committee_reports (cycle_id);
"""
