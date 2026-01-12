"""
Orchestrator - Module Registry.

============================================================
RESPONSIBILITY
============================================================
Manages module registration, dependency resolution, and lifecycle.

- Register modules with dependencies
- Resolve dependency order
- Start/stop modules in correct order
- Track module health

============================================================
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, Set
from dataclasses import dataclass, field

from .models import (
    ModuleDefinition,
    ModuleInstance,
    ModuleStatus,
    ExecutionStage,
    RuntimeMode,
)
from core.exceptions import ModuleError, StartupError, ShutdownError
from core.clock import ClockFactory


# ============================================================
# MODULE PROTOCOL
# ============================================================

class ModuleProtocol(Protocol):
    """Protocol that all modules should implement."""
    
    async def start(self) -> None:
        """Start the module."""
        ...
    
    async def stop(self) -> None:
        """Stop the module."""
        ...
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status."""
        ...


class SimpleModule:
    """Base class for simple modules without start/stop."""
    
    async def start(self) -> None:
        """No-op start."""
        pass
    
    async def stop(self) -> None:
        """No-op stop."""
        pass
    
    def get_health_status(self) -> Dict[str, Any]:
        """Default health status."""
        return {"status": "healthy"}


# ============================================================
# DEPENDENCY GRAPH
# ============================================================

class DependencyGraph:
    """
    Manages module dependencies and resolution order.
    
    Uses topological sort to determine startup order.
    """
    
    def __init__(self):
        self._nodes: Set[str] = set()
        self._edges: Dict[str, Set[str]] = {}  # node -> dependencies
    
    def add_node(self, name: str, dependencies: List[str] = None) -> None:
        """Add a node with its dependencies."""
        self._nodes.add(name)
        self._edges[name] = set(dependencies or [])
        
        # Add dependency nodes if not present
        for dep in (dependencies or []):
            if dep not in self._nodes:
                self._nodes.add(dep)
                self._edges.setdefault(dep, set())
    
    def get_startup_order(self) -> List[str]:
        """
        Get modules in startup order (dependencies first).
        
        Returns:
            List of module names in startup order
            
        Raises:
            ValueError: If circular dependency detected
        """
        visited = set()
        temp_visited = set()
        order = []
        
        def visit(node: str) -> None:
            if node in temp_visited:
                raise ValueError(f"Circular dependency detected involving: {node}")
            if node in visited:
                return
            
            temp_visited.add(node)
            
            for dep in self._edges.get(node, set()):
                visit(dep)
            
            temp_visited.remove(node)
            visited.add(node)
            order.append(node)
        
        for node in self._nodes:
            if node not in visited:
                visit(node)
        
        return order
    
    def get_shutdown_order(self) -> List[str]:
        """Get modules in shutdown order (reverse of startup)."""
        return list(reversed(self.get_startup_order()))
    
    def get_dependents(self, name: str) -> Set[str]:
        """Get modules that depend on the given module."""
        dependents = set()
        for node, deps in self._edges.items():
            if name in deps:
                dependents.add(node)
        return dependents


# ============================================================
# MODULE REGISTRY
# ============================================================

class ModuleRegistry:
    """
    Central registry for all system modules.
    
    Handles:
    - Module registration
    - Dependency resolution
    - Lifecycle management (start/stop)
    - Health tracking
    """
    
    def __init__(self):
        self._definitions: Dict[str, ModuleDefinition] = {}
        self._instances: Dict[str, ModuleInstance] = {}
        self._graph = DependencyGraph()
        self._logger = logging.getLogger(__name__)
        self._lock = asyncio.Lock()
    
    # --------------------------------------------------------
    # Registration
    # --------------------------------------------------------
    
    def register(
        self,
        name: str,
        module_class: type,
        dependencies: List[str] = None,
        required_stages: List[ExecutionStage] = None,
        config_key: str = None,
        enabled: bool = True,
        critical: bool = False,
        timeout_seconds: float = 60.0,
    ) -> None:
        """
        Register a module.
        
        Args:
            name: Unique module name
            module_class: Class to instantiate
            dependencies: Names of dependent modules
            required_stages: Stages where module is active
            config_key: Configuration key
            enabled: Whether module is enabled
            critical: Whether failure stops system
            timeout_seconds: Operation timeout
        """
        definition = ModuleDefinition(
            name=name,
            module_class=module_class,
            dependencies=dependencies or [],
            required_stages=required_stages or [],
            config_key=config_key,
            enabled=enabled,
            critical=critical,
            timeout_seconds=timeout_seconds,
        )
        
        self._definitions[name] = definition
        self._graph.add_node(name, dependencies or [])
        
        self._logger.debug(f"Registered module: {name}")
    
    def register_definition(self, definition: ModuleDefinition) -> None:
        """Register a module from a definition."""
        self._definitions[definition.name] = definition
        self._graph.add_node(definition.name, definition.dependencies)
        self._logger.debug(f"Registered module: {definition.name}")
    
    def unregister(self, name: str) -> None:
        """Unregister a module."""
        if name in self._definitions:
            del self._definitions[name]
        if name in self._instances:
            del self._instances[name]
    
    # --------------------------------------------------------
    # Instance Management
    # --------------------------------------------------------
    
    def get_instance(self, name: str) -> Optional[Any]:
        """Get a module instance."""
        instance = self._instances.get(name)
        return instance.instance if instance else None
    
    def get_module_info(self, name: str) -> Optional[ModuleInstance]:
        """Get module instance info."""
        return self._instances.get(name)
    
    def get_all_instances(self) -> Dict[str, ModuleInstance]:
        """Get all module instances."""
        return dict(self._instances)
    
    def get_all_definitions(self) -> Dict[str, ModuleDefinition]:
        """
        Get all module definitions.
        
        Returns a copy of the internal definitions dictionary,
        useful for inspecting registered modules and their configuration.
        """
        return dict(self._definitions)
    
    def get_startup_order(self) -> List[str]:
        """Get modules in startup order."""
        all_modules = self._graph.get_startup_order()
        # Filter to registered modules only
        return [m for m in all_modules if m in self._definitions]
    
    def get_shutdown_order(self) -> List[str]:
        """Get modules in shutdown order."""
        return list(reversed(self.get_startup_order()))
    
    def get_modules_for_stage(self, stage: ExecutionStage) -> List[str]:
        """Get modules active in a given stage."""
        return [
            name for name, defn in self._definitions.items()
            if stage in defn.required_stages and defn.enabled
        ]
    
    # --------------------------------------------------------
    # Lifecycle
    # --------------------------------------------------------
    
    async def instantiate_all(
        self,
        factory: Callable[[ModuleDefinition], Any],
    ) -> None:
        """
        Instantiate all registered modules.
        
        Args:
            factory: Function to create module instance from definition
        """
        async with self._lock:
            for name in self.get_startup_order():
                if name not in self._instances:
                    defn = self._definitions.get(name)
                    if defn and defn.enabled:
                        try:
                            instance = factory(defn)
                            self._instances[name] = ModuleInstance(
                                definition=defn,
                                instance=instance,
                                status=ModuleStatus.NOT_STARTED,
                            )
                            self._logger.debug(f"Instantiated module: {name}")
                        except Exception as e:
                            self._logger.error(f"Failed to instantiate {name}: {e}")
                            if defn.critical:
                                raise StartupError(
                                    message=f"Failed to instantiate critical module: {name}",
                                    module=name,
                                    cause=e,
                                )
    
    async def start_all(self) -> List[str]:
        """
        Start all modules in dependency order.
        
        Returns:
            List of successfully started modules
        """
        started = []
        
        for name in self.get_startup_order():
            module_info = self._instances.get(name)
            if not module_info:
                continue
            
            if module_info.status != ModuleStatus.NOT_STARTED:
                continue
            
            try:
                await self.start_module(name)
                started.append(name)
            except Exception as e:
                self._logger.error(f"Failed to start module {name}: {e}")
                if module_info.definition.critical:
                    raise
        
        return started
    
    async def start_module(self, name: str) -> None:
        """
        Start a single module.
        
        Args:
            name: Module name
            
        Raises:
            StartupError: If module fails to start
        """
        module_info = self._instances.get(name)
        if not module_info:
            raise ModuleError(
                message=f"Module not found: {name}",
                module_name=name,
            )
        
        if module_info.status == ModuleStatus.RUNNING:
            return
        
        # Check dependencies are running
        for dep in module_info.definition.dependencies:
            dep_info = self._instances.get(dep)
            if not dep_info or dep_info.status != ModuleStatus.RUNNING:
                raise StartupError(
                    message=f"Dependency not running: {dep}",
                    module=name,
                    context={"dependency": dep},
                )
        
        module_info.status = ModuleStatus.STARTING
        clock = ClockFactory.get_clock()
        
        try:
            # Start with timeout
            if hasattr(module_info.instance, 'start'):
                await asyncio.wait_for(
                    module_info.instance.start(),
                    timeout=module_info.definition.timeout_seconds,
                )
            
            module_info.status = ModuleStatus.RUNNING
            module_info.started_at = clock.now()
            module_info.error = None
            
            self._logger.info(f"Started module: {name}")
            
        except asyncio.TimeoutError:
            module_info.status = ModuleStatus.ERROR
            module_info.error = "Start timeout"
            raise StartupError(
                message=f"Module start timeout: {name}",
                module=name,
            )
        except Exception as e:
            module_info.status = ModuleStatus.ERROR
            module_info.error = str(e)
            raise StartupError(
                message=f"Module start failed: {name}",
                module=name,
                cause=e,
            )
    
    async def stop_all(self) -> List[str]:
        """
        Stop all modules in reverse dependency order.
        
        Returns:
            List of successfully stopped modules
        """
        stopped = []
        
        for name in self.get_shutdown_order():
            module_info = self._instances.get(name)
            if not module_info:
                continue
            
            if module_info.status not in (ModuleStatus.RUNNING, ModuleStatus.STARTING):
                continue
            
            try:
                await self.stop_module(name)
                stopped.append(name)
            except Exception as e:
                self._logger.error(f"Failed to stop module {name}: {e}")
        
        return stopped
    
    async def stop_module(self, name: str) -> None:
        """
        Stop a single module.
        
        Args:
            name: Module name
        """
        module_info = self._instances.get(name)
        if not module_info:
            return
        
        if module_info.status not in (ModuleStatus.RUNNING, ModuleStatus.STARTING):
            return
        
        # Check no dependents are still running
        dependents = self._graph.get_dependents(name)
        for dep in dependents:
            dep_info = self._instances.get(dep)
            if dep_info and dep_info.status == ModuleStatus.RUNNING:
                self._logger.warning(
                    f"Stopping {name} while dependent {dep} is running"
                )
        
        module_info.status = ModuleStatus.STOPPING
        clock = ClockFactory.get_clock()
        
        try:
            if hasattr(module_info.instance, 'stop'):
                await asyncio.wait_for(
                    module_info.instance.stop(),
                    timeout=module_info.definition.timeout_seconds,
                )
            
            module_info.status = ModuleStatus.STOPPED
            module_info.stopped_at = clock.now()
            
            self._logger.info(f"Stopped module: {name}")
            
        except asyncio.TimeoutError:
            module_info.status = ModuleStatus.ERROR
            module_info.error = "Stop timeout"
            self._logger.error(f"Module stop timeout: {name}")
        except Exception as e:
            module_info.status = ModuleStatus.ERROR
            module_info.error = str(e)
            self._logger.error(f"Module stop failed: {name}: {e}")
    
    # --------------------------------------------------------
    # Health
    # --------------------------------------------------------
    
    async def check_health(self, name: str) -> Dict[str, Any]:
        """
        Check health of a module.
        
        Args:
            name: Module name
            
        Returns:
            Health status dictionary
        """
        module_info = self._instances.get(name)
        if not module_info:
            return {"status": "not_found", "module": name}
        
        if module_info.status != ModuleStatus.RUNNING:
            return {
                "status": "not_running",
                "module": name,
                "module_status": module_info.status.value,
            }
        
        try:
            if hasattr(module_info.instance, 'get_health_status'):
                health = module_info.instance.get_health_status()
                module_info.health_checks_passed += 1
                return health
            else:
                module_info.health_checks_passed += 1
                return {"status": "healthy", "module": name}
        except Exception as e:
            module_info.health_checks_failed += 1
            return {
                "status": "error",
                "module": name,
                "error": str(e),
            }
    
    async def check_all_health(self) -> Dict[str, Dict[str, Any]]:
        """Check health of all running modules."""
        results = {}
        for name in self._instances:
            results[name] = await self.check_health(name)
        return results
    
    def get_unhealthy_modules(self) -> List[str]:
        """Get list of unhealthy modules."""
        unhealthy = []
        for name, info in self._instances.items():
            if not info.is_healthy:
                unhealthy.append(name)
        return unhealthy
    
    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get summary of all module statuses."""
        status_counts = {}
        for status in ModuleStatus:
            status_counts[status.value] = 0
        
        for info in self._instances.values():
            status_counts[info.status.value] += 1
        
        return {
            "total_registered": len(self._definitions),
            "total_instantiated": len(self._instances),
            "status_counts": status_counts,
            "unhealthy": self.get_unhealthy_modules(),
        }


# ============================================================
# MODULE FACTORY
# ============================================================

class ModuleFactory:
    """
    Factory for creating module instances.
    
    Handles dependency injection and configuration.
    """
    
    def __init__(
        self,
        config: Dict[str, Any] = None,
        shared_dependencies: Dict[str, Any] = None,
    ):
        """
        Initialize factory.
        
        Args:
            config: Configuration dictionary
            shared_dependencies: Shared dependencies for injection
        """
        self._config = config or {}
        self._shared = shared_dependencies or {}
        self._logger = logging.getLogger(__name__)
    
    def create(self, definition: ModuleDefinition) -> Any:
        """
        Create a module instance from definition.
        
        Args:
            definition: Module definition
            
        Returns:
            Module instance
        """
        # Get module config if available
        module_config = None
        if definition.config_key:
            module_config = self._config.get(definition.config_key)
        
        # Try different instantiation patterns
        try:
            # Try with config parameter
            if module_config:
                return definition.module_class(config=module_config)
        except TypeError:
            pass
        
        try:
            # Try with no parameters
            return definition.module_class()
        except TypeError:
            pass
        
        try:
            # Try with shared dependencies
            return definition.module_class(**self._shared)
        except TypeError:
            pass
        
        # Last resort: try with config dict
        return definition.module_class(module_config or {})
    
    def add_shared_dependency(self, name: str, instance: Any) -> None:
        """Add a shared dependency."""
        self._shared[name] = instance
    
    def get_shared_dependency(self, name: str) -> Optional[Any]:
        """Get a shared dependency."""
        return self._shared.get(name)


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "ModuleProtocol",
    "SimpleModule",
    "DependencyGraph",
    "ModuleRegistry",
    "ModuleFactory",
]
