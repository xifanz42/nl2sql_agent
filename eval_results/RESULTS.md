# Eval scoreboard

Single public source of truth for NL2SQL eval results.
See [`app/eval/README.md`](../app/eval/README.md) for how to run.

- Dataset: **private** golden set, 90 cases = **76 SQL questions + 14 clarification cases**.
- Scores are split by case type so different capabilities never share a denominator.
- Raw per-case detail lives in the matching `*.raw.jsonl`, which is gitignored.

## SQL questions (76)

| system | model | valid_sql | EM | **EX** | schema | EX@answered | answer rate | report |
|---|---|---|---|---|---|---|---|---|
| oracle (self-check) | n/a | 100.0% | 100.0% | **100.0%** | 100.0% | 100.0% | 84.4% | [oracle-20260921T134245Z.md](oracle-20260921T134245Z.md) |
| direct (baseline) | Qwen/Qwen3-Coder-30B-A3B-Instruct | 92.1% | 9.2% | **35.5%** | 96.1% | 35.5% | 100.0% | [direct-20260921T134515Z.md](direct-20260921T134515Z.md) |
| harness (agent) | routed † | 85.5% | 21.1% | **51.3%** | 89.5% | 57.4% | 77.8% | [harness-20260921T134848Z.md](harness-20260921T134848Z.md) |
| direct+rag (fair baseline) | — | — | — | — | — | — | — | _planned_ |

**harness vs direct:** ΔEX **+15.8 pt** · ΔEX@answered **+21.9 pt** · Δanswer rate **−22.2 pt**.

## Clarification questions (14)

| system | clarification_correct |
|---|---|
| oracle | 100.0% |
| direct | 0.0% |
| harness | **85.7%** |

These are questions whose metric/category does **not** exist in the database, so no
SQL can answer them; the correct behaviour is to ask back rather than fabricate.

## SQL by difficulty (EX)

| system | easy (3) | medium (46) | hard (27) |
|---|---|---|---|
| oracle | 100.0% | 100.0% | 100.0% |
| direct | 66.7% | 30.4% | 40.7% |
| harness | 100.0% | 67.4% | 18.5% |

† **harness model routing** (by task difficulty, `app/config.py` / `.env`):

| role | difficulty | model |
|---|---|---|
| `SILICON_FLOW_NL2SQL_MODEL` | hard — SQL generation | `Qwen/Qwen3-Coder-30B-A3B-Instruct` |
| `SILICON_FLOW_REASONING_MODEL` | medium — result analysis | `deepseek-ai/DeepSeek-V3` |
| `SILICON_FLOW_HELPER_MODEL` | easy — routing / follow-up | `Qwen/Qwen2.5-7B-Instruct` |

## Notes

- `direct` answers every question, `harness` declines ~22%; `EX@answered` compares
  them at equal answer rate.
- `harness` loses on hard questions (18.5% vs 40.7%) — the main optimization target.
- Token usage is recorded only for `direct` (the agent's `generate_sql()` returns
  text without `usage`).

## Ablation plan

To attribute the gain, results will be reported as an ablation, not a single delta:

| system | schema | RAG | prompt | guardrails / clarify |
|---|---|---|---|---|
| `direct` | ✅ | ❌ | minimal | ❌ |
| `direct+rag` | ✅ | ✅ | minimal | ❌ |
| `harness` | ✅ | ✅ | rich | ✅ |

- Δ1 = `direct+rag` − `direct` → value of RAG alone
- **Δ2 = `harness` − `direct+rag`** → value of the harness beyond RAG (the headline)
- Δ3 = `harness` − `direct` → total

## Updating this scoreboard

1. Run a system: `python -m app.eval.runner --system <oracle|direct|harness> [--model NAME]`.
2. Update that system's row with the new numbers and link the new `<system>-<ts>.md`.
3. Keep only the latest report per system linked here; prune older reports.
