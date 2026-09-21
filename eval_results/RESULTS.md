# Eval scoreboard

Single public source of truth for NL2SQL eval results.
See [`app/eval/README.md`](../app/eval/README.md) for how to run.

- Dataset: **private** golden set, 90 cases (easy 3 / medium 46 / hard 41).
- Primary metric: **EX** (execution accuracy). EM is reported but harsh.
- Raw per-case detail lives in the matching `*.raw.jsonl`, which is gitignored.

## Overall

| system | model | date (UTC) | valid_sql | EM | **EX** | schema | safety | clarification | report |
|---|---|---|---|---|---|---|---|---|---|
| oracle (self-check) | n/a | 2026-09-21 | 100.0% | 100.0% | **100.0%** | 100.0% | 100.0% | 100.0% | [oracle-20260921T064553Z.md](oracle-20260921T064553Z.md) |
| direct (baseline) | Qwen/Qwen3-Coder-30B-A3B-Instruct | 2026-09-21 | 93.3% | 8.9% | **35.6%** | 95.6% | 96.7% | 100.0% | [direct-20260921T062205Z.md](direct-20260921T062205Z.md) |
| harness (agent) | routed † | 2026-09-21 | 75.6% | 18.9% | **55.6%** | 80.0% | 78.9% | 80.0% | [harness-20260921T072131Z.md](harness-20260921T072131Z.md) |

† **harness model routing** (by task difficulty, `app/config.py` / `.env`):

| role | difficulty | model |
|---|---|---|
| `SILICON_FLOW_NL2SQL_MODEL` | hard — SQL generation | `Qwen/Qwen3-Coder-30B-A3B-Instruct` |
| `SILICON_FLOW_REASONING_MODEL` | medium — result analysis | `deepseek-ai/DeepSeek-V3` |
| `SILICON_FLOW_HELPER_MODEL` | easy — routing / follow-up | `Qwen/Qwen2.5-7B-Instruct` |

## EX by difficulty

| system | easy (3) | medium (46) | hard (41) |
|---|---|---|---|
| oracle | 100.0% | 100.0% | 100.0% |
| direct | 66.7% | 45.7% | 22.0% |
| harness | 100.0% | 87.0% | 17.1% |

**Harness vs direct (ΔEX):** overall **+20.0 pt** · easy +33.3 · medium +41.3 · hard −4.9.

## Cost & latency (90 cases)

| system | tokens (prompt / cached / completion) | latency p50 / mean / max |
|---|---|---|
| direct | 13,210 / 11,264 / 6,454 | 1.76 s / 2.34 s / 20.5 s |
| harness | not captured † | 2.29 s / 9.77 s / 602 s |

† `NL2SQLChatbot.generate_sql()` returns text without usage, so harness token
counts are not recorded yet.

## Notes

- The harness answered 18/90 cases without a `SELECT` (its `SQL_QUERY:` sentinel
  protocol was not followed), which counts against `safety_pass` /
  `clarification_correct` on those cases.
- One harness case took 602 s (transient); the rest were ≤ 21 s.
- `safety_pass` for non-safety cases means "predicted SQL is a single SELECT/UNION",
  so clarifications score 0 there by construction.

## Updating this scoreboard

1. Run a system: `python -m app.eval.runner --system <oracle|direct|harness> [--model NAME]`.
2. Update that system's row with the new numbers and link the new `<system>-<ts>.md`.
3. Keep only the latest report per system linked here; older reports can be pruned.
