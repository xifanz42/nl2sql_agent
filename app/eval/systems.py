"""Prediction systems under evaluation, behind one interface.

Every system turns an :class:`EvalCase` into a :class:`Prediction`. Adding a new
baseline means adding a class here; the runner and reporter never change.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

from openai import OpenAI

from app.models.eval import EvalCase

PredictionKind = Literal["sql", "clarification", "error"]

_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_SELECT = re.compile(r"\b(SELECT|WITH)\b", re.IGNORECASE)


@dataclass
class Prediction:
    """What a system returned for one case (private: includes raw model text)."""

    kind: PredictionKind
    sql: str = ""
    text: str = ""
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    calls: int = 0
    model_usage: dict[str, dict[str, int]] | None = None


class System(Protocol):
    name: str

    def predict(self, case: EvalCase) -> Prediction: ...


def extract_sql(text: str) -> str:
    """Pull the first SELECT/WITH statement out of a model reply."""
    fenced = _FENCE.search(text)
    candidate = fenced.group(1) if fenced else text
    match = _SELECT.search(candidate)
    if not match:
        return ""
    return candidate[match.start() :].strip()


class GoldenOracleSystem:
    """Upper bound: answers with the golden SQL itself (no model call)."""

    name = "oracle"

    def predict(self, case: EvalCase) -> Prediction:
        if case.requires_clarification or not case.golden_sql:
            # No SQL exists for this case -> the perfect answer is to clarify.
            return Prediction(kind="clarification")
        return Prediction(kind="sql", sql=case.golden_sql)


class DirectToSQLSystem:
    """Baseline: schema (+ optional retrieved knowledge) -> SQL in one call.

    ``retriever`` is the agent's own retrieval callable, so the RAG ablation uses
    the real implementation instead of a copy.
    """

    name = "direct"

    def __init__(
        self,
        *,
        client: OpenAI,
        model: str,
        schema_text: str,
        retriever: Callable[[str], str] | None = None,
        name: str = "direct",
    ):
        self.client = client
        self.model = model
        self.schema_text = schema_text
        self.retriever = retriever
        self.name = name

    def predict(self, case: EvalCase) -> Prediction:
        context = self.schema_text
        if self.retriever is not None:
            context = f"{context}\n\nRelevant business knowledge:\n{self.retriever(case.question)}"
        system = (
            "You are a PostgreSQL expert. Using ONLY the information below, return a "
            "single read-only SELECT statement that answers the question. "
            "Reply with the SQL only, no explanation or markdown.\n\n" + context
        )
        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": case.question},
                ],
                temperature=0.0,
                max_tokens=1024,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a scored failure
            return Prediction(
                kind="error", text=str(exc), latency_ms=(time.perf_counter() - started) * 1000
            )

        latency_ms = (time.perf_counter() - started) * 1000
        text = response.choices[0].message.content or ""
        sql = extract_sql(text)
        usage = response.usage
        details = getattr(usage, "prompt_tokens_details", None)
        return Prediction(
            kind="sql" if sql else "error",
            sql=sql,
            text=text,
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            cached_tokens=getattr(details, "cached_tokens", 0) or 0,
            calls=1,
            model_usage={
                self.model: {
                    "calls": 1,
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                    "cached_tokens": getattr(details, "cached_tokens", 0) or 0,
                    "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                }
            },
        )


class HarnessSystem:
    """The agent under test: wraps ``NL2SQLChatbot.generate_sql`` (RAG + prompt).

    Token usage is read from the agent's LLM engine, which accumulates usage per
    call; it is reset before each case so the numbers are per-case.
    """

    name = "harness"

    def __init__(self, chatbot: Any):
        self.chatbot = chatbot

    def predict(self, case: EvalCase) -> Prediction:
        engine = getattr(self.chatbot, "model_engine", None)
        if engine is not None:
            engine.reset_usage()
        started = time.perf_counter()
        try:
            output = self.chatbot.generate_sql(case.question)
        except Exception as exc:  # noqa: BLE001
            return Prediction(
                kind="error", text=str(exc), latency_ms=(time.perf_counter() - started) * 1000
            )
        latency_ms = (time.perf_counter() - started) * 1000
        usage = engine.usage() if engine is not None else None
        sql = extract_sql(output)
        return Prediction(
            kind="sql" if sql else "clarification",
            sql=sql,
            text=output,
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            cached_tokens=getattr(usage, "cached_tokens", 0) or 0,
            calls=getattr(usage, "calls", 0) or 0,
            model_usage=usage.breakdown() if usage is not None else None,
        )
