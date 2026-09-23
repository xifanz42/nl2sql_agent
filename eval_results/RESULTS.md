# Eval scoreboard

Single public source of truth for NL2SQL eval results.
See [`app/eval/README.md`](../app/eval/README.md) for how to run.

- Dataset: **private** golden set, 90 cases = **76 SQL questions + 14 clarification cases**.
- Every case carries `required_behavior` = `answer | clarify | refuse`, so scores are
  split by expected behaviour instead of lumped into one number.
- Raw per-case detail lives in the matching `*.raw.jsonl`, which is gitignored.

## Policy compliance — the harness design goal

The agent is designed to **never presume**: when a question is not fully specified
(or not answerable), it should ask rather than invent an answer. This is measured as a
confusion matrix of *should answer* (from `required_behavior`) versus *did answer*.

| system | presumption rate ↓ | over-clarify rate | policy accuracy | report |
|---|---|---|---|---|
| `oracle` (self-check) | 0.0% | 0.0% | 100.0% | [oracle-20260921T134245Z.md](oracle-20260921T134245Z.md) |
| `direct` | **100.0%** | 2.6% | 82.2% | [direct-20260922T150152Z.md](direct-20260922T150152Z.md) |
| `direct+rag` | **100.0%** | 0.0% | 84.4% | [direct+rag-20260922T124000Z.md](direct+rag-20260922T124000Z.md) |
| `harness` | **14.3%** | 10.5% | **88.9%** | [harness-20260921T134848Z.md](harness-20260921T134848Z.md) |

- **presumption rate** = answered when it should have declined (the failure mode the
  agent was built to avoid).
- **over-clarify rate** = asked when it should have answered (the cost of that policy).

Both baselines presume **every** time; the agent presumes 2 of 14 times. This is the
capability that the earlier single-score eval could not see at all.

## Ablation (SQL accuracy)

| system | RAG | prompt | guardrails / clarify | **EX** | EX@answered | answer rate |
|---|---|---|---|---|---|---|
| `direct` | ❌ | naive | ❌ | **28.9%** | 29.7% | 97.8% |
| `direct+rag` | ✅ | naive | ❌ | **61.8%** | 61.8% | 100.0% |
| `harness` | ✅ | rich | ✅ | **51.3%** | 57.4% | 77.8% |
| `oracle` (self-check) | — | — | — | 100.0% | 100.0% | 84.4% |

| delta | meaning | EX |
|---|---|---|
| Δ1 = `direct+rag` − `direct` | value of **RAG alone** | **+32.9 pt** |
| Δ2 = `harness` − `direct+rag` | value of the **harness beyond RAG** | **−10.5 pt** |
| Δ3 = `harness` − `direct` | total | +22.4 pt |

**Reading:** RAG carries SQL accuracy. The agent's extra machinery costs ~10 pt of EX
but buys the presumption-resistance above.

All systems use the same SQL model: `Qwen/Qwen3-Coder-30B-A3B-Instruct`.
`direct+rag` reuses the agent's own retriever (`NL2SQLChatbot.retrieve_knowledge`).

## SQL details (76 questions)

| system | valid_sql | EM | EX | schema |
|---|---|---|---|---|
| `direct` | 85.5% | 9.2% | 28.9% | 90.8% |
| `direct+rag` | 97.4% | 22.4% | 61.8% | 98.7% |
| `harness` | 85.5% | 21.1% | 51.3% | 89.5% |
| `oracle` | 100.0% | 100.0% | 100.0% | 100.0% |

## EX by difficulty

| system | easy (3) | medium (46) | hard (27) |
|---|---|---|---|
| `direct` | 66.7% | 26.1% | 29.6% |
| `direct+rag` | 100.0% | 67.4% | **48.1%** |
| `harness` | 100.0% | 67.4% | **18.5%** |

## Clarification (14 questions, `required_behavior=refuse`)

| system | clarification_correct |
|---|---|
| `oracle` | 100.0% |
| `harness` | **85.7%** |
| `direct` / `direct+rag` | 0.0% |

These ask about metrics/categories that do not exist in the database, so no SQL can
answer them; the correct behaviour is to decline or ask back.

## Open questions

- The 8 cases the agent asked about although `required_behavior=answer` are
  `44, 55, 60, 78, 83, 84, 85, 86` — mostly time-scoped questions on data that only
  covers six days and whose timestamps are all midnight. Several are plausibly
  *actually* under-specified, i.e. the label (not the agent) may be wrong. They need
  independent adjudication before the 10.5% over-clarify rate is trusted.
- The 2 cases the agent answered although it should have declined are `48, 63`.

## Notes

- **The provider is not deterministic** (MoE model): re-running `direct` after a
  prompt-wording tweak moved EX from 35.5% to 28.9%. Treat deltas below ~5 pt as
  inconclusive.
- Token usage is recorded only for the `direct` variants; the agent's
  `generate_sql()` returns text without `usage`.

## Updating this scoreboard

1. Run a system: `python -m app.eval.runner --system <oracle|direct|direct+rag|harness>`.
2. Update that system's row and link the new `<system>-<ts>.md`.
3. Keep only the latest report per system; prune older reports.
