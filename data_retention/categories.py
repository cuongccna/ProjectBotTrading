"""
Data Classification and Categorization.

============================================================
PURPOSE
============================================================
Classifies incoming data into strict categories.

CRITICAL: Every piece of data must be classified before storage.
Classification determines:
- Retention policy
- Storage tier
- Monetization eligibility
- Access control

============================================================
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .models import (
    DataCategory,
    DataSubCategory,
    DataSensitivity,
    RetentionPolicy,
    create_default_retention_policies,
)


logger = logging.getLogger(__name__)


# ============================================================
# CLASSIFICATION RULES
# ============================================================

@dataclass
class ClassificationRule:
    """A rule for classifying data."""
    rule_id: str
    name: str
    category: DataCategory
    subcategory: Optional[DataSubCategory]
    sensitivity: DataSensitivity
    patterns: List[str] = field(default_factory=list)  # Regex patterns
    field_hints: List[str] = field(default_factory=list)  # Field names that hint category
    source_hints: List[str] = field(default_factory=list)  # Source names that hint category
    priority: int = 0  # Higher priority rules evaluated first
    
    def matches(
        self,
        data: Dict[str, Any],
        source_type: Optional[str] = None,
        source_name: Optional[str] = None,
    ) -> Tuple[bool, float]:
        """
        Check if data matches this rule.
        
        Returns (matches, confidence).
        """
        confidence = 0.0
        match_count = 0
        
        # Check source hints
        if source_type and source_type.lower() in [h.lower() for h in self.source_hints]:
            match_count += 1
            confidence += 0.3
        
        if source_name and source_name.lower() in [h.lower() for h in self.source_hints]:
            match_count += 1
            confidence += 0.3
        
        # Check field hints
        data_fields = set(data.keys()) if isinstance(data, dict) else set()
        for hint in self.field_hints:
            if hint.lower() in [f.lower() for f in data_fields]:
                match_count += 1
                confidence += 0.2
        
        # Check patterns (on string representation)
        data_str = str(data).lower()
        for pattern in self.patterns:
            if re.search(pattern, data_str, re.IGNORECASE):
                match_count += 1
                confidence += 0.2
        
        matches = match_count > 0
        confidence = min(confidence, 1.0)
        
        return matches, confidence


# ============================================================
# CATEGORY CLASSIFIER
# ============================================================

class DataClassifier:
    """
    Classifies data into categories.
    
    Every piece of data must be classified before storage.
    """
    
    def __init__(self):
        self._rules = self._build_default_rules()
        self._policies = create_default_retention_policies()
        self._custom_classifiers: Dict[str, Callable] = {}
    
    def _build_default_rules(self) -> List[ClassificationRule]:
        """Build default classification rules."""
        rules = []
        
        # ============================================
        # RAW DATA RULES
        # ============================================
        
        rules.append(ClassificationRule(
            rule_id="raw_news_headlines",
            name="News Headlines",
            category=DataCategory.RAW_DATA,
            subcategory=DataSubCategory.NEWS_HEADLINES,
            sensitivity=DataSensitivity.INTERNAL,
            patterns=[r"headline", r"news", r"article", r"breaking"],
            field_hints=["title", "headline", "summary", "source_url"],
            source_hints=["news_feed", "cryptopanic", "newsapi", "rss"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="raw_market_ohlcv",
            name="Market OHLCV",
            category=DataCategory.RAW_DATA,
            subcategory=DataSubCategory.MARKET_OHLCV,
            sensitivity=DataSensitivity.PUBLIC,
            patterns=[r"ohlcv", r"candlestick", r"kline"],
            field_hints=["open", "high", "low", "close", "volume", "ohlcv"],
            source_hints=["exchange_api", "binance", "okx", "bybit"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="raw_onchain_flow",
            name="On-chain Flow Events",
            category=DataCategory.RAW_DATA,
            subcategory=DataSubCategory.ONCHAIN_FLOW_EVENTS,
            sensitivity=DataSensitivity.INTERNAL,
            patterns=[r"onchain", r"blockchain", r"transfer", r"whale"],
            field_hints=["tx_hash", "from_address", "to_address", "block_number"],
            source_hints=["onchain", "whale_alert", "glassnode"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="raw_exchange_responses",
            name="Exchange API Responses",
            category=DataCategory.RAW_DATA,
            subcategory=DataSubCategory.EXCHANGE_RESPONSES,
            sensitivity=DataSensitivity.CONFIDENTIAL,
            patterns=[r"api_response", r"exchange_response"],
            field_hints=["rate_limit", "api_response", "request_id"],
            source_hints=["exchange_api"],
            priority=5,
        ))
        
        rules.append(ClassificationRule(
            rule_id="raw_orderbook",
            name="Orderbook Snapshots",
            category=DataCategory.RAW_DATA,
            subcategory=DataSubCategory.ORDERBOOK_SNAPSHOTS,
            sensitivity=DataSensitivity.INTERNAL,
            patterns=[r"orderbook", r"depth", r"bids", r"asks"],
            field_hints=["bids", "asks", "depth", "orderbook"],
            source_hints=["exchange_api"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="raw_funding_rates",
            name="Funding Rates",
            category=DataCategory.RAW_DATA,
            subcategory=DataSubCategory.FUNDING_RATES,
            sensitivity=DataSensitivity.PUBLIC,
            patterns=[r"funding_rate", r"funding"],
            field_hints=["funding_rate", "next_funding_time"],
            source_hints=["exchange_api"],
            priority=10,
        ))
        
        # ============================================
        # PROCESSED DATA RULES
        # ============================================
        
        rules.append(ClassificationRule(
            rule_id="processed_cleaned_news",
            name="Cleaned News",
            category=DataCategory.PROCESSED_DATA,
            subcategory=DataSubCategory.CLEANED_NEWS,
            sensitivity=DataSensitivity.INTERNAL,
            patterns=[r"cleaned", r"processed_news", r"parsed_news"],
            field_hints=["cleaned_text", "entities", "processed_at"],
            source_hints=["news_processor", "text_cleaner"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="processed_normalized_market",
            name="Normalized Market Data",
            category=DataCategory.PROCESSED_DATA,
            subcategory=DataSubCategory.NORMALIZED_MARKET_DATA,
            sensitivity=DataSensitivity.INTERNAL,
            patterns=[r"normalized", r"standardized"],
            field_hints=["normalized_price", "z_score", "percentile"],
            source_hints=["data_normalizer", "market_processor"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="processed_flow_metrics",
            name="Flow Metrics",
            category=DataCategory.PROCESSED_DATA,
            subcategory=DataSubCategory.FLOW_METRICS,
            sensitivity=DataSensitivity.INTERNAL,
            patterns=[r"flow_metric", r"net_flow", r"inflow", r"outflow"],
            field_hints=["net_flow", "exchange_inflow", "exchange_outflow"],
            source_hints=["flow_analyzer"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="processed_market_condition",
            name="Market Condition States",
            category=DataCategory.PROCESSED_DATA,
            subcategory=DataSubCategory.MARKET_CONDITION_STATES,
            sensitivity=DataSensitivity.INTERNAL,
            patterns=[r"market_condition", r"regime", r"state"],
            field_hints=["market_state", "condition", "regime"],
            source_hints=["market_analyzer", "condition_detector"],
            priority=10,
        ))
        
        # ============================================
        # DERIVED SCORES RULES
        # ============================================
        
        rules.append(ClassificationRule(
            rule_id="derived_sentiment",
            name="Sentiment Scores",
            category=DataCategory.DERIVED_SCORES,
            subcategory=DataSubCategory.SENTIMENT_SCORES,
            sensitivity=DataSensitivity.CONFIDENTIAL,
            patterns=[r"sentiment", r"score", r"polarity"],
            field_hints=["sentiment_score", "polarity", "subjectivity"],
            source_hints=["sentiment_analyzer", "nlp_engine"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="derived_flow_risk",
            name="Flow Risk Scores",
            category=DataCategory.DERIVED_SCORES,
            subcategory=DataSubCategory.FLOW_RISK_SCORES,
            sensitivity=DataSensitivity.CONFIDENTIAL,
            patterns=[r"flow_risk", r"risk_score"],
            field_hints=["flow_risk_score", "risk_level"],
            source_hints=["flow_risk_scorer"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="derived_aggregated_risk",
            name="Aggregated Risk States",
            category=DataCategory.DERIVED_SCORES,
            subcategory=DataSubCategory.AGGREGATED_RISK_STATES,
            sensitivity=DataSensitivity.CONFIDENTIAL,
            patterns=[r"aggregated_risk", r"combined_risk", r"total_risk"],
            field_hints=["aggregated_risk", "risk_state", "overall_risk"],
            source_hints=["risk_aggregator", "system_risk_controller"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="derived_volatility",
            name="Volatility Indices",
            category=DataCategory.DERIVED_SCORES,
            subcategory=DataSubCategory.VOLATILITY_INDICES,
            sensitivity=DataSensitivity.CONFIDENTIAL,
            patterns=[r"volatility", r"vix", r"variance"],
            field_hints=["volatility_index", "realized_vol", "implied_vol"],
            source_hints=["volatility_calculator"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="derived_regime",
            name="Regime Classifications",
            category=DataCategory.DERIVED_SCORES,
            subcategory=DataSubCategory.REGIME_CLASSIFICATIONS,
            sensitivity=DataSensitivity.CONFIDENTIAL,
            patterns=[r"regime", r"market_phase"],
            field_hints=["regime", "market_phase", "trend_direction"],
            source_hints=["regime_detector"],
            priority=10,
        ))
        
        # ============================================
        # DECISION LOGS RULES
        # ============================================
        
        rules.append(ClassificationRule(
            rule_id="decision_risk",
            name="Risk Decisions",
            category=DataCategory.DECISION_LOGS,
            subcategory=DataSubCategory.RISK_DECISIONS,
            sensitivity=DataSensitivity.RESTRICTED,
            patterns=[r"risk_decision", r"risk_evaluation"],
            field_hints=["risk_decision", "risk_approved", "risk_rejected"],
            source_hints=["system_risk_controller"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="decision_strategy",
            name="Strategy Decisions",
            category=DataCategory.DECISION_LOGS,
            subcategory=DataSubCategory.STRATEGY_DECISIONS,
            sensitivity=DataSensitivity.RESTRICTED,
            patterns=[r"strategy_decision", r"allow", r"block"],
            field_hints=["strategy_allowed", "strategy_blocked", "entry_signal"],
            source_hints=["strategy_manager"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="decision_trade_guard",
            name="Trade Guard Decisions",
            category=DataCategory.DECISION_LOGS,
            subcategory=DataSubCategory.TRADE_GUARD_DECISIONS,
            sensitivity=DataSensitivity.RESTRICTED,
            patterns=[r"trade_guard", r"trade_allowed", r"trade_blocked"],
            field_hints=["trade_guard_decision", "approved", "rejected"],
            source_hints=["trade_guard"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="decision_position_sizing",
            name="Position Sizing Decisions",
            category=DataCategory.DECISION_LOGS,
            subcategory=DataSubCategory.POSITION_SIZING_DECISIONS,
            sensitivity=DataSensitivity.RESTRICTED,
            patterns=[r"position_size", r"sizing"],
            field_hints=["position_size", "max_size", "size_multiplier"],
            source_hints=["position_sizer"],
            priority=10,
        ))
        
        # ============================================
        # EXECUTION RECORDS RULES
        # ============================================
        
        rules.append(ClassificationRule(
            rule_id="execution_submitted",
            name="Orders Submitted",
            category=DataCategory.EXECUTION_RECORDS,
            subcategory=DataSubCategory.ORDERS_SUBMITTED,
            sensitivity=DataSensitivity.RESTRICTED,
            patterns=[r"order_submitted", r"order_created"],
            field_hints=["order_id", "client_order_id", "submitted_at"],
            source_hints=["execution_engine", "order_manager"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="execution_filled",
            name="Orders Filled",
            category=DataCategory.EXECUTION_RECORDS,
            subcategory=DataSubCategory.ORDERS_FILLED,
            sensitivity=DataSensitivity.RESTRICTED,
            patterns=[r"order_filled", r"fill", r"executed"],
            field_hints=["filled_qty", "filled_price", "fill_time"],
            source_hints=["execution_engine"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="execution_partial",
            name="Partial Fills",
            category=DataCategory.EXECUTION_RECORDS,
            subcategory=DataSubCategory.PARTIAL_FILLS,
            sensitivity=DataSensitivity.RESTRICTED,
            patterns=[r"partial_fill", r"partially_filled"],
            field_hints=["partial_qty", "remaining_qty"],
            source_hints=["execution_engine"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="execution_slippage",
            name="Slippage Metrics",
            category=DataCategory.EXECUTION_RECORDS,
            subcategory=DataSubCategory.SLIPPAGE_METRICS,
            sensitivity=DataSensitivity.RESTRICTED,
            patterns=[r"slippage"],
            field_hints=["slippage", "slippage_pct", "price_impact"],
            source_hints=["execution_engine", "slippage_analyzer"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="execution_fees",
            name="Fee Records",
            category=DataCategory.EXECUTION_RECORDS,
            subcategory=DataSubCategory.FEE_RECORDS,
            sensitivity=DataSensitivity.RESTRICTED,
            patterns=[r"fee", r"commission"],
            field_hints=["fee", "commission", "fee_asset"],
            source_hints=["execution_engine"],
            priority=5,
        ))
        
        # ============================================
        # SYSTEM METADATA RULES
        # ============================================
        
        rules.append(ClassificationRule(
            rule_id="meta_health",
            name="Module Health",
            category=DataCategory.SYSTEM_METADATA,
            subcategory=DataSubCategory.MODULE_HEALTH,
            sensitivity=DataSensitivity.INTERNAL,
            patterns=[r"health", r"heartbeat", r"status"],
            field_hints=["health_status", "is_healthy", "last_heartbeat"],
            source_hints=["health_monitor", "watchdog"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="meta_errors",
            name="Errors",
            category=DataCategory.SYSTEM_METADATA,
            subcategory=DataSubCategory.ERRORS,
            sensitivity=DataSensitivity.INTERNAL,
            patterns=[r"error", r"exception", r"failure"],
            field_hints=["error_message", "stack_trace", "error_code"],
            source_hints=["error_handler", "logger"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="meta_latency",
            name="Latency Metrics",
            category=DataCategory.SYSTEM_METADATA,
            subcategory=DataSubCategory.LATENCY_METRICS,
            sensitivity=DataSensitivity.INTERNAL,
            patterns=[r"latency", r"duration", r"response_time"],
            field_hints=["latency_ms", "duration_ms", "response_time"],
            source_hints=["latency_monitor", "profiler"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="meta_anomalies",
            name="Anomalies",
            category=DataCategory.SYSTEM_METADATA,
            subcategory=DataSubCategory.ANOMALIES,
            sensitivity=DataSensitivity.INTERNAL,
            patterns=[r"anomaly", r"outlier", r"unusual"],
            field_hints=["anomaly_score", "is_anomaly", "deviation"],
            source_hints=["anomaly_detector"],
            priority=10,
        ))
        
        rules.append(ClassificationRule(
            rule_id="meta_resource",
            name="Resource Usage",
            category=DataCategory.SYSTEM_METADATA,
            subcategory=DataSubCategory.RESOURCE_USAGE,
            sensitivity=DataSensitivity.INTERNAL,
            patterns=[r"cpu", r"memory", r"disk", r"resource"],
            field_hints=["cpu_percent", "memory_mb", "disk_usage"],
            source_hints=["resource_monitor"],
            priority=10,
        ))
        
        # Sort by priority (higher first)
        rules.sort(key=lambda r: r.priority, reverse=True)
        
        return rules
    
    def classify(
        self,
        data: Dict[str, Any],
        source_type: Optional[str] = None,
        source_name: Optional[str] = None,
        hint_category: Optional[DataCategory] = None,
        hint_subcategory: Optional[DataSubCategory] = None,
    ) -> Tuple[DataCategory, Optional[DataSubCategory], DataSensitivity, float]:
        """
        Classify data into a category.
        
        Returns (category, subcategory, sensitivity, confidence).
        """
        # If explicit hints provided, use them
        if hint_category and hint_subcategory:
            policy = self._policies.get(hint_category)
            sensitivity = policy.sensitivity if policy else DataSensitivity.INTERNAL
            return hint_category, hint_subcategory, sensitivity, 1.0
        
        # Try custom classifiers first
        for name, classifier in self._custom_classifiers.items():
            result = classifier(data, source_type, source_name)
            if result:
                return result
        
        # Try rules
        best_match: Optional[ClassificationRule] = None
        best_confidence = 0.0
        
        for rule in self._rules:
            # If hint_category provided, only check matching rules
            if hint_category and rule.category != hint_category:
                continue
            
            matches, confidence = rule.matches(data, source_type, source_name)
            if matches and confidence > best_confidence:
                best_match = rule
                best_confidence = confidence
        
        if best_match:
            return (
                best_match.category,
                best_match.subcategory,
                best_match.sensitivity,
                best_confidence,
            )
        
        # Default fallback
        logger.warning(
            f"Could not classify data, defaulting to SYSTEM_METADATA. "
            f"source_type={source_type}, source_name={source_name}"
        )
        return (
            DataCategory.SYSTEM_METADATA,
            None,
            DataSensitivity.INTERNAL,
            0.0,
        )
    
    def register_custom_classifier(
        self,
        name: str,
        classifier: Callable[
            [Dict[str, Any], Optional[str], Optional[str]],
            Optional[Tuple[DataCategory, Optional[DataSubCategory], DataSensitivity, float]]
        ],
    ) -> None:
        """Register a custom classifier function."""
        self._custom_classifiers[name] = classifier
        logger.info(f"Registered custom classifier: {name}")
    
    def get_policy(self, category: DataCategory) -> RetentionPolicy:
        """Get retention policy for a category."""
        return self._policies.get(category, RetentionPolicy.for_system_metadata())
    
    def add_rule(self, rule: ClassificationRule) -> None:
        """Add a classification rule."""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)
        logger.info(f"Added classification rule: {rule.rule_id}")


# ============================================================
# SUBCATEGORY MAPPING
# ============================================================

# Maps subcategories to their parent categories
SUBCATEGORY_TO_CATEGORY: Dict[DataSubCategory, DataCategory] = {
    # Raw Data
    DataSubCategory.NEWS_HEADLINES: DataCategory.RAW_DATA,
    DataSubCategory.MARKET_OHLCV: DataCategory.RAW_DATA,
    DataSubCategory.ONCHAIN_FLOW_EVENTS: DataCategory.RAW_DATA,
    DataSubCategory.EXCHANGE_RESPONSES: DataCategory.RAW_DATA,
    DataSubCategory.ORDERBOOK_SNAPSHOTS: DataCategory.RAW_DATA,
    DataSubCategory.FUNDING_RATES: DataCategory.RAW_DATA,
    # Processed Data
    DataSubCategory.CLEANED_NEWS: DataCategory.PROCESSED_DATA,
    DataSubCategory.NORMALIZED_MARKET_DATA: DataCategory.PROCESSED_DATA,
    DataSubCategory.FLOW_METRICS: DataCategory.PROCESSED_DATA,
    DataSubCategory.MARKET_CONDITION_STATES: DataCategory.PROCESSED_DATA,
    DataSubCategory.AGGREGATED_ORDERBOOK: DataCategory.PROCESSED_DATA,
    # Derived Scores
    DataSubCategory.SENTIMENT_SCORES: DataCategory.DERIVED_SCORES,
    DataSubCategory.FLOW_RISK_SCORES: DataCategory.DERIVED_SCORES,
    DataSubCategory.AGGREGATED_RISK_STATES: DataCategory.DERIVED_SCORES,
    DataSubCategory.VOLATILITY_INDICES: DataCategory.DERIVED_SCORES,
    DataSubCategory.REGIME_CLASSIFICATIONS: DataCategory.DERIVED_SCORES,
    # Decision Logs
    DataSubCategory.RISK_DECISIONS: DataCategory.DECISION_LOGS,
    DataSubCategory.STRATEGY_DECISIONS: DataCategory.DECISION_LOGS,
    DataSubCategory.TRADE_GUARD_DECISIONS: DataCategory.DECISION_LOGS,
    DataSubCategory.POSITION_SIZING_DECISIONS: DataCategory.DECISION_LOGS,
    # Execution Records
    DataSubCategory.ORDERS_SUBMITTED: DataCategory.EXECUTION_RECORDS,
    DataSubCategory.ORDERS_FILLED: DataCategory.EXECUTION_RECORDS,
    DataSubCategory.PARTIAL_FILLS: DataCategory.EXECUTION_RECORDS,
    DataSubCategory.SLIPPAGE_METRICS: DataCategory.EXECUTION_RECORDS,
    DataSubCategory.FEE_RECORDS: DataCategory.EXECUTION_RECORDS,
    # System Metadata
    DataSubCategory.MODULE_HEALTH: DataCategory.SYSTEM_METADATA,
    DataSubCategory.ERRORS: DataCategory.SYSTEM_METADATA,
    DataSubCategory.LATENCY_METRICS: DataCategory.SYSTEM_METADATA,
    DataSubCategory.ANOMALIES: DataCategory.SYSTEM_METADATA,
    DataSubCategory.RESOURCE_USAGE: DataCategory.SYSTEM_METADATA,
}


def get_category_for_subcategory(subcategory: DataSubCategory) -> DataCategory:
    """Get the parent category for a subcategory."""
    return SUBCATEGORY_TO_CATEGORY.get(subcategory, DataCategory.SYSTEM_METADATA)


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_classifier() -> DataClassifier:
    """Create a DataClassifier with default rules."""
    return DataClassifier()
