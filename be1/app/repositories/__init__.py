"""Persistence boundaries used by application services."""

from .auth_sessions import AuthSessionRepository
from .otp_challenges import OtpChallengeRepository, RateWindowStats
from .users import UserRepository

__all__ = [
    "AuthSessionRepository",
    "OtpChallengeRepository",
    "RateWindowStats",
    "UserRepository",
]
