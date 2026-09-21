"""Aggregate per-case metrics into a public markdown report + private raw dump.

Public/private split (see app/eval/paths.py):
* markdown report: aggregates + per-case pass/fail only — NEVER questions,
  golden SQL or result rows;
* raw jsonl: full detail, stays gitignored.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

METRIC_NAMES = (
    "valid_sql",
    "exact_match",
    "execution_match",
    "schema_adherence",
    "safety_pass",
    "clarification_correct",
)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate(rows: list[dict[str, Any]]) -> dict[str, float]:
    return {name: _mean([float(row["metrics"][name]) for row in rows]) for name in METRIC_NAMES}


def aggregate_by(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, float]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[row[key]].append(row)
    return {name: aggregate(group) for name, group in sorted(buckets.items())}


def failures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cases where at least one metric is False."""
    return [row for row in rows if not all(row["metrics"].values())]


def write_raw(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _fmt(value: float) -> str:
    return f"{value * 100:.1f}%"


def _metric_table(rows_by_group: dict[str, dict[str, float]], label: str) -> str:
    header = "| " + label + " | " + " | ".join(METRIC_NAMES) + " | n/a |"
    sep = "|" + "---|" * (len(METRIC_NAMES) + 2)
    lines = [header, sep]
    for name, metrics in rows_by_group.items():
        cells = " | ".join(_fmt(metrics[m]) for m in METRIC_NAMES)
        lines.append(f"| {name} | {cells} | — |")
    return "\n".join(lines)


def render_markdown(
    *,
    system_name: str,
    model: str,
    dataset: str,
    total: int,
    overall: dict[str, float],
    by_difficulty: dict[str, dict[str, float]],
    failures: list[dict[str, Any]],
    generated_at: str,
) -> str:
    """Render the sanitized public report (no questions / SQL / rows)."""
    totals = " | ".join(f"{m}: {_fmt(overall[m])}" for m in METRIC_NAMES)

    failure_lines = ["| case id | failed metrics |", "|---|---|"]
    if failures:
        for row in failures:
            failed = ", ".join(k for k, v in row["metrics"].items() if not v)
            failure_lines.append(f"| {row['id']} | {failed} |")
    else:
        failure_lines.append("| — | — |")

    return f"""# NL2SQL eval report

- **system**: `{system_name}`
- **model**: `{model}`
- **dataset**: `{dataset}` (private)
- **cases**: {total}
- **generated**: {generated_at}

## Overall

{totals}

## By difficulty

{_metric_table(by_difficulty, "difficulty")}

## Failed cases (ids only)

{chr(10).join(failure_lines)}

---
Per-case detail (questions, SQL, rows, tokens) is in the matching
`*.raw.jsonl`, which is private and never committed.
"""
