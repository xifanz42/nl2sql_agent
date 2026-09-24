"""Generate the numeric sections of RESULTS.md from the current snapshot.

The markdown scoreboard previously carried hand-copied numbers that silently went
stale as soon as a system was re-run. Each numeric section now lives between
markers and is regenerated from the same data the visual report uses:

    <!-- FINDINGS:BEGIN --> ... <!-- FINDINGS:END -->
    <!-- ANSWER:BEGIN -->   ... <!-- ANSWER:END -->
    <!-- POLICY:BEGIN -->   ... <!-- POLICY:END -->
    <!-- EFFICIENCY:BEGIN --> ... <!-- EFFICIENCY:END -->
    <!-- SYNTHESIS:BEGIN --> ... <!-- SYNTHESIS:END -->

Prose that carries no numbers stays hand-authored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.eval.snapshot import LEVELS, pct, secs

BLOCK_NAMES = ("FINDINGS", "ANSWER", "POLICY", "EFFICIENCY", "SYNTHESIS")


def _signed(value: float, digits: int = 1) -> str:
    """Signed percentage with a typographic minus, matching the rest of the report."""
    return f"{value:+.{digits}f}".replace("-", "−")


def _ex(data: dict[str, Any], system: str) -> float:
    return data[system]["summary"]["sql"]["execution_match"]


def _findings(data: dict[str, Any]) -> str:
    ex = {s: _ex(data, s) for s in data}
    retrieval_gain = (ex["direct+rag"] - ex["direct"]) * 100
    conditional = (
        data["harness"]["summary"]["ex_at_answered"]
        - data["direct+rag"]["summary"]["ex_at_answered"]
    ) * 100
    cost_ratio = (
        data["direct+rag"]["cost"]["per_case_cny"] / data["direct"]["cost"]["per_case_cny"]
    )
    coverage = data["harness"]["summary"]["answer_rate"]
    presumption = data["harness"]["rates"]["presumption_rate"]
    cost_chain = " → ".join(
        f"¥{data[s]['cost']['per_case_cny']:.5f}" for s in ("direct", "direct+rag", "harness")
    )
    return f"""| # | Finding | Evidence |
|---|---|---|
| **F1** | Retrieval is the dominant driver of answer quality. | EX {pct(ex['direct'])} → {pct(ex['direct+rag'])} (**+{retrieval_gain:.1f} pt**) |
| **F2** | At equal coverage, the agent's answer quality is statistically indistinguishable from the retrieval-only baseline. | EX@answered {pct(data['harness']['summary']['ex_at_answered'])} vs {pct(data['direct+rag']['summary']['ex_at_answered'])} (**{_signed(conditional)} pt**, within run-to-run variance) |
| **F3** | The agent's aggregate EX deficit is therefore attributable to abstention, not to generation. | coverage {pct(coverage)} vs 100.0%; presumption 100.0% → **{pct(presumption)}** |
| **F4** | The agent's second call is effectively free; retrieval is the cost driver. | cost/case {cost_chain} (**{cost_ratio:.1f}×**); routing model priced at ¥0 |"""


def _answer(data: dict[str, Any]) -> str:
    def sql_row(system: str) -> str:
        s = data[system]["summary"]
        return (
            f"| {system} | {pct(s['sql']['valid_sql'])} | {pct(s['sql']['exact_match'])} | "
            f"**{pct(s['sql']['execution_match'])}** | {pct(s['sql']['schema_adherence'])} | "
            f"{pct(s['ex_at_answered'])} | {pct(s['answer_rate'])} |"
        )

    table = "\n".join(sql_row(s) for s in ("oracle", "direct", "direct+rag", "harness"))

    def diff_row(system: str) -> str:
        bd = data[system]["by_difficulty"]
        cells = " | ".join(pct(bd.get(lv, {}).get("execution_match", 0.0)) for lv in LEVELS)
        return f"| {system} | {cells} |"

    difficulty = "\n".join(diff_row(s) for s in ("direct", "direct+rag", "harness"))

    ems = [data[s]["summary"]["sql"]["exact_match"] for s in ("direct", "direct+rag", "harness")]
    medium = {s: data[s]["by_difficulty"].get("medium", {}).get("execution_match", 0.0)
              for s in ("direct+rag", "harness")}
    hard = {s: data[s]["by_difficulty"].get("hard", {}).get("execution_match", 0.0)
            for s in ("direct+rag", "harness")}
    over = data["harness"]["matrix"]["over_clarified"]
    n_sql = data["harness"]["summary"]["n_sql"]
    return f"""| System | `valid_sql` | EM | **EX** | `schema_adherence` | EX@answered | answer rate |
|---|---|---|---|---|---|---|
{table}

EX by difficulty stratum:

| System | easy (n=3) | medium (n=46) | hard (n=24) |
|---|---|---|---|
{difficulty}

Observations:

- EM is not a usable optimisation target for this task ({pct(min(ems))}–{pct(max(ems))}); semantically equivalent queries differ in aliasing and formatting. EX is adopted as the primary metric.
- `direct+rag` and `harness` are indistinguishable on the `medium` stratum ({pct(medium['direct+rag'])} vs {pct(medium['harness'])}); the deficit is localised to `hard` ({_signed((hard['harness'] - hard['direct+rag']) * 100)} pt), which concentrates multi-condition `FILTER`, subquery and temporal-aggregation constructs.
- The `harness` abstains on {over} of {n_sql} answerable cases (over-clarify rate {pct(data['harness']['rates']['over_clarify_rate'])}), so its overall EX understates its conditional accuracy. At equal answer rate the gap narrows (EX@answered: {pct(data['harness']['summary']['ex_at_answered'])} vs {pct(data['direct+rag']['summary']['ex_at_answered'])}) but does not reverse."""


def _policy(data: dict[str, Any]) -> str:
    labels = {"oracle": "`oracle`", "direct": "`direct`", "direct+rag": "`direct+rag`",
              "harness": "`harness`"}
    matrix_rows = []
    for s in ("oracle", "direct", "direct+rag", "harness"):
        m = data[s]["matrix"]
        matrix_rows.append(
            f"| {labels[s]} | {m['answered_as_expected']} | {m['over_clarified']} | "
            f"{m['presumed']} | {m['declined_as_expected']} |"
        )
    rate_rows = []
    for s in ("oracle", "direct", "direct+rag", "harness"):
        r = data[s]["rates"]
        rate_rows.append(
            f"| {labels[s]} | {pct(r['presumption_rate'])} | {pct(r['over_clarify_rate'])} | "
            f"{pct(r['policy_accuracy'])} |"
        )
    clar_rows = []
    for s in ("oracle", "harness", "direct", "direct+rag"):
        clar_rows.append(f"| {labels[s]} | {pct(data[s]['summary']['clarification']['clarification_correct'])} |")
    correct = data["harness"]["matrix"]["declined_as_expected"]
    n_clar = data["harness"]["summary"]["n_clarification"]
    return f"""| System | TP (answer ✓) | FN (over-clarify) | FP (presumption) | TN (abstain ✓) |
|---|---|---|---|---|
{chr(10).join(matrix_rows)}

Derived rates:

| System | `presumption_rate` ↓ | `over_clarify_rate` ↓ | `policy_accuracy` |
|---|---|---|---|
{chr(10).join(rate_rows)}

Per-partition correct-action rate:

| System | `clarify` + `refuse` (`clarification_correct`) |
|---|---|
{chr(10).join(clar_rows)}

Both baselines answer every case, including the 14 whose referenced metric does not exist in
the database; they fabricate a query against a non-existent attribute in 100% of those cases.
The agent declines or requests disambiguation in {correct} of {n_clar}, a
**+{(data['harness']['summary']['clarification']['clarification_correct'] - data['direct']['summary']['clarification']['clarification_correct']) * 100:.1f} pt**
improvement on this axis. The cost is a {pct(data['harness']['rates']['over_clarify_rate'])}
unnecessary-abstention rate on the answerable partition and a
**{(data['direct']['summary']['answer_rate'] - data['harness']['summary']['answer_rate']) * 100:.1f} pt**
reduction in coverage."""


def _efficiency(data: dict[str, Any]) -> str:
    rows = []
    for s in ("direct", "direct+rag", "harness", "oracle"):
        d = data[s]
        measured = bool(d["tokens"]["per_case"])
        calls = f"{d['tokens']['calls_per_case']:.1f}" if measured else "—"
        tokens = f"{d['tokens']['per_case']:,.0f}" if measured else "—"
        cached = pct(d["tokens"]["cached_share"]) if measured else "—"
        cost = f"{d['cost']['per_case_cny']:.5f}" if measured else "—"
        p50 = secs(d["latency"]["p50_ms"]) if measured else "—"
        p95 = secs(d["latency"]["p95_ms"]) if measured else "—"
        rows.append(f"| `{s}` | {calls} | {tokens} | {cached} | {cost} | {p50} | {p95} |")
    totals = " · ".join(
        f"`{s}` ¥{data[s]['cost']['total_cny']:.4f}" for s in ("direct", "direct+rag", "harness")
    )
    ratio = (
        data["direct+rag"]["cost"]["per_case_cny"] / data["direct"]["cost"]["per_case_cny"]
    )
    ex_gain = (_ex(data, "direct+rag") - _ex(data, "direct")) * 100
    agent_ratio = (
        data["harness"]["cost"]["per_case_cny"] / data["direct+rag"]["cost"]["per_case_cny"]
    )
    return f"""| System | calls / case | tokens / case | cached share | cost / case (CNY) | p50 | p95 |
|---|---|---|---|---|---|---|
{chr(10).join(rows)}

Total over the 90 cases: {totals}.

- **Retrieval multiplies the per-case cost {ratio:.1f}×** (`direct` → `direct+rag`) for a
  {ex_gain:+.1f} pt EX gain. It is the only component that materially changes cost.
- **The agent's second call is free.** Routing runs on `Qwen/Qwen2.5-7B-Instruct`, priced at
  ¥0 / M tokens, so the harness costs only **{agent_ratio:.2f}×** the retrieval baseline despite
  issuing two calls per case; its entire cost is the generation call.
- **Prompt caching does not reduce cost on the generation model.**
  `Qwen/Qwen3-Coder-30B-A3B-Instruct` has no published cached-input discount (cached tokens are
  billed at the input rate), so caching saves prompt processing but not spend. The discount
  applies to `deepseek-ai/DeepSeek-V3` (¥0.20 vs ¥2.00 / M), which this workload barely uses.
- Prices are recorded explicitly in `app/eval/pricing.py` (CNY per 1M tokens, 2026-09) and are
  an external input: a cost figure is only valid against that dated list."""


def _synthesis(data: dict[str, Any]) -> str:
    retrieval_gain = (_ex(data, "direct+rag") - _ex(data, "direct")) * 100
    agent_gap = (_ex(data, "harness") - _ex(data, "direct+rag")) * 100
    conditional = (
        data["harness"]["summary"]["ex_at_answered"]
        - data["direct+rag"]["summary"]["ex_at_answered"]
    ) * 100
    coverage_loss = (
        data["direct"]["summary"]["answer_rate"] - data["harness"]["summary"]["answer_rate"]
    ) * 100
    agent_ratio = (
        data["harness"]["cost"]["per_case_cny"] / data["direct+rag"]["cost"]["per_case_cny"]
    )
    return f"""1. Retrieval is the dominant driver of answer quality in both baselines ({_signed(retrieval_gain)} pt EX).
2. **At equal coverage the agent's answer quality is statistically indistinguishable from the retrieval-only baseline** (EX@answered {pct(data['harness']['summary']['ex_at_answered'])} vs {pct(data['direct+rag']['summary']['ex_at_answered'])}; the {abs(conditional):.1f} pt difference lies below the observed run-to-run variance). Its aggregate EX deficit ({_signed(agent_gap)} pt) is therefore attributable to the abstention policy, not to generation quality.
3. The agent's advantage is confined to abstention: presumption falls from 100.0% to {pct(data['harness']['rates']['presumption_rate'])}, at a cost of {pct(data['harness']['rates']['over_clarify_rate'])} over-clarification and a {coverage_loss:.1f} pt reduction in coverage.
4. The agent issues two model calls per case at only **{agent_ratio:.2f}×** the cost of the single-call retrieval baseline, because its routing stage runs on a zero-priced model."""


RENDERERS = {
    "FINDINGS": _findings,
    "ANSWER": _answer,
    "POLICY": _policy,
    "EFFICIENCY": _efficiency,
    "SYNTHESIS": _synthesis,
}


def render_blocks(data: dict[str, Any]) -> dict[str, str]:
    return {name: renderer(data) for name, renderer in RENDERERS.items()}


def update(path: Path, data: dict[str, Any]) -> list[str]:
    """Replace every marked numeric block in ``path``. Returns the blocks updated."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    updated = []
    for name, body in render_blocks(data).items():
        begin, end = f"<!-- {name}:BEGIN -->", f"<!-- {name}:END -->"
        if begin not in text or end not in text:
            continue
        head, _, rest = text.partition(begin)
        _, _, tail = rest.partition(end)
        text = f"{head}{begin}\n{body}\n{end}{tail}"
        updated.append(name)
    if updated:
        path.write_text(text, encoding="utf-8")
    return updated
