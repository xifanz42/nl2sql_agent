"""SQL execution / validation models (spec §4.2)."""
from __future__ import annotations

from pydantic import BaseModel


class SQLResult(BaseModel):
    """Outcome of executing a SQL statement."""

    sql: str
    executed: bool
    result: list[dict] | None = None
    error: str | None = None
    execution_time_ms: float


class SQLValidationResult(BaseModel):
    """Result of the multi-layer SQL safety/schema check (spec §3.2 决策 8)."""

    is_valid: bool
    is_safe: bool
    schema_adherence: bool
    issues: list[str]
