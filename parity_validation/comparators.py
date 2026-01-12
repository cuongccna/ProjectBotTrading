"""
Parity Comparators.

============================================================
PURPOSE
============================================================
Compares live vs backtest data across all validation domains.

Each comparator:
1. Compares specific domain data
2. Applies tolerance rules
3. Identifies mismatches
4. Categorizes deviations

============================================================
VALIDATION DOMAINS
============================================================
1. Data Parity - OHLCV, volume, market conditions
2. Feature Parity - Calculated features
3. Decision Parity - Trade Guard, entry permission, sizing
4. Execution Parity - Orders, fills, slippage, fees
5. Accounting Parity - Post-trade balances

============================================================
"""

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    ParityDomain,
    MismatchSeverity,
    MismatchCategory,
    FailureCondition,
    ToleranceConfig,
    MarketSnapshot,
    FeatureSnapshot,
    DecisionSnapshot,
    ExecutionSnapshot,
    FieldMismatch,
    ParityComparisonResult,
)


logger = logging.getLogger(__name__)


# ============================================================
# BASE COMPARATOR
# ============================================================

class BaseComparator(ABC):
    """Abstract base class for parity comparators."""
    
    def __init__(self, tolerance_config: ToleranceConfig):
        self._tolerance = tolerance_config
    
    @property
    @abstractmethod
    def domain(self) -> ParityDomain:
        """Return the parity domain."""
        pass
    
    @abstractmethod
    def compare(
        self,
        live_snapshot: Any,
        backtest_snapshot: Any,
        cycle_id: str,
    ) -> ParityComparisonResult:
        """Compare live vs backtest snapshots."""
        pass
    
    def _create_field_mismatch(
        self,
        field_name: str,
        live_value: Any,
        backtest_value: Any,
        tolerance: Optional[Decimal] = None,
    ) -> FieldMismatch:
        """Create a field mismatch record."""
        deviation = None
        deviation_pct = None
        within_tolerance = False
        
        # Calculate deviation for numeric values
        if isinstance(live_value, (int, float, Decimal)) and isinstance(backtest_value, (int, float, Decimal)):
            live_dec = Decimal(str(live_value))
            backtest_dec = Decimal(str(backtest_value))
            deviation = abs(live_dec - backtest_dec)
            
            if live_dec != 0:
                deviation_pct = (deviation / abs(live_dec)) * 100
            elif backtest_dec != 0:
                deviation_pct = Decimal("100")  # 100% deviation from zero
            else:
                deviation_pct = Decimal("0")
            
            # Check tolerance
            if tolerance is not None:
                within_tolerance = deviation <= tolerance
        
        # String comparison
        elif isinstance(live_value, str) and isinstance(backtest_value, str):
            within_tolerance = live_value == backtest_value
        
        # Boolean comparison
        elif isinstance(live_value, bool) and isinstance(backtest_value, bool):
            within_tolerance = live_value == backtest_value
        
        return FieldMismatch(
            field_name=field_name,
            live_value=live_value,
            backtest_value=backtest_value,
            deviation=deviation,
            deviation_pct=deviation_pct,
            within_tolerance=within_tolerance,
            tolerance_used=tolerance,
        )
    
    def _generate_comparison_id(self) -> str:
        """Generate unique comparison ID."""
        return f"cmp_{uuid.uuid4().hex[:12]}"


# ============================================================
# DATA COMPARATOR
# ============================================================

class DataComparator(BaseComparator):
    """Compares data inputs between live and backtest."""
    
    @property
    def domain(self) -> ParityDomain:
        return ParityDomain.DATA
    
    def compare(
        self,
        live_snapshot: MarketSnapshot,
        backtest_snapshot: MarketSnapshot,
        cycle_id: str,
    ) -> ParityComparisonResult:
        """Compare market data snapshots."""
        mismatches: List[FieldMismatch] = []
        failure_conditions: List[FailureCondition] = []
        
        # Compare OHLCV
        if live_snapshot.ohlcv and backtest_snapshot.ohlcv:
            ohlcv_mismatches = self._compare_ohlcv(
                live_snapshot.ohlcv,
                backtest_snapshot.ohlcv,
            )
            mismatches.extend(ohlcv_mismatches)
        
        # Compare derived metrics
        metric_fields = [
            ("volume_24h", self._tolerance.size_relative_tolerance),
            ("sentiment_score", self._tolerance.feature_relative_tolerance),
            ("flow_score", self._tolerance.feature_relative_tolerance),
            ("aggregated_risk_level", self._tolerance.risk_score_tolerance),
        ]
        
        for field_name, tolerance in metric_fields:
            live_val = getattr(live_snapshot, field_name, None)
            backtest_val = getattr(backtest_snapshot, field_name, None)
            
            if live_val is not None and backtest_val is not None:
                mismatch = self._create_field_mismatch(
                    field_name, live_val, backtest_val, tolerance
                )
                if not mismatch.within_tolerance:
                    mismatches.append(mismatch)
        
        # Compare market condition
        if live_snapshot.market_condition != backtest_snapshot.market_condition:
            mismatches.append(self._create_field_mismatch(
                "market_condition",
                live_snapshot.market_condition,
                backtest_snapshot.market_condition,
            ))
        
        # Determine severity
        is_match = len([m for m in mismatches if not m.within_tolerance]) == 0
        severity = self._determine_severity(mismatches)
        
        if not is_match:
            failure_conditions.append(FailureCondition.DATA_INPUT_MISMATCH)
        
        return ParityComparisonResult(
            comparison_id=self._generate_comparison_id(),
            timestamp=datetime.utcnow(),
            domain=self.domain,
            cycle_id=cycle_id,
            is_match=is_match,
            severity=severity,
            mismatches=mismatches,
            failure_conditions=failure_conditions,
            live_snapshot=live_snapshot,
            backtest_snapshot=backtest_snapshot,
        )
    
    def _compare_ohlcv(
        self,
        live_ohlcv: Any,
        backtest_ohlcv: Any,
    ) -> List[FieldMismatch]:
        """Compare OHLCV data."""
        mismatches = []
        price_tolerance = self._tolerance.price_absolute_tolerance
        
        for field in ["open", "high", "low", "close"]:
            live_val = getattr(live_ohlcv, field, None)
            backtest_val = getattr(backtest_ohlcv, field, None)
            
            if live_val is not None and backtest_val is not None:
                mismatch = self._create_field_mismatch(
                    f"ohlcv.{field}", live_val, backtest_val, price_tolerance
                )
                if not mismatch.within_tolerance:
                    mismatches.append(mismatch)
        
        # Volume
        live_vol = getattr(live_ohlcv, "volume", None)
        backtest_vol = getattr(backtest_ohlcv, "volume", None)
        if live_vol is not None and backtest_vol is not None:
            mismatch = self._create_field_mismatch(
                "ohlcv.volume", live_vol, backtest_vol,
                self._tolerance.size_relative_tolerance
            )
            if not mismatch.within_tolerance:
                mismatches.append(mismatch)
        
        return mismatches
    
    def _determine_severity(self, mismatches: List[FieldMismatch]) -> MismatchSeverity:
        """Determine severity based on mismatches."""
        critical_fields = {"ohlcv.close", "aggregated_risk_level"}
        
        for m in mismatches:
            if not m.within_tolerance:
                if m.field_name in critical_fields:
                    return MismatchSeverity.CRITICAL
                if m.deviation_pct and m.deviation_pct > Decimal("5"):
                    return MismatchSeverity.WARNING
        
        return MismatchSeverity.INFO


# ============================================================
# FEATURE COMPARATOR
# ============================================================

class FeatureComparator(BaseComparator):
    """Compares feature calculations between live and backtest."""
    
    @property
    def domain(self) -> ParityDomain:
        return ParityDomain.FEATURE
    
    def compare(
        self,
        live_snapshot: FeatureSnapshot,
        backtest_snapshot: FeatureSnapshot,
        cycle_id: str,
    ) -> ParityComparisonResult:
        """Compare feature snapshots."""
        mismatches: List[FieldMismatch] = []
        failure_conditions: List[FailureCondition] = []
        
        # Get all feature keys
        all_keys = set(live_snapshot.features.keys()) | set(backtest_snapshot.features.keys())
        
        for key in all_keys:
            live_val = live_snapshot.features.get(key)
            backtest_val = backtest_snapshot.features.get(key)
            
            # Missing in one source
            if live_val is None or backtest_val is None:
                mismatches.append(FieldMismatch(
                    field_name=f"feature.{key}",
                    live_value=live_val,
                    backtest_value=backtest_val,
                    within_tolerance=False,
                ))
                continue
            
            # Compare values
            mismatch = self._create_field_mismatch(
                f"feature.{key}",
                live_val,
                backtest_val,
                self._tolerance.feature_relative_tolerance,
            )
            if not mismatch.within_tolerance:
                mismatches.append(mismatch)
        
        # Check version mismatch
        if live_snapshot.calculation_version != backtest_snapshot.calculation_version:
            mismatches.append(FieldMismatch(
                field_name="calculation_version",
                live_value=live_snapshot.calculation_version,
                backtest_value=backtest_snapshot.calculation_version,
                within_tolerance=False,
            ))
        
        is_match = len([m for m in mismatches if not m.within_tolerance]) == 0
        severity = self._determine_severity(mismatches)
        
        if not is_match:
            failure_conditions.append(FailureCondition.FEATURE_CALCULATION_MISMATCH)
        
        return ParityComparisonResult(
            comparison_id=self._generate_comparison_id(),
            timestamp=datetime.utcnow(),
            domain=self.domain,
            cycle_id=cycle_id,
            is_match=is_match,
            severity=severity,
            mismatches=mismatches,
            failure_conditions=failure_conditions,
            live_snapshot=live_snapshot,
            backtest_snapshot=backtest_snapshot,
        )
    
    def _determine_severity(self, mismatches: List[FieldMismatch]) -> MismatchSeverity:
        """Determine severity based on feature mismatches."""
        if not mismatches:
            return MismatchSeverity.INFO
        
        max_deviation = Decimal("0")
        for m in mismatches:
            if m.deviation_pct and m.deviation_pct > max_deviation:
                max_deviation = m.deviation_pct
        
        if max_deviation > Decimal("10"):
            return MismatchSeverity.CRITICAL
        if max_deviation > Decimal("5"):
            return MismatchSeverity.WARNING
        return MismatchSeverity.INFO


# ============================================================
# DECISION COMPARATOR
# ============================================================

class DecisionComparator(BaseComparator):
    """Compares decision states between live and backtest."""
    
    @property
    def domain(self) -> ParityDomain:
        return ParityDomain.DECISION
    
    def compare(
        self,
        live_snapshot: DecisionSnapshot,
        backtest_snapshot: DecisionSnapshot,
        cycle_id: str,
    ) -> ParityComparisonResult:
        """Compare decision snapshots."""
        mismatches: List[FieldMismatch] = []
        failure_conditions: List[FailureCondition] = []
        
        # Trade Guard decision - CRITICAL
        if live_snapshot.trade_guard_decision != backtest_snapshot.trade_guard_decision:
            mismatches.append(FieldMismatch(
                field_name="trade_guard_decision",
                live_value=live_snapshot.trade_guard_decision,
                backtest_value=backtest_snapshot.trade_guard_decision,
                within_tolerance=False,
            ))
            
            # Determine which failure condition
            if live_snapshot.trade_guard_decision == "ALLOW" and backtest_snapshot.trade_guard_decision == "BLOCK":
                failure_conditions.append(FailureCondition.TRADE_ALLOWED_LIVE_BLOCKED_BACKTEST)
            elif live_snapshot.trade_guard_decision == "BLOCK" and backtest_snapshot.trade_guard_decision == "ALLOW":
                failure_conditions.append(FailureCondition.TRADE_BLOCKED_LIVE_ALLOWED_BACKTEST)
        
        # Guard state
        if live_snapshot.guard_state != backtest_snapshot.guard_state:
            mismatches.append(FieldMismatch(
                field_name="guard_state",
                live_value=live_snapshot.guard_state,
                backtest_value=backtest_snapshot.guard_state,
                within_tolerance=False,
            ))
        
        # Entry permission
        if live_snapshot.entry_permitted != backtest_snapshot.entry_permitted:
            mismatches.append(FieldMismatch(
                field_name="entry_permitted",
                live_value=live_snapshot.entry_permitted,
                backtest_value=backtest_snapshot.entry_permitted,
                within_tolerance=False,
            ))
            failure_conditions.append(FailureCondition.ENTRY_PERMISSION_MISMATCH)
        
        # Position size
        if live_snapshot.position_size is not None and backtest_snapshot.position_size is not None:
            mismatch = self._create_field_mismatch(
                "position_size",
                live_snapshot.position_size,
                backtest_snapshot.position_size,
                self._tolerance.size_relative_tolerance,
            )
            if not mismatch.within_tolerance:
                mismatches.append(mismatch)
                failure_conditions.append(FailureCondition.POSITION_SIZE_DEVIATION)
        
        # Risk level
        if live_snapshot.risk_level is not None and backtest_snapshot.risk_level is not None:
            mismatch = self._create_field_mismatch(
                "risk_level",
                live_snapshot.risk_level,
                backtest_snapshot.risk_level,
                self._tolerance.risk_score_tolerance,
            )
            if not mismatch.within_tolerance:
                mismatches.append(mismatch)
                failure_conditions.append(FailureCondition.RISK_LEVEL_MISMATCH)
        
        # Compare reason codes (order doesn't matter)
        live_reasons = set(live_snapshot.reason_codes)
        backtest_reasons = set(backtest_snapshot.reason_codes)
        if live_reasons != backtest_reasons:
            mismatches.append(FieldMismatch(
                field_name="reason_codes",
                live_value=list(live_reasons),
                backtest_value=list(backtest_reasons),
                within_tolerance=False,
            ))
        
        is_match = len([m for m in mismatches if not m.within_tolerance]) == 0
        severity = self._determine_severity(mismatches, failure_conditions)
        
        return ParityComparisonResult(
            comparison_id=self._generate_comparison_id(),
            timestamp=datetime.utcnow(),
            domain=self.domain,
            cycle_id=cycle_id,
            is_match=is_match,
            severity=severity,
            mismatches=mismatches,
            failure_conditions=failure_conditions,
            live_snapshot=live_snapshot,
            backtest_snapshot=backtest_snapshot,
        )
    
    def _determine_severity(
        self,
        mismatches: List[FieldMismatch],
        failure_conditions: List[FailureCondition],
    ) -> MismatchSeverity:
        """Determine severity for decision mismatches."""
        # Trade guard mismatch is FATAL
        fatal_conditions = {
            FailureCondition.TRADE_ALLOWED_LIVE_BLOCKED_BACKTEST,
            FailureCondition.TRADE_BLOCKED_LIVE_ALLOWED_BACKTEST,
        }
        
        if any(fc in fatal_conditions for fc in failure_conditions):
            return MismatchSeverity.FATAL
        
        critical_conditions = {
            FailureCondition.ENTRY_PERMISSION_MISMATCH,
            FailureCondition.POSITION_SIZE_DEVIATION,
        }
        
        if any(fc in critical_conditions for fc in failure_conditions):
            return MismatchSeverity.CRITICAL
        
        if mismatches:
            return MismatchSeverity.WARNING
        
        return MismatchSeverity.INFO


# ============================================================
# EXECUTION COMPARATOR
# ============================================================

class ExecutionComparator(BaseComparator):
    """Compares execution behavior between live and backtest."""
    
    @property
    def domain(self) -> ParityDomain:
        return ParityDomain.EXECUTION
    
    def compare(
        self,
        live_snapshot: ExecutionSnapshot,
        backtest_snapshot: ExecutionSnapshot,
        cycle_id: str,
    ) -> ParityComparisonResult:
        """Compare execution snapshots."""
        mismatches: List[FieldMismatch] = []
        failure_conditions: List[FailureCondition] = []
        
        # Order type
        if live_snapshot.order_type != backtest_snapshot.order_type:
            mismatches.append(FieldMismatch(
                field_name="order_type",
                live_value=live_snapshot.order_type,
                backtest_value=backtest_snapshot.order_type,
                within_tolerance=False,
            ))
        
        # Order side
        if live_snapshot.order_side != backtest_snapshot.order_side:
            mismatches.append(FieldMismatch(
                field_name="order_side",
                live_value=live_snapshot.order_side,
                backtest_value=backtest_snapshot.order_side,
                within_tolerance=False,
            ))
        
        # Order size
        if live_snapshot.order_size is not None and backtest_snapshot.order_size is not None:
            mismatch = self._create_field_mismatch(
                "order_size",
                live_snapshot.order_size,
                backtest_snapshot.order_size,
                self._tolerance.size_relative_tolerance,
            )
            if not mismatch.within_tolerance:
                mismatches.append(mismatch)
        
        # Entry price
        if live_snapshot.entry_price is not None and backtest_snapshot.entry_price is not None:
            mismatch = self._create_field_mismatch(
                "entry_price",
                live_snapshot.entry_price,
                backtest_snapshot.entry_price,
                self._tolerance.price_absolute_tolerance,
            )
            if not mismatch.within_tolerance:
                mismatches.append(mismatch)
        
        # Slippage
        if live_snapshot.slippage is not None and backtest_snapshot.slippage is not None:
            mismatch = self._create_field_mismatch(
                "slippage",
                live_snapshot.slippage,
                backtest_snapshot.slippage,
                self._tolerance.slippage_tolerance,
            )
            if not mismatch.within_tolerance:
                mismatches.append(mismatch)
        
        # Fill ratio
        if live_snapshot.fill_ratio is not None and backtest_snapshot.fill_ratio is not None:
            mismatch = self._create_field_mismatch(
                "fill_ratio",
                live_snapshot.fill_ratio,
                backtest_snapshot.fill_ratio,
                Decimal("0.01"),  # 1% tolerance
            )
            if not mismatch.within_tolerance:
                mismatches.append(mismatch)
        
        # Fees
        if live_snapshot.fees is not None and backtest_snapshot.fees is not None:
            mismatch = self._create_field_mismatch(
                "fees",
                live_snapshot.fees,
                backtest_snapshot.fees,
                self._tolerance.price_relative_tolerance,
            )
            if not mismatch.within_tolerance:
                mismatches.append(mismatch)
        
        # Categorize mismatches
        category = self._categorize_mismatches(mismatches, live_snapshot, backtest_snapshot)
        
        is_match = len([m for m in mismatches if not m.within_tolerance]) == 0
        severity = self._determine_severity(mismatches, category)
        
        if not is_match and category == MismatchCategory.UNEXPECTED:
            failure_conditions.append(FailureCondition.UNEXPLAINED_EXECUTION_DIFFERENCE)
        
        return ParityComparisonResult(
            comparison_id=self._generate_comparison_id(),
            timestamp=datetime.utcnow(),
            domain=self.domain,
            cycle_id=cycle_id,
            is_match=is_match,
            severity=severity,
            mismatches=mismatches,
            failure_conditions=failure_conditions,
            category=category,
            explanation=self._generate_explanation(mismatches, category),
            live_snapshot=live_snapshot,
            backtest_snapshot=backtest_snapshot,
        )
    
    def _categorize_mismatches(
        self,
        mismatches: List[FieldMismatch],
        live: ExecutionSnapshot,
        backtest: ExecutionSnapshot,
    ) -> MismatchCategory:
        """Categorize execution mismatches as expected or unexpected."""
        if not mismatches:
            return MismatchCategory.EXPECTED
        
        # Expected differences due to market conditions
        expected_fields = {"slippage", "fill_ratio", "fill_time_seconds", "fees"}
        
        unexpected_mismatches = [
            m for m in mismatches
            if m.field_name not in expected_fields and not m.within_tolerance
        ]
        
        if unexpected_mismatches:
            return MismatchCategory.UNEXPECTED
        
        return MismatchCategory.EXPECTED
    
    def _determine_severity(
        self,
        mismatches: List[FieldMismatch],
        category: MismatchCategory,
    ) -> MismatchSeverity:
        """Determine severity for execution mismatches."""
        if not mismatches:
            return MismatchSeverity.INFO
        
        if category == MismatchCategory.UNEXPECTED:
            return MismatchSeverity.CRITICAL
        
        # Check deviation magnitudes
        for m in mismatches:
            if m.deviation_pct and m.deviation_pct > Decimal("10"):
                return MismatchSeverity.WARNING
        
        return MismatchSeverity.INFO
    
    def _generate_explanation(
        self,
        mismatches: List[FieldMismatch],
        category: MismatchCategory,
    ) -> str:
        """Generate explanation for execution differences."""
        if not mismatches:
            return "Execution matched perfectly"
        
        if category == MismatchCategory.EXPECTED:
            return "Differences are within expected market variation"
        
        mismatch_fields = [m.field_name for m in mismatches if not m.within_tolerance]
        return f"Unexpected differences in: {', '.join(mismatch_fields)}"


# ============================================================
# ACCOUNTING COMPARATOR
# ============================================================

class AccountingComparator(BaseComparator):
    """Compares post-trade accounting between live and backtest."""
    
    @property
    def domain(self) -> ParityDomain:
        return ParityDomain.ACCOUNTING
    
    def compare(
        self,
        live_snapshot: Dict[str, Any],
        backtest_snapshot: Dict[str, Any],
        cycle_id: str,
    ) -> ParityComparisonResult:
        """Compare accounting snapshots."""
        mismatches: List[FieldMismatch] = []
        failure_conditions: List[FailureCondition] = []
        
        # Balance comparison
        for field in ["balance", "equity", "unrealized_pnl", "realized_pnl"]:
            live_val = live_snapshot.get(field)
            backtest_val = backtest_snapshot.get(field)
            
            if live_val is not None and backtest_val is not None:
                mismatch = self._create_field_mismatch(
                    field,
                    Decimal(str(live_val)),
                    Decimal(str(backtest_val)),
                    self._tolerance.price_relative_tolerance,
                )
                if not mismatch.within_tolerance:
                    mismatches.append(mismatch)
        
        is_match = len([m for m in mismatches if not m.within_tolerance]) == 0
        severity = MismatchSeverity.CRITICAL if not is_match else MismatchSeverity.INFO
        
        return ParityComparisonResult(
            comparison_id=self._generate_comparison_id(),
            timestamp=datetime.utcnow(),
            domain=self.domain,
            cycle_id=cycle_id,
            is_match=is_match,
            severity=severity,
            mismatches=mismatches,
            failure_conditions=failure_conditions,
            live_snapshot=live_snapshot,
            backtest_snapshot=backtest_snapshot,
        )


# ============================================================
# FACTORY FUNCTION
# ============================================================

def create_comparators(
    tolerance_config: Optional[ToleranceConfig] = None,
) -> Dict[ParityDomain, BaseComparator]:
    """Create all comparators with given tolerance config."""
    config = tolerance_config or ToleranceConfig()
    
    return {
        ParityDomain.DATA: DataComparator(config),
        ParityDomain.FEATURE: FeatureComparator(config),
        ParityDomain.DECISION: DecisionComparator(config),
        ParityDomain.EXECUTION: ExecutionComparator(config),
        ParityDomain.ACCOUNTING: AccountingComparator(config),
    }
