"""
System Risk Controller - ORM Models.

============================================================
PURPOSE
============================================================
SQLAlchemy ORM models for persisting:
- Halt events
- State transitions
- Resume requests
- Audit trail

ALL HALT DECISIONS MUST BE LOGGED.

============================================================
"""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Text,
    Enum as SQLAEnum,
    JSON,
    Index,
    ForeignKey,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.declarative import declarative_base

from .types import SystemState, HaltLevel, TriggerCategory


Base = declarative_base()


# ============================================================
# HALT EVENT MODEL
# ============================================================

class HaltEventModel(Base):
    """
    Persisted halt event.
    
    Every halt trigger is logged for audit.
    """
    
    __tablename__ = "system_halt_events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    event_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        index=True,
    )
    """UUID of the event."""
    
    trigger_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    """Halt trigger code (e.g., DI_MISSING_MARKET_DATA)."""
    
    trigger_category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )
    """Trigger category (DATA_INTEGRITY, PROCESSING, etc.)."""
    
    halt_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    """Halt level (1=SOFT, 2=HARD, 3=EMERGENCY)."""
    
    halt_level_name: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    """Halt level name for readability."""
    
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )
    """When the event occurred."""
    
    source_monitor: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    """Monitor that detected the issue."""
    
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    """Human-readable message."""
    
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    """Additional details as JSON."""
    
    resolved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    """Whether this trigger has been resolved."""
    
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )
    """When the trigger was resolved."""
    
    resolved_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    """Who resolved the trigger."""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    """When record was created."""
    
    __table_args__ = (
        Index("ix_halt_events_timestamp_level", "timestamp", "halt_level"),
        Index("ix_halt_events_resolved", "resolved", "timestamp"),
    )


# ============================================================
# STATE TRANSITION MODEL
# ============================================================

class StateTransitionModel(Base):
    """
    Persisted state transition.
    
    Every state change is logged for audit.
    """
    
    __tablename__ = "system_state_transitions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    transition_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        index=True,
    )
    """UUID of the transition."""
    
    from_state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    """State before transition."""
    
    to_state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )
    """State after transition."""
    
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )
    """When transition occurred."""
    
    trigger_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    """Trigger that caused transition (if any)."""
    
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    """Reason for transition."""
    
    is_automatic: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    """Whether transition was automatic."""
    
    halt_event_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
    )
    """Related halt event ID (if any)."""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    """When record was created."""
    
    __table_args__ = (
        Index("ix_state_transitions_timestamp", "timestamp"),
    )


# ============================================================
# RESUME REQUEST MODEL
# ============================================================

class ResumeRequestModel(Base):
    """
    Persisted resume request.
    
    Every resume attempt is logged for audit.
    """
    
    __tablename__ = "system_resume_requests"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    request_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        index=True,
    )
    """UUID of the request."""
    
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )
    """When request was made."""
    
    operator: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    """Who made the request."""
    
    from_state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    """State before resume attempt."""
    
    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    """Reason for resume."""
    
    acknowledged: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    """Whether operator acknowledged."""
    
    confirmed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    """Whether operator confirmed (for emergency)."""
    
    force: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    """Whether this was a forced resume."""
    
    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    """Whether resume was successful."""
    
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    """Error message if failed."""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    """When record was created."""


# ============================================================
# SYSTEM STATE SNAPSHOT MODEL
# ============================================================

class SystemStateSnapshotModel(Base):
    """
    Periodic snapshot of system state.
    
    Used for debugging and analysis.
    """
    
    __tablename__ = "system_state_snapshots"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )
    """When snapshot was taken."""
    
    system_state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    """Current system state."""
    
    active_triggers: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    """Active triggers at snapshot time."""
    
    monitor_results: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    """Monitor results at snapshot time."""
    
    health_metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    """Health metrics at snapshot time."""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    """When record was created."""
    
    __table_args__ = (
        Index("ix_state_snapshots_timestamp", "timestamp"),
    )
