"""
Base Repository Class.

============================================================
PURPOSE
============================================================
Provides common functionality for all repositories including:
- Session management patterns
- Error handling wrappers
- Common query operations
- Logging setup

============================================================
USAGE
============================================================
All domain repositories inherit from BaseRepository.
Session is injected via constructor or method parameters.

============================================================
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Generic, List, Optional, Type, TypeVar
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.exc import (
    IntegrityError as SQLAlchemyIntegrityError,
    OperationalError,
    SQLAlchemyError,
)
from sqlalchemy.orm import Session

from storage.models.base import Base
from storage.repositories.exceptions import (
    ConnectionError,
    DuplicateRecordError,
    IntegrityError,
    QueryError,
    RecordNotFoundError,
    RepositoryException,
    TransactionError,
)


# Type variable for ORM model
T = TypeVar("T", bound=Base)


class BaseRepository(ABC, Generic[T]):
    """
    Abstract base class for all repositories.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    - Provides common CRUD patterns
    - Wraps database errors in repository exceptions
    - Manages logging for all operations
    - Enforces session handling patterns
    
    ============================================================
    USAGE
    ============================================================
    class MyRepository(BaseRepository[MyModel]):
        def __init__(self, session: Session):
            super().__init__(session, MyModel, "MyRepository")
    
    ============================================================
    """
    
    def __init__(
        self,
        session: Session,
        model_class: Type[T],
        repository_name: str
    ) -> None:
        """
        Initialize the repository.
        
        Args:
            session: SQLAlchemy session (injected)
            model_class: The ORM model class this repository manages
            repository_name: Name for logging and error messages
        """
        self._session = session
        self._model_class = model_class
        self._repository_name = repository_name
        self._logger = logging.getLogger(f"repository.{repository_name}")
    
    @property
    def session(self) -> Session:
        """Get the current session."""
        return self._session
    
    @property
    def model_class(self) -> Type[T]:
        """Get the managed model class."""
        return self._model_class
    
    @property
    def repository_name(self) -> str:
        """Get the repository name."""
        return self._repository_name
    
    # =========================================================
    # PROTECTED HELPER METHODS
    # =========================================================
    
    def _handle_db_error(
        self,
        error: Exception,
        operation: str,
        context: Optional[dict] = None
    ) -> None:
        """
        Handle database errors by wrapping in repository exceptions.
        
        Args:
            error: The original exception
            operation: Name of the operation that failed
            context: Additional context for logging
            
        Raises:
            RepositoryException: Always raises appropriate exception
        """
        context = context or {}
        self._logger.error(
            f"Database error in {operation}: {error}",
            extra={"context": context},
            exc_info=True
        )
        
        if isinstance(error, OperationalError):
            raise ConnectionError(
                repository_name=self._repository_name,
                operation=operation,
                original_error=str(error)
            ) from error
        
        if isinstance(error, SQLAlchemyIntegrityError):
            # Check for duplicate key
            error_str = str(error).lower()
            if "duplicate" in error_str or "unique" in error_str:
                raise DuplicateRecordError(
                    repository_name=self._repository_name,
                    constraint_field="unknown",
                    value="unknown"
                ) from error
            
            raise IntegrityError(
                repository_name=self._repository_name,
                operation=operation,
                constraint_name="unknown",
                message=str(error)
            ) from error
        
        raise QueryError(
            repository_name=self._repository_name,
            operation=operation,
            query_description=operation,
            original_error=str(error)
        ) from error
    
    def _add(self, entity: T) -> T:
        """
        Add an entity to the session.
        
        Args:
            entity: The entity to add
            
        Returns:
            The added entity
        """
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.debug(f"Added entity: {entity}")
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "add", {"entity": str(entity)})
            raise  # Never reached, but satisfies type checker
    
    def _get_by_id(self, record_id: UUID) -> Optional[T]:
        """
        Get an entity by its primary key.
        
        Args:
            record_id: The primary key UUID
            
        Returns:
            The entity or None if not found
        """
        try:
            return self._session.get(self._model_class, record_id)
        except SQLAlchemyError as e:
            self._handle_db_error(e, "get_by_id", {"id": str(record_id)})
            raise
    
    def _get_by_id_or_raise(self, record_id: UUID, id_field: str = "id") -> T:
        """
        Get an entity by its primary key, raising if not found.
        
        Args:
            record_id: The primary key UUID
            id_field: Name of the ID field for error message
            
        Returns:
            The entity
            
        Raises:
            RecordNotFoundError: If entity does not exist
        """
        entity = self._get_by_id(record_id)
        if entity is None:
            raise RecordNotFoundError(
                repository_name=self._repository_name,
                record_id=record_id,
                id_field=id_field
            )
        return entity
    
    def _count(self) -> int:
        """
        Count all entities.
        
        Returns:
            Total count of entities
        """
        try:
            stmt = select(func.count()).select_from(self._model_class)
            result = self._session.execute(stmt)
            return result.scalar() or 0
        except SQLAlchemyError as e:
            self._handle_db_error(e, "count")
            raise
    
    def _execute_query(self, stmt: Any) -> List[T]:
        """
        Execute a select statement and return results.
        
        Args:
            stmt: SQLAlchemy select statement
            
        Returns:
            List of entities
        """
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "query")
            raise
    
    def _execute_scalar(self, stmt: Any) -> Optional[T]:
        """
        Execute a select statement and return single result.
        
        Args:
            stmt: SQLAlchemy select statement
            
        Returns:
            Single entity or None
        """
        try:
            result = self._session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            self._handle_db_error(e, "query_scalar")
            raise
    
    def _commit(self) -> None:
        """
        Commit the current transaction.
        
        Raises:
            TransactionError: If commit fails
        """
        try:
            self._session.commit()
        except SQLAlchemyError as e:
            self._session.rollback()
            raise TransactionError(
                repository_name=self._repository_name,
                operation="commit",
                phase="commit",
                original_error=str(e)
            ) from e
    
    def _rollback(self) -> None:
        """
        Rollback the current transaction.
        """
        try:
            self._session.rollback()
        except SQLAlchemyError as e:
            self._logger.error(f"Rollback failed: {e}")
            raise TransactionError(
                repository_name=self._repository_name,
                operation="rollback",
                phase="rollback",
                original_error=str(e)
            ) from e
