import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.modules.identity.models import Session, User
from app.core.security import hash_session_token, hash_password


@pytest.mark.asyncio
async def test_register_success(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "dev1@example.com",
            "password": "PasswordWithLength123!",
            "display_name": "Developer One",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["user"]["email"] == "dev1@example.com"
    assert data["user"]["display_name"] == "Developer One"
    assert "password_hash" not in data["user"]
    assert data["workspace"]["role"] == "owner"
    assert "developer-one" in data["workspace"]["slug"]

    # Verify cookies set
    assert "devvision_session" in response.cookies
    assert "devvision_csrf" in response.cookies


@pytest.mark.asyncio
async def test_register_duplicate_email_generic_response(async_client: AsyncClient):
    payload = {
        "email": "duplicate@example.com",
        "password": "PasswordWithLength123!",
        "display_name": "Original User",
    }
    # Initial registration
    res1 = await async_client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    # Second registration with same email
    res2 = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "DUPLICATE@example.com",  # Different case
            "password": "PasswordWithLength123!",
            "display_name": "Impostor",
        },
    )
    # Anti-enumeration invariant: returns 200 OK generic response, does not leak 409
    assert res2.status_code == 200
    data = res2.json()
    assert data["status"] == "success"
    assert data["user"] is None
    assert data["workspace"] is None
    assert "If this email is not already registered" in data["message"]
    # Impostor should NOT receive session cookie
    assert "devvision_session" not in res2.cookies


@pytest.mark.asyncio
async def test_register_password_length_policy(async_client: AsyncClient):
    # Too short (< 12 chars)
    res_short = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "short@example.com",
            "password": "Short123!",
            "display_name": "Short Pwd",
        },
    )
    assert res_short.status_code == 422

    # Valid 12+ chars with spaces and unicode
    res_valid = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "valid_length@example.com",
            "password": "correct horse battery staple 🚀",
            "display_name": "Valid Passphrase",
        },
    )
    assert res_valid.status_code == 201


@pytest.mark.asyncio
async def test_login_and_logout_flow(async_client: AsyncClient):
    # 1. Register
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "login_user@example.com",
            "password": "MySecretPassword123!",
            "display_name": "Login Tester",
        },
    )

    # 2. Login with valid credentials
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": "LOGIN_USER@example.com",
            "password": "MySecretPassword123!",
        },
    )
    assert login_res.status_code == 200
    assert "devvision_session" in login_res.cookies
    assert "devvision_csrf" in login_res.cookies
    csrf_token = login_res.cookies["devvision_csrf"]

    # 3. Access /api/v1/auth/me (GET does not require CSRF header)
    me_res = await async_client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["user"]["email"] == "login_user@example.com"

    # 4. Logout with missing CSRF header -> 403 CSRF_TOKEN_INVALID
    logout_bad_csrf = await async_client.post("/api/v1/auth/logout")
    assert logout_bad_csrf.status_code == 403
    assert logout_bad_csrf.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    # 5. Logout with valid CSRF header -> 200 OK
    logout_ok = await async_client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_ok.status_code == 200

    # 6. Subsequent /api/v1/auth/me request should be unauthenticated (401)
    me_after_logout = await async_client.get("/api/v1/auth/me")
    assert me_after_logout.status_code == 401


@pytest.mark.asyncio
async def test_login_anti_enumeration(async_client: AsyncClient):
    # Non-existent email
    res_nonexistent = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "SomePassword123!",
        },
    )
    assert res_nonexistent.status_code == 401
    assert res_nonexistent.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert res_nonexistent.json()["error"]["message"] == "Invalid email or password."

    # Existing user with incorrect password
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "realuser@example.com",
            "password": "RealPassword123!",
            "display_name": "Real User",
        },
    )
    res_wrong_pw = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": "realuser@example.com",
            "password": "IncorrectPassword123!",
        },
    )
    assert res_wrong_pw.status_code == 401
    assert res_wrong_pw.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert res_wrong_pw.json()["error"]["message"] == "Invalid email or password."


@pytest.mark.asyncio
async def test_login_inactive_user(async_client: AsyncClient, db_session: AsyncSession):
    # Register user
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "inactive@example.com",
            "password": "MyPassword123!",
            "display_name": "Inactive User",
        },
    )

    # Deactivate in database
    user = await db_session.scalar(select(User).where(User.email == "inactive@example.com"))
    user.is_active = False
    await db_session.commit()

    # Attempt login
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": "inactive@example.com",
            "password": "MyPassword123!",
        },
    )
    assert login_res.status_code == 403
    assert login_res.json()["error"]["code"] == "USER_INACTIVE"


@pytest.mark.asyncio
async def test_expired_session_rejection_and_lazy_delete(async_client: AsyncClient, db_session: AsyncSession):
    # Register user
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "expired@example.com",
            "password": "Password123456!",
            "display_name": "Expiring User",
        },
    )
    session_token = reg_res.cookies["devvision_session"]
    token_hash = hash_session_token(session_token)

    # Manually expire session in DB
    session = await db_session.scalar(select(Session).where(Session.token_hash == token_hash))
    session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()

    # Attempt authenticated request
    res = await async_client.get("/api/v1/auth/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHENTICATED"

    # Verify session was lazily deleted
    session_after = await db_session.scalar(select(Session).where(Session.token_hash == token_hash))
    assert session_after is None