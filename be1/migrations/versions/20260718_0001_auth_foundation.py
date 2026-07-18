"""Create users, OTP challenges, and authentication sessions.

Revision ID: 20260718_0001
Revises:
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260718_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the authentication foundation schema."""

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone_e164", sa.String(length=16), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "phone_e164 ~ '^\\+[1-9][0-9]{7,14}$'",
            name=op.f("ck_users_phone_e164_format"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("phone_e164", name="uq_users_phone_e164"),
    )

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
        sa.CheckConstraint(
            "attempts_remaining >= 0",
            name=op.f(
                "ck_otp_challenges_attempts_remaining_nonnegative"
            ),
        ),
        sa.CheckConstraint(
            "phone_e164 ~ '^\\+[1-9][0-9]{7,14}$'",
            name=op.f("ck_otp_challenges_phone_e164_format"),
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

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "refresh_token_digest",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_auth_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.UniqueConstraint(
            "refresh_token_digest",
            name="uq_auth_sessions_refresh_token_digest",
        ),
    )
    op.create_index(
        "ix_auth_sessions_expires_at",
        "auth_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_sessions_user_id",
        "auth_sessions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the authentication foundation schema."""

    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_table("auth_sessions")

    op.drop_index(
        "ix_otp_challenges_phone_created",
        table_name="otp_challenges",
    )
    op.drop_index(
        "ix_otp_challenges_expires_at",
        table_name="otp_challenges",
    )
    op.drop_table("otp_challenges")

    op.drop_table("users")
