"""
Product Data Packaging - Pipeline.

============================================================
PURPOSE
============================================================
Orchestrate the complete data packaging pipeline:
1. Extract data from retained sources
2. Transform data (delay, aggregate, normalize)
3. Validate safety (non-actionable, anonymized)
4. Format output (JSON, CSV, Parquet)

============================================================
PIPELINE FLOW
============================================================

    Retained Data
         |
         v
    [EXTRACTOR]  <- Read-only access
         |
         v
    Extracted Records
         |
         v
    [TRANSFORMER] <- Delay, Aggregate, Normalize
         |
         v
    Transformed Records
         |
         v
    [SAFETY CHECKER] <- Non-actionable, Anonymize
         |
         v
    Sanitized Records
         |
         v
    [FORMATTER] <- JSON, CSV, Parquet
         |
         v
    Formatted Output + Metadata

============================================================
FAILURE ISOLATION
============================================================
Pipeline failures must NOT affect trading.
All operations are read-only.

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import logging
import uuid


from .models import (
    ProductType,
    ProductDefinition,
    TimeBucket,
    OutputFormat,
    AllowedDataSource,
    ExportRequest,
    ExportResponse,
    ExportStatus,
    ExportMetadata,
)
from .schemas import (
    ProductSchema,
    get_product_definition,
    create_schema_registry,
)
from .extractors import (
    BaseExtractor,
    ExtractorFactory,
    ExtractionQuery,
    ExtractionResult,
    DataStoreInterface,
)
from .transformers import (
    ProductTransformer,
    TransformedRecord,
    TransformationResult,
    create_product_transformer,
)
from .safety import (
    SafetyChecker,
    SafetyCheckResult,
    create_safety_checker,
)
from .formatters import (
    OutputManager,
    FormattedOutput,
    MetadataBuilder,
    create_output_manager,
    create_metadata_builder,
)


logger = logging.getLogger(__name__)


# ============================================================
# PIPELINE STATUS
# ============================================================

class PipelineStage(Enum):
    """Stages in the packaging pipeline."""
    EXTRACTION = "extraction"
    TRANSFORMATION = "transformation"
    SAFETY_CHECK = "safety_check"
    FORMATTING = "formatting"
    COMPLETE = "complete"


@dataclass
class StageResult:
    """Result of a pipeline stage."""
    stage: PipelineStage
    success: bool
    duration_ms: int
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    record_count: int = 0


@dataclass
class PipelineResult:
    """Result of complete pipeline execution."""
    success: bool
    request_id: str
    product_type: ProductType
    
    # Stage results
    stages: List[StageResult]
    
    # Final output
    output: Optional[FormattedOutput] = None
    
    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_duration_ms: int = 0
    
    # Errors
    error_message: Optional[str] = None
    failed_stage: Optional[PipelineStage] = None
    
    def to_export_response(self) -> ExportResponse:
        """Convert to ExportResponse."""
        return ExportResponse(
            request_id=self.request_id,
            status=ExportStatus.COMPLETED if self.success else ExportStatus.FAILED,
            data=self.output.content if self.output else None,
            metadata=self.output.metadata if self.output else None,
            error_message=self.error_message,
            completed_at=self.completed_at,
            processing_time_ms=self.total_duration_ms,
        )


# ============================================================
# PIPELINE CONFIGURATION
# ============================================================

@dataclass
class PipelineConfig:
    """Configuration for the packaging pipeline."""
    # Timeout settings
    extraction_timeout_seconds: int = 30
    transformation_timeout_seconds: int = 30
    total_timeout_seconds: int = 120
    
    # Limits
    max_records_per_request: int = 10000
    max_time_range_days: int = 365
    
    # Behavior
    fail_fast: bool = True  # Stop on first error
    include_metadata: bool = True
    
    # Retry settings
    max_retries: int = 3
    retry_delay_seconds: int = 1


# ============================================================
# PRODUCT PIPELINE
# ============================================================

class ProductPipeline:
    """
    Pipeline for packaging a specific product type.
    
    Handles extraction → transformation → safety → formatting.
    """
    
    def __init__(
        self,
        product_definition: ProductDefinition,
        data_store: Optional[DataStoreInterface] = None,
        config: Optional[PipelineConfig] = None,
    ):
        self._definition = product_definition
        self._config = config or PipelineConfig()
        
        # Create components
        self._extractor = ExtractorFactory.create(
            product_definition.product_type,
            data_store,
        )
        
        self._transformer = create_product_transformer(
            product_type=product_definition.product_type,
            aggregation_config=product_definition.aggregation,
            delay_config=product_definition.delay,
            normalization_config=product_definition.normalization,
        )
        
        self._safety_checker = create_safety_checker()
        self._output_manager = create_output_manager()
        self._metadata_builder = create_metadata_builder(product_definition.schema)
    
    @property
    def product_type(self) -> ProductType:
        """Product type this pipeline serves."""
        return self._definition.product_type
    
    @property
    def supported_formats(self) -> List[OutputFormat]:
        """Supported output formats."""
        return self._definition.supported_formats
    
    async def execute(self, request: ExportRequest) -> PipelineResult:
        """Execute the complete pipeline."""
        request_id = request.request_id
        stages = []
        started_at = datetime.utcnow()
        
        logger.info(
            f"Starting pipeline for {self.product_type.value}, "
            f"request: {request_id}"
        )
        
        try:
            # Validate request
            validation_error = self._validate_request(request)
            if validation_error:
                return PipelineResult(
                    success=False,
                    request_id=request_id,
                    product_type=self.product_type,
                    stages=stages,
                    error_message=validation_error,
                    started_at=started_at,
                    completed_at=datetime.utcnow(),
                )
            
            # Stage 1: Extraction
            extraction_result, extraction_stage = await self._run_extraction(request)
            stages.append(extraction_stage)
            
            if not extraction_result.success:
                return self._build_failure_result(
                    request_id,
                    stages,
                    started_at,
                    PipelineStage.EXTRACTION,
                    extraction_result.error_message,
                )
            
            # Stage 2: Transformation
            transform_result, transform_stage = self._run_transformation(
                extraction_result.records
            )
            stages.append(transform_stage)
            
            if not transform_result.success:
                return self._build_failure_result(
                    request_id,
                    stages,
                    started_at,
                    PipelineStage.TRANSFORMATION,
                    transform_result.error_message,
                )
            
            # Stage 3: Safety Check
            safe_records, safety_result, safety_stage = self._run_safety_check(
                transform_result.records
            )
            stages.append(safety_stage)
            
            if not safety_result.is_safe and self._config.fail_fast:
                return self._build_failure_result(
                    request_id,
                    stages,
                    started_at,
                    PipelineStage.SAFETY_CHECK,
                    f"Safety check failed: {safety_result.issues}",
                )
            
            # Stage 4: Formatting
            output, format_stage = self._run_formatting(
                safe_records,
                request,
            )
            stages.append(format_stage)
            
            if output is None:
                return self._build_failure_result(
                    request_id,
                    stages,
                    started_at,
                    PipelineStage.FORMATTING,
                    "Formatting failed",
                )
            
            # Success
            completed_at = datetime.utcnow()
            total_duration = int((completed_at - started_at).total_seconds() * 1000)
            
            logger.info(
                f"Pipeline completed for {self.product_type.value}, "
                f"request: {request_id}, records: {len(safe_records)}, "
                f"duration: {total_duration}ms"
            )
            
            return PipelineResult(
                success=True,
                request_id=request_id,
                product_type=self.product_type,
                stages=stages,
                output=output,
                started_at=started_at,
                completed_at=completed_at,
                total_duration_ms=total_duration,
            )
            
        except Exception as e:
            logger.error(
                f"Pipeline error for {self.product_type.value}: {e}",
                exc_info=True,
            )
            return PipelineResult(
                success=False,
                request_id=request_id,
                product_type=self.product_type,
                stages=stages,
                error_message=str(e),
                started_at=started_at,
                completed_at=datetime.utcnow(),
            )
    
    def _validate_request(self, request: ExportRequest) -> Optional[str]:
        """Validate the export request."""
        # Check time range
        time_range = request.end_time - request.start_time
        max_range = timedelta(days=self._config.max_time_range_days)
        
        if time_range > max_range:
            return (
                f"Time range too large: {time_range.days} days "
                f"(max: {self._config.max_time_range_days} days)"
            )
        
        if request.start_time >= request.end_time:
            return "Start time must be before end time"
        
        # Check format
        if request.format not in self.supported_formats:
            return (
                f"Format {request.format.value} not supported. "
                f"Supported: {[f.value for f in self.supported_formats]}"
            )
        
        return None
    
    async def _run_extraction(
        self,
        request: ExportRequest,
    ) -> tuple[ExtractionResult, StageResult]:
        """Run the extraction stage."""
        start = datetime.utcnow()
        
        try:
            # Use first allowed source
            source = self._definition.allowed_sources[0]
            
            query = ExtractionQuery(
                source=source,
                product_type=self.product_type,
                start_time=request.start_time,
                end_time=request.end_time,
                symbols=request.symbols,
                time_bucket=request.time_bucket,
                limit=self._config.max_records_per_request,
            )
            
            result = await self._extractor.extract(query)
            
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)
            
            return result, StageResult(
                stage=PipelineStage.EXTRACTION,
                success=result.success,
                duration_ms=duration,
                error_message=result.error_message,
                warnings=result.warnings,
                record_count=result.record_count,
            )
            
        except Exception as e:
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)
            return ExtractionResult(
                success=False,
                source=self._definition.allowed_sources[0],
                records=[],
                record_count=0,
                start_time=request.start_time,
                end_time=request.end_time,
                error_message=str(e),
            ), StageResult(
                stage=PipelineStage.EXTRACTION,
                success=False,
                duration_ms=duration,
                error_message=str(e),
            )
    
    def _run_transformation(
        self,
        records: list,
    ) -> tuple[TransformationResult, StageResult]:
        """Run the transformation stage."""
        start = datetime.utcnow()
        
        try:
            # Get numeric and categorical fields from schema
            numeric_fields = []
            categorical_fields = []
            
            for field in self._definition.schema.fields:
                if field.data_type in ("number", "integer"):
                    numeric_fields.append(field.name)
                elif field.data_type == "string" and field.enum_values:
                    categorical_fields.append(field.name)
            
            result = self._transformer.transform(
                records=records,
                numeric_fields=numeric_fields,
                categorical_fields=categorical_fields,
            )
            
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)
            
            return result, StageResult(
                stage=PipelineStage.TRANSFORMATION,
                success=result.success,
                duration_ms=duration,
                error_message=result.error_message,
                warnings=result.warnings,
                record_count=result.record_count,
            )
            
        except Exception as e:
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)
            return TransformationResult(
                success=False,
                product_type=self.product_type,
                records=[],
                record_count=0,
                original_count=len(records),
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
                error_message=str(e),
            ), StageResult(
                stage=PipelineStage.TRANSFORMATION,
                success=False,
                duration_ms=duration,
                error_message=str(e),
            )
    
    def _run_safety_check(
        self,
        records: List[TransformedRecord],
    ) -> tuple[List[TransformedRecord], SafetyCheckResult, StageResult]:
        """Run the safety check stage."""
        start = datetime.utcnow()
        
        try:
            safe_records, result = self._safety_checker.check_and_sanitize(records)
            
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)
            
            return safe_records, result, StageResult(
                stage=PipelineStage.SAFETY_CHECK,
                success=result.is_safe,
                duration_ms=duration,
                warnings=result.issues,
                record_count=len(safe_records),
            )
            
        except Exception as e:
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)
            from .safety import NonActionableCheck
            
            return [], SafetyCheckResult(
                is_safe=False,
                non_actionable_check=NonActionableCheck(
                    is_valid=False,
                    violations=[str(e)],
                    signal_types_found=[],
                    recommendations=[],
                ),
                anonymization_applied=False,
                precision_obscured=False,
                min_aggregation_met=False,
                issues=[str(e)],
            ), StageResult(
                stage=PipelineStage.SAFETY_CHECK,
                success=False,
                duration_ms=duration,
                error_message=str(e),
            )
    
    def _run_formatting(
        self,
        records: List[TransformedRecord],
        request: ExportRequest,
    ) -> tuple[Optional[FormattedOutput], StageResult]:
        """Run the formatting stage."""
        start = datetime.utcnow()
        
        try:
            # Build metadata
            export_id = f"export_{uuid.uuid4().hex[:8]}"
            metadata = self._metadata_builder.build(
                export_id=export_id,
                product_id=self._definition.product_id,
                records=records,
                output_format=request.format,
            )
            
            # Format output
            output = self._output_manager.format(
                records=records,
                metadata=metadata,
                output_format=request.format,
            )
            
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)
            
            return output, StageResult(
                stage=PipelineStage.FORMATTING,
                success=True,
                duration_ms=duration,
                record_count=len(records),
            )
            
        except Exception as e:
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)
            return None, StageResult(
                stage=PipelineStage.FORMATTING,
                success=False,
                duration_ms=duration,
                error_message=str(e),
            )
    
    def _build_failure_result(
        self,
        request_id: str,
        stages: List[StageResult],
        started_at: datetime,
        failed_stage: PipelineStage,
        error_message: str,
    ) -> PipelineResult:
        """Build a failure result."""
        completed_at = datetime.utcnow()
        total_duration = int((completed_at - started_at).total_seconds() * 1000)
        
        logger.warning(
            f"Pipeline failed at {failed_stage.value} for {self.product_type.value}: "
            f"{error_message}"
        )
        
        return PipelineResult(
            success=False,
            request_id=request_id,
            product_type=self.product_type,
            stages=stages,
            error_message=error_message,
            failed_stage=failed_stage,
            started_at=started_at,
            completed_at=completed_at,
            total_duration_ms=total_duration,
        )


# ============================================================
# PIPELINE FACTORY
# ============================================================

class PipelineFactory:
    """Factory for creating pipelines."""
    
    def __init__(
        self,
        data_store: Optional[DataStoreInterface] = None,
        config: Optional[PipelineConfig] = None,
    ):
        self._data_store = data_store
        self._config = config or PipelineConfig()
        self._pipelines: Dict[ProductType, ProductPipeline] = {}
    
    def get_pipeline(self, product_type: ProductType) -> ProductPipeline:
        """Get or create a pipeline for a product type."""
        if product_type not in self._pipelines:
            definition = get_product_definition(product_type)
            self._pipelines[product_type] = ProductPipeline(
                product_definition=definition,
                data_store=self._data_store,
                config=self._config,
            )
        
        return self._pipelines[product_type]
    
    def get_all_pipelines(self) -> Dict[ProductType, ProductPipeline]:
        """Get all pipelines."""
        for product_type in ProductType:
            self.get_pipeline(product_type)
        return self._pipelines


# ============================================================
# PIPELINE EXECUTOR
# ============================================================

class PipelineExecutor:
    """
    Executor for running pipelines.
    
    Handles concurrent execution and error handling.
    """
    
    def __init__(
        self,
        factory: PipelineFactory,
        max_concurrent: int = 5,
    ):
        self._factory = factory
        self._max_concurrent = max_concurrent
        self._active_count = 0
    
    async def execute(self, request: ExportRequest) -> PipelineResult:
        """Execute a single pipeline request."""
        if self._active_count >= self._max_concurrent:
            return PipelineResult(
                success=False,
                request_id=request.request_id,
                product_type=request.product_type,
                stages=[],
                error_message="Too many concurrent requests",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )
        
        try:
            self._active_count += 1
            pipeline = self._factory.get_pipeline(request.product_type)
            return await pipeline.execute(request)
        finally:
            self._active_count -= 1
    
    def get_active_count(self) -> int:
        """Get number of active executions."""
        return self._active_count


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_pipeline(
    product_type: ProductType,
    data_store: Optional[DataStoreInterface] = None,
    config: Optional[PipelineConfig] = None,
) -> ProductPipeline:
    """Create a pipeline for a product type."""
    definition = get_product_definition(product_type)
    return ProductPipeline(
        product_definition=definition,
        data_store=data_store,
        config=config,
    )


def create_pipeline_factory(
    data_store: Optional[DataStoreInterface] = None,
    config: Optional[PipelineConfig] = None,
) -> PipelineFactory:
    """Create a pipeline factory."""
    return PipelineFactory(data_store=data_store, config=config)


def create_pipeline_executor(
    factory: PipelineFactory,
    max_concurrent: int = 5,
) -> PipelineExecutor:
    """Create a pipeline executor."""
    return PipelineExecutor(factory=factory, max_concurrent=max_concurrent)


def create_pipeline_config(
    max_records: int = 10000,
    max_time_range_days: int = 365,
) -> PipelineConfig:
    """Create a pipeline configuration."""
    return PipelineConfig(
        max_records_per_request=max_records,
        max_time_range_days=max_time_range_days,
    )
