"""Transactional phone/password and JWT authentication workflows."""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from anyio import to_thread
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    LOGIN_IP_RATE_LIMIT_COUNT,
    LOGIN_PHONE_RATE_LIMIT_COUNT,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    validate_auth_config,
)
from app.repositories import (
    AuthSessionRepository,
    LoginAttemptRepository,
    RateWindowStats,
    UserRepository,
)
from db.models import AuthSession, User

from .exceptions import (
    InactiveUser,
    InvalidCredentials,
    InvalidToken,
    LoginRateLimited,
    PhoneAlreadyRegistered,
    RevokedAuthSession,
    WeakPassword,
)
from .phone import normalize_phone
from .security import (
    TokenPair,
    advisory_lock_key,
    client_ip_digest,
    create_token_pair,
    decode_token,
    hash_password,
    phone_login_digest,
    refresh_token_digest,
    refresh_token_matches,
    utc_now,
    verify_and_update_password,
)


@dataclass(frozen=True)
class UserIdentity:
    id: uuid.UUID
    phone_e164: str
    is_active: bool


@dataclass(frozen=True)
class AuthenticationResult:
    user: UserIdentity
    tokens: TokenPair
    is_new_user: bool = False


class AuthService:
    """Coordinate password verification and revocable JWT sessions."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        validate_auth_config()
        self.session = session
        self.clock = clock
        self.users = UserRepository(session)
        self.login_attempts = LoginAttemptRepository(session)
        self.auth_sessions = AuthSessionRepository(session)

    async def register(
        self,
        raw_phone: str,
        password: str,
    ) -> AuthenticationResult:
        """Create a phone/password user and immediately start a session."""

        phone_e164 = normalize_phone(raw_phone)
        self._validate_registration_password(password)
        password_hash = await to_thread.run_sync(hash_password, password)
        now = self._now()

        async with self.session.begin():
            await self._acquire_advisory_locks([f"register:{phone_e164}"])
            if await self.users.get_by_phone(phone_e164) is not None:
                raise PhoneAlreadyRegistered("Phone number is already registered")

            user = await self.users.create(
                phone_e164,
                password_hash=password_hash,
                now=now,
            )
            user.last_login_at = now
            user.updated_at = now
            result = await self._create_authentication_result(
                user,
                now=now,
                is_new_user=True,
            )

        return result

    async def login(
        self,
        raw_phone: str,
        password: str,
        *,
        client_ip: str | None = None,
    ) -> AuthenticationResult:
        """Verify a phone/password pair and start a rate-limited session."""

        phone_e164 = normalize_phone(raw_phone)
        if not isinstance(password, str):
            raise InvalidCredentials("Invalid phone or password")

        phone_digest = phone_login_digest(phone_e164)
        request_ip_digest = (
            client_ip_digest(client_ip) if client_ip is not None else None
        )
        now = self._now()
        window_start = now - timedelta(seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        failure: Exception | None = None
        result: AuthenticationResult | None = None

        lock_identities = [f"login-phone:{phone_digest}"]
        if request_ip_digest is not None:
            lock_identities.append(f"login-ip:{request_ip_digest}")

        async with self.session.begin():
            await self._acquire_advisory_locks(lock_identities)
            await self._enforce_login_limits(
                phone_digest,
                request_ip_digest=request_ip_digest,
                window_start=window_start,
                now=now,
            )

            user = await self.users.get_by_phone(phone_e164)
            stored_hash = user.password_hash if user is not None else None
            valid, updated_hash = await to_thread.run_sync(
                verify_and_update_password,
                password,
                stored_hash,
            )

            if user is None or not valid:
                self.login_attempts.add_failure(
                    phone_digest,
                    request_ip_digest=request_ip_digest,
                    created_at=now,
                )
                await self.session.flush()
                failure = InvalidCredentials("Invalid phone or password")
            elif not user.is_active:
                failure = InvalidCredentials("Invalid phone or password")
            else:
                if updated_hash is not None:
                    user.password_hash = updated_hash
                user.last_login_at = now
                user.updated_at = now
                await self.login_attempts.clear_phone_failures(phone_digest)
                result = await self._create_authentication_result(user, now=now)

        if failure is not None:
            raise failure
        assert result is not None
        return result

    async def refresh(self, refresh_token: str) -> AuthenticationResult:
        """Rotate a refresh token or revoke the session on token replay."""

        claims = decode_token(refresh_token, "refresh")
        now = self._now()
        failure: Exception | None = None
        result: AuthenticationResult | None = None

        async with self.session.begin():
            auth_session = await self.auth_sessions.get_by_id(
                claims.session_id,
                for_update=True,
            )
            if auth_session is None or auth_session.user_id != claims.user_id:
                raise RevokedAuthSession("Authentication session not found")
            if auth_session.revoked_at is not None or auth_session.expires_at <= now:
                raise RevokedAuthSession("Authentication session is revoked")

            if not refresh_token_matches(
                refresh_token,
                auth_session.refresh_token_digest,
            ):
                await self.auth_sessions.revoke(
                    auth_session,
                    revoked_at=now,
                )
                failure = RevokedAuthSession(
                    "Refresh token replay detected; session revoked"
                )
            else:
                user = await self.users.get_by_id(claims.user_id)
                if user is None:
                    await self.auth_sessions.revoke(
                        auth_session,
                        revoked_at=now,
                    )
                    failure = InvalidToken("JWT user does not exist")
                elif not user.is_active:
                    await self.auth_sessions.revoke(
                        auth_session,
                        revoked_at=now,
                    )
                    failure = InactiveUser("User is inactive")
                else:
                    tokens = create_token_pair(
                        user.id,
                        auth_session.id,
                        now=now,
                    )
                    await self.auth_sessions.rotate(
                        auth_session,
                        refresh_token_digest=refresh_token_digest(tokens.refresh_token),
                        expires_at=tokens.refresh_expires_at,
                        used_at=now,
                    )
                    result = AuthenticationResult(
                        user=self._identity(user),
                        tokens=tokens,
                    )

        if failure is not None:
            raise failure
        assert result is not None
        return result

    async def authenticate_access_token(
        self,
        access_token: str,
    ) -> UserIdentity:
        """Resolve a valid access JWT through its revocable DB session."""

        claims = decode_token(access_token, "access")
        now = self._now()

        async with self.session.begin():
            auth_session = await self.auth_sessions.get_by_id(claims.session_id)
            if (
                auth_session is None
                or auth_session.user_id != claims.user_id
                or auth_session.revoked_at is not None
                or auth_session.expires_at <= now
            ):
                raise RevokedAuthSession("Authentication session is revoked")
            user = await self.users.get_by_id(claims.user_id)
            if user is None:
                raise InvalidToken("JWT user does not exist")
            if not user.is_active:
                raise InactiveUser("User is inactive")
            return self._identity(user)

    async def revoke_refresh_token(self, refresh_token: str) -> bool:
        """Idempotently revoke the signed session, including an expired token."""

        claims = decode_token(
            refresh_token,
            "refresh",
            verify_expiration=False,
        )
        now = self._now()

        async with self.session.begin():
            auth_session = await self.auth_sessions.get_by_id(
                claims.session_id,
                for_update=True,
            )
            if auth_session is None or auth_session.user_id != claims.user_id:
                return False
            if auth_session.revoked_at is None:
                await self.auth_sessions.revoke(
                    auth_session,
                    revoked_at=now,
                )
            return True

    async def _create_authentication_result(
        self,
        user: User,
        *,
        now: datetime,
        is_new_user: bool = False,
    ) -> AuthenticationResult:
        session_id = uuid.uuid4()
        tokens = create_token_pair(user.id, session_id, now=now)
        self.auth_sessions.add(
            AuthSession(
                id=session_id,
                user_id=user.id,
                refresh_token_digest=refresh_token_digest(tokens.refresh_token),
                expires_at=tokens.refresh_expires_at,
                created_at=now,
                updated_at=now,
            )
        )
        await self.session.flush()
        return AuthenticationResult(
            user=self._identity(user),
            tokens=tokens,
            is_new_user=is_new_user,
        )

    async def _enforce_login_limits(
        self,
        phone_digest: str,
        *,
        request_ip_digest: str | None,
        window_start: datetime,
        now: datetime,
    ) -> None:
        phone_stats = await self.login_attempts.phone_window_stats(
            phone_digest,
            since=window_start,
        )
        if phone_stats.count >= LOGIN_PHONE_RATE_LIMIT_COUNT:
            raise LoginRateLimited(self._window_retry_after(phone_stats, now))

        if request_ip_digest is not None:
            ip_stats = await self.login_attempts.ip_window_stats(
                request_ip_digest,
                since=window_start,
            )
            if ip_stats.count >= LOGIN_IP_RATE_LIMIT_COUNT:
                raise LoginRateLimited(self._window_retry_after(ip_stats, now))

    async def _acquire_advisory_locks(
        self,
        identities: Iterable[str],
    ) -> None:
        lock_keys = sorted({advisory_lock_key(value) for value in identities})
        for lock_key in lock_keys:
            await self.session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    @staticmethod
    def _validate_registration_password(password: str) -> None:
        if not isinstance(password, str) or not (
            PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH
        ):
            raise WeakPassword("Password does not satisfy the configured length")

    @staticmethod
    def _window_retry_after(
        stats: RateWindowStats,
        now: datetime,
    ) -> int:
        if stats.oldest_at is None:
            return LOGIN_RATE_LIMIT_WINDOW_SECONDS
        available_at = stats.oldest_at + timedelta(
            seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS
        )
        return max(1, math.ceil((available_at - now).total_seconds()))

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None:
            raise RuntimeError("Authentication clock must be timezone-aware")
        return now.astimezone(UTC)

    @staticmethod
    def _identity(user: User) -> UserIdentity:
        return UserIdentity(
            id=user.id,
            phone_e164=user.phone_e164,
            is_active=user.is_active,
        )
