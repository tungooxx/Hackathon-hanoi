"""Cryptographic primitives for passwords, rate-limit identifiers, and JWTs."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.config import (
    AUTH_RATE_LIMIT_SECRET,
    AUTH_TOKEN_DIGEST_SECRET,
    JWT_ACCESS_TTL_SECONDS,
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
    JWT_LEEWAY_SECONDS,
    JWT_REFRESH_TTL_SECONDS,
    JWT_SECRET_KEY,
    validate_auth_config,
)

from .exceptions import ExpiredToken, InvalidToken

TokenType = Literal["access", "refresh"]
_password_hash = PasswordHash.recommended()
_dummy_password_hash = _password_hash.hash(
    "dummy-password-used-only-to-equalize-login-work"
)


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    session_id: uuid.UUID


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID
    token_type: TokenType
    token_id: uuid.UUID
    issued_at: datetime
    expires_at: datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def hash_password(password: str) -> str:
    """Hash a password with pwdlib's recommended Argon2 settings."""

    return _password_hash.hash(password)


def verify_and_update_password(
    password: str,
    password_hash: str | None,
) -> tuple[bool, str | None]:
    """Verify a password and return a replacement hash when parameters age."""

    candidate_hash = password_hash or _dummy_password_hash
    try:
        valid, updated_hash = _password_hash.verify_and_update(
            password,
            candidate_hash,
        )
    except UnknownHashError:
        return False, None
    if password_hash is None:
        return False, None
    return valid, updated_hash


def verify_password(password: str, password_hash: str | None) -> bool:
    return verify_and_update_password(password, password_hash)[0]


def phone_login_digest(phone_e164: str) -> str:
    """Key rate limits without retaining another copy of the phone number."""

    return _hmac_digest(
        AUTH_RATE_LIMIT_SECRET,
        "login-phone",
        phone_e164,
    )


def client_ip_digest(client_ip: str) -> str:
    """Return a stable HMAC digest without retaining the raw client IP."""

    normalized = ipaddress.ip_address(client_ip.strip()).compressed
    return _hmac_digest(AUTH_RATE_LIMIT_SECRET, "client-ip", normalized)


def refresh_token_digest(token: str) -> str:
    return _hmac_digest(
        AUTH_TOKEN_DIGEST_SECRET,
        "refresh-token",
        token,
    )


def refresh_token_matches(token: str, expected_digest: str) -> bool:
    return hmac.compare_digest(refresh_token_digest(token), expected_digest)


def create_token_pair(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> TokenPair:
    """Create an access/refresh pair bound to one revocable session."""

    validate_auth_config()
    issued_at = _as_utc(now or utc_now())
    access_expires_at = issued_at + timedelta(seconds=JWT_ACCESS_TTL_SECONDS)
    refresh_expires_at = issued_at + timedelta(seconds=JWT_REFRESH_TTL_SECONDS)

    access_token = _encode_token(
        user_id,
        session_id,
        "access",
        issued_at,
        access_expires_at,
    )
    refresh_token = _encode_token(
        user_id,
        session_id,
        "refresh",
        issued_at,
        refresh_expires_at,
    )
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
        session_id=session_id,
    )


def decode_token(
    token: str,
    expected_type: TokenType,
    *,
    verify_expiration: bool = True,
) -> TokenClaims:
    """Verify signature, fixed algorithm, issuer, audience, and claim shape."""

    validate_auth_config()
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            leeway=JWT_LEEWAY_SECONDS,
            options={
                "require": [
                    "sub",
                    "sid",
                    "type",
                    "jti",
                    "iat",
                    "exp",
                    "iss",
                    "aud",
                ],
                "verify_exp": verify_expiration,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise ExpiredToken("JWT has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidToken("JWT validation failed") from exc

    if payload.get("type") != expected_type:
        raise InvalidToken("JWT token type is invalid")

    try:
        user_id = uuid.UUID(payload["sub"])
        session_id = uuid.UUID(payload["sid"])
        token_id = uuid.UUID(payload["jti"])
        issued_at = datetime.fromtimestamp(float(payload["iat"]), UTC)
        expires_at = datetime.fromtimestamp(float(payload["exp"]), UTC)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise InvalidToken("JWT claims are invalid") from exc

    return TokenClaims(
        user_id=user_id,
        session_id=session_id,
        token_type=expected_type,
        token_id=token_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def advisory_lock_key(value: str) -> int:
    """Map a rate-limit identity to PostgreSQL's signed 64-bit lock key."""

    digest = hashlib.sha256(value.encode()).digest()[:8]
    return int.from_bytes(digest, byteorder="big", signed=True)


def _encode_token(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    token_type: TokenType,
    issued_at: datetime,
    expires_at: datetime,
) -> str:
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "type": token_type,
        "jti": str(uuid.uuid4()),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def _hmac_digest(secret: str, purpose: str, value: str) -> str:
    message = f"{purpose}\0{value}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Authentication timestamps must be timezone-aware")
    return value.astimezone(UTC)
