"""Public request and response shapes for user-owned conversations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ChatTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
ChatMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]


class CreateChatSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: ChatTitle | None = None


class UpdateChatSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: ChatTitle


class ChatMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: ChatMessage


class ChatSessionResponse(BaseModel):
    id: uuid.UUID
    title: str
    session_content: str
    created_at: datetime
    updated_at: datetime


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionResponse] = Field(default_factory=list)
