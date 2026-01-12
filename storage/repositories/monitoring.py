"""
Monitoring & Alert Repositories.

============================================================
PURPOSE
============================================================
Repositories for system monitoring and alerts. These handle
health checks, heartbeats, alerts, and incident tracking.

============================================================
DATA LIFECYCLE
============================================================
- Stage: MONITORING
- Mutability: APPEND-ONLY (logs are immutable)
- Time-series data with retention policies

============================================================
REPOSITORIES
============================================================
- SystemHealthRepository: Health checks and heartbeats
- AlertLogRepository: Alerts and incident tracking

============================================================
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import UUID

from sqlalchemy import select, and_, desc, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from storage.models.monitoring import (
    HealthCheckResult,
    HealthCheckHistory,
    SystemHeartbeat,
    Alert,
    AlertDelivery,
    IncidentRecord,
    IncidentTimeline,
    TelegramMessage,
)
from storage.repositories.base import BaseRepository
from storage.repositories.exceptions import (
    RecordNotFoundError,
    RepositoryException,
)


class SystemHealthRepository(BaseRepository[HealthCheckResult]):
    """
    Repository for system health monitoring.
    
    ============================================================
    SCOPE
    ============================================================
    Manages HealthCheckResult, HealthCheckHistory, and
    SystemHeartbeat records. Continuous system health monitoring
    and availability tracking.
    
    ============================================================
    MODELS MANAGED
    ============================================================
    - HealthCheckResult: Current health check results
    - HealthCheckHistory: Historical health data
    - SystemHeartbeat: System heartbeat records
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, HealthCheckResult, "SystemHealthRepository")
    
    # =========================================================
    # HEALTH CHECK RESULT OPERATIONS
    # =========================================================
    
    def record_health_check(
        self,
        component: str,
        checked_at: datetime,
        is_healthy: bool,
        status: str,
        latency_ms: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> HealthCheckResult:
        """
        Record a health check result.
        
        Args:
            component: Component identifier
            checked_at: Check timestamp
            is_healthy: Whether component is healthy
            status: Status string
            latency_ms: Latency in milliseconds
            details: Detailed check results
            error_message: Error message if unhealthy
            
        Returns:
            Created HealthCheckResult record
        """
        entity = HealthCheckResult(
            component=component,
            checked_at=checked_at,
            is_healthy=is_healthy,
            status=status,
            latency_ms=latency_ms,
            details=details or {},
            error_message=error_message,
        )
        return self._add(entity)
    
    def get_health_check_by_id(
        self,
        check_id: UUID
    ) -> Optional[HealthCheckResult]:
        """Get health check result by ID."""
        return self._get_by_id(check_id)
    
    def get_latest_health_check(
        self,
        component: str
    ) -> Optional[HealthCheckResult]:
        """
        Get the most recent health check for a component.
        
        Args:
            component: Component identifier
            
        Returns:
            Most recent HealthCheckResult or None
        """
        stmt = (
            select(HealthCheckResult)
            .where(HealthCheckResult.component == component)
            .order_by(desc(HealthCheckResult.checked_at))
            .limit(1)
        )
        return self._execute_scalar(stmt)
    
    def list_health_checks_by_component(
        self,
        component: str,
        limit: int = 100
    ) -> List[HealthCheckResult]:
        """
        List health checks for a component.
        
        Args:
            component: Component identifier
            limit: Maximum records to return
            
        Returns:
            List of HealthCheckResult
        """
        stmt = (
            select(HealthCheckResult)
            .where(HealthCheckResult.component == component)
            .order_by(desc(HealthCheckResult.checked_at))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_unhealthy_checks(
        self,
        limit: int = 100
    ) -> List[HealthCheckResult]:
        """
        List unhealthy check results.
        
        Args:
            limit: Maximum records to return
            
        Returns:
            List of unhealthy HealthCheckResult records
        """
        stmt = (
            select(HealthCheckResult)
            .where(HealthCheckResult.is_healthy == False)
            .order_by(desc(HealthCheckResult.checked_at))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_health_checks_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        component: Optional[str] = None,
        limit: int = 1000
    ) -> List[HealthCheckResult]:
        """
        List health checks within a time range.
        
        Args:
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            component: Optional component filter
            limit: Maximum records to return
            
        Returns:
            List of HealthCheckResult
        """
        conditions = [
            HealthCheckResult.checked_at >= start_time,
            HealthCheckResult.checked_at < end_time,
        ]
        if component:
            conditions.append(HealthCheckResult.component == component)
        
        stmt = (
            select(HealthCheckResult)
            .where(and_(*conditions))
            .order_by(HealthCheckResult.checked_at)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    # =========================================================
    # HEALTH CHECK HISTORY OPERATIONS
    # =========================================================
    
    def record_health_history(
        self,
        component: str,
        recorded_at: datetime,
        period_start: datetime,
        period_end: datetime,
        total_checks: int,
        healthy_checks: int,
        average_latency_ms: Optional[int] = None,
        max_latency_ms: Optional[int] = None,
        uptime_percent: Optional[Decimal] = None,
    ) -> HealthCheckHistory:
        """
        Record health check history aggregation.
        
        Args:
            component: Component identifier
            recorded_at: Record timestamp
            period_start: Period start
            period_end: Period end
            total_checks: Total checks in period
            healthy_checks: Healthy checks in period
            average_latency_ms: Average latency
            max_latency_ms: Maximum latency
            uptime_percent: Uptime percentage
            
        Returns:
            Created HealthCheckHistory record
        """
        entity = HealthCheckHistory(
            component=component,
            recorded_at=recorded_at,
            period_start=period_start,
            period_end=period_end,
            total_checks=total_checks,
            healthy_checks=healthy_checks,
            average_latency_ms=average_latency_ms,
            max_latency_ms=max_latency_ms,
            uptime_percent=uptime_percent,
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.debug(
                f"Health history for {component}: "
                f"{healthy_checks}/{total_checks} healthy"
            )
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_health_history", {
                "component": component
            })
            raise
    
    def list_health_history_by_component(
        self,
        component: str,
        limit: int = 100
    ) -> List[HealthCheckHistory]:
        """
        List health history for a component.
        
        Args:
            component: Component identifier
            limit: Maximum records to return
            
        Returns:
            List of HealthCheckHistory
        """
        stmt = (
            select(HealthCheckHistory)
            .where(HealthCheckHistory.component == component)
            .order_by(desc(HealthCheckHistory.recorded_at))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_health_history_by_component", {
                "component": component
            })
            raise
    
    # =========================================================
    # SYSTEM HEARTBEAT OPERATIONS
    # =========================================================
    
    def record_heartbeat(
        self,
        service: str,
        heartbeat_at: datetime,
        version: str,
        uptime_seconds: int,
        cpu_percent: Optional[Decimal] = None,
        memory_percent: Optional[Decimal] = None,
        active_connections: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SystemHeartbeat:
        """
        Record a system heartbeat.
        
        Args:
            service: Service identifier
            heartbeat_at: Heartbeat timestamp
            version: Service version
            uptime_seconds: Service uptime in seconds
            cpu_percent: CPU usage percentage
            memory_percent: Memory usage percentage
            active_connections: Number of active connections
            metadata: Additional metadata
            
        Returns:
            Created SystemHeartbeat record
        """
        entity = SystemHeartbeat(
            service=service,
            heartbeat_at=heartbeat_at,
            version=version,
            uptime_seconds=uptime_seconds,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            active_connections=active_connections,
            metadata=metadata or {},
        )
        try:
            self._session.add(entity)
            self._session.flush()
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_heartbeat", {
                "service": service
            })
            raise
    
    def get_latest_heartbeat(
        self,
        service: str
    ) -> Optional[SystemHeartbeat]:
        """
        Get the most recent heartbeat for a service.
        
        Args:
            service: Service identifier
            
        Returns:
            Most recent SystemHeartbeat or None
        """
        stmt = (
            select(SystemHeartbeat)
            .where(SystemHeartbeat.service == service)
            .order_by(desc(SystemHeartbeat.heartbeat_at))
            .limit(1)
        )
        try:
            result = self._session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            self._handle_db_error(e, "get_latest_heartbeat", {
                "service": service
            })
            raise
    
    def list_heartbeats_by_service(
        self,
        service: str,
        limit: int = 100
    ) -> List[SystemHeartbeat]:
        """
        List heartbeats for a service.
        
        Args:
            service: Service identifier
            limit: Maximum records to return
            
        Returns:
            List of SystemHeartbeat
        """
        stmt = (
            select(SystemHeartbeat)
            .where(SystemHeartbeat.service == service)
            .order_by(desc(SystemHeartbeat.heartbeat_at))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_heartbeats_by_service", {
                "service": service
            })
            raise
    
    def list_all_latest_heartbeats(self) -> List[SystemHeartbeat]:
        """
        Get the latest heartbeat for each service.
        
        Returns:
            List of SystemHeartbeat (one per service)
        """
        # Get distinct services first
        from sqlalchemy import distinct
        
        try:
            services_stmt = select(distinct(SystemHeartbeat.service))
            result = self._session.execute(services_stmt)
            services = list(result.scalars().all())
            
            heartbeats = []
            for service in services:
                hb = self.get_latest_heartbeat(service)
                if hb:
                    heartbeats.append(hb)
            
            return heartbeats
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_all_latest_heartbeats", {})
            raise


class AlertLogRepository(BaseRepository[Alert]):
    """
    Repository for alerts and incidents.
    
    ============================================================
    SCOPE
    ============================================================
    Manages Alert, AlertDelivery, IncidentRecord, IncidentTimeline,
    and TelegramMessage records. Complete alerting and incident
    management audit trail.
    
    ============================================================
    MODELS MANAGED
    ============================================================
    - Alert: Alert records
    - AlertDelivery: Alert delivery tracking
    - IncidentRecord: Incident records
    - IncidentTimeline: Incident timeline events
    - TelegramMessage: Telegram notifications
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, Alert, "AlertLogRepository")
    
    # =========================================================
    # ALERT OPERATIONS
    # =========================================================
    
    def create_alert(
        self,
        created_at: datetime,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        source: str,
        category: str,
        affected_component: Optional[str] = None,
        affected_symbol: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        state: str = "active",
    ) -> Alert:
        """
        Create an alert.
        
        Args:
            created_at: Creation timestamp
            alert_type: Alert type
            severity: Severity level
            title: Alert title
            message: Alert message
            source: Alert source
            category: Alert category
            affected_component: Affected component
            affected_symbol: Affected symbol
            details: Additional details
            state: Initial state
            
        Returns:
            Created Alert record
        """
        entity = Alert(
            created_at=created_at,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            source=source,
            category=category,
            affected_component=affected_component,
            affected_symbol=affected_symbol,
            details=details or {},
            state=state,
        )
        return self._add(entity)
    
    def get_alert_by_id(self, alert_id: UUID) -> Optional[Alert]:
        """Get alert by ID."""
        return self._get_by_id(alert_id)
    
    def get_alert_by_id_or_raise(self, alert_id: UUID) -> Alert:
        """Get alert by ID, raising if not found."""
        return self._get_by_id_or_raise(alert_id, "alert_id")
    
    def list_alerts_by_severity(
        self,
        severity: str,
        limit: int = 100
    ) -> List[Alert]:
        """
        List alerts by severity.
        
        Args:
            severity: Severity level
            limit: Maximum records to return
            
        Returns:
            List of Alert
        """
        stmt = (
            select(Alert)
            .where(Alert.severity == severity)
            .order_by(desc(Alert.created_at))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_alerts_by_state(
        self,
        state: str,
        limit: int = 100
    ) -> List[Alert]:
        """
        List alerts by state.
        
        Args:
            state: Alert state
            limit: Maximum records to return
            
        Returns:
            List of Alert
        """
        stmt = (
            select(Alert)
            .where(Alert.state == state)
            .order_by(desc(Alert.created_at))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_active_alerts(
        self,
        severity: Optional[str] = None,
        limit: int = 100
    ) -> List[Alert]:
        """
        List active alerts.
        
        Args:
            severity: Optional severity filter
            limit: Maximum records to return
            
        Returns:
            List of active Alert records
        """
        conditions = [Alert.state == "active"]
        if severity:
            conditions.append(Alert.severity == severity)
        
        stmt = (
            select(Alert)
            .where(and_(*conditions))
            .order_by(desc(Alert.created_at))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_alerts_by_category(
        self,
        category: str,
        limit: int = 100
    ) -> List[Alert]:
        """
        List alerts by category.
        
        Args:
            category: Alert category
            limit: Maximum records to return
            
        Returns:
            List of Alert
        """
        stmt = (
            select(Alert)
            .where(Alert.category == category)
            .order_by(desc(Alert.created_at))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_alerts_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        severity: Optional[str] = None,
        limit: int = 1000
    ) -> List[Alert]:
        """
        List alerts within a time range.
        
        Args:
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            severity: Optional severity filter
            limit: Maximum records to return
            
        Returns:
            List of Alert
        """
        conditions = [
            Alert.created_at >= start_time,
            Alert.created_at < end_time,
        ]
        if severity:
            conditions.append(Alert.severity == severity)
        
        stmt = (
            select(Alert)
            .where(and_(*conditions))
            .order_by(Alert.created_at)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    # =========================================================
    # ALERT DELIVERY OPERATIONS
    # =========================================================
    
    def record_alert_delivery(
        self,
        alert_id: UUID,
        channel: str,
        delivered_at: datetime,
        is_successful: bool,
        recipient: Optional[str] = None,
        delivery_id: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AlertDelivery:
        """
        Record alert delivery attempt.
        
        Args:
            alert_id: Reference to alert
            channel: Delivery channel
            delivered_at: Delivery timestamp
            is_successful: Whether delivery succeeded
            recipient: Recipient identifier
            delivery_id: External delivery ID
            error_message: Error message if failed
            metadata: Additional metadata
            
        Returns:
            Created AlertDelivery record
        """
        entity = AlertDelivery(
            alert_id=alert_id,
            channel=channel,
            delivered_at=delivered_at,
            is_successful=is_successful,
            recipient=recipient,
            delivery_id=delivery_id,
            error_message=error_message,
            metadata=metadata or {},
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.debug(
                f"Alert {alert_id} delivered via {channel}: {is_successful}"
            )
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_alert_delivery", {
                "alert_id": str(alert_id),
                "channel": channel
            })
            raise
    
    def list_deliveries_by_alert(
        self,
        alert_id: UUID
    ) -> List[AlertDelivery]:
        """
        List all deliveries for an alert.
        
        Args:
            alert_id: The alert UUID
            
        Returns:
            List of AlertDelivery
        """
        stmt = (
            select(AlertDelivery)
            .where(AlertDelivery.alert_id == alert_id)
            .order_by(AlertDelivery.delivered_at)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_deliveries_by_alert", {
                "alert_id": str(alert_id)
            })
            raise
    
    def list_failed_deliveries(
        self,
        limit: int = 100
    ) -> List[AlertDelivery]:
        """
        List failed delivery attempts.
        
        Args:
            limit: Maximum records to return
            
        Returns:
            List of failed AlertDelivery records
        """
        stmt = (
            select(AlertDelivery)
            .where(AlertDelivery.is_successful == False)
            .order_by(desc(AlertDelivery.delivered_at))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_failed_deliveries", {})
            raise
    
    # =========================================================
    # INCIDENT RECORD OPERATIONS
    # =========================================================
    
    def create_incident(
        self,
        created_at: datetime,
        title: str,
        description: str,
        severity: str,
        category: str,
        source: str,
        affected_components: List[str],
        triggered_by: Optional[UUID] = None,
        state: str = "open",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IncidentRecord:
        """
        Create an incident record.
        
        Args:
            created_at: Creation timestamp
            title: Incident title
            description: Incident description
            severity: Severity level
            category: Incident category
            source: Incident source
            affected_components: List of affected components
            triggered_by: Alert that triggered incident
            state: Initial state
            metadata: Additional metadata
            
        Returns:
            Created IncidentRecord
        """
        entity = IncidentRecord(
            created_at=created_at,
            title=title,
            description=description,
            severity=severity,
            category=category,
            source=source,
            affected_components=affected_components,
            triggered_by=triggered_by,
            state=state,
            metadata=metadata or {},
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.warning(f"Incident created: {title}")
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "create_incident", {"title": title})
            raise
    
    def get_incident_by_id(
        self,
        incident_id: UUID
    ) -> Optional[IncidentRecord]:
        """Get incident by ID."""
        stmt = select(IncidentRecord).where(IncidentRecord.id == incident_id)
        return self._execute_scalar(stmt)
    
    def list_open_incidents(
        self,
        severity: Optional[str] = None,
        limit: int = 100
    ) -> List[IncidentRecord]:
        """
        List open incidents.
        
        Args:
            severity: Optional severity filter
            limit: Maximum records to return
            
        Returns:
            List of open IncidentRecord records
        """
        conditions = [IncidentRecord.state == "open"]
        if severity:
            conditions.append(IncidentRecord.severity == severity)
        
        stmt = (
            select(IncidentRecord)
            .where(and_(*conditions))
            .order_by(desc(IncidentRecord.created_at))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_open_incidents", {})
            raise
    
    def list_incidents_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000
    ) -> List[IncidentRecord]:
        """
        List incidents within a time range.
        
        Args:
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            limit: Maximum records to return
            
        Returns:
            List of IncidentRecord
        """
        stmt = (
            select(IncidentRecord)
            .where(and_(
                IncidentRecord.created_at >= start_time,
                IncidentRecord.created_at < end_time,
            ))
            .order_by(IncidentRecord.created_at)
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_incidents_by_time_range", {
                "start": str(start_time),
                "end": str(end_time)
            })
            raise
    
    # =========================================================
    # INCIDENT TIMELINE OPERATIONS
    # =========================================================
    
    def record_incident_timeline_event(
        self,
        incident_id: UUID,
        event_at: datetime,
        event_type: str,
        description: str,
        actor: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IncidentTimeline:
        """
        Record an incident timeline event.
        
        Args:
            incident_id: Reference to incident
            event_at: Event timestamp
            event_type: Event type
            description: Event description
            actor: Who performed the action
            metadata: Additional metadata
            
        Returns:
            Created IncidentTimeline record
        """
        entity = IncidentTimeline(
            incident_id=incident_id,
            event_at=event_at,
            event_type=event_type,
            description=description,
            actor=actor,
            metadata=metadata or {},
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.debug(f"Incident {incident_id} timeline: {event_type}")
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_incident_timeline_event", {
                "incident_id": str(incident_id)
            })
            raise
    
    def list_timeline_by_incident(
        self,
        incident_id: UUID
    ) -> List[IncidentTimeline]:
        """
        List timeline events for an incident.
        
        Args:
            incident_id: The incident UUID
            
        Returns:
            List of IncidentTimeline
        """
        stmt = (
            select(IncidentTimeline)
            .where(IncidentTimeline.incident_id == incident_id)
            .order_by(IncidentTimeline.event_at)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_timeline_by_incident", {
                "incident_id": str(incident_id)
            })
            raise
    
    # =========================================================
    # TELEGRAM MESSAGE OPERATIONS
    # =========================================================
    
    def record_telegram_message(
        self,
        sent_at: datetime,
        chat_id: str,
        message_type: str,
        content: str,
        is_successful: bool,
        alert_id: Optional[UUID] = None,
        message_id: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TelegramMessage:
        """
        Record a Telegram message.
        
        Args:
            sent_at: Send timestamp
            chat_id: Telegram chat ID
            message_type: Message type
            content: Message content
            is_successful: Whether send succeeded
            alert_id: Related alert if applicable
            message_id: Telegram message ID if successful
            error_message: Error message if failed
            metadata: Additional metadata
            
        Returns:
            Created TelegramMessage record
        """
        entity = TelegramMessage(
            sent_at=sent_at,
            chat_id=chat_id,
            message_type=message_type,
            content=content,
            is_successful=is_successful,
            alert_id=alert_id,
            message_id=message_id,
            error_message=error_message,
            metadata=metadata or {},
        )
        try:
            self._session.add(entity)
            self._session.flush()
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_telegram_message", {
                "chat_id": chat_id
            })
            raise
    
    def list_telegram_messages_by_chat(
        self,
        chat_id: str,
        limit: int = 100
    ) -> List[TelegramMessage]:
        """
        List Telegram messages for a chat.
        
        Args:
            chat_id: Telegram chat ID
            limit: Maximum records to return
            
        Returns:
            List of TelegramMessage
        """
        stmt = (
            select(TelegramMessage)
            .where(TelegramMessage.chat_id == chat_id)
            .order_by(desc(TelegramMessage.sent_at))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_telegram_messages_by_chat", {
                "chat_id": chat_id
            })
            raise
    
    def list_failed_telegram_messages(
        self,
        limit: int = 100
    ) -> List[TelegramMessage]:
        """
        List failed Telegram messages.
        
        Args:
            limit: Maximum records to return
            
        Returns:
            List of failed TelegramMessage records
        """
        stmt = (
            select(TelegramMessage)
            .where(TelegramMessage.is_successful == False)
            .order_by(desc(TelegramMessage.sent_at))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_failed_telegram_messages", {})
            raise
    
    def list_telegram_messages_by_alert(
        self,
        alert_id: UUID
    ) -> List[TelegramMessage]:
        """
        List Telegram messages for an alert.
        
        Args:
            alert_id: The alert UUID
            
        Returns:
            List of TelegramMessage
        """
        stmt = (
            select(TelegramMessage)
            .where(TelegramMessage.alert_id == alert_id)
            .order_by(TelegramMessage.sent_at)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_telegram_messages_by_alert", {
                "alert_id": str(alert_id)
            })
            raise
