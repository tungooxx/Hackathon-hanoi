"""Add user-owned chat sessions.

Revision ID: 20260718_0004
Revises: 20260718_0003
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260718_0004"
down_revision: str | Sequence[str] | None = "20260718_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the user ownership boundary for LangGraph conversations."""

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "title",
            sa.String(length=120),
            server_default=sa.text("'Cuộc trò chuyện mới'"),
            nullable=False,
        ),
        sa.Column("langgraph_thread_id", sa.Uuid(), nullable=False),
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
            "char_length(btrim(title)) BETWEEN 1 AND 120",
            name=op.f("ck_chat_sessions_title_length"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_chat_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_sessions")),
        sa.UniqueConstraint(
            "langgraph_thread_id",
            name=op.f("uq_chat_sessions_langgraph_thread_id"),
        ),
    )
    op.create_index(
        "ix_chat_sessions_user_updated",
        "chat_sessions",
        ["user_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove user-owned chat-session metadata."""

    op.drop_index(
        "ix_chat_sessions_user_updated",
        table_name="chat_sessions",
    )
    op.drop_table("chat_sessions")
