"""Langfuse tracing (optional): có LANGFUSE_PUBLIC_KEY + SECRET_KEY trong env là tự bật.

main.py set session_id vào contextvar mỗi request; llm.py lấy lf_config() gắn vào
mọi call LangChain -> trace group theo session trên dashboard, không phải xâu
session_id qua từng node của graph.
"""
from contextvars import ContextVar

from .config import LANGFUSE_ENABLED

_session_id: ContextVar[str | None] = ContextVar("session_id", default=None)
_handler = None


def set_session(session_id: str) -> None:
    _session_id.set(session_id)


def lf_config(name: str) -> dict:
    """Config truyền vào .ainvoke/.astream. Langfuse tắt -> chỉ có run_name."""
    global _handler
    if not LANGFUSE_ENABLED:
        return {"run_name": name}
    if _handler is None:
        from langfuse.langchain import CallbackHandler

        _handler = CallbackHandler()
    return {
        "run_name": name,
        "callbacks": [_handler],
        "metadata": {"langfuse_session_id": _session_id.get()},
    }
