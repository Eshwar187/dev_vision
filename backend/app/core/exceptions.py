import uuid
from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.logging import get_logger

logger = get_logger("exceptions")


class AppException(Exception):
    """Base domain exception for DevVision AI."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class EntityNotFoundException(AppException):
    """Raised when an entity is not found."""

    def __init__(self, message: str = "Entity not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="ENTITY_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ValidationException(AppException):
    """Raised when domain validation fails."""

    def __init__(self, message: str = "Validation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class ExternalServiceException(AppException):
    """Raised when an external service (e.g. MinIO, Redis) encounters an error."""

    def __init__(self, message: str = "External service failure", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="EXTERNAL_SERVICE_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=details,
        )


# ==============================================================================
# Phase 1: Authentication & Workspace Governance Exceptions
# ==============================================================================

class AuthenticationException(AppException):
    """Raised when request lacks valid authentication."""

    def __init__(self, message: str = "Authentication required.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="UNAUTHENTICATED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class InvalidCredentialsException(AppException):
    """Raised when email or password verification fails."""

    def __init__(self, message: str = "Invalid email or password.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="INVALID_CREDENTIALS",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class CSRFException(AppException):
    """Raised when CSRF token verification fails."""

    def __init__(self, message: str = "CSRF token validation failed.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="CSRF_TOKEN_INVALID",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class AuthorizationException(AppException):
    """Raised when authenticated user lacks sufficient permissions."""

    def __init__(self, message: str = "Insufficient permissions in this workspace.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class UserInactiveException(AppException):
    """Raised when account is deactivated."""

    def __init__(self, message: str = "Account is inactive. Please contact support.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="USER_INACTIVE",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class WorkspaceNotFoundException(AppException):
    """Raised when workspace does not exist or user is not a member (IDOR defense)."""

    def __init__(self, message: str = "Workspace not found.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="WORKSPACE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class UserNotFoundException(AppException):
    """Raised when an operation targets a non-existent user."""

    def __init__(self, message: str = "User not found.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="USER_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class MemberAlreadyExistsException(AppException):
    """Raised when adding a user who is already a member."""

    def __init__(self, message: str = "User is already a member of this workspace.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="MEMBER_ALREADY_EXISTS",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class LastOwnerException(AppException):
    """Raised when an action would remove or demote the last remaining owner."""

    def __init__(self, message: str = "Workspace must have at least one owner.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="CANNOT_REMOVE_LAST_OWNER",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class OwnershipTransferException(AppException):
    """Raised when ownership transfer cannot be performed."""

    def __init__(self, message: str = "Invalid ownership transfer request.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="INVALID_OWNERSHIP_TRANSFER",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


def build_error_response(
    code: str,
    message: str,
    status_code: int,
    request_id: str,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Builds a standardized RFC-compliant error JSON envelope."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id,
            }
        },
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    # Do not log invalid credentials at warning level in normal production
    if exc.code == "INVALID_CREDENTIALS":
        logger.info(
            "Authentication failed",
            code=exc.code,
            request_id=request_id,
        )
    else:
        logger.warning(
            "Application exception caught",
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            request_id=request_id,
            details=exc.details,
        )
    return build_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        request_id=request_id,
        details=exc.details,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.info(
        "Request validation error",
        request_id=request_id,
        errors=exc.errors(),
    )
    return build_error_response(
        code="REQUEST_VALIDATION_ERROR",
        message="Request parameters or body failed schema validation.",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        request_id=request_id,
        details={"validation_errors": exc.errors()},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return build_error_response(
        code=f"HTTP_{exc.status_code}",
        message=str(exc.detail),
        status_code=exc.status_code,
        request_id=request_id,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.exception(
        "Unhandled server error",
        request_id=request_id,
        error=str(exc),
    )
    return build_error_response(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected internal server error occurred. Please contact support with the request_id.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        request_id=request_id,
    )