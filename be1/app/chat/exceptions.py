"""Expected failures for the user-owned chat service."""


class ChatServiceError(Exception):
    """Base class for sanitized chat API failures."""


class ChatSessionNotFound(ChatServiceError):
    """The session does not exist or is not owned by the current user."""


class ChatRuntimeUnavailable(ChatServiceError):
    """The persistent LangGraph runtime has not started."""
