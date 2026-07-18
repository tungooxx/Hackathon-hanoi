"""OTP delivery interfaces and the development-only console provider."""

from __future__ import annotations

import logging
from typing import Protocol

from app.config import APP_ENV, OTP_PROVIDER

from .exceptions import AuthConfigurationError, OtpDeliveryError
from .phone import mask_phone

logger = logging.getLogger(__name__)


class OtpProvider(Protocol):
    """Deliver a one-time code without owning challenge persistence."""

    async def send_otp(
        self,
        phone_e164: str,
        code: str,
        *,
        expires_in_seconds: int,
    ) -> None:
        """Deliver an OTP or raise OtpDeliveryError."""


class ConsoleOtpProvider:
    """Print OTPs for local development; never enable in production."""

    def __init__(self, *, environment: str = APP_ENV) -> None:
        if environment in {"prod", "production"}:
            raise AuthConfigurationError(
                "Console OTP delivery is forbidden in production"
            )

    async def send_otp(
        self,
        phone_e164: str,
        code: str,
        *,
        expires_in_seconds: int,
    ) -> None:
        logger.warning(
            "DEVELOPMENT OTP for %s: %s (expires in %ss)",
            mask_phone(phone_e164),
            code,
            expires_in_seconds,
        )


def build_otp_provider() -> OtpProvider:
    """Build the configured provider without silently falling back."""

    if OTP_PROVIDER == "console":
        return ConsoleOtpProvider()
    raise OtpDeliveryError(
        f"OTP provider {OTP_PROVIDER!r} is not implemented or configured"
    )
