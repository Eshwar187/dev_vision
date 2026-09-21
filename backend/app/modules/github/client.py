"""High-performance, secure GitHub API client.
Enforces RS256 App JWT minting, ephemeral in-memory token caching, SSRF defenses,
strict redirect validation, and Authorization stripping.
"""

import asyncio
import ipaddress
import socket
import time
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import httpx
import jwt
import structlog

from app.core.config import get_settings
from app.core.exceptions import ValidationException

logger = structlog.get_logger(__name__)
settings = get_settings()

APPROVED_ARCHIVE_HOSTS = {"codeload.github.com"}


def is_safe_ip(ip_str: str) -> bool:
    """Validate that resolved IP address is not private, loopback, link-local, or cloud metadata."""
    try:
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or str(ip) == "169.254.169.254"
        ):
            return False
        return True
    except ValueError:
        return False


def validate_redirect_url(url: str) -> None:
    """Ensure redirect URL uses HTTPS, targets approved archive hosts, and resolves to safe public IPs."""
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValidationException(f"Insecure redirect scheme rejected: {parsed.scheme}")

    hostname = (parsed.hostname or "").lower()
    if hostname not in APPROVED_ARCHIVE_HOSTS:
        raise ValidationException(f"Redirect to unapproved archive host rejected: {hostname}")

    # DNS Resolution safety check
    try:
        addr_info = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
        for entry in addr_info:
            ip = entry[4][0]
            if not is_safe_ip(ip):
                raise ValidationException(f"Redirect resolved to restricted network address: {ip}")
    except socket.gaierror as e:
        raise ValidationException(f"Failed to resolve archive redirect destination: {e}")


class GitHubClient:
    def __init__(self):
        # In-memory installation token cache: { installation_id: { "token": str, "expires_at": datetime } }
        self._token_cache: Dict[int, Dict[str, Any]] = {}
        self._cache_locks: Dict[int, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _get_lock_for_installation(self, installation_id: int) -> asyncio.Lock:
        async with self._global_lock:
            if installation_id not in self._cache_locks:
                self._cache_locks[installation_id] = asyncio.Lock()
            return self._cache_locks[installation_id]

    def _create_app_jwt(self) -> str:
        """Create a short-lived (10 minute) RS256 JWT for GitHub App authentication."""
        app_id = settings.GITHUB_APP_ID
        private_key = settings.GITHUB_APP_PRIVATE_KEY
        if not app_id or not private_key:
            raise ValidationException("GitHub App credentials (ID / Private Key) are not configured.")

        # Normalize private key newlines if escaped
        if "\\n" in private_key:
            private_key = private_key.replace("\\n", "\n")

        now = int(time.time())
        payload = {
            "iat": now - 60,  # 60 seconds clock skew tolerance
            "exp": now + 600,  # 10 minutes maximum allowed by GitHub
            "iss": str(app_id),
        }
        return jwt.encode(payload, private_key, algorithm="RS256")

    async def get_installation_token(self, installation_id: int) -> str:
        """Retrieve or mint an in-memory installation access token for the given installation.
        Refreshes token 5 minutes before expiry. Never persists token.
        """
        lock = await self._get_lock_for_installation(installation_id)
        async with lock:
            now = datetime.now(timezone.utc)
            cached = self._token_cache.get(installation_id)
            if cached and cached["expires_at"] > (now + timedelta(minutes=5)):
                return cached["token"]

            # Mint new token via GitHub API
            app_jwt = self._create_app_jwt()
            url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
            headers = {
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "DevVision-AI",
            }

            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, headers=headers)
                if res.status_code != 201:
                    logger.error("github_token_minting_failed", status=res.status_code, body=res.text)
                    raise ValidationException(f"Failed to obtain installation token: {res.status_code}")

                data = res.json()
                token = data["token"]
                expires_at_str = data["expires_at"]
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))

                self._token_cache[installation_id] = {
                    "token": token,
                    "expires_at": expires_at,
                }
                return token

    def invalidate_installation_token(self, installation_id: int) -> None:
        """Invalidate cached token (e.g. following a 401 response)."""
        self._token_cache.pop(installation_id, None)

    async def exchange_oauth_code(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: Optional[str] = None,
    ) -> str:
        """Exchange OAuth code using PKCE code_verifier for an ephemeral user access token.
        User token is returned in-memory and MUST NOT be persisted.
        """
        client_id = settings.GITHUB_APP_CLIENT_ID
        client_secret = settings.GITHUB_APP_CLIENT_SECRET
        if not client_id or not client_secret:
            raise ValidationException("GitHub App OAuth Client ID/Secret not configured.")

        url = "https://github.com/login/oauth/access_token"
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "code_verifier": code_verifier,
        }
        if redirect_uri:
            payload["redirect_uri"] = redirect_uri

        headers = {
            "Accept": "application/json",
            "User-Agent": "DevVision-AI",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            if res.status_code != 200:
                raise ValidationException(f"OAuth code exchange failed with status {res.status_code}")

            data = res.json()
            if "error" in data:
                raise ValidationException(f"OAuth error: {data.get('error_description', data['error'])}")

            user_token = data.get("access_token")
            if not user_token:
                raise ValidationException("No access_token returned in OAuth exchange.")
            return user_token

    async def get_authenticated_user(self, user_token: str) -> Dict[str, Any]:
        """Fetch authenticated user profile using ephemeral user token."""
        url = "https://api.github.com/user"
        headers = {
            "Authorization": f"Bearer {user_token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "DevVision-AI",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code != 200:
                raise ValidationException(f"Failed to fetch authenticated GitHub user: {res.status_code}")
            return res.json()

    async def verify_user_installation_authority(
        self,
        user_token: str,
        installation_id: int,
        installer_github_user: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Verify the GitHub user actually possesses administrative authority over the installation.
        Rejects read-only and write-only users; accepts administrative users.
        Returns the verified installation metadata.
        """
        # 1. Fetch installations accessible to the user
        url = "https://api.github.com/user/installations"
        headers = {
            "Authorization": f"Bearer {user_token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "DevVision-AI",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code != 200:
                raise ValidationException("Failed to query user installations from GitHub.")

            data = res.json()
            installations = data.get("installations", [])
            target_inst = next((inst for inst in installations if inst["id"] == installation_id), None)
            if not target_inst:
                raise ValidationException(
                    f"Installation {installation_id} is not accessible to the authenticated GitHub user."
                )

            account = target_inst.get("account", {})
            target_type = target_inst.get("target_type", account.get("type", "User"))

            # 2. Administrative authority verification
            if target_type == "User":
                # For personal account installations, installer must be the account owner
                if account.get("id") != installer_github_user.get("id"):
                    raise ValidationException("Only the personal account owner can authorize installations.")
            elif target_type == "Organization":
                org_login = account.get("login")
                # Query user's membership role in the organization
                membership_url = f"https://api.github.com/orgs/{org_login}/memberships/{installer_github_user.get('login')}"
                mem_res = await client.get(membership_url, headers=headers)
                if mem_res.status_code == 200:
                    mem_data = mem_res.json()
                    role = mem_data.get("role")
                    if role != "admin":
                        raise ValidationException(
                            f"Administrative authority required. Current organization role is '{role}'."
                        )
                else:
                    # Fallback: inspect installation permissions block if membership endpoint is unavailable
                    permissions = target_inst.get("permissions", {})
                    # If organization explicitly granted admin permissions
                    if permissions.get("administration") != "write" and permissions.get("organization_administration") != "write":
                        # If unable to prove admin role, reject for security
                        raise ValidationException(
                            "Cannot verify organization administrative authority for this installation."
                        )

            return target_inst

    async def verify_app_installation_exists(self, installation_id: int) -> Dict[str, Any]:
        """Independently verify that the installation exists and belongs to this DevVision App."""
        app_jwt = self._create_app_jwt()
        url = f"https://api.github.com/app/installations/{installation_id}"
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "DevVision-AI",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code != 200:
                raise ValidationException(
                    f"Installation {installation_id} does not belong to this DevVision GitHub App."
                )
            return res.json()

    async def list_installation_repositories(
        self,
        installation_id: int,
    ) -> List[Dict[str, Any]]:
        """List repositories accessible to the installation with pagination."""
        token = await self.get_installation_token(installation_id)
        repos: List[Dict[str, Any]] = []
        page = 1
        per_page = 100

        async with httpx.AsyncClient(timeout=20.0) as client:
            while True:
                url = f"https://api.github.com/installation/repositories?per_page={per_page}&page={page}"
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "DevVision-AI",
                }
                res = await client.get(url, headers=headers)
                if res.status_code == 401:
                    self.invalidate_installation_token(installation_id)
                    token = await self.get_installation_token(installation_id)
                    headers["Authorization"] = f"Bearer {token}"
                    res = await client.get(url, headers=headers)

                if res.status_code != 200:
                    raise ValidationException(f"Failed to list installation repositories: {res.status_code}")

                data = res.json()
                page_repos = data.get("repositories", [])
                repos.extend(page_repos)

                total_count = data.get("total_count", 0)
                if len(repos) >= total_count or not page_repos:
                    break
                page += 1

        return repos

    async def resolve_commit_sha(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        ref: str,
    ) -> str:
        """Resolve a mutable branch or tag ref into a verified 40-hex character commit SHA."""
        token = await self.get_installation_token(installation_id)
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{ref}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "DevVision-AI",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 401:
                self.invalidate_installation_token(installation_id)
                token = await self.get_installation_token(installation_id)
                headers["Authorization"] = f"Bearer {token}"
                res = await client.get(url, headers=headers)

            if res.status_code == 404:
                raise ValidationException(f"Commit/ref '{ref}' not found in repository {owner}/{repo}.")
            if res.status_code != 200:
                raise ValidationException(f"Failed to resolve commit ref: {res.status_code}")

            sha = res.json().get("sha", "")
            if len(sha) != 40 or not all(c in "0123456789abcdefABCDEF" for c in sha):
                raise ValidationException("Invalid commit SHA returned by GitHub API.")
            return sha.lower()

    async def download_tarball_archive(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        commit_sha: str,
        max_bytes: int = 100 * 1024 * 1024,
    ) -> bytes:
        """Download tarball archive for an immutable commit SHA with strict redirect security.
        Strips Authorization headers before crossing to archive host (codeload.github.com).
        Enforces compressed size limit.
        """
        token = await self.get_installation_token(installation_id)
        initial_url = f"https://api.github.com/repos/{owner}/{repo}/tarball/{commit_sha}"
        initial_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "DevVision-AI",
        }

        # Step 1: Initial request to api.github.com with follow_redirects=False
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            res = await client.get(initial_url, headers=initial_headers)

            # GitHub returns 302 redirect to codeload.github.com
            if res.status_code in (301, 302, 307, 308):
                redirect_url = res.headers.get("Location")
                if not redirect_url:
                    raise ValidationException("GitHub tarball response lacked Location header.")

                # Validate redirect destination strictly (HTTPS, codeload.github.com, no private IPs)
                validate_redirect_url(redirect_url)

                # Step 2: Follow redirect WITHOUT Authorization header
                archive_headers = {
                    "User-Agent": "DevVision-AI",
                    "Accept": "*/*",
                }

                # Stream response body to enforce compressed size limit
                chunks = []
                total_downloaded = 0
                async with client.stream("GET", redirect_url, headers=archive_headers) as stream_res:
                    if stream_res.status_code != 200:
                        raise ValidationException(f"Archive download failed with status {stream_res.status_code}")

                    async for chunk in stream_res.aiter_bytes(chunk_size=65536):
                        total_downloaded += len(chunk)
                        if total_downloaded > max_bytes:
                            raise ValidationException(
                                f"Repository archive exceeds compressed size limit of {max_bytes // (1024 * 1024)}MB."
                            )
                        chunks.append(chunk)

                return b"".join(chunks)

            elif res.status_code == 200:
                # Direct response without redirect (fallback)
                if len(res.content) > max_bytes:
                    raise ValidationException("Repository archive exceeds compressed size limit.")
                return res.content
            else:
                raise ValidationException(f"Tarball request failed with status {res.status_code}: {res.text}")
