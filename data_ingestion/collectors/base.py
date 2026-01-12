"""
Data Ingestion - Base Collector.

============================================================
PURPOSE
============================================================
Abstract base class for all data collectors.

============================================================
DESIGN PRINCIPLES
============================================================
- No business logic - collection only
- Repository-based persistence
- Standardized error handling
- Full observability

============================================================
"""

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID, uuid4

from data_ingestion.types import (
    CollectorConfig,
    DataType,
    IngestionResult,
    IngestionSource,
    IngestionStatus,
    FetchError,
    ParseError,
    StorageError,
)


T = TypeVar("T")  # Type for raw items


class BaseCollector(ABC, Generic[T]):
    """
    Abstract base class for data collectors.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    - Fetch data from external sources
    - Normalize to raw item format
    - Persist via repositories
    - Track ingestion metrics
    - Handle errors gracefully
    
    ============================================================
    LIFECYCLE
    ============================================================
    1. Initialize with config and repository
    2. Call collect() to run a collection cycle
    3. Results are persisted and metrics returned
    
    ============================================================
    """
    
    def __init__(
        self,
        config: CollectorConfig,
        source: IngestionSource,
        data_type: DataType,
    ) -> None:
        """
        Initialize the collector.
        
        Args:
            config: Collector configuration
            source: Ingestion source identifier
            data_type: Type of data being collected
        """
        self._config = config
        self._source = source
        self._data_type = data_type
        self._logger = logging.getLogger(f"collector.{source.value}")
        self._collector_instance = f"{source.value}_{uuid4().hex[:8]}"
    
    @property
    def source_name(self) -> str:
        """Get the source name."""
        return self._source.value
    
    @property
    def is_enabled(self) -> bool:
        """Check if collector is enabled."""
        return self._config.enabled
    
    @property
    def version(self) -> str:
        """Get collector version."""
        return self._config.version
    
    # =========================================================
    # ABSTRACT METHODS - Must be implemented by subclasses
    # =========================================================
    
    @abstractmethod
    async def fetch_data(self) -> List[Dict[str, Any]]:
        """
        Fetch raw data from the external source.
        
        Returns:
            List of raw data dictionaries
            
        Raises:
            FetchError: On network or API errors
        """
        pass
    
    @abstractmethod
    def parse_item(self, raw_data: Dict[str, Any]) -> T:
        """
        Parse a raw data dictionary into a typed item.
        
        Args:
            raw_data: Raw data from external source
            
        Returns:
            Parsed raw item
            
        Raises:
            ParseError: On parsing errors
        """
        pass
    
    @abstractmethod
    async def store_item(self, item: T, batch_id: UUID) -> bool:
        """
        Store a single item via the repository.
        
        Args:
            item: Parsed raw item
            batch_id: Collection batch ID
            
        Returns:
            True if stored, False if skipped (duplicate)
            
        Raises:
            StorageError: On storage errors
        """
        pass
    
    # =========================================================
    # COLLECTION WORKFLOW
    # =========================================================
    
    async def collect(self) -> IngestionResult:
        """
        Run a complete collection cycle.
        
        This method:
        1. Fetches data from external source
        2. Parses each item
        3. Stores via repository
        4. Returns metrics
        
        Returns:
            IngestionResult with metrics and status
        """
        result = IngestionResult(
            source=self.source_name,
            data_type=self._data_type,
            started_at=datetime.utcnow(),
        )
        
        if not self.is_enabled:
            result.status = IngestionStatus.SKIPPED
            result.mark_complete(datetime.utcnow())
            self._logger.info(f"Collector {self.source_name} is disabled, skipping")
            return result
        
        self._logger.info(f"Starting collection for {self.source_name}")
        
        try:
            # Step 1: Fetch data
            raw_data_list = await self._fetch_with_retry()
            result.records_fetched = len(raw_data_list)
            self._logger.info(f"Fetched {result.records_fetched} records from {self.source_name}")
            
            # Step 2 & 3: Parse and store each item
            for raw_data in raw_data_list:
                try:
                    item = self.parse_item(raw_data)
                    stored = await self.store_item(item, result.batch_id)
                    
                    if stored:
                        result.records_stored += 1
                    else:
                        result.records_skipped += 1
                        
                except ParseError as e:
                    result.records_failed += 1
                    result.add_error(f"Parse error: {e}")
                    self._logger.warning(f"Parse error for {self.source_name}: {e}")
                    
                except StorageError as e:
                    result.records_failed += 1
                    result.add_error(f"Storage error: {e}")
                    self._logger.error(f"Storage error for {self.source_name}: {e}")
            
            # Determine final status
            if result.records_failed == 0:
                result.status = IngestionStatus.SUCCESS
            elif result.records_stored > 0:
                result.status = IngestionStatus.PARTIAL
            else:
                result.status = IngestionStatus.FAILED
                
        except FetchError as e:
            result.mark_failed(f"Fetch error: {e}")
            self._logger.error(f"Fetch failed for {self.source_name}: {e}")
            
        except Exception as e:
            result.mark_failed(f"Unexpected error: {e}")
            self._logger.exception(f"Unexpected error in {self.source_name}")
        
        result.mark_complete(datetime.utcnow())
        self._log_result(result)
        return result
    
    async def _fetch_with_retry(self) -> List[Dict[str, Any]]:
        """
        Fetch data with retry logic.
        
        Returns:
            List of raw data dictionaries
            
        Raises:
            FetchError: After all retries exhausted
        """
        last_error: Optional[Exception] = None
        
        for attempt in range(self._config.max_retries):
            try:
                return await self.fetch_data()
            except FetchError as e:
                last_error = e
                if not e.recoverable:
                    raise
                
                wait_time = 2 ** attempt  # Exponential backoff
                self._logger.warning(
                    f"Fetch attempt {attempt + 1} failed for {self.source_name}, "
                    f"retrying in {wait_time}s: {e}"
                )
                
                import asyncio
                await asyncio.sleep(wait_time)
        
        raise FetchError(
            message=f"All {self._config.max_retries} fetch attempts failed",
            source=self.source_name,
            recoverable=False,
            details={"last_error": str(last_error)},
        )
    
    def _log_result(self, result: IngestionResult) -> None:
        """Log the ingestion result."""
        log_data = result.to_dict()
        
        if result.status == IngestionStatus.SUCCESS:
            self._logger.info(f"Collection complete: {log_data}")
        elif result.status == IngestionStatus.PARTIAL:
            self._logger.warning(f"Collection partial: {log_data}")
        else:
            self._logger.error(f"Collection failed: {log_data}")
    
    # =========================================================
    # UTILITY METHODS
    # =========================================================
    
    @staticmethod
    def compute_payload_hash(payload: Dict[str, Any]) -> str:
        """
        Compute SHA-256 hash of payload for deduplication.
        
        Args:
            payload: Payload dictionary
            
        Returns:
            Hex-encoded SHA-256 hash
        """
        # Sort keys for consistent hashing
        payload_str = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(payload_str.encode()).hexdigest()
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get collector health status.
        
        Returns:
            Health status dictionary
        """
        return {
            "source": self.source_name,
            "enabled": self.is_enabled,
            "version": self.version,
            "collector_instance": self._collector_instance,
        }
