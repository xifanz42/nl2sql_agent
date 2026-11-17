"""HTTP request/response models for the NL2SQL API."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, field_validator

from app.config import settings
from app.models.chat import ChatResult


class ChatRequest(BaseModel):
    """One user turn. ``session_id`` is optional on the first request."""

    message: str
    session_id: uuid.UUID | None = None

    @field_validator("message")
    @classmethod
    def _validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be empty")
        limit = settings.max_message_chars
        if len(value) > limit:
            raise ValueError(f"message must be at most {limit} characters")
        return value

    @field_validator("session_id")
    @classmethod
    def _reject_nil_session(cls, value: uuid.UUID | None) -> uuid.UUID | None:
        if value is not None and value.int == 0:
            raise ValueError("session_id must not be the nil UUID")
        return value


class ChatResponse(BaseModel):
    """Typed result returned to the presentation layer."""

    session_id: uuid.UUID
    result: ChatResult
