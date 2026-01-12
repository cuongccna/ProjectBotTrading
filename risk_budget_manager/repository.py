"""
Risk Budget Manager - Repository.

============================================================
PURPOSE
============================================================
Repository pattern implementation for risk budget persistence.

Provides clean interface for:
- Saving risk evaluations
- Tracking position risk
- Recording daily usage
- Storing alerts and halts

============================================================
"""

from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, desc, and_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    RiskEvaluationRecord,
    PositionRiskRecord,
    DailyRiskRecord,
    DrawdownRecord,
    RiskAlertRecord,
    TradingHaltRecord,
    EquitySnapshotRecord,
)
from .types import (
    TradeRiskRequest,
    TradeRiskResponse,
    OpenPositionRisk,
    DailyRiskUsage,
    RiskBudgetSnapshot,
    AlertSeverity,
)


class RiskBudgetRepository:
    """
    Repository for risk budget persistence operations.
    
    ============================================================
    METHODS
    ============================================================
    - save_evaluation: Persist evaluation decision
    - save_position_risk: Track position risk
    - save_daily_usage: Record daily statistics
    - save_alert: Store alert for audit
    
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
    # EVALUATION RECORDS
    # --------------------------------------------------------
    
    async def save_evaluation(
        self,
        request: TradeRiskRequest,
        response: TradeRiskResponse,
    ) -> RiskEvaluationRecord:
        """
        Save a risk evaluation record.
        
        Args:
            request: The original request
            response: The evaluation response
        
        Returns:
            Created RiskEvaluationRecord
        """
        record = RiskEvaluationRecord(
            request_id=request.request_id,
            symbol=request.symbol,
            exchange=request.exchange,
            direction=request.direction,
            entry_price=request.entry_price,
            stop_loss_price=request.stop_loss_price,
            position_size=request.position_size,
            proposed_risk_pct=response.original_risk_pct,
            proposed_risk_amount=request.calculate_risk_amount(),
            decision=response.decision.value,
            reason=response.primary_reason.value if response.primary_reason else None,
            allowed_risk_pct=response.allowed_risk_pct,
            allowed_position_size=response.allowed_position_size,
            size_reduction_pct=response.size_reduction_pct,
            account_equity=response.account_equity,
            daily_limit_pct=self._get_daily_limit_from_checks(response),
            daily_used_pct=response.daily_risk_used,
            daily_remaining_pct=self._get_daily_remaining_from_checks(response),
            open_limit_pct=self._get_open_limit_from_checks(response),
            open_used_pct=response.open_risk_used,
            open_remaining_pct=self._get_open_remaining_from_checks(response),
            current_drawdown_pct=response.current_drawdown,
            strategy_id=request.strategy_id,
            intent_id=request.intent_id,
            budget_checks_json=[check.to_dict() for check in response.budget_checks],
            evaluation_timestamp=response.timestamp,
            evaluation_duration_ms=response.evaluation_duration_ms,
        )
        
        self._session.add(record)
        await self._session.flush()
        
        return record
    
    def _get_daily_limit_from_checks(self, response: TradeRiskResponse) -> float:
        """Extract daily limit from budget checks."""
        for check in response.budget_checks:
            if check.dimension.value == "DAILY_CUMULATIVE":
                return check.budget_limit
        return 0.0
    
    def _get_daily_remaining_from_checks(self, response: TradeRiskResponse) -> float:
        """Extract daily remaining from budget checks."""
        for check in response.budget_checks:
            if check.dimension.value == "DAILY_CUMULATIVE":
                return check.budget_remaining
        return 0.0
    
    def _get_open_limit_from_checks(self, response: TradeRiskResponse) -> float:
        """Extract open position limit from budget checks."""
        for check in response.budget_checks:
            if check.dimension.value == "OPEN_POSITION":
                return check.budget_limit
        return 0.0
    
    def _get_open_remaining_from_checks(self, response: TradeRiskResponse) -> float:
        """Extract open remaining from budget checks."""
        for check in response.budget_checks:
            if check.dimension.value == "OPEN_POSITION":
                return check.budget_remaining
        return 0.0
    
    async def get_evaluations_by_symbol(
        self,
        symbol: str,
        limit: int = 100,
    ) -> List[RiskEvaluationRecord]:
        """Get evaluations for a symbol."""
        stmt = (
            select(RiskEvaluationRecord)
            .where(RiskEvaluationRecord.symbol == symbol)
            .order_by(desc(RiskEvaluationRecord.evaluation_timestamp))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_evaluations_in_range(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        decision: Optional[str] = None,
        limit: int = 1000,
    ) -> List[RiskEvaluationRecord]:
        """Get evaluations in a time range."""
        end_time = end_time or datetime.utcnow()
        
        conditions = [
            RiskEvaluationRecord.evaluation_timestamp >= start_time,
            RiskEvaluationRecord.evaluation_timestamp <= end_time,
        ]
        
        if decision:
            conditions.append(RiskEvaluationRecord.decision == decision)
        
        stmt = (
            select(RiskEvaluationRecord)
            .where(and_(*conditions))
            .order_by(desc(RiskEvaluationRecord.evaluation_timestamp))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    # --------------------------------------------------------
    # POSITION RISK RECORDS
    # --------------------------------------------------------
    
    async def save_position_risk(
        self,
        position: OpenPositionRisk,
    ) -> PositionRiskRecord:
        """
        Save position risk record.
        
        Args:
            position: Position risk data
        
        Returns:
            Created PositionRiskRecord
        """
        record = PositionRiskRecord(
            position_id=position.position_id,
            symbol=position.symbol,
            exchange=position.exchange,
            direction=position.direction,
            entry_price=position.entry_price,
            initial_stop_loss=position.stop_loss_price,
            current_stop_loss=position.stop_loss_price,
            initial_size=position.position_size,
            current_size=position.position_size,
            initial_risk_pct=position.risk_percentage,
            initial_risk_amount=position.risk_amount,
            current_risk_pct=position.risk_percentage,
            current_risk_amount=position.risk_amount,
            equity_at_entry=position.equity_at_entry,
            status=position.status.value,
            opened_at=position.opened_at,
            stop_loss_history=[],
        )
        
        self._session.add(record)
        await self._session.flush()
        
        return record
    
    async def update_position_risk(
        self,
        position_id: str,
        current_stop_loss: Optional[float] = None,
        current_size: Optional[float] = None,
        current_risk_pct: Optional[float] = None,
        current_risk_amount: Optional[float] = None,
        status: Optional[str] = None,
        closed_at: Optional[datetime] = None,
        realized_pnl: Optional[float] = None,
        exit_price: Optional[float] = None,
    ) -> None:
        """Update position risk record."""
        values = {}
        
        if current_stop_loss is not None:
            values["current_stop_loss"] = current_stop_loss
        if current_size is not None:
            values["current_size"] = current_size
        if current_risk_pct is not None:
            values["current_risk_pct"] = current_risk_pct
        if current_risk_amount is not None:
            values["current_risk_amount"] = current_risk_amount
        if status is not None:
            values["status"] = status
        if closed_at is not None:
            values["closed_at"] = closed_at
        if realized_pnl is not None:
            values["realized_pnl"] = realized_pnl
        if exit_price is not None:
            values["exit_price"] = exit_price
        
        if values:
            stmt = (
                update(PositionRiskRecord)
                .where(PositionRiskRecord.position_id == position_id)
                .values(**values)
            )
            await self._session.execute(stmt)
            await self._session.flush()
    
    async def get_open_positions(self) -> List[PositionRiskRecord]:
        """Get all open position records."""
        stmt = (
            select(PositionRiskRecord)
            .where(PositionRiskRecord.status == "OPEN")
            .order_by(desc(PositionRiskRecord.opened_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_position_by_id(
        self,
        position_id: str,
    ) -> Optional[PositionRiskRecord]:
        """Get position by ID."""
        stmt = select(PositionRiskRecord).where(
            PositionRiskRecord.position_id == position_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    
    # --------------------------------------------------------
    # DAILY RISK RECORDS
    # --------------------------------------------------------
    
    async def save_daily_usage(
        self,
        usage: DailyRiskUsage,
    ) -> DailyRiskRecord:
        """
        Save daily risk usage record.
        
        Args:
            usage: Daily usage data
        
        Returns:
            Created or updated DailyRiskRecord
        """
        # Check if record exists for this date
        existing = await self.get_daily_record(usage.date)
        
        if existing:
            # Update existing
            existing.risk_consumed = usage.risk_consumed
            existing.peak_open_risk = usage.peak_open_risk
            existing.trades_evaluated = usage.trades_taken + usage.trades_rejected
            existing.trades_rejected = usage.trades_rejected
            existing.realized_pnl = usage.realized_pnl
            existing.updated_at = datetime.utcnow()
            
            await self._session.flush()
            return existing
        
        # Create new
        record = DailyRiskRecord(
            date=usage.date,
            risk_budget_limit=usage.risk_budget_limit,
            risk_consumed=usage.risk_consumed,
            peak_open_risk=usage.peak_open_risk,
            trades_evaluated=usage.trades_taken + usage.trades_rejected,
            trades_allowed=usage.trades_taken,
            trades_rejected=usage.trades_rejected,
            realized_pnl=usage.realized_pnl,
        )
        
        self._session.add(record)
        await self._session.flush()
        
        return record
    
    async def get_daily_record(
        self,
        date_str: str,
    ) -> Optional[DailyRiskRecord]:
        """Get daily record for a date."""
        stmt = select(DailyRiskRecord).where(DailyRiskRecord.date == date_str)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_daily_records_range(
        self,
        start_date: str,
        end_date: str,
    ) -> List[DailyRiskRecord]:
        """Get daily records in a date range."""
        stmt = (
            select(DailyRiskRecord)
            .where(
                and_(
                    DailyRiskRecord.date >= start_date,
                    DailyRiskRecord.date <= end_date,
                )
            )
            .order_by(desc(DailyRiskRecord.date))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    # --------------------------------------------------------
    # DRAWDOWN RECORDS
    # --------------------------------------------------------
    
    async def save_drawdown_snapshot(
        self,
        peak_equity: float,
        trough_equity: float,
        current_equity: float,
        drawdown_pct: float,
        is_new_peak: bool = False,
        is_new_trough: bool = False,
        triggered_halt: bool = False,
    ) -> DrawdownRecord:
        """Save drawdown snapshot."""
        record = DrawdownRecord(
            peak_equity=peak_equity,
            trough_equity=trough_equity,
            current_equity=current_equity,
            drawdown_pct=drawdown_pct,
            drawdown_amount=peak_equity - current_equity,
            is_recovering=current_equity > trough_equity,
            recovery_pct=((current_equity - trough_equity) / (peak_equity - trough_equity) * 100)
                if peak_equity > trough_equity else 0,
            is_new_peak=is_new_peak,
            is_new_trough=is_new_trough,
            triggered_halt=triggered_halt,
        )
        
        self._session.add(record)
        await self._session.flush()
        
        return record
    
    async def get_latest_drawdown(self) -> Optional[DrawdownRecord]:
        """Get latest drawdown record."""
        stmt = (
            select(DrawdownRecord)
            .order_by(desc(DrawdownRecord.timestamp))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_max_drawdown_in_range(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """Get maximum drawdown in a time range."""
        end_time = end_time or datetime.utcnow()
        
        stmt = (
            select(func.max(DrawdownRecord.drawdown_pct))
            .where(
                and_(
                    DrawdownRecord.timestamp >= start_time,
                    DrawdownRecord.timestamp <= end_time,
                )
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar()
    
    # --------------------------------------------------------
    # ALERT RECORDS
    # --------------------------------------------------------
    
    async def save_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        alert_type: Optional[str] = None,
        related_symbol: Optional[str] = None,
        related_position_id: Optional[str] = None,
        account_equity: Optional[float] = None,
        daily_risk_used: Optional[float] = None,
        current_drawdown: Optional[float] = None,
        telegram_sent: bool = False,
        telegram_message_id: Optional[str] = None,
    ) -> RiskAlertRecord:
        """Save alert record."""
        record = RiskAlertRecord(
            severity=severity.value,
            title=title,
            message=message,
            alert_type=alert_type,
            related_symbol=related_symbol,
            related_position_id=related_position_id,
            account_equity=account_equity,
            daily_risk_used=daily_risk_used,
            current_drawdown=current_drawdown,
            telegram_sent=telegram_sent,
            telegram_message_id=telegram_message_id,
        )
        
        self._session.add(record)
        await self._session.flush()
        
        return record
    
    async def get_recent_alerts(
        self,
        hours: int = 24,
        severity: Optional[str] = None,
    ) -> List[RiskAlertRecord]:
        """Get recent alerts."""
        since = datetime.utcnow() - timedelta(hours=hours)
        
        conditions = [RiskAlertRecord.timestamp >= since]
        if severity:
            conditions.append(RiskAlertRecord.severity == severity)
        
        stmt = (
            select(RiskAlertRecord)
            .where(and_(*conditions))
            .order_by(desc(RiskAlertRecord.timestamp))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    # --------------------------------------------------------
    # TRADING HALT RECORDS
    # --------------------------------------------------------
    
    async def save_halt(
        self,
        reason: str,
        description: Optional[str],
        equity_at_halt: float,
        drawdown_at_halt: float,
        daily_risk_at_halt: Optional[float] = None,
        open_positions_at_halt: Optional[int] = None,
    ) -> TradingHaltRecord:
        """Save trading halt record."""
        record = TradingHaltRecord(
            reason=reason,
            description=description,
            equity_at_halt=equity_at_halt,
            drawdown_at_halt=drawdown_at_halt,
            daily_risk_at_halt=daily_risk_at_halt,
            open_positions_at_halt=open_positions_at_halt,
        )
        
        self._session.add(record)
        await self._session.flush()
        
        return record
    
    async def update_halt_resumed(
        self,
        halt_id: UUID,
        resumed_by: str,
        resume_reason: Optional[str] = None,
    ) -> None:
        """Update halt record with resume info."""
        stmt = (
            update(TradingHaltRecord)
            .where(TradingHaltRecord.id == halt_id)
            .values(
                resumed_at=datetime.utcnow(),
                resumed_by=resumed_by,
                resume_reason=resume_reason,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
    
    async def get_active_halt(self) -> Optional[TradingHaltRecord]:
        """Get current active halt (not resumed)."""
        stmt = (
            select(TradingHaltRecord)
            .where(TradingHaltRecord.resumed_at.is_(None))
            .order_by(desc(TradingHaltRecord.halted_at))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    
    # --------------------------------------------------------
    # EQUITY SNAPSHOTS
    # --------------------------------------------------------
    
    async def save_equity_snapshot(
        self,
        snapshot: RiskBudgetSnapshot,
        exchange: str = "binance",
    ) -> EquitySnapshotRecord:
        """Save equity snapshot."""
        record = EquitySnapshotRecord(
            account_equity=snapshot.account_equity,
            available_balance=snapshot.account_equity,  # Simplified
            unrealized_pnl=0.0,  # Would come from exchange
            peak_equity=snapshot.peak_equity,
            drawdown_from_peak=snapshot.current_drawdown_pct,
            open_positions=snapshot.open_positions,
            open_risk_pct=snapshot.open_used_pct,
            daily_risk_used_pct=snapshot.daily_used_pct,
            exchange=exchange,
        )
        
        self._session.add(record)
        await self._session.flush()
        
        return record
    
    async def get_equity_history(
        self,
        hours: int = 24,
        exchange: Optional[str] = None,
    ) -> List[EquitySnapshotRecord]:
        """Get equity history."""
        since = datetime.utcnow() - timedelta(hours=hours)
        
        conditions = [EquitySnapshotRecord.timestamp >= since]
        if exchange:
            conditions.append(EquitySnapshotRecord.exchange == exchange)
        
        stmt = (
            select(EquitySnapshotRecord)
            .where(and_(*conditions))
            .order_by(EquitySnapshotRecord.timestamp)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_peak_equity(
        self,
        exchange: Optional[str] = None,
    ) -> Optional[float]:
        """Get historical peak equity."""
        conditions = []
        if exchange:
            conditions.append(EquitySnapshotRecord.exchange == exchange)
        
        stmt = select(func.max(EquitySnapshotRecord.peak_equity))
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        result = await self._session.execute(stmt)
        return result.scalar()
    
    # --------------------------------------------------------
    # ANALYTICS
    # --------------------------------------------------------
    
    async def get_decision_distribution(
        self,
        hours: int = 24,
    ) -> Dict[str, int]:
        """Get distribution of decisions."""
        since = datetime.utcnow() - timedelta(hours=hours)
        
        stmt = (
            select(
                RiskEvaluationRecord.decision,
                func.count(RiskEvaluationRecord.id),
            )
            .where(RiskEvaluationRecord.evaluation_timestamp >= since)
            .group_by(RiskEvaluationRecord.decision)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
    
    async def get_rejection_reasons(
        self,
        hours: int = 24,
    ) -> Dict[str, int]:
        """Get distribution of rejection reasons."""
        since = datetime.utcnow() - timedelta(hours=hours)
        
        stmt = (
            select(
                RiskEvaluationRecord.reason,
                func.count(RiskEvaluationRecord.id),
            )
            .where(
                and_(
                    RiskEvaluationRecord.evaluation_timestamp >= since,
                    RiskEvaluationRecord.reason.isnot(None),
                )
            )
            .group_by(RiskEvaluationRecord.reason)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
