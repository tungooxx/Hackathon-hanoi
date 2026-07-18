"""Add privacy-preserving OTP request IP rate limiting.

Revision ID: 20260718_0002
Revises: 20260718_0001
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260718_0002"
down_revision: str | Sequence[str] | None = "20260718_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store an HMAC digest rather than a raw client IP address."""

    op.add_column(
        "otp_challenges",
        sa.Column(
            "request_ip_digest",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_otp_challenges_ip_created",
        "otp_challenges",
        ["request_ip_digest", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the OTP request IP digest."""

    op.drop_index(
        "ix_otp_challenges_ip_created",
        table_name="otp_challenges",
    )
    op.drop_column("otp_challenges", "request_ip_digest")
