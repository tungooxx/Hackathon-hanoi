"""Conversation-history formatting shared by the graph and LLM adapters."""

from __future__ import annotations

from typing import Literal, TypedDict


class HistoryMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


def render_session_context(
    session_content: str,
    recent_messages: list[HistoryMessage],
) -> str:
    """Render the exact context window that may be supplied to an LLM."""

    sections: list[str] = []
    if compressed := session_content.strip():
        sections.append(
            "## Compressed session context\n\n"
            f"{compressed}"
        )
    if recent_messages:
        turns = "\n\n".join(
            f"### {'User' if message['role'] == 'user' else 'Assistant'}\n\n"
            f"{message['content'].strip()}"
            for message in recent_messages
        )
        sections.append(f"## Recent uncompressed messages\n\n{turns}")
    return "\n\n".join(sections)


def append_message(
    recent_messages: list[HistoryMessage],
    *,
    role: Literal["user", "assistant"],
    content: str,
) -> list[HistoryMessage]:
    """Return a new message window without mutating checkpointed state."""

    return [
        *recent_messages,
        {"role": role, "content": content},
    ]


def mock_markdown_summary(
    session_content: str,
    recent_messages: list[HistoryMessage],
) -> str:
    """Deterministic Markdown compressor used when ``MOCK_LLM=1``."""

    sections = ["# Session context"]
    if compressed := session_content.strip():
        sections.extend([
            "## Previously compressed context",
            compressed,
        ])
    sections.append("## Newly compressed turns")
    if recent_messages:
        sections.extend(
            f"- **{'User' if message['role'] == 'user' else 'Assistant'}:** "
            f"{message['content'].strip()}"
            for message in recent_messages
        )
    else:
        sections.append("- No completed turns to compress.")
    return "\n\n".join(sections)
