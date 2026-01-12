"""
Product Data Packaging - Safety Layer.

============================================================
PURPOSE
============================================================
Ensure all data products are SAFE for external consumption:
1. Non-actionable validation (no trading signals)
2. Anonymization (no identifiers)
3. Signal detection and removal
4. Reverse-engineering prevention

============================================================
CRITICAL CONSTRAINTS
============================================================
Data products MUST NOT contain:
- Buy/Sell/Long/Short signals
- Directional bias
- Price targets
- Entry/exit points
- Position sizing recommendations
- Risk thresholds
- Any actionable trading information

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import logging
import re
import hashlib


from .models import (
    ProductType,
    ActionableSignalType,
    NonActionableCheck,
)
from .transformers import TransformedRecord


logger = logging.getLogger(__name__)


# ============================================================
# PROHIBITED TERMS AND PATTERNS
# ============================================================

class ProhibitedTerms:
    """
    Terms that MUST NOT appear in data products.
    
    These terms indicate actionable trading signals.
    """
    
    # Direct trading signals
    SIGNAL_TERMS: Set[str] = {
        "buy",
        "sell",
        "long",
        "short",
        "enter",
        "exit",
        "open",
        "close",
        "bullish",
        "bearish",
        "upside",
        "downside",
        "target",
        "stop_loss",
        "stop loss",
        "take_profit",
        "take profit",
        "entry_price",
        "exit_price",
        "recommended",
        "should_trade",
        "trade_signal",
        "signal_strength",
        "action_required",
    }
    
    # Directional indicators
    DIRECTIONAL_TERMS: Set[str] = {
        "going_up",
        "going_down",
        "will_rise",
        "will_fall",
        "expect_increase",
        "expect_decrease",
        "prediction",
        "forecast_direction",
    }
    
    # Position sizing terms
    POSITION_TERMS: Set[str] = {
        "position_size",
        "lot_size",
        "leverage",
        "margin",
        "allocation",
        "quantity",
        "units",
    }
    
    # Internal thresholds
    THRESHOLD_TERMS: Set[str] = {
        "threshold",
        "limit",
        "max_risk",
        "risk_limit",
        "max_loss",
        "max_position",
    }
    
    @classmethod
    def get_all_prohibited(cls) -> Set[str]:
        """Get all prohibited terms."""
        return (
            cls.SIGNAL_TERMS |
            cls.DIRECTIONAL_TERMS |
            cls.POSITION_TERMS |
            cls.THRESHOLD_TERMS
        )


# ============================================================
# NON-ACTIONABLE VALIDATOR
# ============================================================

class NonActionableValidator:
    """
    Validates that data products are non-actionable.
    
    CRITICAL: All products must pass this validation.
    """
    
    def __init__(self):
        self._prohibited_terms = ProhibitedTerms.get_all_prohibited()
        self._prohibited_patterns = self._compile_patterns()
    
    def _compile_patterns(self) -> List[re.Pattern]:
        """Compile regex patterns for detection."""
        patterns = [
            # Direct signals
            re.compile(r"\b(buy|sell|long|short)\s*(signal|now|immediately)", re.I),
            # Price targets
            re.compile(r"\b(target|price)\s*[:=]\s*\d+", re.I),
            # Percentages with direction
            re.compile(r"\b(up|down)\s*\d+\s*%", re.I),
            # Recommendations
            re.compile(r"\b(recommend|suggest)\s*(buy|sell|long|short)", re.I),
            # Entry/Exit
            re.compile(r"\b(entry|exit)\s*(point|price|level)", re.I),
            # Stop loss / Take profit
            re.compile(r"\b(stop|take)\s*(loss|profit)", re.I),
        ]
        return patterns
    
    def validate(self, data: Dict[str, Any]) -> NonActionableCheck:
        """
        Validate that data is non-actionable.
        
        Returns NonActionableCheck with validation result.
        """
        violations = []
        signal_types = []
        recommendations = []
        
        # Check field names
        for field_name in data.keys():
            field_lower = field_name.lower()
            
            # Check against prohibited terms
            for term in self._prohibited_terms:
                if term in field_lower:
                    violations.append(
                        f"Prohibited field name: '{field_name}' contains '{term}'"
                    )
                    signal_types.append(self._classify_signal_type(term))
        
        # Check field values
        self._check_values(data, violations, signal_types)
        
        # Check patterns
        self._check_patterns(data, violations, signal_types)
        
        # Generate recommendations
        if violations:
            recommendations = self._generate_recommendations(violations, signal_types)
        
        # Deduplicate signal types
        signal_types = list(set(signal_types))
        
        return NonActionableCheck(
            is_valid=len(violations) == 0,
            violations=violations,
            signal_types_found=signal_types,
            recommendations=recommendations,
        )
    
    def _check_values(
        self,
        data: Dict[str, Any],
        violations: List[str],
        signal_types: List[ActionableSignalType],
    ) -> None:
        """Check field values for prohibited content."""
        for field_name, value in data.items():
            if isinstance(value, str):
                value_lower = value.lower()
                
                for term in self._prohibited_terms:
                    if term in value_lower:
                        violations.append(
                            f"Prohibited value in '{field_name}': contains '{term}'"
                        )
                        signal_types.append(self._classify_signal_type(term))
            
            elif isinstance(value, dict):
                # Recursively check nested dicts
                nested_check = self.validate(value)
                violations.extend(nested_check.violations)
                signal_types.extend(nested_check.signal_types_found)
    
    def _check_patterns(
        self,
        data: Dict[str, Any],
        violations: List[str],
        signal_types: List[ActionableSignalType],
    ) -> None:
        """Check for prohibited patterns."""
        for field_name, value in data.items():
            if isinstance(value, str):
                for pattern in self._prohibited_patterns:
                    if pattern.search(value):
                        violations.append(
                            f"Prohibited pattern in '{field_name}': "
                            f"matches '{pattern.pattern}'"
                        )
                        signal_types.append(ActionableSignalType.DIRECTIONAL_BIAS)
    
    def _classify_signal_type(self, term: str) -> ActionableSignalType:
        """Classify a term into a signal type."""
        term_lower = term.lower()
        
        if term_lower in {"buy", "long", "enter", "open"}:
            return ActionableSignalType.BUY_SIGNAL
        elif term_lower in {"sell", "short", "exit", "close"}:
            return ActionableSignalType.SELL_SIGNAL
        elif term_lower in {"target", "price_target"}:
            return ActionableSignalType.PRICE_TARGET
        elif term_lower in {"stop_loss", "stop loss"}:
            return ActionableSignalType.STOP_LOSS
        elif term_lower in {"take_profit", "take profit"}:
            return ActionableSignalType.TAKE_PROFIT
        elif term_lower in {"entry", "entry_price"}:
            return ActionableSignalType.ENTRY_SIGNAL
        elif term_lower in {"exit", "exit_price"}:
            return ActionableSignalType.EXIT_SIGNAL
        else:
            return ActionableSignalType.DIRECTIONAL_BIAS
    
    def _generate_recommendations(
        self,
        violations: List[str],
        signal_types: List[ActionableSignalType],
    ) -> List[str]:
        """Generate recommendations for fixing violations."""
        recommendations = []
        
        if ActionableSignalType.BUY_SIGNAL in signal_types:
            recommendations.append(
                "Remove or rename fields containing buy signals"
            )
        
        if ActionableSignalType.SELL_SIGNAL in signal_types:
            recommendations.append(
                "Remove or rename fields containing sell signals"
            )
        
        if ActionableSignalType.PRICE_TARGET in signal_types:
            recommendations.append(
                "Remove price targets - use normalized scores instead"
            )
        
        if ActionableSignalType.DIRECTIONAL_BIAS in signal_types:
            recommendations.append(
                "Remove directional language - use neutral descriptions"
            )
        
        if ActionableSignalType.STOP_LOSS in signal_types or \
           ActionableSignalType.TAKE_PROFIT in signal_types:
            recommendations.append(
                "Remove risk management terms - these are internal"
            )
        
        return recommendations


# ============================================================
# DATA ANONYMIZER
# ============================================================

class DataAnonymizer:
    """
    Anonymizes data to prevent identification.
    
    CRITICAL: All identifying information must be removed.
    """
    
    # Fields that must be removed
    PROHIBITED_FIELDS: Set[str] = {
        "user_id",
        "account_id",
        "api_key",
        "secret",
        "wallet_address",
        "ip_address",
        "email",
        "name",
        "phone",
        "transaction_id",
        "order_id",
        "trade_id",
        "session_id",
    }
    
    # Patterns for sensitive data
    SENSITIVE_PATTERNS: List[Tuple[str, re.Pattern]] = [
        ("api_key", re.compile(r"[A-Za-z0-9]{32,}")),
        ("email", re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")),
        ("ip_address", re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
        ("wallet", re.compile(r"0x[a-fA-F0-9]{40}")),
        ("btc_address", re.compile(r"[13][a-km-zA-HJ-NP-Z1-9]{25,34}")),
    ]
    
    def __init__(self, salt: str = "product_packaging_salt"):
        self._salt = salt
    
    def anonymize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Anonymize data by removing or masking sensitive fields.
        
        Returns a new dictionary with anonymized data.
        """
        result = {}
        
        for key, value in data.items():
            key_lower = key.lower()
            
            # Skip prohibited fields entirely
            if key_lower in self.PROHIBITED_FIELDS:
                logger.debug(f"Removed prohibited field: {key}")
                continue
            
            # Check for sensitive patterns in key name
            if self._is_sensitive_key(key):
                logger.debug(f"Removed sensitive field: {key}")
                continue
            
            # Process value
            if isinstance(value, dict):
                result[key] = self.anonymize(value)
            elif isinstance(value, list):
                result[key] = [
                    self.anonymize(v) if isinstance(v, dict) else self._clean_value(v)
                    for v in value
                ]
            elif isinstance(value, str):
                result[key] = self._clean_value(value)
            else:
                result[key] = value
        
        return result
    
    def _is_sensitive_key(self, key: str) -> bool:
        """Check if a key name indicates sensitive data."""
        key_lower = key.lower()
        sensitive_keywords = {
            "secret",
            "password",
            "token",
            "credential",
            "private",
            "key",
        }
        return any(kw in key_lower for kw in sensitive_keywords)
    
    def _clean_value(self, value: Any) -> Any:
        """Clean a value by detecting and masking sensitive content."""
        if not isinstance(value, str):
            return value
        
        cleaned = value
        
        for pattern_name, pattern in self.SENSITIVE_PATTERNS:
            if pattern.search(cleaned):
                cleaned = pattern.sub(f"[REDACTED_{pattern_name.upper()}]", cleaned)
        
        return cleaned
    
    def hash_identifier(self, identifier: str) -> str:
        """Create a consistent hash for an identifier."""
        content = f"{self._salt}_{identifier}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# ============================================================
# REVERSE ENGINEERING PREVENTION
# ============================================================

class ReverseEngineeringPrevention:
    """
    Prevents reverse engineering of trading system from data products.
    
    CRITICAL: Data products must not reveal internal logic.
    """
    
    # Precision limits for different field types
    PRECISION_LIMITS: Dict[str, int] = {
        "score": 2,  # 0.00 - 1.00
        "ratio": 2,
        "intensity": 2,
        "probability": 2,
        "confidence": 2,
        "latency": 0,  # Integer milliseconds
        "count": 0,  # Integer
    }
    
    # Fields that should be binned instead of exact values
    BINNED_FIELDS: Set[str] = {
        "exchange_count",
        "source_count",
    }
    
    def __init__(self):
        self._min_aggregation = 3  # Minimum records per output
    
    def obscure_precision(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Reduce precision of numeric values."""
        result = {}
        
        for key, value in data.items():
            if isinstance(value, float):
                precision = self._get_precision(key)
                result[key] = round(value, precision)
            elif isinstance(value, dict):
                result[key] = self.obscure_precision(value)
            else:
                result[key] = value
        
        return result
    
    def _get_precision(self, field_name: str) -> int:
        """Get precision limit for a field."""
        field_lower = field_name.lower()
        
        for key, precision in self.PRECISION_LIMITS.items():
            if key in field_lower:
                return precision
        
        return 2  # Default precision
    
    def apply_minimum_aggregation(
        self,
        records: List[TransformedRecord],
    ) -> List[TransformedRecord]:
        """
        Filter out records that don't meet minimum aggregation.
        
        This prevents exposure of individual data points.
        """
        return [
            r for r in records
            if r.record_count >= self._min_aggregation
        ]
    
    def bin_count_field(self, count: int, bin_size: int = 5) -> str:
        """Bin a count field to prevent exact value exposure."""
        if count < bin_size:
            return f"<{bin_size}"
        elif count < bin_size * 2:
            return f"{bin_size}-{bin_size * 2 - 1}"
        elif count < bin_size * 4:
            return f"{bin_size * 2}-{bin_size * 4 - 1}"
        else:
            return f"{bin_size * 4}+"
    
    def validate_no_system_exposure(
        self,
        data: Dict[str, Any],
    ) -> Tuple[bool, List[str]]:
        """Validate that data doesn't expose system internals."""
        issues = []
        
        # Check for internal-sounding field names
        internal_patterns = {
            "internal",
            "config",
            "threshold",
            "parameter",
            "setting",
            "weight",
            "model",
        }
        
        for key in data.keys():
            key_lower = key.lower()
            for pattern in internal_patterns:
                if pattern in key_lower:
                    issues.append(
                        f"Field '{key}' may expose internal system details"
                    )
        
        return len(issues) == 0, issues


# ============================================================
# SAFETY CHECKER
# ============================================================

@dataclass
class SafetyCheckResult:
    """Result of a complete safety check."""
    is_safe: bool
    non_actionable_check: NonActionableCheck
    anonymization_applied: bool
    precision_obscured: bool
    min_aggregation_met: bool
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.utcnow)


class SafetyChecker:
    """
    Complete safety checker for data products.
    
    Combines all safety validations into one interface.
    """
    
    def __init__(self):
        self._non_actionable = NonActionableValidator()
        self._anonymizer = DataAnonymizer()
        self._anti_reverse = ReverseEngineeringPrevention()
    
    def check_and_sanitize(
        self,
        records: List[TransformedRecord],
    ) -> Tuple[List[TransformedRecord], SafetyCheckResult]:
        """
        Check and sanitize records for safety.
        
        Returns sanitized records and safety check result.
        """
        issues = []
        recommendations = []
        
        # Step 1: Apply minimum aggregation filter
        filtered_records = self._anti_reverse.apply_minimum_aggregation(records)
        min_aggregation_met = len(filtered_records) == len(records)
        
        if not min_aggregation_met:
            removed = len(records) - len(filtered_records)
            issues.append(
                f"Removed {removed} records due to minimum aggregation requirement"
            )
        
        # Step 2: Sanitize each record
        sanitized_records = []
        all_actionable_checks = []
        
        for record in filtered_records:
            # Check non-actionable
            na_check = self._non_actionable.validate(record.data)
            all_actionable_checks.append(na_check)
            
            if not na_check.is_valid:
                issues.extend(na_check.violations)
                recommendations.extend(na_check.recommendations)
                # Still sanitize but mark the issue
            
            # Anonymize
            anonymized_data = self._anonymizer.anonymize(record.data)
            
            # Obscure precision
            obscured_data = self._anti_reverse.obscure_precision(anonymized_data)
            
            # Check for system exposure
            no_exposure, exposure_issues = \
                self._anti_reverse.validate_no_system_exposure(obscured_data)
            
            if not no_exposure:
                issues.extend(exposure_issues)
            
            # Create sanitized record
            sanitized_record = TransformedRecord(
                record_id=record.record_id,
                product_type=record.product_type,
                timestamp_bucket=record.timestamp_bucket,
                time_bucket_size=record.time_bucket_size,
                data=obscured_data,
                record_count=record.record_count,
                aggregation_method=record.aggregation_method,
                completeness=record.completeness,
                metadata=record.metadata,
            )
            sanitized_records.append(sanitized_record)
        
        # Aggregate non-actionable check
        all_valid = all(c.is_valid for c in all_actionable_checks)
        all_signal_types = []
        for check in all_actionable_checks:
            all_signal_types.extend(check.signal_types_found)
        
        combined_na_check = NonActionableCheck(
            is_valid=all_valid,
            violations=issues,
            signal_types_found=list(set(all_signal_types)),
            recommendations=recommendations,
        )
        
        # Build result
        result = SafetyCheckResult(
            is_safe=all_valid and len(issues) == 0,
            non_actionable_check=combined_na_check,
            anonymization_applied=True,
            precision_obscured=True,
            min_aggregation_met=min_aggregation_met,
            issues=issues,
            recommendations=recommendations,
        )
        
        return sanitized_records, result
    
    def validate_only(self, data: Dict[str, Any]) -> SafetyCheckResult:
        """Validate data without modifying it."""
        na_check = self._non_actionable.validate(data)
        no_exposure, exposure_issues = \
            self._anti_reverse.validate_no_system_exposure(data)
        
        issues = list(na_check.violations) + exposure_issues
        
        return SafetyCheckResult(
            is_safe=na_check.is_valid and no_exposure,
            non_actionable_check=na_check,
            anonymization_applied=False,
            precision_obscured=False,
            min_aggregation_met=True,
            issues=issues,
            recommendations=na_check.recommendations,
        )


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_non_actionable_validator() -> NonActionableValidator:
    """Create a non-actionable validator."""
    return NonActionableValidator()


def create_anonymizer(salt: str = None) -> DataAnonymizer:
    """Create a data anonymizer."""
    return DataAnonymizer(salt=salt or "product_packaging_salt")


def create_safety_checker() -> SafetyChecker:
    """Create a complete safety checker."""
    return SafetyChecker()


def create_reverse_engineering_prevention() -> ReverseEngineeringPrevention:
    """Create a reverse engineering prevention instance."""
    return ReverseEngineeringPrevention()
