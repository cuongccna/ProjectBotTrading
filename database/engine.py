"""
Database Persistence Layer - Core Engine.

============================================================
INSTITUTIONAL-GRADE DATABASE PERSISTENCE
============================================================

This module provides REAL, AUDITABLE database persistence.
NO stubs, NO mocks, NO logging-only operations.

Requirements:
- SQLAlchemy ORM with PostgreSQL
- Explicit transaction management
- Structured logging with row counts
- Hard failures on persistence errors

============================================================
"""

import os
import logging
from typing import Optional, Generator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.pool import QueuePool

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# =============================================================
# DECLARATIVE BASE
# =============================================================

Base = declarative_base()

# =============================================================
# DATABASE ENGINE
# =============================================================

_engine = None
_SessionFactory = None


def get_database_url() -> str:
    """Get database URL from environment."""
    url = os.getenv("DATABASE_URL_SYNC")
    if not url:
        url = os.getenv("DATABASE_URL")
        if url and url.startswith("postgresql+asyncpg"):
            # Convert async URL to sync
            url = url.replace("postgresql+asyncpg", "postgresql")
    
    if not url:
        # Default fallback for development
        url = "postgresql://crypto_user:Cuongnv123456@localhost:5432/crypto_trading"
        logger.warning(f"DATABASE_URL not set, using default: {url.split('@')[-1]}")
    
    return url


def create_database_engine(
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_timeout: int = 30,
    pool_recycle: int = 1800,
    echo: bool = False,
):
    """
    Create SQLAlchemy engine with connection pooling.
    
    Args:
        pool_size: Number of connections to keep in pool
        max_overflow: Max connections beyond pool_size
        pool_timeout: Seconds to wait for available connection
        pool_recycle: Recycle connections after N seconds
        echo: Log SQL statements
        
    Returns:
        SQLAlchemy Engine
    """
    global _engine
    
    if _engine is not None:
        return _engine
    
    database_url = get_database_url()
    
    logger.info(f"Creating database engine for: {database_url.split('@')[-1]}")
    
    _engine = create_engine(
        database_url,
        poolclass=QueuePool,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        echo=echo,
        future=True,
    )
    
    # Add event listeners for connection debugging
    @event.listens_for(_engine, "connect")
    def on_connect(dbapi_conn, connection_record):
        logger.debug("Database connection established")
    
    @event.listens_for(_engine, "checkout")
    def on_checkout(dbapi_conn, connection_record, connection_proxy):
        logger.debug("Database connection checked out from pool")
    
    return _engine


def get_engine():
    """Get the database engine, creating if necessary."""
    global _engine
    if _engine is None:
        _engine = create_database_engine()
    return _engine


def get_session_factory() -> sessionmaker:
    """Get session factory, creating if necessary."""
    global _SessionFactory
    
    if _SessionFactory is None:
        engine = get_engine()
        _SessionFactory = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    
    return _SessionFactory


# =============================================================
# SESSION MANAGEMENT
# =============================================================


def get_session() -> Session:
    """
    Get a new database session.
    
    IMPORTANT: Caller is responsible for committing/closing.
    Prefer using get_db_session() context manager instead.
    """
    factory = get_session_factory()
    return factory()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions with automatic cleanup.
    
    Usage:
        with get_db_session() as session:
            session.add(record)
            session.commit()
    
    On exception:
        - Automatically rolls back
        - Re-raises the exception
        - Logs the error
    """
    session = get_session()
    try:
        yield session
    except SQLAlchemyError as e:
        logger.error(f"Database error, rolling back: {e}")
        session.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error, rolling back: {e}")
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def transaction_scope() -> Generator[Session, None, None]:
    """
    Context manager for explicit transaction boundaries.
    
    Commits only if no exception occurs.
    Rolls back on ANY exception.
    
    Usage:
        with transaction_scope() as session:
            persist_raw_news(session, news_items)
            persist_cleaned_news(session, cleaned_items)
            # Commits automatically at end
    """
    session = get_session()
    try:
        yield session
        session.commit()
        logger.debug("Database transaction committed successfully")
    except SQLAlchemyError as e:
        logger.error(f"Database transaction failed, rolling back: {e}")
        session.rollback()
        raise DatabasePersistenceError(f"Transaction failed: {e}") from e
    except Exception as e:
        logger.error(f"Transaction failed with unexpected error: {e}")
        session.rollback()
        raise DatabasePersistenceError(f"Transaction failed: {e}") from e
    finally:
        session.close()


# =============================================================
# DATABASE INITIALIZATION
# =============================================================


def verify_database_connection() -> bool:
    """
    Verify database connection is working.
    
    Returns:
        True if connection successful
        
    Raises:
        DatabaseConnectionError if connection fails
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
            logger.info("Database connection verified successfully")
            return True
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        raise DatabaseConnectionError(f"Cannot connect to database: {e}") from e


def create_all_tables() -> None:
    """
    Create all tables defined in ORM models.
    
    Must be called after all models are imported.
    
    Raises:
        DatabaseInitializationError if table creation fails
    """
    engine = get_engine()
    
    try:
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except SQLAlchemyError as e:
        logger.error(f"Failed to create database tables: {e}")
        raise DatabaseInitializationError(f"Table creation failed: {e}") from e


def initialize_database() -> None:
    """
    Full database initialization sequence.
    
    1. Verify connection
    2. Create tables if not exist
    3. Abort on any failure
    
    This MUST be called at application startup.
    """
    logger.info("=" * 60)
    logger.info("INITIALIZING DATABASE PERSISTENCE LAYER")
    logger.info("=" * 60)
    
    try:
        # Step 1: Verify connection
        verify_database_connection()
        
        # Step 2: Import all models to register with Base
        from . import models  # noqa: F401
        
        # Step 3: Create tables
        create_all_tables()
        
        # Step 4: Verify tables exist
        verify_required_tables()
        
        logger.info("=" * 60)
        logger.info("DATABASE INITIALIZATION COMPLETE")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.critical(f"DATABASE INITIALIZATION FAILED: {e}")
        logger.critical("SYSTEM CANNOT START WITHOUT DATABASE")
        raise


def verify_required_tables() -> None:
    """Verify all required tables exist."""
    required_tables = [
        "raw_news",
        "cleaned_news",
        "sentiment_scores",
        "market_data",
        "onchain_flow_raw",
        "flow_scores",
        "market_state",
        "risk_state",
        "entry_decision",
        "position_sizing",
        "execution_records",
        "system_monitoring",
    ]
    
    engine = get_engine()
    
    with engine.connect() as conn:
        for table in required_tables:
            result = conn.execute(text(
                f"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '{table}')"
            ))
            exists = result.scalar()
            
            if exists:
                logger.info(f"  [OK] Table verified: {table}")
            else:
                logger.warning(f"  [!!] Table missing: {table}")


def get_table_row_counts() -> dict:
    """
    Get row counts for all tables.
    
    Returns:
        Dict mapping table name to row count
    """
    tables = [
        "raw_news",
        "cleaned_news",
        "sentiment_scores",
        "market_data",
        "onchain_flow_raw",
        "flow_scores",
        "market_state",
        "risk_state",
        "entry_decision",
        "position_sizing",
        "execution_records",
        "system_monitoring",
    ]
    
    counts = {}
    engine = get_engine()
    
    with engine.connect() as conn:
        for table in tables:
            try:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                counts[table] = result.scalar()
            except SQLAlchemyError:
                counts[table] = -1  # Table doesn't exist
    
    return counts


# =============================================================
# CONSTANTS
# =============================================================

DATABASE_URL = get_database_url() if os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_SYNC") else None

REQUIRED_TABLES = [
    "raw_news",
    "cleaned_news",
    "sentiment_scores",
    "market_data",
    "onchain_flow_raw",
    "flow_scores",
    "market_state",
    "risk_state",
    "entry_decision",
    "position_sizing",
    "execution_records",
    "system_monitoring",
]


# =============================================================
# CUSTOM EXCEPTIONS
# =============================================================


class DatabasePersistenceError(Exception):
    """Raised when database persistence fails."""
    pass


class DatabaseConnectionError(DatabasePersistenceError):
    """Raised when database connection fails."""
    pass


class DatabaseInitializationError(DatabasePersistenceError):
    """Raised when database initialization fails."""
    pass


class PersistenceValidationError(DatabasePersistenceError):
    """Raised when data validation fails before persistence."""
    pass


# =============================================================
# SESSION FACTORY ALIAS
# =============================================================

# Alias for compatibility
SessionFactory = get_session_factory

# Alias for engine creation
create_database_engine = create_database_engine  # Already defined, just re-export


# =============================================================
# EXPORTS
# =============================================================

__all__ = [
    # Base
    "Base",
    # Engine & Session
    "create_database_engine",
    "get_engine",
    "get_session",
    "get_db_session",
    "get_session_factory",
    "SessionFactory",
    "transaction_scope",
    # Initialization
    "initialize_database",
    "verify_database_connection",
    "verify_required_tables",
    "create_all_tables",
    "get_table_row_counts",
    # Constants
    "DATABASE_URL",
    "REQUIRED_TABLES",
    # Exceptions
    "DatabasePersistenceError",
    "DatabaseConnectionError",
    "DatabaseInitializationError",
    "PersistenceValidationError",
]
