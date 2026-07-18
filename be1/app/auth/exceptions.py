"""Domain exceptions raised by the authentication service layer."""

from __future__ import annotations


class AuthServiceError(Exception):
    """Base class for expected authentication failures."""


class AuthConfigurationError(AuthServiceError):
    """Authentication is not configured safely for the environment."""


class InvalidPhoneNumber(AuthServiceError):
    """The supplied phone number cannot receive an OTP."""


class OtpCooldown(AuthServiceError):
    """A new OTP cannot be requested until the resend cooldown elapses."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("OTP resend cooldown is active")
        self.retry_after_seconds = retry_after_seconds


class OtpRateLimited(AuthServiceError):
    """The phone or IP request window has reached its limit."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("OTP request rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


class OtpChallengeNotFound(AuthServiceError):
    """The OTP challenge identifier is unknown."""


class OtpChallengeExpired(AuthServiceError):
    """The OTP challenge has expired."""


class OtpChallengeConsumed(AuthServiceError):
    """The OTP challenge was already used or invalidated."""


class InvalidOtpCode(AuthServiceError):
    """The OTP did not match the stored digest."""

    def __init__(self, attempts_remaining: int) -> None:
        super().__init__("Invalid OTP code")
        self.attempts_remaining = attempts_remaining


class OtpDeliveryError(AuthServiceError):
    """The configured provider could not deliver an OTP."""


class InvalidToken(AuthServiceError):
    """A JWT is malformed, incorrectly signed, or has invalid claims."""


class ExpiredToken(InvalidToken):
    """A JWT has passed its expiration time."""


class RevokedAuthSession(AuthServiceError):
    """The JWT belongs to a revoked or replaced authentication session."""


class InactiveUser(AuthServiceError):
    """The JWT belongs to a disabled user."""
