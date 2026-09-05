import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.core.security import normalize_email


class UserRegisterRequest(BaseModel):
    """User registration payload."""

    email: EmailStr
    password: str = Field(..., min_length=12, max_length=128, description="Minimum 12 characters, all UTF-8 characters allowed.")
    display_name: str = Field(..., min_length=2, max_length=100)

    @field_validator("email", mode="before")
    @classmethod
    def clean_email(cls, v: str) -> str:
        if isinstance(v, str):
            return normalize_email(v)
        return v

    @field_validator("display_name", mode="before")
    @classmethod
    def clean_display_name(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v


class UserLoginRequest(BaseModel):
    """User login payload."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def clean_email(cls, v: str) -> str:
        if isinstance(v, str):
            return normalize_email(v)
        return v


class UserResponse(BaseModel):
    """User profile response without sensitive security hashes."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    is_active: bool
    created_at: datetime


class WorkspaceSimpleResponse(BaseModel):
    """Minimal workspace info returned upon registration."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    role: str


class RegisterResponse(BaseModel):
    """Generic registration response preventing account enumeration."""

    status: str
    message: str
    user: Optional[UserResponse] = None
    workspace: Optional[WorkspaceSimpleResponse] = None


class LoginResponse(BaseModel):
    """Login response returning authenticated user profile."""

    user: UserResponse


class LogoutResponse(BaseModel):
    """Logout status message."""

    status: str
    message: str