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
from app.core.llm import (
    EVAL_MAX_TOKENS,
    EVAL_TEMPERATURE,
    Provider,
    SiliconFlowLLM,
    build_provider,
)
from app.eval import ledger, reporter
from app.eval.execute import ExpectedResultCache, run_sql
from app.eval.metrics import score_case
from app.eval.paths import EvalPaths
from app.eval.systems import DirectToSQLSystem, GoldenOracleSystem, HarnessSystem, System
from app.models.eval import EvalCase
from app.models.sql import SQLResult

SYSTEMS = ("oracle", "direct", "direct+rag", "harness")


def load_cases(path: Path, limit: int | None = None) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(EvalCase.model_validate_json(line))
    return cases[:limit] if limit else cases


def _load_chatbot():
    from app.chatbot.nl2sql import NL2SQLChatbot  # heavy deps, imported lazily

    return NL2SQLChatbot()


def build_system(
    name: str, *, db: ReadOnlyDataBase, model: str | None, provider: Provider
) -> System:
    if name == "oracle":
        return GoldenOracleSystem()
    if name in ("direct", "direct+rag"):
        # Exactly one model call. The system prompt is the agent's own template
        # (``render_prompt``), and retrieval for `direct+rag` reuses the agent's
        # retriever, so neither the prompt nor the retrieval is a confounder when
        # comparing against `harness`. Deliberately NOT ``_prepare_prompt``: that
        # would also run the agent's follow-up detector, importing agent
        # architecture into the baseline.
        chatbot = _load_chatbot()
        if name == "direct+rag":
            prompt_builder = lambda q: chatbot.render_prompt(  # noqa: E731
                knowledge=chatbot.retrieve_knowledge(q)
            )
        else:
            prompt_builder = lambda q: chatbot.render_prompt()  # noqa: E731
        return DirectToSQLSystem(
            client=provider.client,
            model=model or provider.coder_model,
            schema_text=db.extract_schema(),
            prompt_builder=prompt_builder,
            extra_body=provider.extra_body,
            name=name,
        )
    if name == "harness":
        chatbot = _load_chatbot()
        # The agent builds its own engine from .env; swap it so a provider switch
        # covers the harness too -- it is the only system that reads the model
        # from settings instead of from this function's arguments.
        chatbot.model_engine = SiliconFlowLLM(provider)
        return HarnessSystem(chatbot)
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
                "required_behavior": case.required_behavior,
                "tags": case.tags,
                "predicted_kind": prediction.kind,
                "predicted_sql": prediction.sql,
                "raw_output": prediction.text,
                "golden_sql": case.golden_sql,
                "db_error": result.error,
                "latency_ms": round(prediction.latency_ms, 1),
                "calls": prediction.calls,
                "model_usage": prediction.model_usage,
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


def _models_used(rows: list[dict[str, Any]], fallback: str | None) -> list[str]:
    models = {model for row in rows for model in (row.get("model_usage") or {})}
    if not models and fallback:
        models.add(fallback)
    return sorted(models)


def _append_ledger(
    system, rows, identity, report_name, model_override, cache_discarded, decoding=None
) -> None:
    """Record provenance and aggregates for this run (public, sanitized)."""
    summary = reporter.summarize(rows)
    rates = reporter.policy_rates(reporter.policy_matrix(rows))
    tokens = reporter.token_stats(rows)
    coder_model = model_override or getattr(system, "model", None)
    cost = reporter.cost_stats(rows, fallback_model=coder_model)
    record = ledger.make_record(
        system=system.name,
        dataset=identity,
        models=_models_used(rows, coder_model),
        coder_model=coder_model,
        metrics={
            **summary["sql"],
            "clarification_correct": summary["clarification"]["clarification_correct"],
            "answer_rate": summary["answer_rate"],
            "ex_at_answered": summary["ex_at_answered"],
            "presumption_rate": rates["presumption_rate"],
            "over_clarify_rate": rates["over_clarify_rate"],
            "policy_accuracy": rates["policy_accuracy"],
        },
        tokens={
            "per_case": tokens["per_case"],
            "cached_share": tokens["cached_share"],
            "calls_per_case": tokens["calls_per_case"],
        },
        cost_cny={"per_case": cost["per_case_cny"], "total": cost["total_cny"]},
        latency_ms=reporter.latency_stats(rows),
        report=report_name,
        decoding=decoding,
        notes="stale expected-result cache discarded" if cache_discarded else None,
    )
    ledger.append_run(record)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the NL2SQL eval harness.")
    parser.add_argument("--system", choices=SYSTEMS, default="direct")
    parser.add_argument(
        "--provider",
        choices=("siliconflow", "deepseek"),
        default="siliconflow",
        help="which OpenAI-compatible endpoint the coder call goes to",
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="keep DeepSeek thinking mode on (default: disabled -- it ignores temperature)",
    )
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
    identity = ledger.dataset_identity(dataset)
    cache = ExpectedResultCache(
        args.expected_cache or paths.expected_cache, dataset_hash=identity.hash
    )
    provider = build_provider(args.provider, args.model, thinking=args.thinking)
    system = build_system(args.system, db=db, model=args.model, provider=provider)
    effective_model = args.model or provider.coder_model
    decoding = {
        "temperature": EVAL_TEMPERATURE,
        "max_tokens": EVAL_MAX_TOKENS,
        # Only meaningful on the DeepSeek endpoint; None = not applicable.
        "thinking": args.thinking if args.provider == "deepseek" else None,
    }

    print(
        f"system={system.name} provider={provider.label} model={effective_model} "
        f"decoding={decoding} n={len(cases)} dataset={identity.label}"
    )
    rows = score_system(system, cases, db=db, cache=cache, schema=schema)
    cache.save()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = paths.raw(effective_model, system.name, stamp)
    report_path = paths.report(effective_model, system.name, stamp)
    reporter.write_raw(raw_path, rows)
    report_path.write_text(
        reporter.render_markdown(
            system_name=system.name,
            model=str(effective_model),
            dataset=dataset.name,
            rows=rows,
            generated_at=stamp,
        ),
        encoding="utf-8",
    )

    _append_ledger(
        system,
        rows,
        identity,
        paths.ledger_report(effective_model, system.name, stamp),
        effective_model,
        cache.discarded,
        decoding,
    )

    print(f"\nreport: {report_path}")
    print(f"raw:    {raw_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
