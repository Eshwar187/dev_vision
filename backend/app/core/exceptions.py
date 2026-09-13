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


# ==============================================================================
# Phase 2: Document Management Exceptions
# ==============================================================================

class DuplicateDocumentException(AppException):
    """Raised when a document with identical checksum exists in the workspace."""

    def __init__(self, message: str = "A document with identical content already exists in this workspace.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="DUPLICATE_DOCUMENT",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class DocumentNotFoundException(AppException):
    """Raised when a document is not found in the target workspace."""

    def __init__(self, message: str = "Document not found in this workspace.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="DOCUMENT_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class FileTooLargeException(AppException):
    """Raised when an uploaded file exceeds the configured size ceiling."""

    def __init__(self, message: str = "File size exceeds the maximum permitted limit.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="FILE_TOO_LARGE",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            details=details,
        )


class UnsupportedMediaTypeException(AppException):
    """Raised when a file extension or MIME type is unsupported."""

    def __init__(self, message: str = "Unsupported file type or extension.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="UNSUPPORTED_MEDIA_TYPE",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
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


class RateLimitException(AppException):
    """Raised when an operation exceeds its configured rate limit."""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please try again later.",
        retry_after: int = 60,
        details: Optional[Dict[str, Any]] = None,
    ):
        d = details or {}
        d["retry_after"] = retry_after
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=d,
        )
        self.retry_after = retry_after


class TimeoutException(AppException):
    """Raised when an operation or local AI inference times out."""

    def __init__(self, message: str = "The requested operation timed out.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="REQUEST_TIMEOUT",
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            details=details,
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
    resp = build_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        request_id=request_id,
        details=exc.details,
    )
    if hasattr(exc, "retry_after") and exc.retry_after:
        resp.headers["Retry-After"] = str(exc.retry_after)
    return resp


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