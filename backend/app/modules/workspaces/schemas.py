import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.core.security import normalize_email


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)


class WorkspaceUpdateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_by: Optional[uuid.UUID]
    role: str
    created_at: datetime


class WorkspaceDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_by: Optional[uuid.UUID]
    role: str
    member_count: int
    created_at: datetime


class WorkspaceMemberItem(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: str
    joined_at: datetime


class WorkspaceMemberListResponse(BaseModel):
    members: List[WorkspaceMemberItem]


class MemberAddRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="member")

    @field_validator("email", mode="before")
    @classmethod
    def clean_email(cls, v: str) -> str:
        if isinstance(v, str):
            return normalize_email(v)
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("admin", "member"):
            raise ValueError("Role must be 'admin' or 'member'. To grant owner role, use ownership transfer.")
        return v


class MemberRoleUpdateRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("admin", "member"):
            raise ValueError("Role must be 'admin' or 'member'. To grant owner role, use ownership transfer.")
        return v


class TransferOwnershipRequest(BaseModel):
    new_owner_user_id: uuid.UUID