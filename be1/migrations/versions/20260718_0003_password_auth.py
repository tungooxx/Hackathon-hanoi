"""Replace phone OTP challenges with password authentication.

Revision ID: 20260718_0003
Revises: 20260718_0002
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260718_0003"
down_revision: str | Sequence[str] | None = "20260718_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add password hashes and privacy-preserving failed-login tracking."""

    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )

    op.create_table(
        "auth_login_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "request_ip_digest",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_login_attempts"),
    )
    op.create_index(
        "ix_auth_login_attempts_phone_created",
        "auth_login_attempts",
        ["phone_digest", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_login_attempts_ip_created",
        "auth_login_attempts",
        ["request_ip_digest", "created_at"],
        unique=False,
    )

    op.drop_index(
        "ix_otp_challenges_ip_created",
        table_name="otp_challenges",
    )
    op.drop_index(
        "ix_otp_challenges_phone_created",
        table_name="otp_challenges",
    )
    op.drop_index(
        "ix_otp_challenges_expires_at",
        table_name="otp_challenges",
    )
    op.drop_table("otp_challenges")


def downgrade() -> None:
    """Restore OTP challenge storage and remove password login data."""

    op.create_table(
        "otp_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone_e164", sa.String(length=16), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempts_remaining",
            sa.SmallInteger(),
            server_default=sa.text("5"),
            nullable=False,
        ),
        sa.Column(
            "resend_available_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "request_ip_digest",
            sa.String(length=64),
            nullable=True,
        ),
        sa.CheckConstraint(
            "attempts_remaining >= 0",
            name="ck_otp_challenges_attempts_remaining_nonnegative",
        ),
        sa.CheckConstraint(
            "phone_e164 ~ '^\\+[1-9][0-9]{7,14}$'",
            name="ck_otp_challenges_phone_e164_format",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_otp_challenges"),
    )
    op.create_index(
        "ix_otp_challenges_expires_at",
        "otp_challenges",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_otp_challenges_phone_created",
        "otp_challenges",
        ["phone_e164", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_otp_challenges_ip_created",
        "otp_challenges",
        ["request_ip_digest", "created_at"],
        unique=False,
    )

    op.drop_index(
        "ix_auth_login_attempts_ip_created",
        table_name="auth_login_attempts",
    )
    op.drop_index(
        "ix_auth_login_attempts_phone_created",
        table_name="auth_login_attempts",
    )
    op.drop_table("auth_login_attempts")
    op.drop_column("users", "password_hash")
