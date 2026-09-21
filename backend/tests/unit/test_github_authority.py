"""Unit tests for GitHub installer administrative authority verification."""

import pytest
from unittest.mock import AsyncMock, patch
from app.core.exceptions import ValidationException
from app.modules.github.client import GitHubClient


@pytest.mark.asyncio
async def test_personal_account_authority_owner_accepted():
    """Verify that a personal account installation is accepted when the installer is the account owner."""
    client = GitHubClient()
    user_token = "ghu_fake_user_token"
    installation_id = 12345
    installer_github_user = {"id": 999, "login": "alice"}

    mock_installations_response = {
        "installations": [
            {
                "id": 12345,
                "target_type": "User",
                "account": {"id": 999, "login": "alice", "type": "User"},
            }
        ]
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(status_code=200, json=lambda: mock_installations_response)
        res = await client.verify_user_installation_authority(
            user_token=user_token,
            installation_id=installation_id,
            installer_github_user=installer_github_user,
        )
        assert res["id"] == 12345


@pytest.mark.asyncio
async def test_personal_account_authority_mismatched_owner_rejected():
    """Verify that a personal account installation is rejected if the installer is not the account owner."""
    client = GitHubClient()
    user_token = "ghu_fake_user_token"
    installation_id = 12345
    installer_github_user = {"id": 888, "login": "attacker"}  # Different ID

    mock_installations_response = {
        "installations": [
            {
                "id": 12345,
                "target_type": "User",
                "account": {"id": 999, "login": "alice", "type": "User"},
            }
        ]
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(status_code=200, json=lambda: mock_installations_response)
        with pytest.raises(ValidationException, match="Only the personal account owner can authorize"):
            await client.verify_user_installation_authority(
                user_token=user_token,
                installation_id=installation_id,
                installer_github_user=installer_github_user,
            )


@pytest.mark.asyncio
async def test_organization_account_authority_admin_accepted():
    """Verify that an organization installation is accepted when user is verified org admin."""
    client = GitHubClient()
    user_token = "ghu_fake_user_token"
    installation_id = 54321
    installer_github_user = {"id": 101, "login": "org_admin_user"}

    mock_installations_response = {
        "installations": [
            {
                "id": 54321,
                "target_type": "Organization",
                "account": {"id": 500, "login": "acme-corp", "type": "Organization"},
            }
        ]
    }
    mock_membership_response = {"role": "admin", "state": "active"}

    with patch("httpx.AsyncClient.get") as mock_get:
        # First call returns installations list; second call returns membership
        mock_get.side_effect = [
            AsyncMock(status_code=200, json=lambda: mock_installations_response),
            AsyncMock(status_code=200, json=lambda: mock_membership_response),
        ]
        res = await client.verify_user_installation_authority(
            user_token=user_token,
            installation_id=installation_id,
            installer_github_user=installer_github_user,
        )
        assert res["id"] == 54321


@pytest.mark.asyncio
async def test_organization_account_authority_readonly_member_rejected():
    """Verify that an organization installation is rejected when user has read-only/member role."""
    client = GitHubClient()
    user_token = "ghu_fake_user_token"
    installation_id = 54321
    installer_github_user = {"id": 102, "login": "readonly_user"}

    mock_installations_response = {
        "installations": [
            {
                "id": 54321,
                "target_type": "Organization",
                "account": {"id": 500, "login": "acme-corp", "type": "Organization"},
            }
        ]
    }
    mock_membership_response = {"role": "member", "state": "active"}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = [
            AsyncMock(status_code=200, json=lambda: mock_installations_response),
            AsyncMock(status_code=200, json=lambda: mock_membership_response),
        ]
        with pytest.raises(ValidationException, match="Administrative authority required"):
            await client.verify_user_installation_authority(
                user_token=user_token,
                installation_id=installation_id,
                installer_github_user=installer_github_user,
            )


@pytest.mark.asyncio
async def test_organization_account_authority_write_only_member_rejected():
    """Verify that an organization installation is rejected when user is write-only / non-admin."""
    client = GitHubClient()
    user_token = "ghu_fake_user_token"
    installation_id = 54321
    installer_github_user = {"id": 103, "login": "writer_user"}

    mock_installations_response = {
        "installations": [
            {
                "id": 54321,
                "target_type": "Organization",
                "account": {"id": 500, "login": "acme-corp", "type": "Organization"},
            }
        ]
    }
    # Membership endpoint not found or returns non-admin role
    mock_membership_response = {"role": "contributor", "state": "active"}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = [
            AsyncMock(status_code=200, json=lambda: mock_installations_response),
            AsyncMock(status_code=200, json=lambda: mock_membership_response),
        ]
        with pytest.raises(ValidationException, match="Administrative authority required"):
            await client.verify_user_installation_authority(
                user_token=user_token,
                installation_id=installation_id,
                installer_github_user=installer_github_user,
            )
