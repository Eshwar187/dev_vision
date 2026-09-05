import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.exceptions import InvalidCredentialsException, UserInactiveException
from app.core.logging import get_logger
from app.core.security import (
    generate_csrf_token,
    generate_session_token,
    hash_password,
    hash_session_token,
    normalize_email,
    verify_dummy_password,
    verify_password,
)
from app.modules.identity.models import Session, User
from app.modules.identity.schemas import UserLoginRequest, UserRegisterRequest
from app.modules.workspaces.models import Workspace, WorkspaceMembership

logger = get_logger("identity.service")
settings = get_settings()


class IdentityService:
    """Service managing user authentication, sessions, and registration."""

    @staticmethod
    def _generate_slug(base_name: str) -> str:
        """Generates a URL-safe base slug from a display name."""
        cleaned = "".join(c if c.isalnum() else "-" for c in base_name.lower())
        slug = "-".join(part for part in cleaned.split("-") if part)
        return slug or "workspace"

    @classmethod
    async def _resolve_unique_slug(cls, db: AsyncSession, base_slug: str) -> str:
        """Resolves collisions by appending numeric suffix (e.g. acme, acme-1, acme-2)."""
        slug = base_slug
        counter = 1
        while True:
            existing = await db.scalar(select(Workspace.id).where(Workspace.slug == slug))
            if not existing:
                return slug
            slug = f"{base_slug}-{counter}"
            counter += 1

    @classmethod
    async def register_user(
        cls,
        db: AsyncSession,
        data: UserRegisterRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[Optional[User], Optional[Workspace], Optional[str], Optional[str]]:
        """
        Registers a new user, creates their initial personal workspace (role: owner),
        and issues an authenticated session within a single transaction.

        Anti-Enumeration Defense:
        If email already exists, executes dummy Argon2id verification and returns
        (None, None, None, None) to present a uniform success message to caller.
        """
        normalized = normalize_email(data.email)

        # Check existing user
        existing_user = await db.scalar(select(User).where(User.email == normalized))
        if existing_user:
            # Equalize timing via dummy verification
            verify_dummy_password(data.password)
            logger.info("Registration attempted with existing email (anti-enumeration applied)")
            return None, None, None, None

        pwd_hash = hash_password(data.password)

        try:
            # 1. Create User
            user = User(
                email=normalized,
                password_hash=pwd_hash,
                display_name=data.display_name,
                is_active=True,
            )
            db.add(user)
            await db.flush()  # Populates user.id

            # 2. Create Default Workspace
            base_slug = cls._generate_slug(f"{data.display_name}-workspace")
            slug = await cls._resolve_unique_slug(db, base_slug)

            workspace = Workspace(
                name=f"{data.display_name}'s Workspace",
                slug=slug,
                created_by=user.id,
            )
            db.add(workspace)
            await db.flush()  # Populates workspace.id

            # 3. Create Owner Membership
            membership = WorkspaceMembership(
                user_id=user.id,
                workspace_id=workspace.id,
                role="owner",
            )
            db.add(membership)

            # 4. Generate Session & CSRF Tokens
            raw_session_token = generate_session_token()
            csrf_token = generate_csrf_token()
            token_hash = hash_session_token(raw_session_token)

            expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS)
            session = Session(
                user_id=user.id,
                token_hash=token_hash,
                ip_address=ip_address,
                user_agent=user_agent,
                expires_at=expires_at,
            )
            db.add(session)

            await db.commit()
            await db.refresh(user)
            await db.refresh(workspace)

            logger.info("New user registered successfully", user_id=str(user.id))
            return user, workspace, raw_session_token, csrf_token

        except IntegrityError:
            await db.rollback()
            # Race condition: another request registered same email concurrently
            verify_dummy_password(data.password)
            return None, None, None, None
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def authenticate_user(
        cls,
        db: AsyncSession,
        data: UserLoginRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[User, str, str]:
        """
        Authenticates user via email and password using Argon2id.
        Applies dummy hash verification if email does not exist to prevent timing attacks.
        Returns (user, raw_session_token, csrf_token).
        """
        normalized = normalize_email(data.email)
        user = await db.scalar(select(User).where(User.email == normalized))

        if not user:
            verify_dummy_password(data.password)
            raise InvalidCredentialsException()

        if not user.is_active:
            raise UserInactiveException()

        if not verify_password(data.password, user.password_hash):
            raise InvalidCredentialsException()

        # Create session
        raw_session_token = generate_session_token()
        csrf_token = generate_csrf_token()
        token_hash = hash_session_token(raw_session_token)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS)

        session = Session(
            user_id=user.id,
            token_hash=token_hash,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )
        db.add(session)
        await db.commit()
        await db.refresh(user)

        logger.info("User logged in successfully", user_id=str(user.id))
        return user, raw_session_token, csrf_token

    @classmethod
    async def logout(cls, db: AsyncSession, token_hash: str) -> None:
        """Invalidates current session by deleting it from database."""
        session = await db.scalar(select(Session).where(Session.token_hash == token_hash))
        if session:
            await db.delete(session)
            await db.commit()
            logger.info("Session invalidated on logout", user_id=str(session.user_id))

    @classmethod
    async def get_user_by_session_hash(cls, db: AsyncSession, token_hash: str) -> Optional[User]:
        """
        Retrieves user associated with a valid, unexpired session token hash.
        Lazily deletes expired session if encountered.
        """
        result = await db.execute(
            select(Session, User)
            .join(User, Session.user_id == User.id)
            .where(Session.token_hash == token_hash)
        )
        row = result.first()
        if not row:
            return None

        session, user = row
        now = datetime.now(timezone.utc)

        # Lazy deletion of expired session
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            await db.delete(session)
            await db.commit()
            return None

        if not user.is_active:
            return None

        return user