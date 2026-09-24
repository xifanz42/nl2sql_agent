"""Shared evaluation snapshot: load the latest run per system and derive metrics.

Both report generators (the visual page and the markdown scoreboard) consume this
module, so there is exactly one implementation of "what does the current state
look like" and the two renderers cannot disagree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.eval import reporter
from app.eval.paths import EvalPaths

# (id, label, role, retrieval, prompt, guardrails, abstention)
SYSTEMS: list[tuple[str, str, str, str, str, str, str]] = [
    ("oracle", "Oracle", "Reference upper bound", "—", "—", "—", "—"),
    ("direct", "Direct", "Schema-only baseline", "none", "minimal", "none", "none"),
    ("direct+rag", "Direct+RAG", "Retrieval-augmented baseline", "dense", "minimal", "none", "none"),
    ("harness", "Harness", "System under evaluation", "dense", "engineered", "yes", "yes"),
]
TONE = {"oracle": "grey", "direct": "amber", "direct+rag": "blue", "harness": "green"}
# Single-model systems whose raw dumps predate per-model accounting.
FALLBACK_MODEL = {
    "direct": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
    "direct+rag": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
}
LEVELS = ("easy", "medium", "hard")


def latest_raw(system: str, output_dir: Path | None = None) -> Path | None:
    directory = output_dir or EvalPaths.default().output_dir
    files = sorted(directory.glob(f"{system}-*.raw.jsonl"))
    return files[-1] if files else None


def derive(system: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """All aggregates a renderer needs for one system."""
    matrix = reporter.policy_matrix(rows)
    return {
        "rows": rows,
        "summary": reporter.summarize(rows),
        "matrix": matrix,
        "rates": reporter.policy_rates(matrix),
        "latency": reporter.latency_stats(rows),
        "tokens": reporter.token_stats(rows),
        "cost": reporter.cost_stats(rows, FALLBACK_MODEL.get(system)),
        "by_difficulty": reporter.summarize_by_sql_difficulty(rows),
    }


def load_all(
    behaviors: dict[str, str] | None = None, output_dir: Path | None = None
) -> dict[str, dict[str, Any]]:
    """Derive the current state for every system that has a raw dump."""
    if behaviors is None:
        behaviors = reporter.load_case_behaviors(EvalPaths.default().dataset)
    data: dict[str, dict[str, Any]] = {}
    for system, *_ in SYSTEMS:
        path = latest_raw(system, output_dir)
        if path:
            data[system] = derive(system, reporter.load_raw(path, behaviors))
    return data


def pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%"


def secs(ms: float) -> str:
    return f"{ms / 1000:.2f} s"


def money(value: float) -> str:
    return f"¥{value:.4f}"
