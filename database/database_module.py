"""
Database Module for Orchestrator.

============================================================
PURPOSE
============================================================
Wraps the database engine as an orchestrator-compatible module.
Provides lifecycle management for database connections.

============================================================
DESIGN
============================================================
This is a thin wrapper around database/engine.py to provide:
- Orchestrator lifecycle hooks (start/stop)
- Health monitoring
- Connection pool management

============================================================
"""

import logging
from typing import Any, Dict, Optional

from database.engine import (
    initialize_database,
    get_engine,
    get_session,
    get_db_session,
    verify_database_connection,
)


logger = logging.getLogger("database.module")


class DatabaseModule:
    """
    Real database module for orchestrator.
    
    ============================================================
    RESPONSIBILITY
    ============================================================
    - Initialize database engine on start
    - Provide health status
    - Dispose connections on stop
    
    ============================================================
    NOT A PLACEHOLDER
    ============================================================
    This is a REAL module that manages database connections.
    
    ============================================================
    """
    
    # Class marker: This is NOT a placeholder
    _is_placeholder: bool = False
    
    def __init__(
        self,
        auto_create_tables: bool = True,
        **kwargs,
    ) -> None:
        """
        Initialize the database module.
        
        Args:
            auto_create_tables: Whether to create tables on start
            **kwargs: Additional arguments (for orchestrator compatibility)
        """
        self._auto_create_tables = auto_create_tables
        self._running = False
        self._initialized = False
        
        logger.info("DatabaseModule initialized")
    
    # --------------------------------------------------------
    # ORCHESTRATOR INTERFACE
    # --------------------------------------------------------
    
    async def start(self) -> None:
        """
        Start the database module.
        
        Initializes the database engine and optionally creates tables.
        """
        logger.info("Starting DatabaseModule...")
        
        try:
            # Initialize database
            if self._auto_create_tables:
                initialize_database()
                logger.info("Database tables initialized")
            
            # Verify connection works
            if not verify_database_connection():
                raise RuntimeError("Database connection verification failed")
            
            self._initialized = True
            self._running = True
            logger.info("DatabaseModule started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start DatabaseModule: {e}")
            raise
    
    async def stop(self) -> None:
        """
        Stop the database module.
        
        Disposes of the database engine and connection pool.
        """
        logger.info("Stopping DatabaseModule...")
        
        try:
            # Get engine and dispose if available
            engine = get_engine()
            if engine is not None:
                engine.dispose()
            
            self._running = False
            self._initialized = False
            logger.info("DatabaseModule stopped")
            
        except Exception as e:
            logger.error(f"Error stopping DatabaseModule: {e}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status for monitoring.
        
        Returns:
            Dict with health status information
        """
        if not self._running:
            return {
                "status": "stopped",
                "module": "DatabaseModule",
                "is_placeholder": False,
                "initialized": self._initialized,
            }
        
        # Check connection health
        try:
            engine = get_engine()
            pool_status = None
            
            if engine is not None and hasattr(engine, 'pool'):
                pool = engine.pool
                pool_status = {
                    "size": pool.size() if hasattr(pool, 'size') else None,
                    "checked_in": pool.checkedin() if hasattr(pool, 'checkedin') else None,
                    "checked_out": pool.checkedout() if hasattr(pool, 'checkedout') else None,
                    "overflow": pool.overflow() if hasattr(pool, 'overflow') else None,
                }
            
            return {
                "status": "healthy",
                "module": "DatabaseModule",
                "is_placeholder": False,
                "initialized": self._initialized,
                "pool": pool_status,
            }
            
        except Exception as e:
            return {
                "status": "degraded",
                "module": "DatabaseModule",
                "is_placeholder": False,
                "error": str(e),
            }
    
    def can_trade(self) -> bool:
        """Check if module allows trading (for compatibility)."""
        return self._running and self._initialized
    
    def is_halted(self) -> bool:
        """Check if module is halted (for compatibility)."""
        return not self._running
    
    # --------------------------------------------------------
    # DATABASE ACCESS HELPERS
    # --------------------------------------------------------
    
    def get_session(self):
        """Get a database session."""
        return get_session()
    
    def get_db_session(self):
        """Get a database session context manager."""
        return get_db_session()
    
    @property
    def is_initialized(self) -> bool:
        """Check if database is initialized."""
        return self._initialized
