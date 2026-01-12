"""
Exchange Adapter Factory.

============================================================
PURPOSE
============================================================
Factory pattern for creating exchange adapter instances.

FEATURES:
- Centralized adapter creation
- Configuration injection
- Environment-based defaults
- Adapter registry for extension

============================================================
USAGE
============================================================
```python
# Create adapter by exchange ID
adapter = AdapterFactory.create("binance", testnet=True)

# Create with explicit config
config = AdapterConfig(
    api_key="...",
    api_secret="...",
    testnet=True,
)
adapter = AdapterFactory.create("bybit", config=config)

# Create all adapters
adapters = AdapterFactory.create_all(["binance", "okx", "bybit"])
```

============================================================
"""

import os
import logging
from enum import Enum
from typing import Dict, Any, Optional, List, Type, Callable
from dataclasses import dataclass, field

from .base import ExchangeAdapter


logger = logging.getLogger(__name__)


# ============================================================
# EXCHANGE IDENTIFIERS
# ============================================================

class ExchangeId(Enum):
    """Supported exchange identifiers."""
    
    BINANCE = "binance"
    OKX = "okx"
    BYBIT = "bybit"
    MOCK = "mock"


# ============================================================
# ADAPTER CONFIGURATION
# ============================================================

@dataclass
class AdapterConfig:
    """
    Configuration for exchange adapter.
    
    Common configuration shared across adapters.
    """
    
    # Credentials (can be None to use env vars)
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    
    # Exchange-specific
    passphrase: Optional[str] = None  # OKX
    
    # Environment
    testnet: bool = False
    simulated: bool = False  # OKX demo mode
    
    # Connection
    timeout_seconds: float = 30.0
    
    # Exchange-specific options
    options: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_env(cls, exchange_id: str, testnet: bool = False) -> "AdapterConfig":
        """
        Create config from environment variables.
        
        Args:
            exchange_id: Exchange identifier
            testnet: Use testnet
            
        Returns:
            AdapterConfig
        """
        exchange_id = exchange_id.upper()
        
        return cls(
            api_key=os.environ.get(f"{exchange_id}_API_KEY"),
            api_secret=os.environ.get(f"{exchange_id}_API_SECRET"),
            passphrase=os.environ.get(f"{exchange_id}_PASSPHRASE"),
            testnet=testnet,
        )


# ============================================================
# ADAPTER FACTORY
# ============================================================

class AdapterFactory:
    """
    Factory for creating exchange adapters.
    
    Provides centralized adapter creation with configuration
    injection and extension support.
    """
    
    # Registry of adapter classes
    _registry: Dict[str, Type[ExchangeAdapter]] = {}
    
    # Custom creation functions
    _creators: Dict[str, Callable[[AdapterConfig], ExchangeAdapter]] = {}
    
    @classmethod
    def register(
        cls,
        exchange_id: str,
        adapter_class: Type[ExchangeAdapter] = None,
        creator: Callable[[AdapterConfig], ExchangeAdapter] = None,
    ) -> None:
        """
        Register an adapter class or creator.
        
        Args:
            exchange_id: Exchange identifier
            adapter_class: Adapter class to register
            creator: Custom creator function
        """
        exchange_id = exchange_id.lower()
        
        if adapter_class:
            cls._registry[exchange_id] = adapter_class
        if creator:
            cls._creators[exchange_id] = creator
    
    @classmethod
    def unregister(cls, exchange_id: str) -> None:
        """Unregister an adapter."""
        exchange_id = exchange_id.lower()
        cls._registry.pop(exchange_id, None)
        cls._creators.pop(exchange_id, None)
    
    @classmethod
    def create(
        cls,
        exchange_id: str,
        config: AdapterConfig = None,
        **kwargs,
    ) -> ExchangeAdapter:
        """
        Create an exchange adapter.
        
        Args:
            exchange_id: Exchange identifier
            config: Adapter configuration
            **kwargs: Additional arguments passed to adapter
            
        Returns:
            ExchangeAdapter instance
            
        Raises:
            ValueError: If exchange not supported
        """
        exchange_id = exchange_id.lower()
        
        # Create default config if not provided
        if config is None:
            config = AdapterConfig.from_env(
                exchange_id,
                testnet=kwargs.pop("testnet", False),
            )
        
        # Merge kwargs into config options
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
            else:
                config.options[key] = value
        
        # Check for custom creator
        if exchange_id in cls._creators:
            return cls._creators[exchange_id](config)
        
        # Check registry
        if exchange_id in cls._registry:
            return cls._create_from_class(exchange_id, config)
        
        # Default creation
        return cls._create_default(exchange_id, config)
    
    @classmethod
    def _create_from_class(
        cls,
        exchange_id: str,
        config: AdapterConfig,
    ) -> ExchangeAdapter:
        """Create adapter from registered class."""
        adapter_class = cls._registry[exchange_id]
        
        # Build kwargs from config
        kwargs = cls._config_to_kwargs(exchange_id, config)
        
        return adapter_class(**kwargs)
    
    @classmethod
    def _create_default(
        cls,
        exchange_id: str,
        config: AdapterConfig,
    ) -> ExchangeAdapter:
        """Create adapter using default imports."""
        kwargs = cls._config_to_kwargs(exchange_id, config)
        
        if exchange_id == "binance":
            from .binance import BinanceAdapter
            return BinanceAdapter(**kwargs)
        
        elif exchange_id == "okx":
            from .okx import OKXAdapter
            return OKXAdapter(**kwargs)
        
        elif exchange_id == "bybit":
            from .bybit import BybitAdapter
            return BybitAdapter(**kwargs)
        
        elif exchange_id == "mock":
            from .mock import MockExchangeAdapter
            return MockExchangeAdapter(**kwargs)
        
        else:
            raise ValueError(f"Unsupported exchange: {exchange_id}")
    
    @classmethod
    def _config_to_kwargs(
        cls,
        exchange_id: str,
        config: AdapterConfig,
    ) -> Dict[str, Any]:
        """Convert config to adapter kwargs."""
        kwargs = {}
        
        # Common args
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.api_secret:
            kwargs["api_secret"] = config.api_secret
        if config.timeout_seconds:
            kwargs["timeout_seconds"] = config.timeout_seconds
        
        # Exchange-specific
        if exchange_id == "binance":
            kwargs["testnet"] = config.testnet
        
        elif exchange_id == "okx":
            if config.passphrase:
                kwargs["passphrase"] = config.passphrase
            kwargs["simulated"] = config.simulated or config.testnet
        
        elif exchange_id == "bybit":
            kwargs["testnet"] = config.testnet
        
        # Add any extra options
        kwargs.update(config.options)
        
        return kwargs
    
    @classmethod
    def create_all(
        cls,
        exchange_ids: List[str],
        config_map: Dict[str, AdapterConfig] = None,
        **common_kwargs,
    ) -> Dict[str, ExchangeAdapter]:
        """
        Create multiple adapters.
        
        Args:
            exchange_ids: List of exchange identifiers
            config_map: Optional config per exchange
            **common_kwargs: Common arguments for all adapters
            
        Returns:
            Dict of exchange_id -> adapter
        """
        config_map = config_map or {}
        adapters = {}
        
        for exchange_id in exchange_ids:
            try:
                config = config_map.get(exchange_id)
                adapters[exchange_id] = cls.create(
                    exchange_id,
                    config=config,
                    **common_kwargs,
                )
            except Exception as e:
                logger.error(f"Failed to create adapter for {exchange_id}: {e}")
        
        return adapters
    
    @classmethod
    def list_supported(cls) -> List[str]:
        """List supported exchanges."""
        # Built-in + registered
        builtin = ["binance", "okx", "bybit", "mock"]
        registered = list(cls._registry.keys())
        return list(set(builtin + registered))


# ============================================================
# ADAPTER POOL
# ============================================================

class AdapterPool:
    """
    Pool of exchange adapters.
    
    Manages lifecycle of multiple adapters.
    """
    
    def __init__(self):
        """Initialize pool."""
        self._adapters: Dict[str, ExchangeAdapter] = {}
        self._connected: Dict[str, bool] = {}
    
    async def add(
        self,
        exchange_id: str,
        adapter: ExchangeAdapter = None,
        config: AdapterConfig = None,
        auto_connect: bool = True,
    ) -> ExchangeAdapter:
        """
        Add adapter to pool.
        
        Args:
            exchange_id: Exchange identifier
            adapter: Existing adapter (or create new)
            config: Config for new adapter
            auto_connect: Connect automatically
            
        Returns:
            Adapter instance
        """
        if adapter is None:
            adapter = AdapterFactory.create(exchange_id, config)
        
        self._adapters[exchange_id] = adapter
        self._connected[exchange_id] = False
        
        if auto_connect:
            await self.connect(exchange_id)
        
        return adapter
    
    async def remove(self, exchange_id: str) -> None:
        """Remove adapter from pool."""
        if exchange_id in self._adapters:
            adapter = self._adapters[exchange_id]
            if self._connected.get(exchange_id):
                await adapter.disconnect()
            del self._adapters[exchange_id]
            del self._connected[exchange_id]
    
    def get(self, exchange_id: str) -> Optional[ExchangeAdapter]:
        """Get adapter by exchange ID."""
        return self._adapters.get(exchange_id)
    
    def __getitem__(self, exchange_id: str) -> ExchangeAdapter:
        """Get adapter by exchange ID."""
        if exchange_id not in self._adapters:
            raise KeyError(f"Adapter not found: {exchange_id}")
        return self._adapters[exchange_id]
    
    def __contains__(self, exchange_id: str) -> bool:
        """Check if adapter exists."""
        return exchange_id in self._adapters
    
    async def connect(self, exchange_id: str = None) -> None:
        """
        Connect adapter(s).
        
        Args:
            exchange_id: Specific exchange or all if None
        """
        if exchange_id:
            adapter = self._adapters.get(exchange_id)
            if adapter and not self._connected.get(exchange_id):
                await adapter.connect()
                self._connected[exchange_id] = True
        else:
            for eid, adapter in self._adapters.items():
                if not self._connected.get(eid):
                    await adapter.connect()
                    self._connected[eid] = True
    
    async def disconnect(self, exchange_id: str = None) -> None:
        """
        Disconnect adapter(s).
        
        Args:
            exchange_id: Specific exchange or all if None
        """
        if exchange_id:
            adapter = self._adapters.get(exchange_id)
            if adapter and self._connected.get(exchange_id):
                await adapter.disconnect()
                self._connected[exchange_id] = False
        else:
            for eid, adapter in self._adapters.items():
                if self._connected.get(eid):
                    await adapter.disconnect()
                    self._connected[eid] = False
    
    async def disconnect_all(self) -> None:
        """Disconnect all adapters."""
        await self.disconnect()
    
    def list_exchanges(self) -> List[str]:
        """List exchanges in pool."""
        return list(self._adapters.keys())
    
    def list_connected(self) -> List[str]:
        """List connected exchanges."""
        return [eid for eid, connected in self._connected.items() if connected]
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect_all()


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def create_adapter(
    exchange_id: str,
    testnet: bool = False,
    **kwargs,
) -> ExchangeAdapter:
    """
    Create exchange adapter.
    
    Convenience wrapper for AdapterFactory.create().
    
    Args:
        exchange_id: Exchange identifier (binance, okx, bybit)
        testnet: Use testnet
        **kwargs: Additional arguments
        
    Returns:
        ExchangeAdapter instance
    """
    return AdapterFactory.create(exchange_id, testnet=testnet, **kwargs)


async def create_connected_adapter(
    exchange_id: str,
    testnet: bool = False,
    **kwargs,
) -> ExchangeAdapter:
    """
    Create and connect exchange adapter.
    
    Args:
        exchange_id: Exchange identifier
        testnet: Use testnet
        **kwargs: Additional arguments
        
    Returns:
        Connected ExchangeAdapter instance
    """
    adapter = AdapterFactory.create(exchange_id, testnet=testnet, **kwargs)
    await adapter.connect()
    return adapter
