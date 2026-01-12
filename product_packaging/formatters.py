"""
Product Data Packaging - Output Formatters.

============================================================
PURPOSE
============================================================
Format transformed data into standardized output formats:
- JSON
- CSV
- Parquet (optional)

All exports include comprehensive metadata.

============================================================
REQUIREMENTS
============================================================
Every export must include:
- Schema version
- Data description
- Update frequency
- Known limitations
- Export timestamp
- Checksum

============================================================
"""

import csv
import io
import json
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import logging


from .models import (
    ProductType,
    ProductSchema,
    OutputFormat,
    TimeBucket,
    ExportMetadata,
)
from .transformers import TransformedRecord


logger = logging.getLogger(__name__)


# ============================================================
# FORMATTED OUTPUT
# ============================================================

@dataclass
class FormattedOutput:
    """Formatted data output."""
    format: OutputFormat
    content: Union[str, bytes]
    metadata: ExportMetadata
    
    # Content info
    content_type: str = "application/json"
    file_extension: str = ".json"
    
    # Size info
    size_bytes: int = 0
    record_count: int = 0
    
    # Compression (optional)
    is_compressed: bool = False
    compression_type: Optional[str] = None


# ============================================================
# BASE FORMATTER
# ============================================================

class BaseFormatter(ABC):
    """Base class for output formatters."""
    
    @property
    @abstractmethod
    def format(self) -> OutputFormat:
        """Output format this formatter produces."""
        pass
    
    @property
    @abstractmethod
    def content_type(self) -> str:
        """MIME type of the output."""
        pass
    
    @property
    @abstractmethod
    def file_extension(self) -> str:
        """File extension for the output."""
        pass
    
    @abstractmethod
    def format_records(
        self,
        records: List[TransformedRecord],
        metadata: ExportMetadata,
    ) -> FormattedOutput:
        """Format records into output."""
        pass
    
    def _calculate_checksum(self, content: Union[str, bytes]) -> str:
        """Calculate SHA-256 checksum of content."""
        if isinstance(content, str):
            content = content.encode("utf-8")
        return hashlib.sha256(content).hexdigest()


# ============================================================
# JSON FORMATTER
# ============================================================

class JsonFormatter(BaseFormatter):
    """Formats data as JSON."""
    
    def __init__(self, pretty: bool = True, include_metadata: bool = True):
        self._pretty = pretty
        self._include_metadata = include_metadata
    
    @property
    def format(self) -> OutputFormat:
        return OutputFormat.JSON
    
    @property
    def content_type(self) -> str:
        return "application/json"
    
    @property
    def file_extension(self) -> str:
        return ".json"
    
    def format_records(
        self,
        records: List[TransformedRecord],
        metadata: ExportMetadata,
    ) -> FormattedOutput:
        """Format records as JSON."""
        # Build data array
        data_array = []
        for record in records:
            record_data = dict(record.data)
            record_data["_record_id"] = record.record_id
            record_data["_timestamp_bucket"] = record.timestamp_bucket.isoformat()
            record_data["_time_bucket_size"] = record.time_bucket_size.value
            data_array.append(record_data)
        
        # Build output structure
        output = {
            "data": data_array,
        }
        
        if self._include_metadata:
            output["metadata"] = metadata.to_dict()
        
        # Serialize
        if self._pretty:
            content = json.dumps(output, indent=2, default=str)
        else:
            content = json.dumps(output, default=str)
        
        # Calculate checksum
        checksum = self._calculate_checksum(content)
        
        # Update metadata with checksum
        metadata.checksum = checksum
        if self._include_metadata:
            output["metadata"]["export"]["checksum"] = checksum
            if self._pretty:
                content = json.dumps(output, indent=2, default=str)
            else:
                content = json.dumps(output, default=str)
        
        return FormattedOutput(
            format=self.format,
            content=content,
            metadata=metadata,
            content_type=self.content_type,
            file_extension=self.file_extension,
            size_bytes=len(content.encode("utf-8")),
            record_count=len(records),
        )


# ============================================================
# CSV FORMATTER
# ============================================================

class CsvFormatter(BaseFormatter):
    """Formats data as CSV."""
    
    def __init__(
        self,
        delimiter: str = ",",
        include_header: bool = True,
        quote_strings: bool = True,
    ):
        self._delimiter = delimiter
        self._include_header = include_header
        self._quote_strings = quote_strings
    
    @property
    def format(self) -> OutputFormat:
        return OutputFormat.CSV
    
    @property
    def content_type(self) -> str:
        return "text/csv"
    
    @property
    def file_extension(self) -> str:
        return ".csv"
    
    def format_records(
        self,
        records: List[TransformedRecord],
        metadata: ExportMetadata,
    ) -> FormattedOutput:
        """Format records as CSV."""
        if not records:
            return FormattedOutput(
                format=self.format,
                content="",
                metadata=metadata,
                content_type=self.content_type,
                file_extension=self.file_extension,
                size_bytes=0,
                record_count=0,
            )
        
        # Collect all field names
        all_fields = set()
        for record in records:
            all_fields.update(record.data.keys())
        
        # Add standard fields
        standard_fields = ["_record_id", "_timestamp_bucket", "_time_bucket_size"]
        fieldnames = standard_fields + sorted(all_fields)
        
        # Write CSV
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=fieldnames,
            delimiter=self._delimiter,
            quoting=csv.QUOTE_MINIMAL if self._quote_strings else csv.QUOTE_NONE,
        )
        
        if self._include_header:
            writer.writeheader()
        
        for record in records:
            row = dict(record.data)
            row["_record_id"] = record.record_id
            row["_timestamp_bucket"] = record.timestamp_bucket.isoformat()
            row["_time_bucket_size"] = record.time_bucket_size.value
            writer.writerow(row)
        
        content = output.getvalue()
        
        # Calculate checksum
        checksum = self._calculate_checksum(content)
        metadata.checksum = checksum
        
        return FormattedOutput(
            format=self.format,
            content=content,
            metadata=metadata,
            content_type=self.content_type,
            file_extension=self.file_extension,
            size_bytes=len(content.encode("utf-8")),
            record_count=len(records),
        )
    
    def format_metadata_csv(self, metadata: ExportMetadata) -> str:
        """Format metadata as a separate CSV."""
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow(["field", "value"])
        
        meta_dict = metadata.to_dict()
        
        def flatten_dict(d: Dict, prefix: str = "") -> List[tuple]:
            items = []
            for k, v in d.items():
                key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    items.extend(flatten_dict(v, key))
                else:
                    items.append((key, v))
            return items
        
        for key, value in flatten_dict(meta_dict):
            writer.writerow([key, value])
        
        return output.getvalue()


# ============================================================
# PARQUET FORMATTER
# ============================================================

class ParquetFormatter(BaseFormatter):
    """
    Formats data as Parquet.
    
    Note: Requires pyarrow or fastparquet library.
    Falls back to JSON if not available.
    """
    
    def __init__(self):
        self._parquet_available = self._check_parquet_available()
    
    def _check_parquet_available(self) -> bool:
        """Check if parquet library is available."""
        try:
            import pyarrow  # noqa: F401
            return True
        except ImportError:
            try:
                import fastparquet  # noqa: F401
                return True
            except ImportError:
                logger.warning(
                    "Parquet library not available. "
                    "Install pyarrow or fastparquet for Parquet support."
                )
                return False
    
    @property
    def format(self) -> OutputFormat:
        return OutputFormat.PARQUET
    
    @property
    def content_type(self) -> str:
        return "application/octet-stream"
    
    @property
    def file_extension(self) -> str:
        return ".parquet"
    
    def format_records(
        self,
        records: List[TransformedRecord],
        metadata: ExportMetadata,
    ) -> FormattedOutput:
        """Format records as Parquet."""
        if not self._parquet_available:
            # Fall back to JSON
            logger.warning("Parquet not available, falling back to JSON")
            json_formatter = JsonFormatter()
            output = json_formatter.format_records(records, metadata)
            output.format = OutputFormat.PARQUET  # Mark as intended Parquet
            return output
        
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            
            # Build data for table
            data = []
            for record in records:
                row = dict(record.data)
                row["_record_id"] = record.record_id
                row["_timestamp_bucket"] = record.timestamp_bucket.isoformat()
                row["_time_bucket_size"] = record.time_bucket_size.value
                data.append(row)
            
            if not data:
                return FormattedOutput(
                    format=self.format,
                    content=b"",
                    metadata=metadata,
                    content_type=self.content_type,
                    file_extension=self.file_extension,
                    size_bytes=0,
                    record_count=0,
                )
            
            # Create table
            table = pa.Table.from_pylist(data)
            
            # Add metadata to table
            meta_json = json.dumps(metadata.to_dict())
            table = table.replace_schema_metadata({
                "product_metadata": meta_json,
            })
            
            # Write to buffer
            buffer = io.BytesIO()
            pq.write_table(table, buffer)
            content = buffer.getvalue()
            
            # Calculate checksum
            checksum = self._calculate_checksum(content)
            metadata.checksum = checksum
            
            return FormattedOutput(
                format=self.format,
                content=content,
                metadata=metadata,
                content_type=self.content_type,
                file_extension=self.file_extension,
                size_bytes=len(content),
                record_count=len(records),
            )
            
        except Exception as e:
            logger.error(f"Error formatting Parquet: {e}")
            # Fall back to JSON
            json_formatter = JsonFormatter()
            return json_formatter.format_records(records, metadata)


# ============================================================
# METADATA BUILDER
# ============================================================

class MetadataBuilder:
    """Builds export metadata."""
    
    def __init__(self, schema: ProductSchema):
        self._schema = schema
    
    def build(
        self,
        export_id: str,
        product_id: str,
        records: List[TransformedRecord],
        output_format: OutputFormat,
    ) -> ExportMetadata:
        """Build export metadata."""
        if not records:
            now = datetime.utcnow()
            return ExportMetadata(
                export_id=export_id,
                product_id=product_id,
                product_type=self._schema.product_type,
                schema_version=self._schema.version.version_string,
                data_start_time=now,
                data_end_time=now,
                time_bucket=TimeBucket.HOUR_1,
                record_count=0,
                aggregation_method="none",
                data_freshness_seconds=0,
                completeness_ratio=0.0,
                exported_at=now,
                format=output_format,
                checksum="",
                schema_checksum=self._schema.get_checksum(),
                known_limitations=self._schema.known_limitations,
                update_frequency=self._schema.update_frequency,
            )
        
        # Calculate time range
        start_time = min(r.timestamp_bucket for r in records)
        end_time = max(r.timestamp_bucket for r in records)
        
        # Get time bucket from first record
        time_bucket = records[0].time_bucket_size
        
        # Get aggregation method
        aggregation_method = records[0].aggregation_method
        
        # Calculate freshness (time since newest data)
        now = datetime.utcnow()
        freshness = (now - end_time).total_seconds()
        
        # Calculate completeness
        avg_completeness = sum(r.completeness for r in records) / len(records)
        
        return ExportMetadata(
            export_id=export_id,
            product_id=product_id,
            product_type=self._schema.product_type,
            schema_version=self._schema.version.version_string,
            data_start_time=start_time,
            data_end_time=end_time,
            time_bucket=time_bucket,
            record_count=len(records),
            aggregation_method=aggregation_method,
            data_freshness_seconds=int(freshness),
            completeness_ratio=avg_completeness,
            exported_at=now,
            format=output_format,
            checksum="",  # Will be calculated by formatter
            schema_checksum=self._schema.get_checksum(),
            known_limitations=self._schema.known_limitations,
            update_frequency=self._schema.update_frequency,
        )


# ============================================================
# FORMATTER FACTORY
# ============================================================

class FormatterFactory:
    """Factory for creating formatters."""
    
    @staticmethod
    def create(format: OutputFormat) -> BaseFormatter:
        """Create a formatter for the given format."""
        if format == OutputFormat.JSON:
            return JsonFormatter()
        elif format == OutputFormat.CSV:
            return CsvFormatter()
        elif format == OutputFormat.PARQUET:
            return ParquetFormatter()
        else:
            raise ValueError(f"Unknown format: {format}")
    
    @staticmethod
    def get_all_formatters() -> Dict[OutputFormat, BaseFormatter]:
        """Get all available formatters."""
        return {
            OutputFormat.JSON: JsonFormatter(),
            OutputFormat.CSV: CsvFormatter(),
            OutputFormat.PARQUET: ParquetFormatter(),
        }


# ============================================================
# OUTPUT MANAGER
# ============================================================

class OutputManager:
    """
    Manages output formatting.
    
    Provides a unified interface for all formatters.
    """
    
    def __init__(self):
        self._formatters = FormatterFactory.get_all_formatters()
    
    def format(
        self,
        records: List[TransformedRecord],
        metadata: ExportMetadata,
        output_format: OutputFormat,
    ) -> FormattedOutput:
        """Format records into the specified format."""
        if output_format not in self._formatters:
            raise ValueError(f"Unknown format: {output_format}")
        
        formatter = self._formatters[output_format]
        return formatter.format_records(records, metadata)
    
    def get_supported_formats(self) -> List[OutputFormat]:
        """Get list of supported formats."""
        return list(self._formatters.keys())
    
    def get_content_type(self, output_format: OutputFormat) -> str:
        """Get MIME type for a format."""
        if output_format not in self._formatters:
            return "application/octet-stream"
        return self._formatters[output_format].content_type
    
    def get_file_extension(self, output_format: OutputFormat) -> str:
        """Get file extension for a format."""
        if output_format not in self._formatters:
            return ".bin"
        return self._formatters[output_format].file_extension


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_json_formatter(pretty: bool = True) -> JsonFormatter:
    """Create a JSON formatter."""
    return JsonFormatter(pretty=pretty)


def create_csv_formatter(delimiter: str = ",") -> CsvFormatter:
    """Create a CSV formatter."""
    return CsvFormatter(delimiter=delimiter)


def create_parquet_formatter() -> ParquetFormatter:
    """Create a Parquet formatter."""
    return ParquetFormatter()


def create_formatter(output_format: OutputFormat) -> BaseFormatter:
    """Create a formatter for the given format."""
    return FormatterFactory.create(output_format)


def create_output_manager() -> OutputManager:
    """Create an output manager."""
    return OutputManager()


def create_metadata_builder(schema: ProductSchema) -> MetadataBuilder:
    """Create a metadata builder."""
    return MetadataBuilder(schema)
