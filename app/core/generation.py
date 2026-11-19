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
# Bare SQL must start a line; a prose "with" must never become a statement.
_SELECT_START = re.compile(r"^[ \t]*SELECT\b", re.IGNORECASE | re.MULTILINE)
_WITH_START = re.compile(
    r"^[ \t]*WITH\s+(?:RECURSIVE\s+)?"
    r'(?:"[^"]+"|[A-Za-z_][\w$]*)'
    r"(?:\s*\([^)]*\))?"
    r"\s+AS\s+(?:NOT\s+)?(?:MATERIALIZED\s*)?\(",
    re.IGNORECASE | re.MULTILINE,
)
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
_REFUSE_MARKERS = ("无法回答:", "无法回答：")


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


def _sql_from(candidate: str) -> str:
    """Return one SQL statement from a candidate string, or ``""``."""
    starts = [
        match
        for match in (_SELECT_START.search(candidate), _WITH_START.search(candidate))
        if match is not None
    ]
    if not starts:
        return ""
    start = min(starts, key=lambda match: match.start())
    sql = candidate[start.start() :].replace("```", "").strip()
    if not sql.endswith(";"):
        sql += ";"
    return sql


def parse_generation(text: str | None) -> GenerationResult:
    """Classify one model reply; extract at most one SQL statement.

    ``error`` is returned for validator/parse errors so callers never mine a
    ``SELECT`` out of an error message. ``refuse`` is a deliberate "no valid SQL
    exists" answer, distinct from ``clarify``. ``unknown`` means "no SQL and no
    known marker"; the evaluator scores that as an abstention, while the chatbot
    keeps its existing "rephrase your question" response.
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

    # An explicit SQL marker or fenced block is an answer even with prose around it.
    marker = _SQL_QUERY.search(text)
    if marker is not None:
        sql = _sql_from(text[marker.end() :])
        if sql:
            return GenerationResult("sql", sql=sql, raw=raw)
    else:
        fenced = _FENCE.search(text)
        if fenced:
            sql = _sql_from(fenced.group(1))
            if sql:
                return GenerationResult("sql", sql=sql, raw=raw)

    # A deliberate refusal/clarification wins over a bare SELECT in its reason:
    # models routinely echo "SELECT" when explaining what they cannot do.
    for refuse_marker in _REFUSE_MARKERS:
        if refuse_marker in text:
            message = text.split(refuse_marker, 1)[1].strip()
            return GenerationResult("refuse", message=message, raw=raw)

    for clarify_marker in _CLARIFY_MARKERS:
        if clarify_marker in text:
            message = text.split(clarify_marker, 1)[1].strip()
            return GenerationResult("clarify", message=message, raw=raw)

    sql = _sql_from(strip_fences(text))
    if sql:
        return GenerationResult("sql", sql=sql, raw=raw)

    return GenerationResult("unknown", message=text, raw=raw)
