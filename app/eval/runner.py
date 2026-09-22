"""Eval runner CLI: load golden set -> predict -> execute -> score -> report.

    python -m app.eval.runner --system direct --limit 20
    python -m app.eval.runner --system oracle
    python -m app.eval.runner --system harness          # needs the RAG env
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.database import ReadOnlyDataBase
from app.core.llm import SiliconFlowLLM
from app.eval import reporter
from app.eval.execute import ExpectedResultCache, run_sql
from app.eval.metrics import score_case
from app.eval.paths import EvalPaths
from app.eval.systems import DirectToSQLSystem, GoldenOracleSystem, HarnessSystem, System
from app.models.eval import EvalCase
from app.models.sql import SQLResult

SYSTEMS = ("oracle", "direct", "harness")


def load_cases(path: Path, limit: int | None = None) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(EvalCase.model_validate_json(line))
    return cases[:limit] if limit else cases


def build_system(name: str, *, db: ReadOnlyDataBase, model: str | None) -> System:
    if name == "oracle":
        return GoldenOracleSystem()
    if name == "direct":
        llm = SiliconFlowLLM()
        return DirectToSQLSystem(
            client=llm.client,
            model=model or llm.SILICON_FLOW_NL2SQL_MODEL,
            schema_text=db.extract_schema(),
        )
    if name == "harness":
        from app.chatbot.nl2sql import NL2SQLChatbot  # imported lazily (heavy deps)

        return HarnessSystem(NL2SQLChatbot())
    raise SystemExit(f"unknown system: {name}")


def score_system(
    system: System,
    cases: list[EvalCase],
    *,
    db: ReadOnlyDataBase,
    cache: ExpectedResultCache,
    schema: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total = len(cases)
    for index, case in enumerate(cases, 1):
        prediction = system.predict(case)

        if prediction.kind == "sql" and prediction.sql:
            result = run_sql(db, prediction.sql)
        else:
            result = SQLResult(sql="", executed=False, execution_time_ms=0.0)

        if case.requires_clarification:
            expected_rows: list = []
        else:
            expected_rows = cache.compute_or_get(case.id, case.golden_sql, db)
        metrics = score_case(
            predicted_sql=prediction.sql,
            predicted_kind=prediction.kind,
            result=result,
            golden_sql=case.golden_sql,
            expected_rows=expected_rows,
            schema=schema,
            requires_clarification=case.requires_clarification,
            difficulty=case.difficulty,
        )

        rows.append(
            {
                "id": case.id,
                "difficulty": case.difficulty,
                "requires_clarification": case.requires_clarification,
                "tags": case.tags,
                "predicted_kind": prediction.kind,
                "predicted_sql": prediction.sql,
                "raw_output": prediction.text,
                "golden_sql": case.golden_sql,
                "db_error": result.error,
                "latency_ms": round(prediction.latency_ms, 1),
                "prompt_tokens": prediction.prompt_tokens,
                "completion_tokens": prediction.completion_tokens,
                "cached_tokens": prediction.cached_tokens,
                "metrics": metrics,
            }
        )

        flag = "EX" if metrics["execution_match"] else "  "
        print(
            f"[{index:>3}/{total}] {case.id:<10} {prediction.kind:<13} "
            f"{flag}  {prediction.latency_ms:7.0f} ms"
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the NL2SQL eval harness.")
    parser.add_argument("--system", choices=SYSTEMS, default="direct")
    parser.add_argument("--model", default=None, help="override the model (e.g. a working one)")
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None, help="score only the first N cases")
    parser.add_argument("--expected-cache", type=Path, default=None)
    args = parser.parse_args(argv)

    paths = EvalPaths.default()
    dataset = args.dataset or paths.dataset
    cases = load_cases(dataset, args.limit)
    if not cases:
        parser.error(f"no cases loaded from {dataset}")

    db = ReadOnlyDataBase()
    schema = db.get_schema_as_dict()
    cache = ExpectedResultCache(args.expected_cache or paths.expected_cache)
    system = build_system(args.system, db=db, model=args.model)

    print(f"system={system.name} model={args.model or getattr(system, 'model', 'n/a')} n={len(cases)}")
    rows = score_system(system, cases, db=db, cache=cache, schema=schema)
    cache.save()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = paths.raw(system.name, stamp)
    report_path = paths.report(system.name, stamp)
    reporter.write_raw(raw_path, rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        reporter.render_markdown(
            system_name=system.name,
            model=str(args.model or getattr(system, "model", "n/a")),
            dataset=dataset.name,
            rows=rows,
            generated_at=stamp,
        ),
        encoding="utf-8",
    )

    print(f"\nreport: {report_path}")
    print(f"raw:    {raw_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
