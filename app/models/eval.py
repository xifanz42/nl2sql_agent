"""Eval dataset / report models (spec §4.2 & §4.3)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EvalCase(BaseModel):
    """A single golden eval sample.

    ``expected_result`` is optional: it can be left ``None`` and populated later
    by executing ``golden_sql`` against the live DB during a baseline run.
    """

    id: str
    question: str
    golden_sql: str
    expected_result: list[dict] | None = None
    difficulty: Literal["easy", "medium", "hard", "clarification", "safety"]
    tags: list[str] = []
    requires_clarification: bool = False


class EvalPrediction(BaseModel):
    """One model prediction produced during an eval run."""

    id: str
    question: str
    predicted_sql: str
    golden_sql: str
    expected_result: list[dict] | None = None
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float


class EvalReport(BaseModel):
    """Aggregated eval report."""

    model: str
    dataset: str
    total: int
    metrics: dict
    by_difficulty: dict
    by_tag: dict
    failed_cases: list[dict]
