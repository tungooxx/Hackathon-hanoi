"""SQLAlchemy models for durable application data."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    SmallInteger,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class whose metadata is shared with Alembic."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """UTC-aware creation and modification timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class User(TimestampMixin, Base):
    """A customer identity, keyed independently from their phone number."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "phone_e164 ~ '^\\+[1-9][0-9]{7,14}$'",
            name="phone_e164_format",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    phone_e164: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        unique=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    auth_sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class OtpChallenge(TimestampMixin, Base):
    """A short-lived, hashed phone-verification challenge."""

    __tablename__ = "otp_challenges"
    __table_args__ = (
        CheckConstraint(
            "phone_e164 ~ '^\\+[1-9][0-9]{7,14}$'",
            name="phone_e164_format",
        ),
        CheckConstraint(
            "attempts_remaining >= 0",
            name="attempts_remaining_nonnegative",
        ),
        Index("ix_otp_challenges_phone_created", "phone_e164", "created_at"),
        Index(
            "ix_otp_challenges_ip_created",
            "request_ip_digest",
            "created_at",
        ),
        Index("ix_otp_challenges_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    phone_e164: Mapped[str] = mapped_column(String(16), nullable=False)
    request_ip_digest: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    code_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    attempts_remaining: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=5,
        server_default=text("5"),
    )
    resend_available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class AuthSession(TimestampMixin, Base):
    """A revocable refresh-token session for one user."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_id", "user_id"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    refresh_token_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped[User] = relationship(back_populates="auth_sessions")
