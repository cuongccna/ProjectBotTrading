"""
Repository Layer Exceptions.

============================================================
PURPOSE
============================================================
Defines repository-specific exceptions for proper error handling
and propagation. All database errors must be caught and wrapped
in these exceptions.

============================================================
USAGE
============================================================
Repositories catch SQLAlchemy/database exceptions and re-raise
as repository exceptions with context.

Business layers catch repository exceptions and handle accordingly.

============================================================
"""

from typing import Any, Optional
from uuid import UUID


class RepositoryException(Exception):
    """
    Base exception for all repository operations.
    
    All repository-specific exceptions inherit from this class.
    Business layers can catch this for generic error handling.
    """
    
    def __init__(
        self,
        message: str,
        repository_name: str,
        operation: str,
        details: Optional[dict] = None
    ) -> None:
        self.message = message
        self.repository_name = repository_name
        self.operation = operation
        self.details = details or {}
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        return f"[{self.repository_name}] {self.operation}: {self.message}"


class RecordNotFoundError(RepositoryException):
    """
    Raised when a requested record does not exist.
    
    Use for get_by_* operations when the record is expected
    to exist but cannot be found.
    """
    
    def __init__(
        self,
        repository_name: str,
        record_id: Any,
        id_field: str = "id"
    ) -> None:
        super().__init__(
            message=f"Record with {id_field}={record_id} not found",
            repository_name=repository_name,
            operation="get",
            details={id_field: str(record_id)}
        )
        self.record_id = record_id
        self.id_field = id_field


class DuplicateRecordError(RepositoryException):
    """
    Raised when attempting to create a duplicate record.
    
    Use when unique constraint violations occur during insert.
    """
    
    def __init__(
        self,
        repository_name: str,
        constraint_field: str,
        value: Any
    ) -> None:
        super().__init__(
            message=f"Duplicate record: {constraint_field}={value} already exists",
            repository_name=repository_name,
            operation="create",
            details={"field": constraint_field, "value": str(value)}
        )
        self.constraint_field = constraint_field
        self.value = value


class IntegrityError(RepositoryException):
    """
    Raised when database integrity constraints are violated.
    
    Includes foreign key violations, check constraints, etc.
    """
    
    def __init__(
        self,
        repository_name: str,
        operation: str,
        constraint_name: str,
        message: str
    ) -> None:
        super().__init__(
            message=f"Integrity constraint violated ({constraint_name}): {message}",
            repository_name=repository_name,
            operation=operation,
            details={"constraint": constraint_name}
        )
        self.constraint_name = constraint_name


class ConnectionError(RepositoryException):
    """
    Raised when database connection fails.
    
    Use for connection timeouts, pool exhaustion, etc.
    """
    
    def __init__(
        self,
        repository_name: str,
        operation: str,
        original_error: str
    ) -> None:
        super().__init__(
            message=f"Database connection failed: {original_error}",
            repository_name=repository_name,
            operation=operation,
            details={"original_error": original_error}
        )


class QueryError(RepositoryException):
    """
    Raised when a query execution fails.
    
    Use for syntax errors, invalid parameters, etc.
    """
    
    def __init__(
        self,
        repository_name: str,
        operation: str,
        query_description: str,
        original_error: str
    ) -> None:
        super().__init__(
            message=f"Query failed ({query_description}): {original_error}",
            repository_name=repository_name,
            operation=operation,
            details={
                "query_description": query_description,
                "original_error": original_error
            }
        )


class TransactionError(RepositoryException):
    """
    Raised when transaction management fails.
    
    Use for commit failures, rollback issues, etc.
    """
    
    def __init__(
        self,
        repository_name: str,
        operation: str,
        phase: str,
        original_error: str
    ) -> None:
        super().__init__(
            message=f"Transaction {phase} failed: {original_error}",
            repository_name=repository_name,
            operation=operation,
            details={"phase": phase, "original_error": original_error}
        )
        self.phase = phase


class ImmutableRecordError(RepositoryException):
    """
    Raised when attempting to modify an immutable record.
    
    Use for append-only tables where updates are forbidden.
    """
    
    def __init__(
        self,
        repository_name: str,
        record_id: Any,
        attempted_operation: str
    ) -> None:
        super().__init__(
            message=f"Cannot {attempted_operation} immutable record {record_id}",
            repository_name=repository_name,
            operation=attempted_operation,
            details={"record_id": str(record_id)}
        )
        self.record_id = record_id
        self.attempted_operation = attempted_operation


class ValidationError(RepositoryException):
    """
    Raised when repository-level validation fails.
    
    Use for required fields, format validation at repository level.
    Note: Business validation belongs in service layer.
    """
    
    def __init__(
        self,
        repository_name: str,
        operation: str,
        field: str,
        reason: str
    ) -> None:
        super().__init__(
            message=f"Validation failed for {field}: {reason}",
            repository_name=repository_name,
            operation=operation,
            details={"field": field, "reason": reason}
        )
        self.field = field
        self.reason = reason
