"""Allow anonymous guest chat sessions.

Revision ID: 20260718_0006
Revises: 20260718_0005
Create Date: 2026-07-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260718_0006"
down_revision: str | Sequence[str] | None = "20260718_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Let a chat session exist without an owning user (guest mode)."""

    op.alter_column(
        "chat_sessions",
        "user_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )


def downgrade() -> None:
    """Restore the user ownership requirement (drops guest sessions)."""

    op.execute("DELETE FROM chat_sessions WHERE user_id IS NULL")
    op.alter_column(
        "chat_sessions",
        "user_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
