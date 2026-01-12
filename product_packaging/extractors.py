"""
Product Data Packaging - Data Extractors.

============================================================
PURPOSE
============================================================
Extract data from retained data sources for product packaging.

CRITICAL: This module is READ-ONLY.
CRITICAL: Only extracts from ALLOWED sources.
CRITICAL: NEVER accesses prohibited data sources.

============================================================
ALLOWED SOURCES
============================================================
- Raw Data
- Processed Data
- Derived Scores
- Market Condition States

============================================================
PROHIBITED SOURCES (NEVER ACCESS)
============================================================
- Execution logic
- Strategy logic
- Risk thresholds
- Account trade history
- Position sizing logic
- API keys
- Account balances

============================================================
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Set
import logging
import hashlib


from .models import (
    ProductType,
    TimeBucket,
    AllowedDataSource,
    ProhibitedDataSource,
)


logger = logging.getLogger(__name__)


# ============================================================
# DATA SOURCE VALIDATION
# ============================================================

class DataSourceValidator:
    """
    Validates that only allowed data sources are accessed.
    
    CRITICAL: This is a security boundary.
    """
    
    # Allowed sources
    ALLOWED_SOURCES: Set[str] = {
        "raw_data",
        "processed_data",
        "derived_scores",
        "market_condition_states",
        "sentiment_scores",
        "flow_metrics",
        "volatility_metrics",
        "risk_scores",
        "health_metrics",
    }
    
    # Prohibited patterns - NEVER allow access to these
    PROHIBITED_PATTERNS: Set[str] = {
        "execution",
        "strategy",
        "position_size",
        "risk_threshold",
        "api_key",
        "secret",
        "account",
        "balance",
        "trade_history",
        "order_book_internal",
        "private",
        "credential",
    }
    
    @classmethod
    def validate_source(cls, source_name: str) -> bool:
        """
        Validate that a data source is allowed.
        
        Returns True if source is allowed, False otherwise.
        """
        source_lower = source_name.lower()
        
        # Check for prohibited patterns
        for pattern in cls.PROHIBITED_PATTERNS:
            if pattern in source_lower:
                logger.warning(
                    f"Attempted access to prohibited data source: {source_name}"
                )
                return False
        
        # Check if explicitly allowed
        if source_lower in cls.ALLOWED_SOURCES:
            return True
        
        # Check against enum values
        for allowed in AllowedDataSource:
            if allowed.value in source_lower:
                return True
        
        # Default deny
        logger.warning(f"Unknown data source denied: {source_name}")
        return False
    
    @classmethod
    def validate_query(cls, query: Dict[str, Any]) -> bool:
        """Validate that a query doesn't access prohibited data."""
        # Check table/collection names
        if "table" in query:
            if not cls.validate_source(query["table"]):
                return False
        
        if "collection" in query:
            if not cls.validate_source(query["collection"]):
                return False
        
        # Check for prohibited field access
        if "fields" in query:
            for field in query["fields"]:
                for pattern in cls.PROHIBITED_PATTERNS:
                    if pattern in field.lower():
                        logger.warning(
                            f"Attempted access to prohibited field: {field}"
                        )
                        return False
        
        return True


# ============================================================
# EXTRACTED DATA MODELS
# ============================================================

@dataclass
class ExtractedRecord:
    """A single record extracted from data source."""
    record_id: str
    source: AllowedDataSource
    timestamp: datetime
    data: Dict[str, Any]
    symbol: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Result of a data extraction operation."""
    success: bool
    source: AllowedDataSource
    records: List[ExtractedRecord]
    record_count: int
    start_time: datetime
    end_time: datetime
    extraction_timestamp: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class ExtractionQuery:
    """Query for data extraction."""
    source: AllowedDataSource
    product_type: ProductType
    start_time: datetime
    end_time: datetime
    symbols: Optional[List[str]] = None
    time_bucket: TimeBucket = TimeBucket.HOUR_1
    limit: Optional[int] = None
    
    def validate(self) -> bool:
        """Validate the query."""
        # Ensure time range is valid
        if self.start_time >= self.end_time:
            return False
        
        # Ensure source is allowed
        return DataSourceValidator.validate_source(self.source.value)


# ============================================================
# DATA STORE INTERFACE
# ============================================================

class DataStoreInterface(Protocol):
    """
    Interface for data store access.
    
    This is a read-only interface.
    """
    
    async def query(
        self,
        source: AllowedDataSource,
        start_time: datetime,
        end_time: datetime,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query data from the store (read-only)."""
        ...
    
    async def count(
        self,
        source: AllowedDataSource,
        start_time: datetime,
        end_time: datetime,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count records matching criteria."""
        ...


# ============================================================
# BASE EXTRACTOR
# ============================================================

class BaseExtractor(ABC):
    """
    Base class for data extractors.
    
    All extractors are READ-ONLY.
    """
    
    def __init__(self, data_store: Optional[DataStoreInterface] = None):
        self._data_store = data_store
        self._validator = DataSourceValidator()
    
    @property
    @abstractmethod
    def product_type(self) -> ProductType:
        """Product type this extractor serves."""
        pass
    
    @property
    @abstractmethod
    def allowed_sources(self) -> List[AllowedDataSource]:
        """Data sources this extractor can access."""
        pass
    
    def validate_access(self, source: AllowedDataSource) -> bool:
        """Validate access to a data source."""
        if source not in self.allowed_sources:
            logger.warning(
                f"Extractor {self.__class__.__name__} cannot access {source}"
            )
            return False
        return self._validator.validate_source(source.value)
    
    @abstractmethod
    async def extract(self, query: ExtractionQuery) -> ExtractionResult:
        """Extract data based on query."""
        pass
    
    def _create_record_id(self, data: Dict[str, Any], timestamp: datetime) -> str:
        """Create a unique record ID."""
        content = f"{timestamp.isoformat()}_{str(data)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# ============================================================
# SENTIMENT EXTRACTOR
# ============================================================

class SentimentExtractor(BaseExtractor):
    """Extractor for sentiment data."""
    
    @property
    def product_type(self) -> ProductType:
        return ProductType.SENTIMENT_INDEX
    
    @property
    def allowed_sources(self) -> List[AllowedDataSource]:
        return [
            AllowedDataSource.DERIVED_SCORES,
            AllowedDataSource.PROCESSED_DATA,
        ]
    
    async def extract(self, query: ExtractionQuery) -> ExtractionResult:
        """Extract sentiment data."""
        if not self.validate_access(query.source):
            return ExtractionResult(
                success=False,
                source=query.source,
                records=[],
                record_count=0,
                start_time=query.start_time,
                end_time=query.end_time,
                error_message="Access to data source denied",
            )
        
        records = []
        
        # If we have a data store, query it
        if self._data_store:
            filters = {}
            if query.symbols:
                filters["symbol"] = {"$in": query.symbols}
            
            raw_data = await self._data_store.query(
                source=query.source,
                start_time=query.start_time,
                end_time=query.end_time,
                filters=filters,
                limit=query.limit,
            )
            
            for item in raw_data:
                # Extract only sentiment-related fields
                sentiment_data = self._extract_sentiment_fields(item)
                if sentiment_data:
                    record = ExtractedRecord(
                        record_id=self._create_record_id(
                            sentiment_data,
                            item.get("timestamp", datetime.utcnow()),
                        ),
                        source=query.source,
                        timestamp=item.get("timestamp", datetime.utcnow()),
                        data=sentiment_data,
                        symbol=item.get("symbol"),
                    )
                    records.append(record)
        
        return ExtractionResult(
            success=True,
            source=query.source,
            records=records,
            record_count=len(records),
            start_time=query.start_time,
            end_time=query.end_time,
        )
    
    def _extract_sentiment_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract only sentiment-related fields."""
        result = {}
        
        # Allowed sentiment fields
        allowed_fields = {
            "sentiment_score",
            "sentiment_confidence",
            "source_count",
            "sentiment_change",
            "volatility_indicator",
            "timestamp",
            "symbol",
        }
        
        for key, value in data.items():
            if key.lower() in allowed_fields:
                result[key] = value
        
        return result


# ============================================================
# FLOW PRESSURE EXTRACTOR
# ============================================================

class FlowPressureExtractor(BaseExtractor):
    """Extractor for flow pressure data."""
    
    @property
    def product_type(self) -> ProductType:
        return ProductType.FLOW_PRESSURE
    
    @property
    def allowed_sources(self) -> List[AllowedDataSource]:
        return [
            AllowedDataSource.PROCESSED_DATA,
            AllowedDataSource.DERIVED_SCORES,
        ]
    
    async def extract(self, query: ExtractionQuery) -> ExtractionResult:
        """Extract flow pressure data."""
        if not self.validate_access(query.source):
            return ExtractionResult(
                success=False,
                source=query.source,
                records=[],
                record_count=0,
                start_time=query.start_time,
                end_time=query.end_time,
                error_message="Access to data source denied",
            )
        
        records = []
        
        if self._data_store:
            filters = {}
            if query.symbols:
                filters["symbol"] = {"$in": query.symbols}
            
            raw_data = await self._data_store.query(
                source=query.source,
                start_time=query.start_time,
                end_time=query.end_time,
                filters=filters,
                limit=query.limit,
            )
            
            for item in raw_data:
                flow_data = self._extract_flow_fields(item)
                if flow_data:
                    record = ExtractedRecord(
                        record_id=self._create_record_id(
                            flow_data,
                            item.get("timestamp", datetime.utcnow()),
                        ),
                        source=query.source,
                        timestamp=item.get("timestamp", datetime.utcnow()),
                        data=flow_data,
                        symbol=item.get("symbol"),
                    )
                    records.append(record)
        
        return ExtractionResult(
            success=True,
            source=query.source,
            records=records,
            record_count=len(records),
            start_time=query.start_time,
            end_time=query.end_time,
        )
    
    def _extract_flow_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract only flow-related fields."""
        result = {}
        
        # Allowed flow fields (no wallet-level data)
        allowed_fields = {
            "net_flow_pressure",
            "inflow_intensity",
            "outflow_intensity",
            "flow_volatility",
            "exchange_count",
            "timestamp",
            "symbol",
        }
        
        # Prohibited fields (wallet-level data)
        prohibited_patterns = {
            "wallet",
            "address",
            "transaction",
            "tx_hash",
            "sender",
            "receiver",
        }
        
        for key, value in data.items():
            key_lower = key.lower()
            
            # Skip prohibited patterns
            if any(p in key_lower for p in prohibited_patterns):
                continue
            
            if key_lower in allowed_fields:
                result[key] = value
        
        return result


# ============================================================
# MARKET CONDITION EXTRACTOR
# ============================================================

class MarketConditionExtractor(BaseExtractor):
    """Extractor for market condition data."""
    
    @property
    def product_type(self) -> ProductType:
        return ProductType.MARKET_CONDITION_TIMELINE
    
    @property
    def allowed_sources(self) -> List[AllowedDataSource]:
        return [
            AllowedDataSource.MARKET_CONDITION_STATES,
            AllowedDataSource.PROCESSED_DATA,
        ]
    
    async def extract(self, query: ExtractionQuery) -> ExtractionResult:
        """Extract market condition data."""
        if not self.validate_access(query.source):
            return ExtractionResult(
                success=False,
                source=query.source,
                records=[],
                record_count=0,
                start_time=query.start_time,
                end_time=query.end_time,
                error_message="Access to data source denied",
            )
        
        records = []
        
        if self._data_store:
            filters = {}
            if query.symbols:
                filters["symbol"] = {"$in": query.symbols}
            
            raw_data = await self._data_store.query(
                source=query.source,
                start_time=query.start_time,
                end_time=query.end_time,
                filters=filters,
                limit=query.limit,
            )
            
            for item in raw_data:
                condition_data = self._extract_condition_fields(item)
                if condition_data:
                    record = ExtractedRecord(
                        record_id=self._create_record_id(
                            condition_data,
                            item.get("timestamp", datetime.utcnow()),
                        ),
                        source=query.source,
                        timestamp=item.get("timestamp", datetime.utcnow()),
                        data=condition_data,
                        symbol=item.get("symbol"),
                    )
                    records.append(record)
        
        return ExtractionResult(
            success=True,
            source=query.source,
            records=records,
            record_count=len(records),
            start_time=query.start_time,
            end_time=query.end_time,
        )
    
    def _extract_condition_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract only market condition fields."""
        result = {}
        
        allowed_fields = {
            "trend_regime",
            "range_regime",
            "volatility_regime",
            "regime_stability",
            "regime_duration_buckets",
            "timestamp",
            "symbol",
        }
        
        for key, value in data.items():
            if key.lower() in allowed_fields:
                result[key] = value
        
        return result


# ============================================================
# RISK REGIME EXTRACTOR
# ============================================================

class RiskRegimeExtractor(BaseExtractor):
    """Extractor for risk regime data."""
    
    @property
    def product_type(self) -> ProductType:
        return ProductType.RISK_REGIME_DATASET
    
    @property
    def allowed_sources(self) -> List[AllowedDataSource]:
        return [
            AllowedDataSource.DERIVED_SCORES,
            AllowedDataSource.MARKET_CONDITION_STATES,
        ]
    
    async def extract(self, query: ExtractionQuery) -> ExtractionResult:
        """Extract risk regime data."""
        if not self.validate_access(query.source):
            return ExtractionResult(
                success=False,
                source=query.source,
                records=[],
                record_count=0,
                start_time=query.start_time,
                end_time=query.end_time,
                error_message="Access to data source denied",
            )
        
        records = []
        
        if self._data_store:
            filters = {}
            if query.symbols:
                filters["symbol"] = {"$in": query.symbols}
            
            raw_data = await self._data_store.query(
                source=query.source,
                start_time=query.start_time,
                end_time=query.end_time,
                filters=filters,
                limit=query.limit,
            )
            
            for item in raw_data:
                risk_data = self._extract_risk_fields(item)
                if risk_data:
                    record = ExtractedRecord(
                        record_id=self._create_record_id(
                            risk_data,
                            item.get("timestamp", datetime.utcnow()),
                        ),
                        source=query.source,
                        timestamp=item.get("timestamp", datetime.utcnow()),
                        data=risk_data,
                        symbol=item.get("symbol"),
                    )
                    records.append(record)
        
        return ExtractionResult(
            success=True,
            source=query.source,
            records=records,
            record_count=len(records),
            start_time=query.start_time,
            end_time=query.end_time,
        )
    
    def _extract_risk_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract only risk-related fields (not thresholds)."""
        result = {}
        
        # Allowed risk observation fields
        allowed_fields = {
            "risk_level",
            "risk_score",
            "regime_change_probability",
            "consecutive_buckets",
            "timestamp",
            "symbol",
        }
        
        # Prohibited fields (internal thresholds/logic)
        prohibited_patterns = {
            "threshold",
            "limit",
            "max_position",
            "stop_loss",
            "take_profit",
            "entry",
            "exit",
        }
        
        for key, value in data.items():
            key_lower = key.lower()
            
            # Skip prohibited patterns
            if any(p in key_lower for p in prohibited_patterns):
                continue
            
            if key_lower in allowed_fields:
                result[key] = value
        
        # Extract risk components if present (normalized only)
        if "risk_components" in data and isinstance(data["risk_components"], dict):
            components = {}
            for comp_key, comp_value in data["risk_components"].items():
                # Only include normalized values (0-1)
                if isinstance(comp_value, (int, float)) and 0 <= comp_value <= 1:
                    components[comp_key] = comp_value
            if components:
                result["risk_components"] = components
        
        return result


# ============================================================
# SYSTEM HEALTH EXTRACTOR
# ============================================================

class SystemHealthExtractor(BaseExtractor):
    """Extractor for system health data."""
    
    @property
    def product_type(self) -> ProductType:
        return ProductType.SYSTEM_HEALTH_METRICS
    
    @property
    def allowed_sources(self) -> List[AllowedDataSource]:
        return [AllowedDataSource.PROCESSED_DATA]
    
    async def extract(self, query: ExtractionQuery) -> ExtractionResult:
        """Extract system health data."""
        if not self.validate_access(query.source):
            return ExtractionResult(
                success=False,
                source=query.source,
                records=[],
                record_count=0,
                start_time=query.start_time,
                end_time=query.end_time,
                error_message="Access to data source denied",
            )
        
        records = []
        
        if self._data_store:
            raw_data = await self._data_store.query(
                source=query.source,
                start_time=query.start_time,
                end_time=query.end_time,
                filters={"type": "health_metrics"},
                limit=query.limit,
            )
            
            for item in raw_data:
                health_data = self._extract_health_fields(item)
                if health_data:
                    record = ExtractedRecord(
                        record_id=self._create_record_id(
                            health_data,
                            item.get("timestamp", datetime.utcnow()),
                        ),
                        source=query.source,
                        timestamp=item.get("timestamp", datetime.utcnow()),
                        data=health_data,
                    )
                    records.append(record)
        
        return ExtractionResult(
            success=True,
            source=query.source,
            records=records,
            record_count=len(records),
            start_time=query.start_time,
            end_time=query.end_time,
        )
    
    def _extract_health_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract only health-related fields."""
        result = {}
        
        allowed_fields = {
            "data_freshness_score",
            "average_latency_ms",
            "availability_ratio",
            "data_completeness",
            "error_rate",
            "stability_indicator",
            "timestamp",
        }
        
        # Prohibited fields (internal architecture details)
        prohibited_patterns = {
            "server",
            "host",
            "ip_address",
            "internal",
            "config",
            "secret",
            "key",
        }
        
        for key, value in data.items():
            key_lower = key.lower()
            
            # Skip prohibited patterns
            if any(p in key_lower for p in prohibited_patterns):
                continue
            
            if key_lower in allowed_fields:
                result[key] = value
        
        return result


# ============================================================
# EXTRACTOR FACTORY
# ============================================================

class ExtractorFactory:
    """Factory for creating extractors."""
    
    _extractors: Dict[ProductType, type] = {
        ProductType.SENTIMENT_INDEX: SentimentExtractor,
        ProductType.FLOW_PRESSURE: FlowPressureExtractor,
        ProductType.MARKET_CONDITION_TIMELINE: MarketConditionExtractor,
        ProductType.RISK_REGIME_DATASET: RiskRegimeExtractor,
        ProductType.SYSTEM_HEALTH_METRICS: SystemHealthExtractor,
    }
    
    @classmethod
    def create(
        cls,
        product_type: ProductType,
        data_store: Optional[DataStoreInterface] = None,
    ) -> BaseExtractor:
        """Create an extractor for the given product type."""
        if product_type not in cls._extractors:
            raise ValueError(f"Unknown product type: {product_type}")
        
        extractor_class = cls._extractors[product_type]
        return extractor_class(data_store=data_store)
    
    @classmethod
    def get_all_extractors(
        cls,
        data_store: Optional[DataStoreInterface] = None,
    ) -> Dict[ProductType, BaseExtractor]:
        """Get all extractors."""
        return {
            product_type: cls.create(product_type, data_store)
            for product_type in cls._extractors
        }


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_extractor(
    product_type: ProductType,
    data_store: Optional[DataStoreInterface] = None,
) -> BaseExtractor:
    """Create an extractor for the given product type."""
    return ExtractorFactory.create(product_type, data_store)


def create_data_source_validator() -> DataSourceValidator:
    """Create a data source validator."""
    return DataSourceValidator()
