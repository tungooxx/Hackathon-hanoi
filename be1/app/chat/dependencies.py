"""FastAPI dependencies for chat sessions and the persistent graph."""

from typing import Annotated

from fastapi import Depends

from app.auth.dependencies import DatabaseSession

from .runtime import ChatGraphRuntime, chat_graph_runtime
from .service import ChatSessionService


def get_chat_session_service(
    session: DatabaseSession,
) -> ChatSessionService:
    return ChatSessionService(session)


def get_chat_graph_runtime() -> ChatGraphRuntime:
    return chat_graph_runtime


ChatSessionServiceDependency = Annotated[
    ChatSessionService,
    Depends(get_chat_session_service),
]
ChatGraphRuntimeDependency = Annotated[
    ChatGraphRuntime,
    Depends(get_chat_graph_runtime),
]
