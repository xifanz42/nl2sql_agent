"""Chat-layer models (spec §4.2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    """A single chat turn."""

    role: Literal["user", "assistant", "system", "tool"]
    content: str
    metadata: dict = {}


class Turn(BaseModel):
    """One user/assistant exchange inside a :class:`ChatSession`."""

    user: str
    system: str = ""


class ChatSession(BaseModel):
    """Short-term conversation state, stored per session.

    ``summary`` / ``summary_upto`` are reserved for the compaction step; they are
    serialized here so the storage schema does not change when compaction lands.
    """

    history: list[Turn] = Field(default_factory=list)
    summary: str = ""
    summary_upto: int = 0
    last_sql: str = ""
    clarify_count: int = 0


class ChatResult(BaseModel):
    """Typed result returned by the agent to the presentation layer.

    The LLM never sees this object: it still receives a prompt and returns text.
    The legacy ``process_query`` string is rendered from this model.
    """

    kind: Literal[
        "sql",
        "clarification",
        "refuse",
        "exploration",
        "invalid",
        "execution_error",
        "store_error",
        "too_many_rows",
    ]
    sql: str = ""
    rows: list[dict] = Field(default_factory=list)
    analysis: str = ""
    message: str = ""
    execution_time_ms: float = 0.0
    processing_time_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    calls: int = 0
    cost_cny: float = 0.0
    unpriced_models: list[str] = Field(default_factory=list)
    total_rows: int = 0
    truncated: bool = False

    def history_text(self) -> str:
        """Compact text for the stored conversation history.

        Deliberately excludes ``rows``: the session store is plaintext and a
        conversation should not persist full query results.
        """
        if self.kind == "sql":
            return (
                f"SQL: {self.sql}\n"
                f"Rows: {len(self.rows)}\n"
                f"Analysis: {self.analysis}"
            )
        if self.kind == "too_many_rows":
            return (
                f"SQL: {self.sql}\n"
                f"Rows: {self.total_rows} (analysis skipped; too many rows)\n"
                "User must narrow the query."
            )
        if self.kind == "execution_error":
            return f"SQL: {self.sql}\nError: {self.message}"
        return self.message

    def render_text(self) -> str:
        """Render the legacy CLI string for this result."""
        if self.kind in (
            "clarification",
            "refuse",
            "exploration",
            "invalid",
            "store_error",
        ):
            return self.message
        if self.kind == "too_many_rows":
            return (
                f"Generated SQL: {self.sql}\n\n"
                f"{self.message}\n\n"
                f"Processing time: {self.processing_time_ms / 1000:.2f}s"
            )
        if self.kind == "execution_error":
            text = (
                f"Generated SQL: {self.sql}\n\n"
                f"Execution error:\n{self.message}\n\n"
                f"Execution time: {self.execution_time_ms:.0f} ms"
            )
        else:
            text = f"Generated SQL: {self.sql}\n\nResults:\n{self.rows}"
            text += f"\n\nAnalysis:\n\n{self.analysis}"
        return text + f"\n\nProcessing time: {self.processing_time_ms / 1000:.2f}s"


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
