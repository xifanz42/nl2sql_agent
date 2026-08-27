"""Chat-layer models (spec §4.2)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Message(BaseModel):
    """A single chat turn."""

    role: Literal["user", "assistant", "system", "tool"]
    content: str
    metadata: dict = {}


class ChatRequest(BaseModel):
    """Incoming chat request."""

    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    """Final answer returned to the interface layer."""

    sql: str
    result: list[dict]
    analysis: str
    clarification_needed: bool = False
    clarification_question: str | None = None
