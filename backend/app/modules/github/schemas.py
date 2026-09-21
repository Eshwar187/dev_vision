"""Pydantic schemas for GitHub integration requests and responses."""

import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class GitHubConnectInitResponse(BaseModel):
    authorization_url: str
    state: str
    expires_at: datetime


class GitHubInstallationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    installation_id: int
    account_login: str
    account_id: int
    account_type: str
    installer_github_user_login: str
    created_at: datetime


class GitHubInstallationListResponse(BaseModel):
    items: List[GitHubInstallationSummary]


class GitHubDiscoveredRepo(BaseModel):
    github_repo_id: int
    name: str
    full_name: str
    default_branch: str
    is_private: bool
    is_archived: bool
    attachment_status: str  # 'unattached', 'attached_to_this_workspace', 'unavailable'
    installation_id: int
    installation_account: str


class GitHubDiscoveredRepoListResponse(BaseModel):
    items: List[GitHubDiscoveredRepo]


class GitHubRepoAttachRequest(BaseModel):
    github_repo_id: int = Field(..., description="GitHub's numeric repository ID")


class GitHubRepositorySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    codebase_id: uuid.UUID
    github_installation_id: uuid.UUID
    github_repo_id: int
    name: str
    full_name: str
    default_branch: str
    is_private: bool
    is_archived: bool
    created_at: datetime


class GitHubSyncRequest(BaseModel):
    ref: Optional[str] = Field(None, description="Branch or tag name. Defaults to repository default branch.")
    force: bool = Field(False, description="If True, reindexes even if commit SHA matches the active generation.")


class GitHubSyncRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    workspace_id: uuid.UUID
    requested_ref: str
    commit_sha: Optional[str] = None
    status: str
    file_count: int
    byte_count: int
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class GitHubSyncRunListResponse(BaseModel):
    items: List[GitHubSyncRunSummary]
