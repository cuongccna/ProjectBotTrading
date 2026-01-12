"""
Monitoring Domain ORM Models.

============================================================
PURPOSE
============================================================
Models for storing monitoring and alerting data: health checks,
alerts, incidents, telegram messages, and system heartbeats.

============================================================
DATA LIFECYCLE ROLE
============================================================
- Stage: OPERATIONAL (monitoring)
- Mutability: IMMUTABLE (append-only)
- Source: Monitoring systems
- Consumers: Ops dashboard, incident response

============================================================
MODELS
============================================================
- HealthCheckResult: Health check outcomes
- HealthCheckHistory: Historical health data
- Alert: Alert records
- AlertDelivery: Alert delivery attempts
- IncidentRecord: Incident records
- IncidentTimeline: Incident timeline events
- TelegramMessage: Sent telegram messages
- SystemHeartbeat: System heartbeat records

============================================================
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.models.base import Base


class HealthCheckResult(Base):
    """
    Health check results.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores results of health checks for system components.
    Each check is immutable; trends are in HealthCheckHistory.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: IMMUTABLE
    - Retention: 30 days
    - Source: Health check service
    
    ============================================================
    TRACEABILITY
    ============================================================
    - component: Component checked
    - check_name: Specific check
    - version: Checker version
    
    ============================================================
    """
    
    __tablename__ = "health_check_results"
    
    # Primary Key
    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for result"
    )
    
    # Component Details
    component: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Component being checked"
    )
    
    check_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Name of health check"
    )
    
    # Result
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Status: healthy, degraded, unhealthy, unknown"
    )
    
    is_healthy: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Simple healthy/unhealthy flag"
    )
    
    # Details
    message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Status message"
    )
    
    details: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Detailed check results"
    )
    
    # Metrics
    response_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Response time in milliseconds"
    )
    
    metric_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Primary metric value if applicable"
    )
    
    metric_threshold: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="Threshold for metric"
    )
    
    # Timestamps
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When check was performed"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Checker version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_health_component", "component"),
        Index("idx_health_check", "check_name"),
        Index("idx_health_status", "status"),
        Index("idx_health_checked_at", "checked_at"),
        Index("idx_health_healthy", "is_healthy"),
    )


class HealthCheckHistory(Base):
    """
    Historical health check aggregates.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores aggregated health check history for trend analysis.
    Aggregated from HealthCheckResult records.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: HISTORICAL
    - Mutability: IMMUTABLE
    - Retention: 1 year
    - Source: Aggregation job
    
    ============================================================
    TRACEABILITY
    ============================================================
    - period_start/end: Aggregation period
    - source_count: Number of checks aggregated
    
    ============================================================
    """
    
    __tablename__ = "health_check_history"
    
    # Primary Key
    history_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for history record"
    )
    
    # Component Details
    component: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Component"
    )
    
    check_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Check name"
    )
    
    # Period
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Period start"
    )
    
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Period end"
    )
    
    period_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Period type: hourly, daily"
    )
    
    # Aggregated Metrics
    check_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of checks in period"
    )
    
    healthy_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of healthy checks"
    )
    
    degraded_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of degraded checks"
    )
    
    unhealthy_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of unhealthy checks"
    )
    
    uptime_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Uptime percentage"
    )
    
    # Response Time Stats
    avg_response_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Average response time"
    )
    
    max_response_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Maximum response time"
    )
    
    min_response_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Minimum response time"
    )
    
    # Created At
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When record was created"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="System version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_health_hist_component", "component"),
        Index("idx_health_hist_check", "check_name"),
        Index("idx_health_hist_period", "period_start", "period_end"),
        Index("idx_health_hist_type", "period_type"),
    )


class Alert(Base):
    """
    Alert records.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores all alerts generated by the system. Each alert
    is immutable; status changes via AlertDelivery.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: IMMUTABLE
    - Retention: 90 days
    - Source: Alert router
    
    ============================================================
    TRACEABILITY
    ============================================================
    - source_component: What generated alert
    - trigger_event_id: Related event if applicable
    - version: Alert system version
    
    ============================================================
    """
    
    __tablename__ = "alerts"
    
    # Primary Key
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for alert"
    )
    
    # Alert Details
    alert_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Alert type"
    )
    
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Severity: info, warning, error, critical"
    )
    
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Alert title"
    )
    
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Alert message"
    )
    
    # Source
    source_component: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Component that generated alert"
    )
    
    trigger_event_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Related event ID"
    )
    
    # Context
    context_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Alert context data"
    )
    
    tags: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Alert tags"
    )
    
    # Routing
    channels: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        comment="Delivery channels"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="Status: pending, sent, acknowledged, resolved"
    )
    
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When acknowledged"
    )
    
    acknowledged_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Who acknowledged"
    )
    
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When resolved"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When alert was created"
    )
    
    # Deduplication
    dedup_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Deduplication key"
    )
    
    is_duplicate: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether this is a duplicate"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Alert system version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_alert_type", "alert_type"),
        Index("idx_alert_severity", "severity"),
        Index("idx_alert_source", "source_component"),
        Index("idx_alert_status", "status"),
        Index("idx_alert_created_at", "created_at"),
        Index("idx_alert_dedup", "dedup_key"),
    )


class AlertDelivery(Base):
    """
    Alert delivery attempts.
    
    ============================================================
    PURPOSE
    ============================================================
    Tracks delivery attempts for each alert to each channel.
    Supports retry logic and delivery confirmation.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: IMMUTABLE
    - Retention: 30 days
    - Source: Alert router
    
    ============================================================
    TRACEABILITY
    ============================================================
    - alert_id: FK to alert
    - Full delivery attempt history
    
    ============================================================
    """
    
    __tablename__ = "alert_deliveries"
    
    # Primary Key
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for delivery"
    )
    
    # Foreign Key
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("alerts.alert_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to alert"
    )
    
    # Channel Details
    channel: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Delivery channel: telegram, email, webhook"
    )
    
    destination: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Destination address/ID"
    )
    
    # Delivery Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="Status: pending, sent, delivered, failed"
    )
    
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of delivery attempts"
    )
    
    # Response
    response_code: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Response code if applicable"
    )
    
    response_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Response message"
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if failed"
    )
    
    # Timestamps
    first_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="First attempt time"
    )
    
    last_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Last attempt time"
    )
    
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Successful delivery time"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_del_alert", "alert_id"),
        Index("idx_del_channel", "channel"),
        Index("idx_del_status", "status"),
        Index("idx_del_first_attempt", "first_attempt_at"),
    )


class IncidentRecord(Base):
    """
    Incident records.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores incident records for significant system events
    requiring investigation or response.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: APPEND-ONLY
    - Retention: 5 years
    - Source: Incident management
    
    ============================================================
    TRACEABILITY
    ============================================================
    - trigger_alert_id: Related alert if applicable
    - Full incident timeline stored
    
    ============================================================
    """
    
    __tablename__ = "incident_records"
    
    # Primary Key
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for incident"
    )
    
    # Incident Number (human-readable)
    incident_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        comment="Human-readable incident number"
    )
    
    # Related Alert
    trigger_alert_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("alerts.alert_id", ondelete="SET NULL"),
        nullable=True,
        comment="Alert that triggered incident"
    )
    
    # Incident Details
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Incident title"
    )
    
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Incident description"
    )
    
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Severity: low, medium, high, critical"
    )
    
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Incident category"
    )
    
    # Impact
    impact_description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Description of impact"
    )
    
    affected_components: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        comment="List of affected components"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        comment="Status: open, investigating, mitigating, resolved, closed"
    )
    
    # Assignment
    assigned_to: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Assigned responder"
    )
    
    # Resolution
    root_cause: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Root cause analysis"
    )
    
    resolution: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Resolution description"
    )
    
    follow_up_actions: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Follow-up actions"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When incident was created"
    )
    
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When issue was first detected"
    )
    
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When incident was acknowledged"
    )
    
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When incident was resolved"
    )
    
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When incident was closed"
    )
    
    # Metrics
    time_to_acknowledge_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Time to acknowledge in seconds"
    )
    
    time_to_resolve_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Time to resolve in seconds"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="System version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_incident_number", "incident_number"),
        Index("idx_incident_severity", "severity"),
        Index("idx_incident_status", "status"),
        Index("idx_incident_category", "category"),
        Index("idx_incident_created_at", "created_at"),
    )


class IncidentTimeline(Base):
    """
    Incident timeline events.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores timeline events for incidents to track progress
    and actions taken during incident response.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: IMMUTABLE
    - Retention: 5 years
    - Source: Incident management
    
    ============================================================
    TRACEABILITY
    ============================================================
    - incident_id: FK to incident
    - Full event history
    
    ============================================================
    """
    
    __tablename__ = "incident_timelines"
    
    # Primary Key
    timeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for timeline entry"
    )
    
    # Foreign Key
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incident_records.incident_id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to incident"
    )
    
    # Event Details
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Event type: status_change, action, note, escalation"
    )
    
    event_description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Event description"
    )
    
    # Actor
    actor: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Who/what performed action"
    )
    
    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Actor type: user, system, automation"
    )
    
    # Metadata
    event_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional event data"
    )
    
    # Timestamps
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When event occurred"
    )
    
    # Sequence
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Event sequence number"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_timeline_incident", "incident_id"),
        Index("idx_timeline_type", "event_type"),
        Index("idx_timeline_occurred_at", "occurred_at"),
    )


class TelegramMessage(Base):
    """
    Telegram message records.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores all Telegram messages sent by the system for
    audit and retry purposes.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: IMMUTABLE
    - Retention: 90 days
    - Source: Telegram notifier
    
    ============================================================
    TRACEABILITY
    ============================================================
    - alert_id: Related alert if applicable
    - Full message content stored
    
    ============================================================
    """
    
    __tablename__ = "telegram_messages"
    
    # Primary Key
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Internal message identifier"
    )
    
    # Related Alert
    alert_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("alerts.alert_id", ondelete="SET NULL"),
        nullable=True,
        comment="Related alert if applicable"
    )
    
    # Telegram Details
    chat_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Telegram chat ID"
    )
    
    telegram_message_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Telegram-assigned message ID"
    )
    
    # Message Content
    message_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Message type: text, photo, document"
    )
    
    message_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Message text content"
    )
    
    parse_mode: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Parse mode: HTML, Markdown"
    )
    
    # Attachments
    has_attachment: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether message has attachment"
    )
    
    attachment_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Attachment type"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="Status: pending, sent, delivered, failed"
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if failed"
    )
    
    # Retry
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of retry attempts"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When message was created"
    )
    
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When message was sent"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="System version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_tg_alert", "alert_id"),
        Index("idx_tg_chat", "chat_id"),
        Index("idx_tg_status", "status"),
        Index("idx_tg_created_at", "created_at"),
    )


class SystemHeartbeat(Base):
    """
    System heartbeat records.
    
    ============================================================
    PURPOSE
    ============================================================
    Stores heartbeat signals from system components to track
    liveness and detect failures.
    
    ============================================================
    DATA LIFECYCLE
    ============================================================
    - Stage: OPERATIONAL
    - Mutability: IMMUTABLE
    - Retention: 7 days
    - Source: All components
    
    ============================================================
    TRACEABILITY
    ============================================================
    - component: Sending component
    - Full health snapshot included
    
    ============================================================
    """
    
    __tablename__ = "system_heartbeats"
    
    # Primary Key
    heartbeat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for heartbeat"
    )
    
    # Component Details
    component: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Component name"
    )
    
    instance_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Instance identifier"
    )
    
    # Heartbeat Data
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Status: alive, degraded, shutting_down"
    )
    
    uptime_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Component uptime in seconds"
    )
    
    # Resource Usage
    cpu_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="CPU usage percentage"
    )
    
    memory_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Memory usage percentage"
    )
    
    memory_mb: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Memory usage in MB"
    )
    
    # Work Stats
    items_processed: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Items processed since last heartbeat"
    )
    
    queue_depth: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Current queue depth"
    )
    
    # Metadata (renamed from 'metadata' - reserved in SQLAlchemy)
    heartbeat_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional metadata"
    )
    
    # Timestamps
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Heartbeat timestamp"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Component version"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_hb_component", "component"),
        Index("idx_hb_instance", "instance_id"),
        Index("idx_hb_status", "status"),
        Index("idx_hb_at", "heartbeat_at"),
    )
