# Eval scoreboard

Single public source of truth for NL2SQL eval results.
See [`app/eval/README.md`](../app/eval/README.md) for how to run.

- Dataset: **private** golden set, 90 cases = **73 SQL questions + 17 clarification cases**.
- Every case declares `required_behavior` = `answer | clarify | refuse` (human-adjudicated,
  see `RECLASSIFY` in `scripts/build_golden_dataset.py`), so scores are split by expected
  behaviour instead of being lumped into one number.
- Raw per-case detail lives in the matching `*.raw.jsonl`, which is gitignored.

## Policy compliance — the harness design goal

The agent is designed to **never presume**: when a question is not fully specified (or not
answerable), it should ask rather than invent an answer.

| system | presumption rate ↓ | over-clarify rate | policy accuracy | report |
|---|---|---|---|---|
| `oracle` (self-check) | 0.0% | 0.0% | 100.0% | [oracle-20260924T053243Z.md](oracle-20260924T053243Z.md) |
| `direct` | **100.0%** | 2.7% | 78.9% | [direct-20260922T150152Z.md](direct-20260922T150152Z.md) |
| `direct+rag` | **100.0%** | 0.0% | 81.1% | [direct+rag-20260922T124000Z.md](direct+rag-20260922T124000Z.md) |
| `harness` | **11.8%** | 6.8% | **92.2%** | [harness-20260921T134848Z.md](harness-20260921T134848Z.md) |

- **presumption rate** = answered when it should have declined (the failure mode the agent
  was built to avoid).
- **over-clarify rate** = asked when it should have answered (the cost of that policy).

Both baselines presume **every** time; the agent presumes 2 of 17 times.

## Ablation (SQL accuracy)

| system | RAG | prompt | guardrails / clarify | **EX** | EX@answered | answer rate |
|---|---|---|---|---|---|---|
| `direct` | ❌ | naive | ❌ | **28.8%** | 29.6% | 97.8% |
| `direct+rag` | ✅ | naive | ❌ | **63.0%** | 63.0% | 100.0% |
| `harness` | ✅ | rich | ✅ | **53.4%** | 57.4% | 77.8% |
| `oracle` (self-check) | — | — | — | 100.0% | 100.0% | 81.1% |

| delta | meaning | EX |
|---|---|---|
| Δ1 = `direct+rag` − `direct` | value of **RAG alone** | **+34.2 pt** |
| Δ2 = `harness` − `direct+rag` | value of the **harness beyond RAG** | **−9.6 pt** |
| Δ3 = `harness` − `direct` | total | +24.6 pt |

**Reading:** RAG carries SQL accuracy. The agent's extra machinery costs ~10 pt of EX but
buys the presumption resistance above.

All systems use the same SQL model: `Qwen/Qwen3-Coder-30B-A3B-Instruct`.
`direct+rag` reuses the agent's own retriever (`NL2SQLChatbot.retrieve_knowledge`).

## SQL details (73 questions)

| system | valid_sql | EM | EX | schema |
|---|---|---|---|---|
| `direct` | 86.3% | 9.6% | 28.8% | 90.4% |
| `direct+rag` | 97.3% | 23.3% | 63.0% | 98.6% |
| `harness` | 89.0% | 21.9% | 53.4% | 93.2% |
| `oracle` | 100.0% | 100.0% | 100.0% | 100.0% |

## EX by difficulty

| system | easy (3) | medium (46) | hard (24) |
|---|---|---|---|
| `direct` | 66.7% | 26.1% | 29.2% |
| `direct+rag` | 100.0% | 67.4% | **50.0%** |
| `harness` | 100.0% | 67.4% | **20.8%** |

## Clarification (17 questions)

| system | clarification_correct |
|---|---|
| `oracle` | 100.0% |
| `harness` | **88.2%** |
| `direct` / `direct+rag` | 0.0% |

14 cases ask about metrics/categories that do not exist (`refuse`); 3 are under-specified
questions where the agent should ask back (`clarify`).

## Cost & latency (90 cases)

| system | latency p50 / p95 / mean / max | tokens (prompt / cached / completion) | per case |
|---|---|---|---|
| `direct` | 1.30 s / 5.14 s / 2.21 s / 23.45 s | 13,210 / 11,520 / 7,134 | 226 |
| `direct+rag` | 2.22 s / 4.18 s / 2.36 s / 7.31 s | 110,140 / 87,744 / 4,830 | **1,277** |
| `harness` | 1.70 s / 3.80 s / 2.03 s / 8.12 s | not recorded (returns text without `usage`) | — |
| `oracle` | ~0 s (no model call) | — | — |

RAG costs **5.6× the tokens** of the naive baseline (retrieved knowledge is injected every
call); the agent is not slower than `direct` despite making an extra (small-model) call.

## Open questions

- The remaining 5 over-clarified cases (`78, 83, 84, 85, 86`) are season/weekend questions;
  3 of them return empty because the data only covers 6 days in August. They are kept as
  `answer` — producing an empty result is the correct behaviour — but are tagged here.
- The 2 presumed cases are `48, 63`.
- Token accounting for `harness` needs a `(text, usage)` variant in `app/core/llm.py`.

## Notes

- **The provider is not deterministic** (MoE model): a prompt-wording tweak once moved
  `direct` EX by ~7 pt. Treat deltas below ~5 pt as inconclusive; prefer paired runs.
- Reports can be re-rendered from a raw dump without re-running models; the renderer
  overlays the current `required_behavior` from the golden set.

## Updating this scoreboard

1. Run a system: `python -m app.eval.runner --system <oracle|direct|direct+rag|harness>`.
2. Update that system's row and link the new `<system>-<ts>.md`.
3. Keep only the latest report per system; prune older reports.
