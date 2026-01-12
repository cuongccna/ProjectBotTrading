"""
Product Data Packaging - Main Manager.

============================================================
PURPOSE
============================================================
Unified interface for the Product Data Packaging layer.

Provides:
- Single entry point for all product packaging operations
- Failure isolation (packaging failures don't affect trading)
- Product catalog management
- Health monitoring

============================================================
CRITICAL CONSTRAINTS
============================================================
- This module does NOT trade
- This module does NOT affect internal decisions
- This module ONLY prepares data for external consumption
- All failures are isolated and logged

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import logging
import uuid
import asyncio


from .models import (
    ProductType,
    ProductTier,
    ProductDefinition,
    TimeBucket,
    OutputFormat,
    DeliveryMethod,
    ExportRequest,
    ExportResponse,
    ExportStatus,
    RateLimitConfig,
    create_default_rate_limit,
)
from .schemas import (
    ProductSchema,
    SchemaRegistry,
    create_schema_registry,
    get_product_definition,
    get_all_product_definitions,
)
from .extractors import DataStoreInterface
from .pipeline import (
    ProductPipeline,
    PipelineFactory,
    PipelineExecutor,
    PipelineConfig,
    PipelineResult,
    create_pipeline_factory,
    create_pipeline_executor,
    create_pipeline_config,
)
from .access import (
    AccessController,
    AccessCheckResult,
    AccessLog,
    create_access_controller,
)


logger = logging.getLogger(__name__)


# ============================================================
# HEALTH STATUS
# ============================================================

class HealthStatus(Enum):
    """Health status of the packaging system."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a component."""
    name: str
    status: HealthStatus
    last_check: datetime
    error_count: int = 0
    last_error: Optional[str] = None


@dataclass
class SystemHealth:
    """Overall system health."""
    status: HealthStatus
    components: List[ComponentHealth]
    checked_at: datetime = field(default_factory=datetime.utcnow)
    
    # Statistics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_latency_ms: float = 0.0


# ============================================================
# PRODUCT CATALOG
# ============================================================

@dataclass
class ProductInfo:
    """Information about an available product."""
    product_id: str
    product_type: ProductType
    name: str
    description: str
    tier: ProductTier
    schema_version: str
    supported_formats: List[OutputFormat]
    supported_time_buckets: List[TimeBucket]
    update_frequency: str
    data_delay_seconds: int
    is_available: bool = True


class ProductCatalog:
    """
    Catalog of available data products.
    
    Provides product discovery and metadata.
    """
    
    def __init__(self):
        self._products: Dict[str, ProductDefinition] = {}
        self._schema_registry = create_schema_registry()
        self._load_products()
    
    def _load_products(self) -> None:
        """Load all product definitions."""
        for definition in get_all_product_definitions():
            self._products[definition.product_id] = definition
    
    def list_products(
        self,
        tier: Optional[ProductTier] = None,
        product_type: Optional[ProductType] = None,
    ) -> List[ProductInfo]:
        """List available products."""
        products = []
        
        for definition in self._products.values():
            if tier and definition.tier != tier:
                continue
            if product_type and definition.product_type != product_type:
                continue
            
            info = ProductInfo(
                product_id=definition.product_id,
                product_type=definition.product_type,
                name=definition.name,
                description=definition.description,
                tier=definition.tier,
                schema_version=definition.schema.version.version_string,
                supported_formats=definition.supported_formats,
                supported_time_buckets=definition.schema.time_buckets,
                update_frequency=definition.schema.update_frequency,
                data_delay_seconds=definition.delay.min_delay_seconds,
                is_available=definition.is_active,
            )
            products.append(info)
        
        return products
    
    def get_product(self, product_id: str) -> Optional[ProductDefinition]:
        """Get a product by ID."""
        return self._products.get(product_id)
    
    def get_product_by_type(self, product_type: ProductType) -> Optional[ProductDefinition]:
        """Get a product by type."""
        for definition in self._products.values():
            if definition.product_type == product_type:
                return definition
        return None
    
    def get_schema(
        self,
        product_type: ProductType,
        version: Optional[str] = None,
    ) -> Optional[ProductSchema]:
        """Get schema for a product."""
        try:
            return self._schema_registry.get_schema(product_type, version)
        except ValueError:
            return None
    
    def list_schema_versions(self, product_type: ProductType) -> List[str]:
        """List available schema versions for a product."""
        return self._schema_registry.list_versions(product_type)


# ============================================================
# FAIL-SAFE WRAPPER
# ============================================================

class FailSafeWrapper:
    """
    Wraps operations to ensure failures don't propagate.
    
    CRITICAL: Packaging failures must NOT affect trading.
    """
    
    def __init__(self, component_name: str):
        self._component_name = component_name
        self._error_count = 0
        self._last_error: Optional[str] = None
        self._last_error_time: Optional[datetime] = None
    
    async def safe_execute(
        self,
        operation: Callable,
        *args,
        default_result: Any = None,
        **kwargs,
    ) -> Any:
        """
        Execute an operation safely.
        
        Returns default_result on failure.
        """
        try:
            if asyncio.iscoroutinefunction(operation):
                return await operation(*args, **kwargs)
            else:
                return operation(*args, **kwargs)
        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            self._last_error_time = datetime.utcnow()
            
            logger.error(
                f"Error in {self._component_name}: {e}",
                exc_info=True,
            )
            
            return default_result
    
    def get_health(self) -> ComponentHealth:
        """Get health status of this component."""
        if self._error_count == 0:
            status = HealthStatus.HEALTHY
        elif self._error_count < 5:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.UNHEALTHY
        
        return ComponentHealth(
            name=self._component_name,
            status=status,
            last_check=datetime.utcnow(),
            error_count=self._error_count,
            last_error=self._last_error,
        )
    
    def reset_errors(self) -> None:
        """Reset error count."""
        self._error_count = 0
        self._last_error = None
        self._last_error_time = None


# ============================================================
# PRODUCT PACKAGING MANAGER
# ============================================================

class ProductPackagingManager:
    """
    Main manager for the Product Data Packaging layer.
    
    Provides a unified interface for all packaging operations.
    
    CRITICAL CONSTRAINTS:
    - This module does NOT trade
    - This module does NOT affect internal decisions
    - All failures are isolated
    """
    
    def __init__(
        self,
        data_store: Optional[DataStoreInterface] = None,
        pipeline_config: Optional[PipelineConfig] = None,
        rate_limit_config: Optional[RateLimitConfig] = None,
    ):
        # Configuration
        self._pipeline_config = pipeline_config or create_pipeline_config()
        self._rate_limit_config = rate_limit_config or create_default_rate_limit()
        
        # Components
        self._catalog = ProductCatalog()
        self._pipeline_factory = create_pipeline_factory(
            data_store=data_store,
            config=self._pipeline_config,
        )
        self._executor = create_pipeline_executor(
            factory=self._pipeline_factory,
            max_concurrent=5,
        )
        self._access_controller = create_access_controller(
            rate_limit_config=self._rate_limit_config,
        )
        
        # Fail-safe wrappers
        self._safe_pipeline = FailSafeWrapper("pipeline")
        self._safe_access = FailSafeWrapper("access_control")
        
        # Statistics
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._total_latency_ms = 0
        
        logger.info("ProductPackagingManager initialized")
    
    # --------------------------------------------------------
    # PRODUCT DISCOVERY
    # --------------------------------------------------------
    
    def list_products(
        self,
        tier: Optional[ProductTier] = None,
    ) -> List[ProductInfo]:
        """List available data products."""
        return self._catalog.list_products(tier=tier)
    
    def get_product_info(self, product_id: str) -> Optional[ProductInfo]:
        """Get information about a specific product."""
        products = self._catalog.list_products()
        for product in products:
            if product.product_id == product_id:
                return product
        return None
    
    def get_schema(
        self,
        product_type: ProductType,
        version: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get JSON schema for a product."""
        schema = self._catalog.get_schema(product_type, version)
        if schema:
            return schema.to_json_schema()
        return None
    
    # --------------------------------------------------------
    # EXPORT OPERATIONS
    # --------------------------------------------------------
    
    async def export(
        self,
        client_id: str,
        product_type: ProductType,
        start_time: datetime,
        end_time: datetime,
        time_bucket: TimeBucket = TimeBucket.HOUR_1,
        output_format: OutputFormat = OutputFormat.JSON,
        symbols: Optional[List[str]] = None,
    ) -> ExportResponse:
        """
        Export data for a product.
        
        This is the main entry point for data export.
        """
        request_id = f"req_{uuid.uuid4().hex[:8]}"
        started_at = datetime.utcnow()
        
        self._total_requests += 1
        
        # Get product definition
        definition = self._catalog.get_product_by_type(product_type)
        if not definition:
            self._failed_requests += 1
            return ExportResponse(
                request_id=request_id,
                status=ExportStatus.FAILED,
                error_message=f"Unknown product type: {product_type.value}",
            )
        
        # Create export request
        request = ExportRequest(
            request_id=request_id,
            product_id=definition.product_id,
            product_type=product_type,
            start_time=start_time,
            end_time=end_time,
            time_bucket=time_bucket,
            format=output_format,
            delivery_method=DeliveryMethod.FILE_DOWNLOAD,
            symbols=symbols,
            requester_id=self._hash_client_id(client_id),
        )
        
        # Check access
        access_result = await self._safe_access.safe_execute(
            lambda: self._access_controller.check_access(client_id, request),
            default_result=AccessCheckResult(allowed=False, error_message="Access check failed"),
        )
        
        if not access_result.allowed:
            self._failed_requests += 1
            
            # Log the denied access
            self._access_controller.record_access(
                client_id=client_id,
                request=request,
                success=False,
                error_message=access_result.error_message,
            )
            
            return ExportResponse(
                request_id=request_id,
                status=ExportStatus.FAILED,
                error_message=access_result.error_message,
            )
        
        # Execute pipeline
        result = await self._safe_pipeline.safe_execute(
            self._executor.execute,
            request,
            default_result=None,
        )
        
        # Calculate latency
        completed_at = datetime.utcnow()
        latency_ms = int((completed_at - started_at).total_seconds() * 1000)
        self._total_latency_ms += latency_ms
        
        if result is None:
            self._failed_requests += 1
            
            self._access_controller.record_access(
                client_id=client_id,
                request=request,
                success=False,
                error_message="Pipeline execution failed",
                processing_time_ms=latency_ms,
            )
            
            return ExportResponse(
                request_id=request_id,
                status=ExportStatus.FAILED,
                error_message="Pipeline execution failed",
                processing_time_ms=latency_ms,
            )
        
        # Record access
        record_count = result.output.record_count if result.output else 0
        self._access_controller.record_access(
            client_id=client_id,
            request=request,
            success=result.success,
            record_count=record_count,
            error_message=result.error_message,
            processing_time_ms=latency_ms,
        )
        
        if result.success:
            self._successful_requests += 1
        else:
            self._failed_requests += 1
        
        return result.to_export_response()
    
    async def export_json(
        self,
        client_id: str,
        product_type: ProductType,
        start_time: datetime,
        end_time: datetime,
        time_bucket: TimeBucket = TimeBucket.HOUR_1,
        symbols: Optional[List[str]] = None,
    ) -> ExportResponse:
        """Export data as JSON."""
        return await self.export(
            client_id=client_id,
            product_type=product_type,
            start_time=start_time,
            end_time=end_time,
            time_bucket=time_bucket,
            output_format=OutputFormat.JSON,
            symbols=symbols,
        )
    
    async def export_csv(
        self,
        client_id: str,
        product_type: ProductType,
        start_time: datetime,
        end_time: datetime,
        time_bucket: TimeBucket = TimeBucket.HOUR_1,
        symbols: Optional[List[str]] = None,
    ) -> ExportResponse:
        """Export data as CSV."""
        return await self.export(
            client_id=client_id,
            product_type=product_type,
            start_time=start_time,
            end_time=end_time,
            time_bucket=time_bucket,
            output_format=OutputFormat.CSV,
            symbols=symbols,
        )
    
    # --------------------------------------------------------
    # ACCESS MANAGEMENT
    # --------------------------------------------------------
    
    def get_access_logs(
        self,
        client_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AccessLog]:
        """Get access logs."""
        return self._access_controller.get_access_logs(
            client_id=client_id,
            limit=limit,
        )
    
    def get_access_statistics(
        self,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get access statistics."""
        return self._access_controller.get_statistics(client_id=client_id)
    
    # --------------------------------------------------------
    # HEALTH MONITORING
    # --------------------------------------------------------
    
    def get_health(self) -> SystemHealth:
        """Get system health status."""
        components = [
            self._safe_pipeline.get_health(),
            self._safe_access.get_health(),
        ]
        
        # Determine overall status
        if all(c.status == HealthStatus.HEALTHY for c in components):
            overall = HealthStatus.HEALTHY
        elif any(c.status == HealthStatus.UNHEALTHY for c in components):
            overall = HealthStatus.UNHEALTHY
        else:
            overall = HealthStatus.DEGRADED
        
        avg_latency = (
            self._total_latency_ms / self._total_requests
            if self._total_requests > 0 else 0.0
        )
        
        return SystemHealth(
            status=overall,
            components=components,
            total_requests=self._total_requests,
            successful_requests=self._successful_requests,
            failed_requests=self._failed_requests,
            average_latency_ms=avg_latency,
        )
    
    def reset_health_counters(self) -> None:
        """Reset health counters."""
        self._safe_pipeline.reset_errors()
        self._safe_access.reset_errors()
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._total_latency_ms = 0
    
    # --------------------------------------------------------
    # UTILITIES
    # --------------------------------------------------------
    
    def _hash_client_id(self, client_id: str) -> str:
        """Hash client ID for privacy."""
        import hashlib
        return hashlib.sha256(client_id.encode()).hexdigest()[:16]


# ============================================================
# FAIL-SAFE MANAGER WRAPPER
# ============================================================

class FailSafePackagingManager:
    """
    Fail-safe wrapper for ProductPackagingManager.
    
    CRITICAL: Ensures packaging never affects trading.
    """
    
    def __init__(
        self,
        data_store: Optional[DataStoreInterface] = None,
        pipeline_config: Optional[PipelineConfig] = None,
        rate_limit_config: Optional[RateLimitConfig] = None,
    ):
        try:
            self._manager = ProductPackagingManager(
                data_store=data_store,
                pipeline_config=pipeline_config,
                rate_limit_config=rate_limit_config,
            )
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize ProductPackagingManager: {e}")
            self._manager = None
            self._initialized = False
    
    @property
    def is_initialized(self) -> bool:
        """Check if manager is properly initialized."""
        return self._initialized
    
    async def export(self, *args, **kwargs) -> ExportResponse:
        """Export with fail-safe protection."""
        if not self._initialized or self._manager is None:
            return ExportResponse(
                request_id="error",
                status=ExportStatus.FAILED,
                error_message="Packaging system not initialized",
            )
        
        try:
            return await self._manager.export(*args, **kwargs)
        except Exception as e:
            logger.error(f"Export failed: {e}", exc_info=True)
            return ExportResponse(
                request_id="error",
                status=ExportStatus.FAILED,
                error_message=str(e),
            )
    
    def list_products(self, *args, **kwargs) -> List[ProductInfo]:
        """List products with fail-safe protection."""
        if not self._initialized or self._manager is None:
            return []
        
        try:
            return self._manager.list_products(*args, **kwargs)
        except Exception as e:
            logger.error(f"list_products failed: {e}")
            return []
    
    def get_health(self) -> SystemHealth:
        """Get health with fail-safe protection."""
        if not self._initialized or self._manager is None:
            return SystemHealth(
                status=HealthStatus.UNHEALTHY,
                components=[],
            )
        
        try:
            return self._manager.get_health()
        except Exception as e:
            logger.error(f"get_health failed: {e}")
            return SystemHealth(
                status=HealthStatus.UNHEALTHY,
                components=[],
            )


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_product_packaging_manager(
    data_store: Optional[DataStoreInterface] = None,
    pipeline_config: Optional[PipelineConfig] = None,
    rate_limit_config: Optional[RateLimitConfig] = None,
) -> ProductPackagingManager:
    """Create a product packaging manager."""
    return ProductPackagingManager(
        data_store=data_store,
        pipeline_config=pipeline_config,
        rate_limit_config=rate_limit_config,
    )


def create_fail_safe_packaging_manager(
    data_store: Optional[DataStoreInterface] = None,
    pipeline_config: Optional[PipelineConfig] = None,
    rate_limit_config: Optional[RateLimitConfig] = None,
) -> FailSafePackagingManager:
    """Create a fail-safe product packaging manager."""
    return FailSafePackagingManager(
        data_store=data_store,
        pipeline_config=pipeline_config,
        rate_limit_config=rate_limit_config,
    )


def create_product_catalog() -> ProductCatalog:
    """Create a product catalog."""
    return ProductCatalog()
