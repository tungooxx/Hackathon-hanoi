"""Add compressed Markdown context to chat sessions.

Revision ID: 20260718_0005
Revises: 20260718_0004
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260718_0005"
down_revision: str | Sequence[str] | None = "20260718_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store cumulative compressed context outside raw graph checkpoints."""

    op.add_column(
        "chat_sessions",
        sa.Column(
            "session_content",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove cumulative compressed context."""

    op.drop_column("chat_sessions", "session_content")
