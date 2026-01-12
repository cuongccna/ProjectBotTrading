"""
Data Anonymization for Monetization Preparation.

============================================================
PURPOSE
============================================================
Prepares data for future monetization by anonymizing and
aggregating without enabling sales.

Requirements:
- No user-identifiable information
- No exchange API keys
- No account balances
- No execution secrets

Data must be anonymized and aggregated before external use.

============================================================
"""

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set

from .models import (
    DataCategory,
    DataSubCategory,
    DataSensitivity,
    MonetizationStatus,
    MonetizationMetadata,
    DataProductType,
    DataProductDefinition,
)


logger = logging.getLogger(__name__)


# ============================================================
# SENSITIVE FIELD PATTERNS
# ============================================================

# Fields that MUST be removed or anonymized
PROHIBITED_FIELDS = {
    # API credentials
    "api_key", "api_secret", "secret_key", "private_key", "passphrase",
    "access_token", "refresh_token", "bearer_token", "auth_token",
    # Account identifiers
    "account_id", "user_id", "client_id", "wallet_address", "address",
    "email", "phone", "name", "username",
    # Financial secrets
    "balance", "equity", "margin", "available_balance", "total_balance",
    "unrealized_pnl", "realized_pnl", "portfolio_value",
    # Execution secrets
    "client_order_id", "internal_order_id", "execution_id",
    # IP and location
    "ip_address", "ip", "location", "country", "city",
}

# Patterns for sensitive data detection
SENSITIVE_PATTERNS = [
    (r"[a-zA-Z0-9]{32,}", "api_key_like"),  # Long alphanumeric strings
    (r"0x[a-fA-F0-9]{40}", "eth_address"),  # Ethereum addresses
    (r"[13][a-km-zA-HJ-NP-Z1-9]{25,34}", "btc_address"),  # Bitcoin addresses
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "email"),
    (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "ip_address"),
]


# ============================================================
# ANONYMIZER
# ============================================================

class DataAnonymizer:
    """
    Anonymizes data for safe external use.
    
    Removes or masks all sensitive information.
    """
    
    def __init__(
        self,
        salt: Optional[str] = None,
        additional_prohibited: Optional[Set[str]] = None,
    ):
        self._salt = salt or uuid.uuid4().hex
        self._prohibited_fields = PROHIBITED_FIELDS.copy()
        if additional_prohibited:
            self._prohibited_fields.update(additional_prohibited)
        self._compiled_patterns = [
            (re.compile(pattern), name)
            for pattern, name in SENSITIVE_PATTERNS
        ]
    
    def anonymize(
        self,
        data: Dict[str, Any],
        category: DataCategory,
    ) -> Dict[str, Any]:
        """
        Anonymize a data dictionary.
        
        Returns a new dictionary with sensitive data removed/masked.
        """
        result = {}
        
        for key, value in data.items():
            # Check if field is prohibited
            if self._is_prohibited_field(key):
                logger.debug(f"Removed prohibited field: {key}")
                continue
            
            # Recursively handle nested dicts
            if isinstance(value, dict):
                result[key] = self.anonymize(value, category)
            elif isinstance(value, list):
                result[key] = [
                    self.anonymize(v, category) if isinstance(v, dict) else self._anonymize_value(v)
                    for v in value
                ]
            else:
                result[key] = self._anonymize_value(value)
        
        return result
    
    def _is_prohibited_field(self, field_name: str) -> bool:
        """Check if field name is prohibited."""
        normalized = field_name.lower().replace("-", "_")
        return normalized in self._prohibited_fields
    
    def _anonymize_value(self, value: Any) -> Any:
        """Anonymize a single value."""
        if value is None:
            return None
        
        if isinstance(value, str):
            return self._anonymize_string(value)
        
        return value
    
    def _anonymize_string(self, value: str) -> str:
        """Anonymize a string value."""
        # Check for sensitive patterns
        for pattern, pattern_name in self._compiled_patterns:
            if pattern.search(value):
                logger.debug(f"Masked sensitive pattern: {pattern_name}")
                return f"[REDACTED:{pattern_name}]"
        
        return value
    
    def hash_identifier(self, identifier: str) -> str:
        """
        Hash an identifier for anonymization.
        
        Produces consistent hash for same input (with salt).
        """
        combined = f"{self._salt}:{identifier}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def validate_anonymized(self, data: Dict[str, Any]) -> List[str]:
        """
        Validate that data is properly anonymized.
        
        Returns list of issues found.
        """
        issues = []
        
        def check_dict(d: Dict[str, Any], path: str = "") -> None:
            for key, value in d.items():
                full_path = f"{path}.{key}" if path else key
                
                if self._is_prohibited_field(key):
                    issues.append(f"Prohibited field found: {full_path}")
                
                if isinstance(value, dict):
                    check_dict(value, full_path)
                elif isinstance(value, str):
                    for pattern, pattern_name in self._compiled_patterns:
                        if pattern.search(value):
                            issues.append(
                                f"Sensitive pattern ({pattern_name}) in {full_path}"
                            )
        
        check_dict(data)
        return issues


# ============================================================
# AGGREGATOR
# ============================================================

class DataAggregator:
    """
    Aggregates data for anonymized products.
    """
    
    def aggregate_sentiment(
        self,
        scores: List[Decimal],
        aggregation: str = "mean",
    ) -> Decimal:
        """Aggregate sentiment scores."""
        if not scores:
            return Decimal("0")
        
        if aggregation == "mean":
            return sum(scores) / len(scores)
        elif aggregation == "median":
            sorted_scores = sorted(scores)
            mid = len(sorted_scores) // 2
            if len(sorted_scores) % 2 == 0:
                return (sorted_scores[mid - 1] + sorted_scores[mid]) / 2
            return sorted_scores[mid]
        elif aggregation == "max":
            return max(scores)
        elif aggregation == "min":
            return min(scores)
        else:
            return sum(scores) / len(scores)
    
    def aggregate_risk_levels(
        self,
        risk_states: List[str],
    ) -> Dict[str, Any]:
        """Aggregate risk level distribution."""
        distribution = {}
        for state in risk_states:
            distribution[state] = distribution.get(state, 0) + 1
        
        total = len(risk_states)
        return {
            "distribution": distribution,
            "percentages": {
                k: round(v / total * 100, 2) for k, v in distribution.items()
            },
            "total_observations": total,
        }
    
    def aggregate_market_conditions(
        self,
        conditions: List[Dict[str, Any]],
        time_bucket: str = "1h",
    ) -> Dict[str, Any]:
        """Aggregate market condition data."""
        if not conditions:
            return {}
        
        # Group by time bucket
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        
        for cond in conditions:
            ts = cond.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            
            if time_bucket == "1h":
                bucket_key = ts.strftime("%Y-%m-%d-%H") if ts else "unknown"
            elif time_bucket == "1d":
                bucket_key = ts.strftime("%Y-%m-%d") if ts else "unknown"
            else:
                bucket_key = ts.strftime("%Y-%m-%d-%H") if ts else "unknown"
            
            if bucket_key not in buckets:
                buckets[bucket_key] = []
            buckets[bucket_key].append(cond)
        
        return {
            "time_bucket": time_bucket,
            "bucket_count": len(buckets),
            "total_observations": len(conditions),
        }
    
    def create_time_series(
        self,
        data_points: List[Dict[str, Any]],
        value_field: str,
        timestamp_field: str = "timestamp",
        aggregation: str = "mean",
    ) -> List[Dict[str, Any]]:
        """Create aggregated time series."""
        # Group by day
        daily_values: Dict[str, List[Decimal]] = {}
        
        for point in data_points:
            ts = point.get(timestamp_field)
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            
            day_key = ts.strftime("%Y-%m-%d") if ts else "unknown"
            value = point.get(value_field)
            
            if value is not None:
                if day_key not in daily_values:
                    daily_values[day_key] = []
                daily_values[day_key].append(Decimal(str(value)))
        
        # Aggregate each day
        series = []
        for day, values in sorted(daily_values.items()):
            agg_value = self.aggregate_sentiment(values, aggregation)
            series.append({
                "date": day,
                "value": float(agg_value),
                "count": len(values),
            })
        
        return series


# ============================================================
# MONETIZATION PREPARER
# ============================================================

class MonetizationPreparer:
    """
    Prepares data for future monetization.
    
    NOTE: This does NOT sell data. It only prepares data to be
    monetization-ready when/if that decision is made.
    """
    
    def __init__(
        self,
        anonymizer: Optional[DataAnonymizer] = None,
        aggregator: Optional[DataAggregator] = None,
    ):
        self._anonymizer = anonymizer or DataAnonymizer()
        self._aggregator = aggregator or DataAggregator()
        self._product_definitions: Dict[str, DataProductDefinition] = {}
    
    def register_product_definition(
        self,
        definition: DataProductDefinition,
    ) -> None:
        """Register a potential data product definition."""
        self._product_definitions[definition.product_id] = definition
        logger.info(f"Registered product definition: {definition.product_id}")
    
    def prepare_for_monetization(
        self,
        data: Dict[str, Any],
        category: DataCategory,
        original_record_id: str,
    ) -> tuple:
        """
        Prepare data for monetization.
        
        Returns (anonymized_data, metadata).
        """
        # Step 1: Anonymize
        anonymized = self._anonymizer.anonymize(data, category)
        
        # Step 2: Validate
        issues = self._anonymizer.validate_anonymized(anonymized)
        if issues:
            logger.warning(f"Anonymization issues: {issues}")
            return None, None
        
        # Step 3: Create metadata
        metadata = MonetizationMetadata(
            record_id=f"mon_{uuid.uuid4().hex}",
            original_record_id=original_record_id,
            status=MonetizationStatus.ANONYMIZED,
            anonymization_applied=True,
            pii_removed=True,
            secrets_removed=True,
        )
        
        return anonymized, metadata
    
    def can_monetize(self, category: DataCategory) -> bool:
        """Check if a category can be monetized."""
        # Decision logs and execution records cannot be monetized
        non_monetizable = {
            DataCategory.DECISION_LOGS,
            DataCategory.EXECUTION_RECORDS,
        }
        return category not in non_monetizable
    
    def get_product_schema(
        self,
        product_type: DataProductType,
    ) -> Dict[str, Any]:
        """Get schema for a data product type."""
        schemas = {
            DataProductType.SENTIMENT_INDEX: {
                "fields": ["timestamp", "symbol", "sentiment_score", "confidence"],
                "aggregation": "hourly",
                "description": "Aggregated sentiment scores by symbol",
            },
            DataProductType.RISK_REGIME_DATASET: {
                "fields": ["timestamp", "regime", "probability", "duration_hours"],
                "aggregation": "daily",
                "description": "Market regime classifications over time",
            },
            DataProductType.FLOW_PRESSURE_INDICATOR: {
                "fields": ["timestamp", "symbol", "flow_pressure", "direction"],
                "aggregation": "hourly",
                "description": "On-chain flow pressure indicators",
            },
            DataProductType.MARKET_CONDITION_TIMELINE: {
                "fields": ["timestamp", "condition", "volatility", "liquidity"],
                "aggregation": "hourly",
                "description": "Market condition state timeline",
            },
            DataProductType.VOLATILITY_DASHBOARD: {
                "fields": ["timestamp", "symbol", "realized_vol", "implied_vol"],
                "aggregation": "daily",
                "description": "Volatility metrics dashboard data",
            },
            DataProductType.HISTORICAL_RISK_EVENTS: {
                "fields": ["timestamp", "event_type", "severity", "duration"],
                "aggregation": "event-based",
                "description": "Historical risk event dataset",
            },
        }
        return schemas.get(product_type, {})
    
    def create_sample_product(
        self,
        product_type: DataProductType,
        source_data: List[Dict[str, Any]],
        category: DataCategory,
    ) -> Dict[str, Any]:
        """
        Create a sample data product.
        
        This is for testing/preview only, not for sale.
        """
        if not self.can_monetize(category):
            raise ValueError(f"Category {category.value} cannot be monetized")
        
        # Anonymize all source data
        anonymized_data = [
            self._anonymizer.anonymize(d, category)
            for d in source_data
        ]
        
        schema = self.get_product_schema(product_type)
        
        return {
            "product_type": product_type.value,
            "schema": schema,
            "sample_size": len(anonymized_data),
            "created_at": datetime.utcnow().isoformat(),
            "disclaimer": "For informational purposes only. Not trading advice.",
            "status": "sample_only",
        }


# ============================================================
# PII DETECTOR
# ============================================================

class PIIDetector:
    """
    Detects personally identifiable information.
    """
    
    def __init__(self):
        self._patterns = SENSITIVE_PATTERNS
        self._field_blacklist = PROHIBITED_FIELDS
    
    def scan(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Scan data for PII.
        
        Returns list of detected PII locations.
        """
        findings = []
        
        def scan_dict(d: Dict[str, Any], path: str = "") -> None:
            for key, value in d.items():
                full_path = f"{path}.{key}" if path else key
                
                # Check field name
                if key.lower() in self._field_blacklist:
                    findings.append({
                        "type": "field_name",
                        "path": full_path,
                        "field": key,
                        "risk": "high",
                    })
                
                # Check value
                if isinstance(value, dict):
                    scan_dict(value, full_path)
                elif isinstance(value, str):
                    for pattern, pattern_name in SENSITIVE_PATTERNS:
                        if re.search(pattern, value):
                            findings.append({
                                "type": "pattern_match",
                                "path": full_path,
                                "pattern": pattern_name,
                                "risk": "high",
                            })
        
        scan_dict(data)
        return findings
    
    def is_safe(self, data: Dict[str, Any]) -> bool:
        """Check if data is safe (no PII detected)."""
        return len(self.scan(data)) == 0


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_anonymizer(
    salt: Optional[str] = None,
    additional_prohibited: Optional[Set[str]] = None,
) -> DataAnonymizer:
    """Create a DataAnonymizer."""
    return DataAnonymizer(salt, additional_prohibited)


def create_aggregator() -> DataAggregator:
    """Create a DataAggregator."""
    return DataAggregator()


def create_monetization_preparer(
    anonymizer: Optional[DataAnonymizer] = None,
    aggregator: Optional[DataAggregator] = None,
) -> MonetizationPreparer:
    """Create a MonetizationPreparer."""
    return MonetizationPreparer(anonymizer, aggregator)


def create_pii_detector() -> PIIDetector:
    """Create a PIIDetector."""
    return PIIDetector()


# ============================================================
# DEFAULT PRODUCT DEFINITIONS
# ============================================================

def get_default_product_definitions() -> List[DataProductDefinition]:
    """Get default data product definitions."""
    return [
        DataProductDefinition(
            product_id="prod_sentiment_index",
            product_type=DataProductType.SENTIMENT_INDEX,
            name="Crypto Sentiment Index",
            description="Aggregated sentiment scores for major cryptocurrencies",
            source_categories=[DataCategory.DERIVED_SCORES],
            aggregation_level="hourly",
            update_frequency="hourly",
            is_enabled=False,
        ),
        DataProductDefinition(
            product_id="prod_risk_regime",
            product_type=DataProductType.RISK_REGIME_DATASET,
            name="Risk Regime Dataset",
            description="Historical market regime classifications",
            source_categories=[DataCategory.DERIVED_SCORES],
            aggregation_level="daily",
            update_frequency="daily",
            is_enabled=False,
        ),
        DataProductDefinition(
            product_id="prod_flow_pressure",
            product_type=DataProductType.FLOW_PRESSURE_INDICATOR,
            name="On-Chain Flow Pressure",
            description="Exchange inflow/outflow pressure indicators",
            source_categories=[DataCategory.PROCESSED_DATA],
            aggregation_level="hourly",
            update_frequency="hourly",
            is_enabled=False,
        ),
        DataProductDefinition(
            product_id="prod_market_condition",
            product_type=DataProductType.MARKET_CONDITION_TIMELINE,
            name="Market Condition Timeline",
            description="Historical market condition state changes",
            source_categories=[DataCategory.PROCESSED_DATA],
            aggregation_level="hourly",
            update_frequency="hourly",
            is_enabled=False,
        ),
        DataProductDefinition(
            product_id="prod_volatility_dash",
            product_type=DataProductType.VOLATILITY_DASHBOARD,
            name="Volatility Dashboard Data",
            description="Realized and implied volatility metrics",
            source_categories=[DataCategory.DERIVED_SCORES],
            aggregation_level="daily",
            update_frequency="daily",
            is_enabled=False,
        ),
        DataProductDefinition(
            product_id="prod_risk_events",
            product_type=DataProductType.HISTORICAL_RISK_EVENTS,
            name="Historical Risk Events",
            description="Dataset of significant risk events",
            source_categories=[DataCategory.DERIVED_SCORES, DataCategory.RAW_DATA],
            aggregation_level="event-based",
            update_frequency="weekly",
            is_enabled=False,
        ),
    ]
