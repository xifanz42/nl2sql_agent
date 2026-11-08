"""Parse one model reply into a typed generation result.

The evaluator and the chatbot must agree on what a reply *means*: SQL, a
clarification, a refusal, or an error. Keeping that decision in one place stops
the two call sites from drifting; the 3a re-baseline exposed exactly that drift
(the eval's extractor kept a stray closing fence that the chatbot's extractor
stripped, turning a correct SQL answer into an execution failure).

This module deliberately does **not** validate SQL. It only classifies and
extracts; ``sqlglot`` + the read-only database remain the security boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

GenerationKind = Literal["sql", "clarify", "refuse", "error", "unknown"]

_SQL_QUERY = re.compile(r"SQL_QUERY\s*:\s*", re.IGNORECASE)
_SQL_START = re.compile(r"\b(SELECT|WITH)\b", re.IGNORECASE)
_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_OPEN_FENCE = re.compile(r"^```(?:sql)?\s*", re.IGNORECASE)
_CLOSING_FENCE = re.compile(r"\s*```\s*$")
_ERROR_PREFIXES = (
    "Generated SQL_QUERY is not valid",
    "Only SELECT queries are allowed",
    "Only a single SQL statement is allowed",
    "SQL parse error",
)
_CLARIFY_MARKERS = ("请提供具体信息:", "引导提问:")


@dataclass(frozen=True)
class GenerationResult:
    kind: GenerationKind
    sql: str = ""
    message: str = ""
    raw: str = ""


def strip_fences(text: str) -> str:
    """Remove paired, unclosed-opening, or stray-closing code fences."""
    text = text.strip()
    paired = _FENCE.search(text)
    if paired:
        text = paired.group(1)
    else:
        text = _OPEN_FENCE.sub("", text)
        text = _CLOSING_FENCE.sub("", text)
    return text.replace("```", "").strip()


def parse_generation(text: str | None) -> GenerationResult:
    """Classify one model reply; extract at most one SQL statement.

    ``error`` is returned for validator/parse errors so callers never mine a
    ``SELECT`` out of an error message. ``unknown`` means "no SQL and no known
    clarification marker"; the evaluator scores that as an abstention, while the
    chatbot keeps its existing "rephrase your question" response.
    """
    raw = text or ""
    text = raw.strip()
    if not text:
        return GenerationResult("unknown", raw=raw)

    if any(text.startswith(prefix) for prefix in _ERROR_PREFIXES) or any(
        phrase in text
        for phrase in ("Only SELECT queries are allowed", "Only a single SQL statement is allowed")
    ):
        return GenerationResult("error", message=text, raw=raw)

    # A reply that carries SQL is an answer, even if it also contains prose.
    marker = _SQL_QUERY.search(text)
    candidate = text[marker.end() :] if marker else text
    candidate = strip_fences(candidate)

    start = _SQL_START.search(candidate)
    if start:
        sql = candidate[start.start() :].replace("```", "").strip()
        if not sql.endswith(";"):
            sql += ";"
        return GenerationResult("sql", sql=sql, raw=raw)

    for clarify_marker in _CLARIFY_MARKERS:
        if clarify_marker in text:
            message = text.split(clarify_marker, 1)[1].strip()
            return GenerationResult("clarify", message=message, raw=raw)

    return GenerationResult("unknown", message=text, raw=raw)
