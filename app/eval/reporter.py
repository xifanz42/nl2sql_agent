"""Aggregate per-case metrics into a public markdown report + private raw dump.

Scores are split by case type so different capabilities never share a denominator:

* SQL questions       -> valid_sql / exact_match / execution_match / schema_adherence
* clarification cases -> clarification_correct
* derived             -> answer_rate, EX@answered

Public/private split (see app/eval/paths.py): the markdown holds aggregates and
case ids only, never questions, golden SQL or result rows.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

SQL_METRICS = ("valid_sql", "exact_match", "execution_match", "schema_adherence")
CLARIFICATION_METRICS = ("clarification_correct",)
ALL_METRICS = SQL_METRICS + CLARIFICATION_METRICS + ("safety_pass",)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _fmt(value: float) -> str:
    return f"{value * 100:.1f}%"


def required_behavior_of(row: dict[str, Any]) -> str:
    """Expected behaviour, with a fallback for raw dumps predating the field."""
    behavior = row.get("required_behavior")
    if behavior:
        return behavior
    return "clarify" if row.get("requires_clarification") else "answer"


def is_clarification(row: dict[str, Any]) -> bool:
    return required_behavior_of(row) != "answer"


def metrics_for(row: dict[str, Any]) -> tuple[str, ...]:
    """Which metrics apply to this case type."""
    return CLARIFICATION_METRICS if is_clarification(row) else SQL_METRICS


def policy_matrix(rows: list[dict[str, Any]]) -> dict[str, int]:
    r"""Confusion matrix of *should answer* versus *did answer*.

    This is the objective measure of the harness design goal "never presume":

    ==================  ===========  ==================
    expected \ actual    answered     did not answer
    ==================  ===========  ==================
    must answer          correct      over-clarified
    must not answer      presumed     correct
    ==================  ===========  ==================
    """
    matrix = {
        "answered_as_expected": 0,
        "over_clarified": 0,
        "presumed": 0,
        "declined_as_expected": 0,
    }
    for row in rows:
        should_answer = required_behavior_of(row) == "answer"
        did_answer = row["predicted_kind"] == "sql"
        if should_answer and did_answer:
            matrix["answered_as_expected"] += 1
        elif should_answer:
            matrix["over_clarified"] += 1
        elif did_answer:
            matrix["presumed"] += 1
        else:
            matrix["declined_as_expected"] += 1
    return matrix


def policy_rates(matrix: dict[str, int]) -> dict[str, float]:
    n_should_answer = matrix["answered_as_expected"] + matrix["over_clarified"]
    n_should_decline = matrix["presumed"] + matrix["declined_as_expected"]
    total = n_should_answer + n_should_decline
    return {
        "n_should_answer": n_should_answer,
        "n_should_decline": n_should_decline,
        "presumption_rate": matrix["presumed"] / n_should_decline if n_should_decline else 0.0,
        "over_clarify_rate": matrix["over_clarified"] / n_should_answer if n_should_answer else 0.0,
        "policy_accuracy": (
            (matrix["answered_as_expected"] + matrix["declined_as_expected"]) / total
            if total
            else 0.0
        ),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sql_rows = [r for r in rows if not is_clarification(r)]
    clar_rows = [r for r in rows if is_clarification(r)]
    answered = [r for r in rows if r["predicted_kind"] == "sql"]
    answered_sql = [r for r in sql_rows if r["predicted_kind"] == "sql"]

    return {
        "n": len(rows),
        "n_sql": len(sql_rows),
        "n_clarification": len(clar_rows),
        "n_answered": len(answered),
        "answer_rate": len(answered) / len(rows) if rows else 0.0,
        "ex_at_answered": _mean([r["metrics"]["execution_match"] for r in answered_sql]),
        "sql": {m: _mean([r["metrics"][m] for r in sql_rows]) for m in SQL_METRICS},
        "clarification": {
            m: _mean([r["metrics"][m] for r in clar_rows]) for m in CLARIFICATION_METRICS
        },
    }


def summarize_by_sql_difficulty(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not is_clarification(row):
            buckets[row["difficulty"]].append(row)
    return {name: summarize(group)["sql"] for name, group in sorted(buckets.items())}


def failures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cases that fail at least one metric applicable to their type."""
    out = []
    for row in rows:
        failed = [m for m in metrics_for(row) if not row["metrics"][m]]
        if failed:
            out.append({"id": row["id"], "failed": failed})
    return out


def write_raw(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_raw(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sql_table(summary: dict[str, Any]) -> str:
    metrics = " | ".join(_fmt(summary["sql"][m]) for m in SQL_METRICS)
    return (
        "| valid_sql | exact_match | execution_match | schema_adherence |\n"
        "|---|---|---|---|\n"
        f"| {metrics} |"
    )


def _difficulty_table(by_difficulty: dict[str, dict[str, float]]) -> str:
    lines = ["| difficulty | valid_sql | exact_match | execution_match | schema_adherence |", "|---|---|---|---|---|"]
    for name, metrics in by_difficulty.items():
        cells = " | ".join(_fmt(metrics[m]) for m in SQL_METRICS)
        lines.append(f"| {name} | {cells} |")
    return "\n".join(lines)


def render_markdown(
    *,
    system_name: str,
    model: str,
    dataset: str,
    rows: list[dict[str, Any]],
    generated_at: str,
) -> str:
    """Render the sanitized public report (no questions / SQL / rows)."""
    summary = summarize(rows)
    failing = failures(rows)
    matrix = policy_matrix(rows)
    rates = policy_rates(matrix)

    failure_lines = ["| case id | failed metrics |", "|---|---|"]
    if failing:
        failure_lines += [f"| {row['id']} | {', '.join(row['failed'])} |" for row in failing]
    else:
        failure_lines.append("| — | — |")

    clarification = ""
    if summary["n_clarification"]:
        clarification = f"""
## Clarification questions ({summary['n_clarification']})

| clarification_correct |
|---|
| {_fmt(summary['clarification']['clarification_correct'])} |
"""

    return f"""# NL2SQL eval report

- **system**: `{system_name}`
- **model**: `{model}`
- **dataset**: `{dataset}` (private)
- **cases**: {summary['n']} ({summary['n_sql']} SQL + {summary['n_clarification']} clarification)
- **generated**: {generated_at}

## Policy compliance

| expected \\ actual | answered | did not answer |
|---|---|---|
| **must answer** ({rates['n_should_answer']}) | {matrix['answered_as_expected']} | {matrix['over_clarified']} |
| **must not answer** ({rates['n_should_decline']}) | {matrix['presumed']} | {matrix['declined_as_expected']} |

- **presumption rate** (answered when it should have asked): {_fmt(rates['presumption_rate'])}
- **over-clarify rate** (asked when it should have answered): {_fmt(rates['over_clarify_rate'])}
- **policy accuracy**: {_fmt(rates['policy_accuracy'])}

## SQL questions ({summary['n_sql']})

{_sql_table(summary)}

- **EX@answered**: {_fmt(summary['ex_at_answered'])} (over SQL questions the system answered)
- **answer rate**: {_fmt(summary['answer_rate'])} (answered {summary['n_answered']}/{summary['n']} cases)

### SQL by difficulty

{_difficulty_table(summarize_by_sql_difficulty(rows))}
{clarification}
## Failed cases (ids only)

{chr(10).join(failure_lines)}

---
Per-case detail (questions, SQL, rows, tokens) is in the matching
`*.raw.jsonl`, which is private and never committed.
"""


def main(argv: list[str] | None = None) -> int:
    """Re-render a markdown report from a raw dump, without re-running models."""
    import argparse
    from datetime import datetime, timezone

    parser = argparse.ArgumentParser(description="Re-render a report from a raw dump.")
    parser.add_argument("raw", type=Path)
    parser.add_argument("--system", default=None, help="defaults to the raw filename prefix")
    parser.add_argument("--model", default="n/a")
    args = parser.parse_args(argv)

    system = args.system or args.raw.name.split("-")[0]
    rows = load_raw(args.raw)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    markdown = render_markdown(
        system_name=system,
        model=args.model,
        dataset="golden_dataset.jsonl",
        rows=rows,
        generated_at=stamp,
    )
    out = args.raw.with_suffix("").with_suffix(".md")
    out.write_text(markdown, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
