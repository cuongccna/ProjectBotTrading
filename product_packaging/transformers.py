"""
Product Data Packaging - Data Transformers.

============================================================
PURPOSE
============================================================
Transform extracted data into non-actionable, aggregated,
normalized products ready for external consumption.

============================================================
TRANSFORMATIONS
============================================================
1. Time Delay - Ensure data is not real-time
2. Aggregation - Combine individual records
3. Normalization - Scale values to standard ranges
4. Rolling Windows - Smooth data over time
5. Bucketing - Group data into time buckets

============================================================
NON-ACTIONABLE DESIGN
============================================================
All transformations are designed to prevent the data from
being directly actionable for trading decisions.

============================================================
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from statistics import mean, median, stdev
from typing import Any, Callable, Dict, List, Optional, Tuple
import logging
import math


from .models import (
    ProductType,
    TimeBucket,
    AggregationConfig,
    DelayConfig,
    NormalizationConfig,
)
from .extractors import ExtractedRecord


logger = logging.getLogger(__name__)


# ============================================================
# TRANSFORMED DATA MODELS
# ============================================================

@dataclass
class TransformedRecord:
    """A record after transformation."""
    record_id: str
    product_type: ProductType
    timestamp_bucket: datetime
    time_bucket_size: TimeBucket
    data: Dict[str, Any]
    
    # Aggregation info
    record_count: int = 1
    aggregation_method: str = "none"
    
    # Quality info
    completeness: float = 1.0
    
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransformationResult:
    """Result of a transformation operation."""
    success: bool
    product_type: ProductType
    records: List[TransformedRecord]
    record_count: int
    original_count: int
    
    # Timing
    start_time: datetime
    end_time: datetime
    transformation_timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Quality
    completeness_ratio: float = 1.0
    
    # Errors
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


# ============================================================
# TIME DELAY TRANSFORMER
# ============================================================

class TimeDelayTransformer:
    """
    Applies time delay to data.
    
    CRITICAL: Data must be delayed to be non-actionable.
    """
    
    def __init__(self, config: DelayConfig):
        self._config = config
        self._min_delay = timedelta(seconds=config.min_delay_seconds)
    
    def should_include(self, record: ExtractedRecord, as_of: datetime = None) -> bool:
        """Check if a record should be included based on delay."""
        if as_of is None:
            as_of = datetime.utcnow()
        
        cutoff = as_of - self._min_delay
        return record.timestamp <= cutoff
    
    def filter_by_delay(
        self,
        records: List[ExtractedRecord],
        as_of: datetime = None,
    ) -> List[ExtractedRecord]:
        """Filter records to only include delayed data."""
        if as_of is None:
            as_of = datetime.utcnow()
        
        cutoff = as_of - self._min_delay
        
        filtered = [r for r in records if r.timestamp <= cutoff]
        
        excluded_count = len(records) - len(filtered)
        if excluded_count > 0:
            logger.debug(
                f"Excluded {excluded_count} records due to delay requirement"
            )
        
        return filtered
    
    def get_delay_seconds(self) -> int:
        """Get current delay in seconds."""
        return self._config.min_delay_seconds


# ============================================================
# TIME BUCKET TRANSFORMER
# ============================================================

class TimeBucketTransformer:
    """Transforms records into time buckets."""
    
    def __init__(self, time_bucket: TimeBucket):
        self._time_bucket = time_bucket
        self._bucket_seconds = time_bucket.seconds
    
    def get_bucket_start(self, timestamp: datetime) -> datetime:
        """Get the start of the bucket for a timestamp."""
        # Truncate to bucket boundary
        epoch = datetime(1970, 1, 1)
        total_seconds = (timestamp - epoch).total_seconds()
        bucket_start_seconds = (
            int(total_seconds // self._bucket_seconds) * self._bucket_seconds
        )
        return epoch + timedelta(seconds=bucket_start_seconds)
    
    def group_by_bucket(
        self,
        records: List[ExtractedRecord],
    ) -> Dict[datetime, List[ExtractedRecord]]:
        """Group records by time bucket."""
        buckets: Dict[datetime, List[ExtractedRecord]] = defaultdict(list)
        
        for record in records:
            bucket_start = self.get_bucket_start(record.timestamp)
            buckets[bucket_start].append(record)
        
        return dict(buckets)
    
    def group_by_bucket_and_symbol(
        self,
        records: List[ExtractedRecord],
    ) -> Dict[Tuple[datetime, str], List[ExtractedRecord]]:
        """Group records by time bucket and symbol."""
        buckets: Dict[Tuple[datetime, str], List[ExtractedRecord]] = defaultdict(list)
        
        for record in records:
            bucket_start = self.get_bucket_start(record.timestamp)
            symbol = record.symbol or "UNKNOWN"
            buckets[(bucket_start, symbol)].append(record)
        
        return dict(buckets)


# ============================================================
# AGGREGATION TRANSFORMER
# ============================================================

class AggregationMethod(Enum):
    """Aggregation methods."""
    MEAN = "mean"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"
    SUM = "sum"
    COUNT = "count"
    MODE = "mode"
    FIRST = "first"
    LAST = "last"


class AggregationTransformer:
    """
    Aggregates multiple records into single values.
    
    CRITICAL: Aggregation helps make data non-actionable.
    """
    
    def __init__(self, config: AggregationConfig):
        self._config = config
        self._method = AggregationMethod(config.method)
        self._min_samples = config.min_samples
    
    def aggregate_values(self, values: List[float]) -> Optional[float]:
        """Aggregate a list of values."""
        if len(values) < self._min_samples:
            logger.debug(
                f"Insufficient samples ({len(values)}) for aggregation "
                f"(minimum: {self._min_samples})"
            )
            return None
        
        if self._method == AggregationMethod.MEAN:
            return mean(values)
        elif self._method == AggregationMethod.MEDIAN:
            return median(values)
        elif self._method == AggregationMethod.MIN:
            return min(values)
        elif self._method == AggregationMethod.MAX:
            return max(values)
        elif self._method == AggregationMethod.SUM:
            return sum(values)
        elif self._method == AggregationMethod.COUNT:
            return float(len(values))
        elif self._method == AggregationMethod.FIRST:
            return values[0]
        elif self._method == AggregationMethod.LAST:
            return values[-1]
        else:
            return mean(values)  # Default to mean
    
    def aggregate_categorical(self, values: List[str]) -> Optional[str]:
        """Aggregate categorical values (mode)."""
        if len(values) < self._min_samples:
            return None
        
        # Return most common value
        counts = defaultdict(int)
        for v in values:
            counts[v] += 1
        return max(counts, key=counts.get)
    
    def aggregate_records(
        self,
        records: List[ExtractedRecord],
        numeric_fields: List[str],
        categorical_fields: List[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate multiple records into one."""
        if len(records) < self._min_samples:
            return {}
        
        result = {}
        
        # Aggregate numeric fields
        for field in numeric_fields:
            values = []
            for record in records:
                if field in record.data:
                    try:
                        values.append(float(record.data[field]))
                    except (ValueError, TypeError):
                        pass
            
            if values:
                aggregated = self.aggregate_values(values)
                if aggregated is not None:
                    result[field] = aggregated
        
        # Aggregate categorical fields
        if categorical_fields:
            for field in categorical_fields:
                values = []
                for record in records:
                    if field in record.data:
                        values.append(str(record.data[field]))
                
                if values:
                    aggregated = self.aggregate_categorical(values)
                    if aggregated is not None:
                        result[field] = aggregated
        
        return result
    
    def meets_minimum_samples(self, count: int) -> bool:
        """Check if count meets minimum sample requirement."""
        return count >= self._min_samples


# ============================================================
# NORMALIZATION TRANSFORMER
# ============================================================

class NormalizationTransformer:
    """
    Normalizes values to standard ranges.
    
    CRITICAL: Normalization helps obscure absolute values.
    """
    
    def __init__(self, config: NormalizationConfig):
        self._config = config
        self._method = config.method
        self._min_value = config.min_value
        self._max_value = config.max_value
        self._clip_outliers = config.clip_outliers
        self._outlier_threshold = config.outlier_threshold
    
    def normalize_value(
        self,
        value: float,
        data_min: float,
        data_max: float,
        data_mean: float = 0.0,
        data_std: float = 1.0,
    ) -> float:
        """Normalize a single value."""
        if self._method == "none":
            return value
        
        if self._method == "min_max":
            if data_max == data_min:
                return (self._min_value + self._max_value) / 2
            normalized = (value - data_min) / (data_max - data_min)
            return self._min_value + normalized * (self._max_value - self._min_value)
        
        elif self._method == "z_score":
            if data_std == 0:
                return 0.0
            z_score = (value - data_mean) / data_std
            
            # Clip outliers
            if self._clip_outliers:
                z_score = max(-self._outlier_threshold, 
                             min(self._outlier_threshold, z_score))
            
            # Scale to range
            normalized = (z_score + self._outlier_threshold) / (2 * self._outlier_threshold)
            return self._min_value + normalized * (self._max_value - self._min_value)
        
        elif self._method == "percentile":
            # Requires full dataset, so just do min-max here
            return self.normalize_value(value, data_min, data_max)
        
        return value
    
    def normalize_series(self, values: List[float]) -> List[float]:
        """Normalize a series of values."""
        if not values or self._method == "none":
            return values
        
        data_min = min(values)
        data_max = max(values)
        data_mean = mean(values) if values else 0.0
        data_std = stdev(values) if len(values) > 1 else 1.0
        
        return [
            self.normalize_value(v, data_min, data_max, data_mean, data_std)
            for v in values
        ]
    
    def normalize_dict(
        self,
        data: Dict[str, Any],
        numeric_fields: List[str],
        stats: Dict[str, Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Normalize numeric fields in a dictionary."""
        if self._method == "none":
            return data
        
        result = dict(data)
        
        for field in numeric_fields:
            if field in result:
                try:
                    value = float(result[field])
                    
                    # Get stats for this field
                    if stats and field in stats:
                        field_stats = stats[field]
                        normalized = self.normalize_value(
                            value,
                            field_stats.get("min", 0.0),
                            field_stats.get("max", 1.0),
                            field_stats.get("mean", 0.5),
                            field_stats.get("std", 1.0),
                        )
                    else:
                        # Assume already in valid range, just clip
                        normalized = max(self._min_value, 
                                       min(self._max_value, value))
                    
                    result[field] = round(normalized, 6)
                except (ValueError, TypeError):
                    pass
        
        return result


# ============================================================
# ROLLING WINDOW TRANSFORMER
# ============================================================

class RollingWindowTransformer:
    """Applies rolling window smoothing to data."""
    
    def __init__(self, window_size: int = 3):
        self._window_size = window_size
    
    def apply_rolling_mean(self, values: List[float]) -> List[float]:
        """Apply rolling mean to values."""
        if len(values) < self._window_size:
            return values
        
        result = []
        for i in range(len(values)):
            start = max(0, i - self._window_size + 1)
            window = values[start:i + 1]
            result.append(mean(window))
        
        return result
    
    def apply_to_records(
        self,
        records: List[TransformedRecord],
        field: str,
    ) -> List[TransformedRecord]:
        """Apply rolling window to a field in records."""
        if len(records) < self._window_size:
            return records
        
        # Sort by timestamp
        sorted_records = sorted(records, key=lambda r: r.timestamp_bucket)
        
        # Extract values
        values = []
        for record in sorted_records:
            if field in record.data:
                try:
                    values.append(float(record.data[field]))
                except (ValueError, TypeError):
                    values.append(None)
            else:
                values.append(None)
        
        # Apply rolling mean where possible
        valid_indices = [i for i, v in enumerate(values) if v is not None]
        if len(valid_indices) >= self._window_size:
            valid_values = [values[i] for i in valid_indices]
            smoothed = self.apply_rolling_mean(valid_values)
            
            for idx, original_idx in enumerate(valid_indices):
                sorted_records[original_idx].data[field] = round(smoothed[idx], 6)
        
        return sorted_records


# ============================================================
# COMPOSITE TRANSFORMER
# ============================================================

class ProductTransformer:
    """
    Composite transformer for complete product transformation.
    
    Applies all transformations in order:
    1. Time delay filtering
    2. Time bucketing
    3. Aggregation
    4. Normalization
    5. Optional rolling window
    """
    
    def __init__(
        self,
        product_type: ProductType,
        aggregation_config: AggregationConfig,
        delay_config: DelayConfig,
        normalization_config: NormalizationConfig,
        enable_rolling_window: bool = False,
        rolling_window_size: int = 3,
    ):
        self._product_type = product_type
        self._delay = TimeDelayTransformer(delay_config)
        self._bucket = TimeBucketTransformer(aggregation_config.time_bucket)
        self._aggregation = AggregationTransformer(aggregation_config)
        self._normalization = NormalizationTransformer(normalization_config)
        self._rolling = RollingWindowTransformer(rolling_window_size) if enable_rolling_window else None
        self._time_bucket = aggregation_config.time_bucket
    
    def transform(
        self,
        records: List[ExtractedRecord],
        numeric_fields: List[str],
        categorical_fields: List[str] = None,
        as_of: datetime = None,
    ) -> TransformationResult:
        """Transform extracted records into product records."""
        if as_of is None:
            as_of = datetime.utcnow()
        
        original_count = len(records)
        
        if not records:
            return TransformationResult(
                success=True,
                product_type=self._product_type,
                records=[],
                record_count=0,
                original_count=0,
                start_time=as_of,
                end_time=as_of,
            )
        
        # Step 1: Apply time delay
        delayed_records = self._delay.filter_by_delay(records, as_of)
        
        if not delayed_records:
            return TransformationResult(
                success=True,
                product_type=self._product_type,
                records=[],
                record_count=0,
                original_count=original_count,
                start_time=as_of,
                end_time=as_of,
                warnings=["All records filtered due to delay requirement"],
            )
        
        # Step 2: Group by bucket and symbol
        grouped = self._bucket.group_by_bucket_and_symbol(delayed_records)
        
        # Step 3: Aggregate and normalize each group
        transformed_records = []
        warnings = []
        
        for (bucket_start, symbol), group_records in grouped.items():
            # Check minimum samples
            if not self._aggregation.meets_minimum_samples(len(group_records)):
                warnings.append(
                    f"Insufficient samples for {symbol} at {bucket_start}"
                )
                continue
            
            # Aggregate
            aggregated = self._aggregation.aggregate_records(
                group_records,
                numeric_fields,
                categorical_fields,
            )
            
            if not aggregated:
                continue
            
            # Add symbol and timestamp
            aggregated["symbol"] = symbol
            aggregated["timestamp_bucket"] = bucket_start.isoformat()
            aggregated["time_bucket_size"] = self._time_bucket.value
            
            # Normalize
            normalized = self._normalization.normalize_dict(
                aggregated,
                numeric_fields,
            )
            
            # Add source count
            normalized["source_count"] = len(group_records)
            
            # Create transformed record
            record = TransformedRecord(
                record_id=f"{self._product_type.value}_{bucket_start.isoformat()}_{symbol}",
                product_type=self._product_type,
                timestamp_bucket=bucket_start,
                time_bucket_size=self._time_bucket,
                data=normalized,
                record_count=len(group_records),
                aggregation_method=self._aggregation._method.value,
            )
            transformed_records.append(record)
        
        # Step 4: Apply rolling window if enabled
        if self._rolling and transformed_records and numeric_fields:
            # Group by symbol for rolling window
            by_symbol = defaultdict(list)
            for record in transformed_records:
                symbol = record.data.get("symbol", "UNKNOWN")
                by_symbol[symbol].append(record)
            
            # Apply to each symbol group
            smoothed_records = []
            for symbol, symbol_records in by_symbol.items():
                for field in numeric_fields:
                    symbol_records = self._rolling.apply_to_records(
                        symbol_records, field
                    )
                smoothed_records.extend(symbol_records)
            
            transformed_records = smoothed_records
        
        # Determine time range
        if transformed_records:
            start_time = min(r.timestamp_bucket for r in transformed_records)
            end_time = max(r.timestamp_bucket for r in transformed_records)
        else:
            start_time = end_time = as_of
        
        # Calculate completeness
        expected_buckets = len(grouped)
        actual_buckets = len(transformed_records)
        completeness = actual_buckets / expected_buckets if expected_buckets > 0 else 1.0
        
        return TransformationResult(
            success=True,
            product_type=self._product_type,
            records=transformed_records,
            record_count=len(transformed_records),
            original_count=original_count,
            start_time=start_time,
            end_time=end_time,
            completeness_ratio=completeness,
            warnings=warnings,
        )


# ============================================================
# TRANSFORMER FACTORY
# ============================================================

def create_delay_transformer(config: DelayConfig) -> TimeDelayTransformer:
    """Create a time delay transformer."""
    return TimeDelayTransformer(config)


def create_bucket_transformer(time_bucket: TimeBucket) -> TimeBucketTransformer:
    """Create a time bucket transformer."""
    return TimeBucketTransformer(time_bucket)


def create_aggregation_transformer(config: AggregationConfig) -> AggregationTransformer:
    """Create an aggregation transformer."""
    return AggregationTransformer(config)


def create_normalization_transformer(config: NormalizationConfig) -> NormalizationTransformer:
    """Create a normalization transformer."""
    return NormalizationTransformer(config)


def create_product_transformer(
    product_type: ProductType,
    aggregation_config: AggregationConfig,
    delay_config: DelayConfig,
    normalization_config: NormalizationConfig,
    enable_rolling_window: bool = False,
) -> ProductTransformer:
    """Create a complete product transformer."""
    return ProductTransformer(
        product_type=product_type,
        aggregation_config=aggregation_config,
        delay_config=delay_config,
        normalization_config=normalization_config,
        enable_rolling_window=enable_rolling_window,
    )
