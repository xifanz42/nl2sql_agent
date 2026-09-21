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
| harness (agent) | — | — | — | — | — | — | — | — | _not run_ |

## EX by difficulty

| system | easy (3) | medium (46) | hard (41) |
|---|---|---|---|
| oracle | 100.0% | 100.0% | 100.0% |
| direct | 66.7% | 45.7% | 22.0% |

## Cost & latency (`direct`, 90 cases)

| metric | value |
|---|---|
| prompt tokens | 13,210 |
| cached tokens | 11,264 |
| completion tokens | 6,454 |
| total tokens | 19,664 (~218 / case) |
| latency p50 / mean / max | 1.76 s / 2.34 s / 20.5 s |

## Updating this scoreboard

1. Run a system: `python -m app.eval.runner --system <oracle|direct|harness> [--model NAME]`.
2. Update that system's row with the new numbers and link the new `<system>-<ts>.md`.
3. Keep only the latest report per system linked here; older reports can be pruned.
