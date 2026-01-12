"""
Risk Scoring Engine - Repository.

============================================================
PURPOSE
============================================================
Repository pattern implementation for risk scoring persistence.

Provides clean interface for:
- Saving risk snapshots
- Recording state transitions
- Querying historical data
- Retrieving latest assessments

============================================================
"""

from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, desc, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import RiskSnapshot, RiskDimensionScore, RiskStateTransition
from .types import (
    RiskScoringOutput,
    RiskStateChange,
    RiskDimension,
    RiskState,
    RiskLevel,
)


class RiskScoringRepository:
    """
    Repository for risk scoring persistence operations.
    
    ============================================================
    METHODS
    ============================================================
    - save_snapshot: Persist a complete risk assessment
    - save_state_transitions: Record state changes
    - get_latest_snapshot: Get most recent assessment
    - get_snapshots_in_range: Historical query
    - get_pending_alerts: Transitions needing alerts
    
    ============================================================
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.
        
        Args:
            session: SQLAlchemy async session
        """
        self._session = session
    
    # --------------------------------------------------------
    # WRITE OPERATIONS
    # --------------------------------------------------------
    
    async def save_snapshot(
        self,
        output: RiskScoringOutput,
        include_raw_json: bool = False
    ) -> RiskSnapshot:
        """
        Save a complete risk assessment snapshot.
        
        Creates:
        - RiskSnapshot record
        - RiskDimensionScore records for each dimension
        
        Args:
            output: The RiskScoringOutput to persist
            include_raw_json: Whether to store full output as JSON
        
        Returns:
            Created RiskSnapshot with ID
        """
        # Create main snapshot
        snapshot = RiskSnapshot(
            total_score=output.total_score,
            risk_level=output.risk_level.name,
            assessment_timestamp=output.timestamp,
            input_data_timestamp=output.input_timestamp,
            engine_version=output.engine_version,
            raw_output_json=output.to_dict() if include_raw_json else None,
        )
        
        self._session.add(snapshot)
        
        # Create dimension scores
        for assessment in [
            output.market_assessment,
            output.liquidity_assessment,
            output.volatility_assessment,
            output.system_integrity_assessment,
        ]:
            dimension_score = RiskDimensionScore(
                snapshot_id=snapshot.id,
                dimension=assessment.dimension.name,
                state=assessment.state.name,
                state_value=assessment.state.value,
                reason=assessment.reason,
                contributing_factors=assessment.contributing_factors,
                thresholds_used=assessment.thresholds_used,
            )
            snapshot.dimension_scores.append(dimension_score)
        
        await self._session.flush()
        return snapshot
    
    async def save_state_transitions(
        self,
        transitions: List[RiskStateChange],
        snapshot_id: Optional[UUID] = None
    ) -> List[RiskStateTransition]:
        """
        Record state change transitions.
        
        Args:
            transitions: List of state changes to record
            snapshot_id: Optional link to triggering snapshot
        
        Returns:
            Created RiskStateTransition records
        """
        records = []
        
        for change in transitions:
            is_escalation = change.new_state.value > change.old_state.value
            
            record = RiskStateTransition(
                snapshot_id=snapshot_id,
                dimension=change.dimension.name,
                old_state=change.old_state.name,
                new_state=change.new_state.name,
                old_state_value=change.old_state.value,
                new_state_value=change.new_state.value,
                is_escalation=is_escalation,
                reason=change.reason,
                transition_timestamp=change.timestamp,
            )
            self._session.add(record)
            records.append(record)
        
        await self._session.flush()
        return records
    
    async def mark_alert_sent(
        self,
        transition_id: UUID,
        sent_at: Optional[datetime] = None
    ) -> None:
        """
        Mark a transition's alert as sent.
        
        Args:
            transition_id: ID of the transition
            sent_at: When the alert was sent (defaults to now)
        """
        stmt = select(RiskStateTransition).where(
            RiskStateTransition.id == transition_id
        )
        result = await self._session.execute(stmt)
        transition = result.scalar_one_or_none()
        
        if transition:
            transition.alert_sent = True
            transition.alert_sent_at = sent_at or datetime.utcnow()
            await self._session.flush()
    
    # --------------------------------------------------------
    # READ OPERATIONS
    # --------------------------------------------------------
    
    async def get_latest_snapshot(self) -> Optional[RiskSnapshot]:
        """
        Get the most recent risk snapshot.
        
        Returns:
            Latest RiskSnapshot or None if no snapshots exist
        """
        stmt = (
            select(RiskSnapshot)
            .order_by(desc(RiskSnapshot.assessment_timestamp))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_snapshot_by_id(self, snapshot_id: UUID) -> Optional[RiskSnapshot]:
        """
        Get a specific snapshot by ID.
        
        Args:
            snapshot_id: UUID of the snapshot
        
        Returns:
            RiskSnapshot or None
        """
        stmt = select(RiskSnapshot).where(RiskSnapshot.id == snapshot_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_snapshots_in_range(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[RiskSnapshot]:
        """
        Get snapshots within a time range.
        
        Args:
            start_time: Start of range (inclusive)
            end_time: End of range (inclusive), defaults to now
            limit: Maximum number of records
        
        Returns:
            List of RiskSnapshot records
        """
        end_time = end_time or datetime.utcnow()
        
        stmt = (
            select(RiskSnapshot)
            .where(
                and_(
                    RiskSnapshot.assessment_timestamp >= start_time,
                    RiskSnapshot.assessment_timestamp <= end_time,
                )
            )
            .order_by(desc(RiskSnapshot.assessment_timestamp))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_snapshots_by_level(
        self,
        risk_level: RiskLevel,
        limit: int = 100,
        since: Optional[datetime] = None
    ) -> List[RiskSnapshot]:
        """
        Get snapshots with a specific risk level.
        
        Args:
            risk_level: Risk level to filter by
            limit: Maximum number of records
            since: Only get records after this time
        
        Returns:
            List of RiskSnapshot records
        """
        conditions = [RiskSnapshot.risk_level == risk_level.name]
        
        if since:
            conditions.append(RiskSnapshot.assessment_timestamp >= since)
        
        stmt = (
            select(RiskSnapshot)
            .where(and_(*conditions))
            .order_by(desc(RiskSnapshot.assessment_timestamp))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_pending_alerts(
        self,
        escalations_only: bool = True
    ) -> List[RiskStateTransition]:
        """
        Get transitions that haven't had alerts sent.
        
        Args:
            escalations_only: Only return escalations (risk increase)
        
        Returns:
            List of RiskStateTransition records needing alerts
        """
        conditions = [RiskStateTransition.alert_sent == False]  # noqa: E712
        
        if escalations_only:
            conditions.append(RiskStateTransition.is_escalation == True)  # noqa: E712
        
        stmt = (
            select(RiskStateTransition)
            .where(and_(*conditions))
            .order_by(RiskStateTransition.transition_timestamp)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_transitions_in_range(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        dimension: Optional[RiskDimension] = None,
        limit: int = 1000
    ) -> List[RiskStateTransition]:
        """
        Get state transitions within a time range.
        
        Args:
            start_time: Start of range
            end_time: End of range (defaults to now)
            dimension: Optional dimension filter
            limit: Maximum number of records
        
        Returns:
            List of RiskStateTransition records
        """
        end_time = end_time or datetime.utcnow()
        
        conditions = [
            RiskStateTransition.transition_timestamp >= start_time,
            RiskStateTransition.transition_timestamp <= end_time,
        ]
        
        if dimension:
            conditions.append(RiskStateTransition.dimension == dimension.name)
        
        stmt = (
            select(RiskStateTransition)
            .where(and_(*conditions))
            .order_by(desc(RiskStateTransition.transition_timestamp))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    # --------------------------------------------------------
    # ANALYTICS
    # --------------------------------------------------------
    
    async def get_average_score(
        self,
        hours: int = 24
    ) -> Optional[float]:
        """
        Get average risk score over a time period.
        
        Args:
            hours: Number of hours to look back
        
        Returns:
            Average score or None if no data
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        
        stmt = select(func.avg(RiskSnapshot.total_score)).where(
            RiskSnapshot.assessment_timestamp >= since
        )
        result = await self._session.execute(stmt)
        return result.scalar()
    
    async def get_level_distribution(
        self,
        hours: int = 24
    ) -> dict[str, int]:
        """
        Get distribution of risk levels over a time period.
        
        Args:
            hours: Number of hours to look back
        
        Returns:
            Dict mapping level name to count
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        
        stmt = (
            select(
                RiskSnapshot.risk_level,
                func.count(RiskSnapshot.id)
            )
            .where(RiskSnapshot.assessment_timestamp >= since)
            .group_by(RiskSnapshot.risk_level)
        )
        result = await self._session.execute(stmt)
        
        return {row[0]: row[1] for row in result.all()}
    
    async def get_escalation_count(
        self,
        hours: int = 24
    ) -> int:
        """
        Get count of risk escalations over a time period.
        
        Args:
            hours: Number of hours to look back
        
        Returns:
            Number of escalation events
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        
        stmt = select(func.count(RiskStateTransition.id)).where(
            and_(
                RiskStateTransition.transition_timestamp >= since,
                RiskStateTransition.is_escalation == True,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0
    
    # --------------------------------------------------------
    # CLEANUP
    # --------------------------------------------------------
    
    async def delete_old_snapshots(
        self,
        older_than_days: int = 30
    ) -> int:
        """
        Delete snapshots older than a specified number of days.
        
        Args:
            older_than_days: Delete records older than this
        
        Returns:
            Number of deleted records
        """
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)
        
        # Get IDs to delete (cascade will handle children)
        stmt = select(RiskSnapshot.id).where(
            RiskSnapshot.assessment_timestamp < cutoff
        )
        result = await self._session.execute(stmt)
        ids_to_delete = [row[0] for row in result.all()]
        
        if ids_to_delete:
            from sqlalchemy import delete
            
            delete_stmt = delete(RiskSnapshot).where(
                RiskSnapshot.id.in_(ids_to_delete)
            )
            await self._session.execute(delete_stmt)
            await self._session.flush()
        
        return len(ids_to_delete)
