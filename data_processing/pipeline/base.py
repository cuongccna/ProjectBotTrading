"""
Data Processing Pipeline - Base Stage Processor.

============================================================
PURPOSE
============================================================
Abstract base class for all processing stage processors.

Each stage processor handles one transition:
- CleaningProcessor: RAW → CLEANED
- NormalizationProcessor: CLEANED → NORMALIZED
- LabelingProcessor: NORMALIZED → LABELED
- FeatureProcessor: LABELED → FEATURE_READY

============================================================
DESIGN PRINCIPLES
============================================================
- Each processor is stateless
- All operations are deterministic
- No look-ahead or future data access
- All I/O through repositories only

============================================================
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

from data_processing.pipeline.types import (
    DataDomain,
    ProcessingStage,
    ProcessingStatus,
    ProcessingResult,
    StageMetrics,
    ProcessingError,
)


# Type variables for input and output types
TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class BaseStageProcessor(ABC, Generic[TInput, TOutput]):
    """
    Abstract base class for processing stage processors.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    - Define the processing workflow for a single stage
    - Track metrics for the stage
    - Handle errors gracefully
    - Persist results via repositories
    
    ============================================================
    WORKFLOW
    ============================================================
    For each record:
    1. Load from source (raw or previous stage)
    2. Validate preconditions
    3. Process (clean, normalize, label, or extract features)
    4. Validate output
    5. Persist to target
    6. Record metrics
    
    ============================================================
    """
    
    def __init__(
        self,
        session: Session,
        domain: DataDomain,
        version: str = "1.0.0",
    ) -> None:
        """
        Initialize the stage processor.
        
        Args:
            session: SQLAlchemy session for database access
            domain: Data domain (news, market, onchain)
            version: Processor version for traceability
        """
        self._session = session
        self._domain = domain
        self._version = version
        self._logger = logging.getLogger(f"processor.{self.stage_name}")
        
        # Metrics
        self._metrics = StageMetrics(stage=self.to_stage)
    
    @property
    @abstractmethod
    def from_stage(self) -> ProcessingStage:
        """The stage this processor reads from."""
        pass
    
    @property
    @abstractmethod
    def to_stage(self) -> ProcessingStage:
        """The stage this processor writes to."""
        pass
    
    @property
    def stage_name(self) -> str:
        """Human-readable stage name."""
        return f"{self.from_stage.value}_to_{self.to_stage.value}"
    
    @property
    def domain(self) -> DataDomain:
        """Data domain being processed."""
        return self._domain
    
    @property
    def version(self) -> str:
        """Processor version."""
        return self._version
    
    # =========================================================
    # ABSTRACT METHODS - MUST BE IMPLEMENTED
    # =========================================================
    
    @abstractmethod
    def load_pending_records(self, limit: int = 100) -> List[TInput]:
        """
        Load records pending processing from the source stage.
        
        Args:
            limit: Maximum number of records to load
            
        Returns:
            List of records to process
        """
        pass
    
    @abstractmethod
    def process_record(self, record: TInput) -> TOutput:
        """
        Process a single record.
        
        This is the core processing logic for the stage.
        Must be deterministic and stateless.
        
        Args:
            record: Input record from previous stage
            
        Returns:
            Processed output record
            
        Raises:
            ProcessingError: On processing failure
        """
        pass
    
    @abstractmethod
    def persist_result(self, result: TOutput, source_id: UUID) -> UUID:
        """
        Persist the processed result to storage.
        
        Args:
            result: Processed output record
            source_id: ID of the source record
            
        Returns:
            ID of the persisted record
        """
        pass
    
    @abstractmethod
    def update_source_stage(self, source_id: UUID) -> None:
        """
        Update the source record's processing stage.
        
        Args:
            source_id: ID of the source record to update
        """
        pass
    
    @abstractmethod
    def get_record_id(self, record: TInput) -> UUID:
        """
        Get the ID from a record.
        
        Args:
            record: Input record
            
        Returns:
            Record UUID
        """
        pass
    
    # =========================================================
    # PROCESSING WORKFLOW
    # =========================================================
    
    def process_batch(
        self,
        limit: int = 100,
        continue_on_error: bool = True,
    ) -> List[ProcessingResult]:
        """
        Process a batch of records through this stage.
        
        Args:
            limit: Maximum records to process
            continue_on_error: Whether to continue on individual errors
            
        Returns:
            List of processing results
        """
        self._metrics.started_at = datetime.utcnow()
        results: List[ProcessingResult] = []
        
        try:
            # Load pending records
            records = self.load_pending_records(limit)
            self._logger.info(f"Loaded {len(records)} records for processing")
            
            for record in records:
                result = self._process_single_record(record)
                results.append(result)
                
                if result.status == ProcessingStatus.FAILED and not continue_on_error:
                    self._logger.error(f"Stopping batch due to error: {result.error_message}")
                    break
            
        except Exception as e:
            self._logger.error(f"Batch processing failed: {e}")
            self._metrics.errors.append(str(e))
        
        finally:
            self._metrics.completed_at = datetime.utcnow()
            if self._metrics.started_at:
                self._metrics.total_duration_seconds = (
                    self._metrics.completed_at - self._metrics.started_at
                ).total_seconds()
        
        return results
    
    def _process_single_record(self, record: TInput) -> ProcessingResult:
        """
        Process a single record with error handling.
        
        Args:
            record: Record to process
            
        Returns:
            Processing result
        """
        record_id = self.get_record_id(record)
        start_time = time.time()
        
        try:
            # Validate preconditions
            self._validate_preconditions(record)
            
            # Process the record
            output = self.process_record(record)
            
            # Validate output
            self._validate_output(output)
            
            # Persist result
            new_id = self.persist_result(output, record_id)
            
            # Update source stage
            self.update_source_stage(record_id)
            
            # Commit transaction
            self._session.commit()
            
            # Update metrics
            self._metrics.records_processed += 1
            self._metrics.records_succeeded += 1
            
            duration_ms = (time.time() - start_time) * 1000
            
            return ProcessingResult(
                record_id=record_id,
                domain=self._domain,
                status=ProcessingStatus.SUCCESS,
                from_stage=self.from_stage,
                to_stage=self.to_stage,
                duration_ms=duration_ms,
                metadata={"new_id": str(new_id)},
            )
            
        except ProcessingError as e:
            self._session.rollback()
            self._metrics.records_processed += 1
            self._metrics.records_failed += 1
            self._metrics.errors.append(str(e))
            
            self._logger.warning(f"Processing error for {record_id}: {e}")
            
            return ProcessingResult(
                record_id=record_id,
                domain=self._domain,
                status=ProcessingStatus.FAILED,
                from_stage=self.from_stage,
                to_stage=self.to_stage,
                duration_ms=(time.time() - start_time) * 1000,
                error_message=str(e),
            )
            
        except Exception as e:
            self._session.rollback()
            self._metrics.records_processed += 1
            self._metrics.records_failed += 1
            self._metrics.errors.append(str(e))
            
            self._logger.error(f"Unexpected error for {record_id}: {e}")
            
            return ProcessingResult(
                record_id=record_id,
                domain=self._domain,
                status=ProcessingStatus.FAILED,
                from_stage=self.from_stage,
                to_stage=self.to_stage,
                duration_ms=(time.time() - start_time) * 1000,
                error_message=str(e),
            )
    
    def _validate_preconditions(self, record: TInput) -> None:
        """
        Validate preconditions before processing.
        
        Override in subclasses for stage-specific validation.
        
        Args:
            record: Record to validate
            
        Raises:
            ProcessingError: If validation fails
        """
        pass
    
    def _validate_output(self, output: TOutput) -> None:
        """
        Validate output after processing.
        
        Override in subclasses for stage-specific validation.
        
        Args:
            output: Output to validate
            
        Raises:
            ProcessingError: If validation fails
        """
        pass
    
    # =========================================================
    # METRICS
    # =========================================================
    
    def get_metrics(self) -> StageMetrics:
        """Get current stage metrics."""
        return self._metrics
    
    def reset_metrics(self) -> None:
        """Reset stage metrics."""
        self._metrics = StageMetrics(stage=self.to_stage)


class CompositeProcessor:
    """
    Combines multiple stage processors into a pipeline.
    
    ============================================================
    PURPOSE
    ============================================================
    Orchestrates multiple stage processors in sequence.
    Ensures correct ordering and handles stage dependencies.
    
    ============================================================
    """
    
    def __init__(
        self,
        processors: List[BaseStageProcessor],
        domain: DataDomain,
    ) -> None:
        """
        Initialize the composite processor.
        
        Args:
            processors: List of stage processors in order
            domain: Data domain being processed
        """
        self._processors = processors
        self._domain = domain
        self._logger = logging.getLogger(f"pipeline.{domain.value}")
        
        # Validate processor chain
        self._validate_processor_chain()
    
    def _validate_processor_chain(self) -> None:
        """Validate that processors form a valid chain."""
        for i in range(len(self._processors) - 1):
            current = self._processors[i]
            next_proc = self._processors[i + 1]
            
            if current.to_stage != next_proc.from_stage:
                raise ValueError(
                    f"Invalid processor chain: {current.stage_name} -> {next_proc.stage_name}"
                )
    
    def process_all_stages(
        self,
        limit_per_stage: int = 100,
        continue_on_error: bool = True,
    ) -> Dict[ProcessingStage, List[ProcessingResult]]:
        """
        Process records through all stages.
        
        Args:
            limit_per_stage: Maximum records per stage
            continue_on_error: Whether to continue on errors
            
        Returns:
            Results grouped by stage
        """
        all_results: Dict[ProcessingStage, List[ProcessingResult]] = {}
        
        for processor in self._processors:
            self._logger.info(f"Processing stage: {processor.stage_name}")
            
            results = processor.process_batch(
                limit=limit_per_stage,
                continue_on_error=continue_on_error,
            )
            
            all_results[processor.to_stage] = results
            
            self._logger.info(
                f"Stage {processor.stage_name} complete: "
                f"{len([r for r in results if r.status == ProcessingStatus.SUCCESS])} succeeded, "
                f"{len([r for r in results if r.status == ProcessingStatus.FAILED])} failed"
            )
        
        return all_results
    
    def get_all_metrics(self) -> Dict[ProcessingStage, StageMetrics]:
        """Get metrics from all stages."""
        return {p.to_stage: p.get_metrics() for p in self._processors}
