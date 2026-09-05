from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_active_user, get_current_user, verify_csrf_token
from app.core.config import get_settings
from app.core.database import get_db
from app.modules.identity.models import User
from app.modules.identity.schemas import (
    LoginResponse,
    LogoutResponse,
    RegisterResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    WorkspaceSimpleResponse,
)
from app.modules.identity.service import IdentityService

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


def _set_auth_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    """Sets HttpOnly session cookie and accessible CSRF cookie."""
    # HttpOnly session cookie (inaccessible to JS)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.cookie_secure_effective,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )
    # Accessible CSRF cookie (read by frontend JS to send in X-CSRF-Token header)
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=False,
        secure=settings.cookie_secure_effective,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clears session and CSRF cookies on logout."""
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(key=settings.CSRF_COOKIE_NAME, path="/")


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user account",
)
async def register(
    request: Request,
    response: Response,
    data: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user, workspace, session_token, csrf_token = await IdentityService.register_user(
        db=db,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if not user or not workspace or not session_token or not csrf_token:
        # Anti-enumeration response: email already registered
        response.status_code = status.HTTP_200_OK
        return RegisterResponse(
            status="success",
            message="If this email is not already registered, your account has been created. Please log in.",
            user=None,
            workspace=None,
        )

    _set_auth_cookies(response, session_token, csrf_token)

    return RegisterResponse(
        status="success",
        message="Account registered successfully.",
        user=UserResponse.model_validate(user),
        workspace=WorkspaceSimpleResponse(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            role="owner",
        ),
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="User login with email and password",
)
async def login(
    request: Request,
    response: Response,
    data: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user, session_token, csrf_token = await IdentityService.authenticate_user(
        db=db,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    _set_auth_cookies(response, session_token, csrf_token)
    return LoginResponse(user=UserResponse.model_validate(user))


@router.post(
    "/logout",
    response_model=LogoutResponse,
    dependencies=[Depends(verify_csrf_token)],
    summary="Logout user and invalidate session",
)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LogoutResponse:
    token_hash = getattr(request.state, "session_token_hash", None)
    if token_hash:
        await IdentityService.logout(db, token_hash)

    _clear_auth_cookies(response)
    return LogoutResponse(status="ok", message="Successfully logged out.")


@router.get(
    "/me",
    response_model=LoginResponse,
    summary="Get current authenticated user profile",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> LoginResponse:
    return LoginResponse(user=UserResponse.model_validate(current_user))