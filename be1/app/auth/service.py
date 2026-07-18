"""Transactional phone OTP and JWT authentication workflows."""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    OTP_IP_RATE_LIMIT_COUNT,
    OTP_MAX_ATTEMPTS,
    OTP_PHONE_RATE_LIMIT_COUNT,
    OTP_RATE_LIMIT_WINDOW_SECONDS,
    OTP_RESEND_COOLDOWN_SECONDS,
    OTP_TTL_SECONDS,
    validate_auth_config,
)
from app.repositories import (
    AuthSessionRepository,
    OtpChallengeRepository,
    RateWindowStats,
    UserRepository,
)
from db.models import AuthSession, OtpChallenge, User

from .exceptions import (
    InactiveUser,
    InvalidOtpCode,
    InvalidToken,
    OtpChallengeConsumed,
    OtpChallengeExpired,
    OtpChallengeNotFound,
    OtpCooldown,
    OtpDeliveryError,
    OtpRateLimited,
    RevokedAuthSession,
)
from .otp_provider import OtpProvider, build_otp_provider
from .phone import mask_phone, normalize_phone
from .security import (
    TokenPair,
    advisory_lock_key,
    client_ip_digest,
    create_token_pair,
    decode_token,
    generate_otp,
    otp_digest,
    otp_matches,
    refresh_token_digest,
    refresh_token_matches,
    utc_now,
)


@dataclass(frozen=True)
class UserIdentity:
    id: uuid.UUID
    phone_e164: str
    is_active: bool


@dataclass(frozen=True)
class OtpRequestResult:
    challenge_id: uuid.UUID
    phone_e164: str
    masked_phone: str
    expires_at: datetime
    resend_available_at: datetime


@dataclass(frozen=True)
class AuthenticationResult:
    user: UserIdentity
    tokens: TokenPair
    is_new_user: bool = False


class AuthService:
    """Coordinate repositories, security primitives, and OTP delivery."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        otp_provider: OtpProvider | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        validate_auth_config()
        self.session = session
        self.otp_provider = otp_provider or build_otp_provider()
        self.clock = clock
        self.users = UserRepository(session)
        self.otp_challenges = OtpChallengeRepository(session)
        self.auth_sessions = AuthSessionRepository(session)

    async def request_otp(
        self,
        raw_phone: str,
        *,
        client_ip: str | None = None,
    ) -> OtpRequestResult:
        """Create, persist, and deliver a rate-limited OTP challenge."""

        phone_e164 = normalize_phone(raw_phone)
        request_ip_digest = (
            client_ip_digest(client_ip) if client_ip is not None else None
        )
        now = self._now()
        window_start = now - timedelta(seconds=OTP_RATE_LIMIT_WINDOW_SECONDS)
        challenge_id = uuid.uuid4()
        code = generate_otp()
        challenge = OtpChallenge(
            id=challenge_id,
            phone_e164=phone_e164,
            request_ip_digest=request_ip_digest,
            code_digest=otp_digest(challenge_id, phone_e164, code),
            expires_at=now + timedelta(seconds=OTP_TTL_SECONDS),
            attempts_remaining=OTP_MAX_ATTEMPTS,
            resend_available_at=now + timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS),
            created_at=now,
            updated_at=now,
        )

        lock_identities = [f"otp-phone:{phone_e164}"]
        if request_ip_digest is not None:
            lock_identities.append(f"otp-ip:{request_ip_digest}")

        async with self.session.begin():
            await self._acquire_advisory_locks(lock_identities)
            await self._enforce_request_limits(
                phone_e164,
                request_ip_digest=request_ip_digest,
                window_start=window_start,
                now=now,
            )
            await self.otp_challenges.invalidate_active_for_phone(
                phone_e164,
                consumed_at=now,
            )
            self.otp_challenges.add(challenge)
            await self.session.flush()

        try:
            await self.otp_provider.send_otp(
                phone_e164,
                code,
                expires_in_seconds=OTP_TTL_SECONDS,
            )
        except Exception as exc:
            await self._invalidate_failed_delivery(challenge_id)
            if isinstance(exc, OtpDeliveryError):
                raise
            raise OtpDeliveryError("OTP delivery failed") from exc

        return OtpRequestResult(
            challenge_id=challenge.id,
            phone_e164=phone_e164,
            masked_phone=mask_phone(phone_e164),
            expires_at=challenge.expires_at,
            resend_available_at=challenge.resend_available_at,
        )

    async def verify_otp(
        self,
        challenge_id: uuid.UUID | str,
        code: str,
    ) -> AuthenticationResult:
        """Consume a valid OTP and create a user authentication session."""

        parsed_challenge_id = self._parse_challenge_id(challenge_id)
        now = self._now()
        failure: Exception | None = None
        result: AuthenticationResult | None = None

        async with self.session.begin():
            challenge_phone = await self.otp_challenges.get_phone(parsed_challenge_id)
            if challenge_phone is None:
                raise OtpChallengeNotFound("OTP challenge was not found")

            await self._acquire_advisory_locks([f"otp-phone:{challenge_phone}"])
            challenge = await self.otp_challenges.get_by_id(
                parsed_challenge_id,
                for_update=True,
            )
            if challenge is None:
                raise OtpChallengeNotFound("OTP challenge was not found")

            if challenge.consumed_at is not None:
                raise OtpChallengeConsumed("OTP challenge is already consumed")

            if challenge.expires_at <= now:
                challenge.consumed_at = now
                challenge.updated_at = now
                failure = OtpChallengeExpired("OTP challenge has expired")
            elif not otp_matches(
                challenge.id,
                challenge.phone_e164,
                code.strip() if isinstance(code, str) else "",
                challenge.code_digest,
            ):
                challenge.attempts_remaining = max(
                    0,
                    challenge.attempts_remaining - 1,
                )
                challenge.updated_at = now
                if challenge.attempts_remaining == 0:
                    challenge.consumed_at = now
                failure = InvalidOtpCode(challenge.attempts_remaining)
            else:
                challenge.consumed_at = now
                challenge.updated_at = now
                user, is_new_user = await self.users.get_or_create_by_phone(
                    challenge.phone_e164,
                    now=now,
                )
                if not user.is_active:
                    failure = InactiveUser("User is inactive")
                else:
                    user.last_login_at = now
                    user.updated_at = now
                    session_id = uuid.uuid4()
                    tokens = create_token_pair(
                        user.id,
                        session_id,
                        now=now,
                    )
                    self.auth_sessions.add(
                        AuthSession(
                            id=session_id,
                            user_id=user.id,
                            refresh_token_digest=refresh_token_digest(
                                tokens.refresh_token
                            ),
                            expires_at=tokens.refresh_expires_at,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    await self.session.flush()
                    result = AuthenticationResult(
                        user=self._identity(user),
                        tokens=tokens,
                        is_new_user=is_new_user,
                    )

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

    async def _enforce_request_limits(
        self,
        phone_e164: str,
        *,
        request_ip_digest: str | None,
        window_start: datetime,
        now: datetime,
    ) -> None:
        latest = await self.otp_challenges.latest_for_phone(phone_e164)
        if latest is not None and latest.resend_available_at > now:
            raise OtpCooldown(self._seconds_until(latest.resend_available_at, now))

        phone_stats = await self.otp_challenges.phone_window_stats(
            phone_e164,
            since=window_start,
        )
        if phone_stats.count >= OTP_PHONE_RATE_LIMIT_COUNT:
            raise OtpRateLimited(self._window_retry_after(phone_stats, now))

        if request_ip_digest is not None:
            ip_stats = await self.otp_challenges.ip_window_stats(
                request_ip_digest,
                since=window_start,
            )
            if ip_stats.count >= OTP_IP_RATE_LIMIT_COUNT:
                raise OtpRateLimited(self._window_retry_after(ip_stats, now))

    async def _invalidate_failed_delivery(
        self,
        challenge_id: uuid.UUID,
    ) -> None:
        failed_at = self._now()
        async with self.session.begin():
            challenge = await self.otp_challenges.get_by_id(
                challenge_id,
                for_update=True,
            )
            if challenge is not None and challenge.consumed_at is None:
                challenge.consumed_at = failed_at
                challenge.resend_available_at = failed_at
                challenge.updated_at = failed_at
                await self.session.flush()

    async def _acquire_advisory_locks(
        self,
        identities: Iterable[str],
    ) -> None:
        lock_keys = sorted({advisory_lock_key(value) for value in identities})
        for lock_key in lock_keys:
            await self.session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    def _window_retry_after(
        self,
        stats: RateWindowStats,
        now: datetime,
    ) -> int:
        if stats.oldest_at is None:
            return OTP_RATE_LIMIT_WINDOW_SECONDS
        available_at = stats.oldest_at + timedelta(
            seconds=OTP_RATE_LIMIT_WINDOW_SECONDS
        )
        return self._seconds_until(available_at, now)

    @staticmethod
    def _seconds_until(available_at: datetime, now: datetime) -> int:
        return max(1, math.ceil((available_at - now).total_seconds()))

    @staticmethod
    def _parse_challenge_id(
        challenge_id: uuid.UUID | str,
    ) -> uuid.UUID:
        if isinstance(challenge_id, uuid.UUID):
            return challenge_id
        try:
            return uuid.UUID(challenge_id)
        except (AttributeError, TypeError, ValueError) as exc:
            raise OtpChallengeNotFound("OTP challenge identifier is invalid") from exc

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
