"""
System Risk Controller - Repository.

============================================================
PURPOSE
============================================================
Database operations for persisting halt events, state 
transitions, and audit trail.

ALL HALT DECISIONS MUST BE PERSISTED.

============================================================
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import uuid

from sqlalchemy import select, update, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from .types import (
    HaltTrigger,
    HaltLevel,
    HaltEvent,
    StateTransition,
    ResumeRequest,
    SystemHealthSnapshot,
)
from .models import (
    HaltEventModel,
    StateTransitionModel,
    ResumeRequestModel,
    SystemStateSnapshotModel,
)


logger = logging.getLogger(__name__)


# ============================================================
# REPOSITORY
# ============================================================

class SystemRiskControllerRepository:
    """
    Repository for System Risk Controller persistence.
    
    ALL halt events, state transitions, and resume requests
    are persisted for audit trail.
    """
    
    def __init__(self, session_factory):
        """
        Initialize repository.
        
        Args:
            session_factory: Async session factory
        """
        self._session_factory = session_factory
    
    # --------------------------------------------------------
    # HALT EVENTS
    # --------------------------------------------------------
    
    async def save_halt_event(
        self,
        event: HaltEvent,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """
        Save a halt event.
        
        Args:
            event: Halt event to save
            session: Optional existing session
            
        Returns:
            Event ID
        """
        async with self._get_session(session) as sess:
            model = HaltEventModel(
                event_id=event.event_id,
                trigger_code=event.trigger.value,
                trigger_category=event.trigger.get_category().value,
                halt_level=event.halt_level.value,
                halt_level_name=event.halt_level.name,
                timestamp=event.timestamp,
                source_monitor=event.source_monitor,
                message=event.message,
                details=event.details,
                resolved=False,
            )
            sess.add(model)
            await sess.commit()
            
            logger.info(f"Saved halt event: {event.event_id}")
            return event.event_id
    
    async def mark_halt_event_resolved(
        self,
        event_id: str,
        resolved_by: str,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """
        Mark a halt event as resolved.
        
        Args:
            event_id: Event ID to resolve
            resolved_by: Who resolved it
            session: Optional existing session
        """
        async with self._get_session(session) as sess:
            stmt = (
                update(HaltEventModel)
                .where(HaltEventModel.event_id == event_id)
                .values(
                    resolved=True,
                    resolved_at=datetime.utcnow(),
                    resolved_by=resolved_by,
                )
            )
            await sess.execute(stmt)
            await sess.commit()
            
            logger.info(f"Resolved halt event: {event_id} by {resolved_by}")
    
    async def get_active_halt_events(
        self,
        session: Optional[AsyncSession] = None,
    ) -> List[HaltEventModel]:
        """
        Get all unresolved halt events.
        
        Args:
            session: Optional existing session
            
        Returns:
            List of active halt events
        """
        async with self._get_session(session) as sess:
            stmt = (
                select(HaltEventModel)
                .where(HaltEventModel.resolved == False)
                .order_by(desc(HaltEventModel.timestamp))
            )
            result = await sess.execute(stmt)
            return list(result.scalars().all())
    
    async def get_halt_events_since(
        self,
        since: datetime,
        session: Optional[AsyncSession] = None,
    ) -> List[HaltEventModel]:
        """
        Get halt events since a timestamp.
        
        Args:
            since: Start timestamp
            session: Optional existing session
            
        Returns:
            List of halt events
        """
        async with self._get_session(session) as sess:
            stmt = (
                select(HaltEventModel)
                .where(HaltEventModel.timestamp >= since)
                .order_by(desc(HaltEventModel.timestamp))
            )
            result = await sess.execute(stmt)
            return list(result.scalars().all())
    
    async def get_halt_events_by_level(
        self,
        level: HaltLevel,
        limit: int = 100,
        session: Optional[AsyncSession] = None,
    ) -> List[HaltEventModel]:
        """
        Get halt events by level.
        
        Args:
            level: Halt level to filter by
            limit: Maximum number of results
            session: Optional existing session
            
        Returns:
            List of halt events
        """
        async with self._get_session(session) as sess:
            stmt = (
                select(HaltEventModel)
                .where(HaltEventModel.halt_level == level.value)
                .order_by(desc(HaltEventModel.timestamp))
                .limit(limit)
            )
            result = await sess.execute(stmt)
            return list(result.scalars().all())
    
    # --------------------------------------------------------
    # STATE TRANSITIONS
    # --------------------------------------------------------
    
    async def save_state_transition(
        self,
        transition: StateTransition,
        halt_event_id: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """
        Save a state transition.
        
        Args:
            transition: Transition to save
            halt_event_id: Related halt event ID
            session: Optional existing session
            
        Returns:
            Transition ID
        """
        transition_id = str(uuid.uuid4())
        
        async with self._get_session(session) as sess:
            model = StateTransitionModel(
                transition_id=transition_id,
                from_state=transition.from_state.value,
                to_state=transition.to_state.value,
                timestamp=transition.timestamp,
                trigger_code=transition.trigger.value if transition.trigger else None,
                reason=transition.reason,
                is_automatic=transition.is_automatic,
                halt_event_id=halt_event_id,
            )
            sess.add(model)
            await sess.commit()
            
            logger.info(
                f"Saved state transition: {transition.from_state} -> "
                f"{transition.to_state}"
            )
            return transition_id
    
    async def get_state_transitions_since(
        self,
        since: datetime,
        session: Optional[AsyncSession] = None,
    ) -> List[StateTransitionModel]:
        """
        Get state transitions since a timestamp.
        
        Args:
            since: Start timestamp
            session: Optional existing session
            
        Returns:
            List of state transitions
        """
        async with self._get_session(session) as sess:
            stmt = (
                select(StateTransitionModel)
                .where(StateTransitionModel.timestamp >= since)
                .order_by(desc(StateTransitionModel.timestamp))
            )
            result = await sess.execute(stmt)
            return list(result.scalars().all())
    
    async def get_recent_transitions(
        self,
        limit: int = 50,
        session: Optional[AsyncSession] = None,
    ) -> List[StateTransitionModel]:
        """
        Get recent state transitions.
        
        Args:
            limit: Maximum number of results
            session: Optional existing session
            
        Returns:
            List of state transitions
        """
        async with self._get_session(session) as sess:
            stmt = (
                select(StateTransitionModel)
                .order_by(desc(StateTransitionModel.timestamp))
                .limit(limit)
            )
            result = await sess.execute(stmt)
            return list(result.scalars().all())
    
    # --------------------------------------------------------
    # RESUME REQUESTS
    # --------------------------------------------------------
    
    async def save_resume_request(
        self,
        request: ResumeRequest,
        from_state: str,
        success: bool,
        error_message: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """
        Save a resume request.
        
        Args:
            request: Resume request
            from_state: State before resume
            success: Whether resume succeeded
            error_message: Error message if failed
            session: Optional existing session
            
        Returns:
            Request ID
        """
        request_id = str(uuid.uuid4())
        
        async with self._get_session(session) as sess:
            model = ResumeRequestModel(
                request_id=request_id,
                timestamp=request.timestamp,
                operator=request.operator,
                from_state=from_state,
                reason=request.reason,
                acknowledged=request.acknowledged,
                confirmed=request.confirmed,
                force=request.force,
                success=success,
                error_message=error_message,
            )
            sess.add(model)
            await sess.commit()
            
            logger.info(
                f"Saved resume request by {request.operator}: "
                f"success={success}"
            )
            return request_id
    
    # --------------------------------------------------------
    # SNAPSHOTS
    # --------------------------------------------------------
    
    async def save_health_snapshot(
        self,
        snapshot: SystemHealthSnapshot,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """
        Save a system health snapshot.
        
        Args:
            snapshot: Health snapshot to save
            session: Optional existing session
        """
        async with self._get_session(session) as sess:
            model = SystemStateSnapshotModel(
                timestamp=snapshot.timestamp,
                system_state=snapshot.system_state.value,
                active_triggers=[t.value for t in snapshot.active_triggers],
                monitor_results={
                    name: {
                        "is_healthy": r.is_healthy,
                        "message": r.message,
                        "metrics": r.metrics,
                    }
                    for name, r in snapshot.monitor_results.items()
                },
                health_metrics={},
            )
            sess.add(model)
            await sess.commit()
    
    async def get_snapshots_since(
        self,
        since: datetime,
        session: Optional[AsyncSession] = None,
    ) -> List[SystemStateSnapshotModel]:
        """
        Get snapshots since a timestamp.
        
        Args:
            since: Start timestamp
            session: Optional existing session
            
        Returns:
            List of snapshots
        """
        async with self._get_session(session) as sess:
            stmt = (
                select(SystemStateSnapshotModel)
                .where(SystemStateSnapshotModel.timestamp >= since)
                .order_by(desc(SystemStateSnapshotModel.timestamp))
            )
            result = await sess.execute(stmt)
            return list(result.scalars().all())
    
    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------
    
    async def get_halt_statistics(
        self,
        days: int = 30,
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """
        Get halt statistics for the past N days.
        
        Args:
            days: Number of days to analyze
            session: Optional existing session
            
        Returns:
            Statistics dictionary
        """
        since = datetime.utcnow() - timedelta(days=days)
        
        events = await self.get_halt_events_since(since, session)
        
        stats = {
            "total_events": len(events),
            "by_level": {
                "SOFT": 0,
                "HARD": 0,
                "EMERGENCY": 0,
            },
            "by_category": {},
            "resolved": 0,
            "unresolved": 0,
        }
        
        for event in events:
            # By level
            level_name = event.halt_level_name
            if level_name in stats["by_level"]:
                stats["by_level"][level_name] += 1
            
            # By category
            category = event.trigger_category
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1
            
            # Resolution status
            if event.resolved:
                stats["resolved"] += 1
            else:
                stats["unresolved"] += 1
        
        return stats
    
    # --------------------------------------------------------
    # HELPERS
    # --------------------------------------------------------
    
    async def _get_session(self, session: Optional[AsyncSession]):
        """Get or create a session."""
        if session:
            yield session
        else:
            async with self._session_factory() as sess:
                yield sess
