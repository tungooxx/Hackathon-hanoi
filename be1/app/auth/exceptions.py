"""Domain exceptions raised by the authentication service layer."""

from __future__ import annotations


class AuthServiceError(Exception):
    """Base class for expected authentication failures."""


class AuthConfigurationError(AuthServiceError):
    """Authentication is not configured safely for the environment."""


class InvalidPhoneNumber(AuthServiceError):
    """The supplied phone number is invalid or unsupported."""


class WeakPassword(AuthServiceError):
    """The supplied registration password violates the password policy."""


class PhoneAlreadyRegistered(AuthServiceError):
    """A user record already owns the supplied phone number."""


class InvalidCredentials(AuthServiceError):
    """The phone/password pair was not accepted."""


class LoginRateLimited(AuthServiceError):
    """The phone or IP failed-login window has reached its limit."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Login rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


class InvalidToken(AuthServiceError):
    """A JWT is malformed, incorrectly signed, or has invalid claims."""


class ExpiredToken(InvalidToken):
    """A JWT has passed its expiration time."""


class RevokedAuthSession(AuthServiceError):
    """The JWT belongs to a revoked or replaced authentication session."""


class InactiveUser(AuthServiceError):
    """The JWT belongs to a disabled user."""
