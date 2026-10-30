# NL2SQL Evaluation — Baseline Report

Reference set: 90 private cases. Numeric sections (§2–§4) are pinned to the
`Qwen/Qwen3-Coder-30B-A3B-Instruct` baseline run (latest 2026-10-11). The run ledger also
contains DeepSeek-V3 and deepseek-flash probes; those rows are provenance, not pooled baseline
scores.

Visual summary: [`results-vis.html`](results-vis.html) ·
Run history: [`results-history.html`](results-history.html) ·
Runner instructions: [`app/eval/README.md`](../app/eval/README.md)

<!-- RUNS:BEGIN -->
Reference set: **v2-adjudicated** (fingerprint `9edea4900e42`, 90 cases) · 25 recorded run(s)

| time (UTC) | system | model | dataset | git | EX | EX@answered | presumption ↓ | over-clarify ↓ | cost / case | report |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-11T07:08:16Z | `harness` | `deepseek-flash` | v2-adjudicated | `e77cce4+` | 54.8% | 55.6% | 29.4% | 1.4% | ¥0.00102 | [reports/deepseek-flash/harness-20261011T070816Z.md](reports/deepseek-flash/harness-20261011T070816Z.md) |
| 2026-10-11T07:06:42Z | `direct+rag` | `deepseek-flash` | v2-adjudicated | `e77cce4+` | 54.8% | 54.8% | 41.2% | 0.0% | ¥0.00128 | [reports/deepseek-flash/direct+rag-20261011T070642Z.md](reports/deepseek-flash/direct+rag-20261011T070642Z.md) |
| 2026-10-11T07:05:08Z | `direct` | `deepseek-flash` | v2-adjudicated | `e77cce4+` | 32.9% | 32.9% | 100.0% | 0.0% | ¥0.00077 | [reports/deepseek-flash/direct-20261011T070508Z.md](reports/deepseek-flash/direct-20261011T070508Z.md) |
| 2026-10-11T06:18:07Z | `harness` | `deepseek-ai/DeepSeek-V3` | v2-adjudicated | `e77cce4+` | 54.8% | 67.8% | 11.8% | 19.2% | ¥0.00334 | [reports/deepseek-v3/harness-20261011T061807Z.md](reports/deepseek-v3/harness-20261011T061807Z.md) |
| 2026-10-11T06:12:35Z | `direct+rag` | `deepseek-ai/DeepSeek-V3` | v2-adjudicated | `e77cce4+` | 49.3% | 58.1% | 11.8% | 15.1% | ¥0.00334 | [reports/deepseek-v3/direct+rag-20261011T061235Z.md](reports/deepseek-v3/direct+rag-20261011T061235Z.md) |
| 2026-10-11T06:07:07Z | `direct` | `deepseek-ai/DeepSeek-V3` | v2-adjudicated | `e77cce4+` | 11.0% | 50.0% | 11.8% | 78.1% | ¥0.00128 | [reports/deepseek-v3/direct-20261011T060707Z.md](reports/deepseek-v3/direct-20261011T060707Z.md) |
| 2026-10-11T05:55:10Z | `harness` | `deepseek-flash` | v2-adjudicated | `e77cce4+` | 56.2% | 61.2% | 11.8% | 8.2% | ¥0.01047 | [reports/deepseek-flash/harness-20261011T055510Z.md](reports/deepseek-flash/harness-20261011T055510Z.md) |
| 2026-10-11T05:45:30Z | `direct+rag` | `deepseek-flash` | v2-adjudicated | `e77cce4+` | 56.2% | 60.3% | 17.6% | 6.9% | ¥0.01122 | [reports/deepseek-flash/direct+rag-20261011T054530Z.md](reports/deepseek-flash/direct+rag-20261011T054530Z.md) |
| 2026-10-11T05:35:28Z | `direct` | `deepseek-flash` | v2-adjudicated | `e77cce4+` | 41.1% | 49.2% | 94.1% | 16.4% | ¥0.01140 | [reports/deepseek-flash/direct-20261011T053528Z.md](reports/deepseek-flash/direct-20261011T053528Z.md) |
| 2026-10-11T05:25:17Z | `harness` | `deepseek-ai/DeepSeek-V3` | v2-adjudicated | `e77cce4+` | 56.2% | 67.2% | 17.6% | 16.4% | ¥0.00334 | [reports/deepseek-v3/harness-20261011T052517Z.md](reports/deepseek-v3/harness-20261011T052517Z.md) |
| 2026-10-11T05:19:52Z | `direct+rag` | `deepseek-ai/DeepSeek-V3` | v2-adjudicated | `e77cce4+` | 53.4% | 62.9% | 5.9% | 15.1% | ¥0.00333 | [reports/deepseek-v3/direct+rag-20261011T051952Z.md](reports/deepseek-v3/direct+rag-20261011T051952Z.md) |
| 2026-10-11T05:14:21Z | `direct` | `deepseek-ai/DeepSeek-V3` | v2-adjudicated | `e77cce4+` | 9.6% | 58.3% | 5.9% | 83.6% | ¥0.00126 | [reports/deepseek-v3/direct-20261011T051421Z.md](reports/deepseek-v3/direct-20261011T051421Z.md) |
| 2026-10-11T05:09:23Z | `harness` | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | v2-adjudicated | `e77cce4+` | 54.8% | 59.7% | 11.8% | 8.2% | ¥0.00119 | [reports/qwen3-coder-30b-a3b-instruct/harness-20261011T050923Z.md](reports/qwen3-coder-30b-a3b-instruct/harness-20261011T050923Z.md) |
| 2026-10-11T05:06:35Z | `direct+rag` | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | v2-adjudicated | `e77cce4+` | 43.8% | 48.5% | 11.8% | 9.6% | ¥0.00119 | [reports/qwen3-coder-30b-a3b-instruct/direct+rag-20261011T050635Z.md](reports/qwen3-coder-30b-a3b-instruct/direct+rag-20261011T050635Z.md) |
| 2026-10-11T05:03:25Z | `direct` | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | v2-adjudicated | `e77cce4+` | 6.9% | 20.8% | 17.6% | 67.1% | ¥0.00046 | [reports/qwen3-coder-30b-a3b-instruct/direct-20261011T050325Z.md](reports/qwen3-coder-30b-a3b-instruct/direct-20261011T050325Z.md) |
| 2026-10-10T09:54:27Z | `direct+rag` | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | v2-adjudicated | `e77cce4` | 47.9% | 52.2% | 17.6% | 8.2% | ¥0.00119 | [reports/qwen3-coder-30b-a3b-instruct/direct+rag-20261010T095427Z.md](reports/qwen3-coder-30b-a3b-instruct/direct+rag-20261010T095427Z.md) |
| 2026-10-10T09:48:41Z | `direct` | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | v2-adjudicated | `e77cce4` | 9.6% | 28.0% | 29.4% | 65.8% | ¥0.00045 | [reports/qwen3-coder-30b-a3b-instruct/direct-20261010T094841Z.md](reports/qwen3-coder-30b-a3b-instruct/direct-20261010T094841Z.md) |
| 2026-10-10T09:05:06Z | `harness` | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | v2-adjudicated | `e77cce4` | 53.4% | 59.1% | 17.6% | 9.6% | ¥0.00119 | [reports/qwen3-coder-30b-a3b-instruct/harness-20261010T090506Z.md](reports/qwen3-coder-30b-a3b-instruct/harness-20261010T090506Z.md) |
| 2026-10-10T08:10:47Z | `oracle` | `—` | v2-adjudicated | `e77cce4` | 100.0% | 100.0% | 0.0% | 0.0% | ¥0.00000 | [reports/no-model/oracle-20261010T081047Z.md](reports/no-model/oracle-20261010T081047Z.md) |
| 2026-09-24T08:48:54Z | `harness` | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | v2-adjudicated | `6c9ac99` | 54.8% | 58.8% | 17.6% | 6.9% | ¥0.00119 | [reports/qwen3-coder-30b-a3b-instruct/harness-20260924T084854Z.md](reports/qwen3-coder-30b-a3b-instruct/harness-20260924T084854Z.md) |
| 2026-09-24T08:25:15Z | `direct+rag` | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | v2-adjudicated | `6c9ac99` | 63.0% | 63.0% | 100.0% | 0.0% | ¥0.00101 | [reports/qwen3-coder-30b-a3b-instruct/direct+rag-20260924T082515Z.md](reports/qwen3-coder-30b-a3b-instruct/direct+rag-20260924T082515Z.md) |
| 2026-09-24T08:22:14Z | `direct` | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | v2-adjudicated | `6c9ac99` | 28.8% | 28.8% | 100.0% | 0.0% | ¥0.00030 | [reports/qwen3-coder-30b-a3b-instruct/direct-20260924T082214Z.md](reports/qwen3-coder-30b-a3b-instruct/direct-20260924T082214Z.md) |
| 2026-09-24T08:18:28Z | `oracle` | `—` | v2-adjudicated | `6c9ac99` | 100.0% | 100.0% | 0.0% | 0.0% | ¥0.00000 | [reports/no-model/oracle-20260924T081828Z.md](reports/no-model/oracle-20260924T081828Z.md) |
| 2026-09-24T08:14:15Z | `oracle` | `—` | v2-adjudicated | `6c9ac99` | 100.0% | 100.0% | 0.0% | 0.0% | ¥0.00000 | [reports/no-model/oracle-20260924T081415Z.md](reports/no-model/oracle-20260924T081415Z.md) |
| 2026-09-24T08:14:03Z | `oracle` | `—` | v2-adjudicated | `6c9ac99` | 100.0% | 100.0% | 0.0% | 0.0% | ¥0.00000 | [reports/no-model/oracle-20260924T081403Z.md](reports/no-model/oracle-20260924T081403Z.md) |

⚠︎ = scored against a different reference set; not comparable with the current one.
Runs span multiple coder models; non-baseline rows are cross-model probes, not pooled
baseline scores. The run table comes from the ledger; the numeric blocks in §2–§4 are
generated from the latest raw dumps pinned to the Qwen3-Coder baseline by
`python scripts/build_history_dashboard.py`.
<!-- RUNS:END -->

---

## 1. Evaluation framework

### 1.1 Case taxonomy

Cases are partitioned by the reference action, declared as `required_behavior`. The reference
collection protocol was answer-only, so the abstention partitions were obtained by explicit
adjudication (§3.4) rather than by the collector.

| `required_behavior` | n | Reference action |
|---|---|---|
| `answer` | 73 | Emit an executable SQL query. |
| `clarify` | 3 | Request disambiguation; the question admits several defensible queries. |
| `refuse` | 14 | Decline; the referenced metric or category is absent from the database. |

### 1.2 Systems under evaluation

| System | Role | Retrieval | Prompt | Guardrails | Abstention |
|---|---|---|---|---|---|
| `oracle` | Reference upper bound / harness self-check | — | — | — | — |
| `direct` | Naive baseline | none | minimal | none | none |
| `direct+rag` | Retrieval-augmented baseline | dense | minimal | none | none |
| `harness` | System under evaluation | dense | engineered | yes | yes |

`direct+rag` shares the `harness` retrieval implementation
(`NL2SQLChatbot.retrieve_knowledge`) so the retrieval variable is held constant.

### 1.3 Metric definitions

Metrics are reported over their own sample space; no averaging is performed across partitions.

| Metric | Sample space | Definition | Direction |
|---|---|---|---|
| `valid_sql` | `answer` | Prediction executes without a database error. | ↑ |
| `exact_match` (EM) | `answer` | Normalised string identity with the reference query. | ↑ |
| `execution_match` (EX) | `answer` | Multiset identity of result sets; row order ignored. **Primary answer metric.** | ↑ |
| `schema_adherence` | `answer` | Every referenced relation resolves in the schema (sqlglot). | ↑ |
| `clarification_correct` | `clarify` + `refuse` | Predicted action agrees with the reference action. | ↑ |
| `presumption_rate` | `clarify` + `refuse` | `P(answer \| abstention required)`. **Primary abstention risk.** | ↓ |
| `over_clarify_rate` | `answer` | `P(abstain \| answer required)`. Cost of the abstention policy. | ↓ |
| `policy_accuracy` | all | `(TP + TN) / N` over the action confusion matrix. | ↑ |
| latency p50 / p95, tokens per case | all | Wall-clock and token consumption. | ↓ |

The action confusion matrix is defined over *reference action* × *predicted action*:

```
                       predicted answer   predicted abstain
reference answer             TP                 FN  (over-clarify)
reference abstain            FP (presumption)   TN
```

---

## 2. Principal findings

<!-- FINDINGS:BEGIN -->
| # | Finding | Evidence |
|---|---|---|
| **F1** | Retrieval is the dominant driver of answer quality. | EX 6.8% → 43.8% (**+37.0 pt**) |
| **F2** | The agent's conditional accuracy differs from the retrieval-only baseline by a single-run delta that has not yet been tested for significance. | EX@answered 59.7% vs 48.5% (**+11.2 pt**) |
| **F3** | On the pinned run the agent's aggregate EX is +11.0 pt vs the retrieval baseline while answering 76.7% of cases. | EX 54.8% vs 43.8%; presumption 11.8% |
| **F4** | The harness issues 1.0 model calls per case; retrieval is the cost driver. | cost/case ¥0.00046 → ¥0.00119 → ¥0.00119 (**2.6×** direct→retrieval) |
<!-- FINDINGS:END -->

---

## 3. Detailed analysis

### 3.1 Answer quality (`answer` partition, n = 73)

<!-- ANSWER:BEGIN -->
| System | `valid_sql` | EM | **EX** | `schema_adherence` | EX@answered | answer rate |
|---|---|---|---|---|---|---|
| oracle | 100.0% | 100.0% | **100.0%** | 100.0% | 100.0% | 81.1% |
| direct | 26.0% | 4.1% | **6.8%** | 27.4% | 20.8% | 30.0% |
| direct+rag | 76.7% | 20.5% | **43.8%** | 78.1% | 48.5% | 75.6% |
| harness | 90.4% | 20.5% | **54.8%** | 91.8% | 59.7% | 76.7% |

EX by difficulty stratum:

| System | easy (n=3) | medium (n=46) | hard (n=24) |
|---|---|---|---|
| direct | 33.3% | 6.5% | 4.2% |
| direct+rag | 100.0% | 56.5% | 12.5% |
| harness | 100.0% | 67.4% | 25.0% |

Observations:

- EM is not a usable optimisation target for this task (4.1%–20.5%); semantically equivalent queries differ in aliasing and formatting. EX is adopted as the primary metric.
- `direct+rag` and `harness` differ on the `medium` stratum (56.5% vs 67.4%, +10.9 pt) and on `hard` (12.5% vs 25.0%, +12.5 pt); the hard stratum concentrates multi-condition `FILTER`, subquery and temporal-aggregation constructs.
- The `harness` abstains on 6 of 73 answerable cases (over-clarify rate 8.2%), so its overall EX understates its conditional accuracy. EX@answered: 59.7% vs 48.5% (+11.2 pt).
<!-- ANSWER:END -->

### 3.2 Abstention policy (`clarify` + `refuse` partitions, n = 17)

Action confusion matrix:

<!-- POLICY:BEGIN -->
| System | TP (answer ✓) | FN (over-clarify) | FP (presumption) | TN (abstain ✓) |
|---|---|---|---|---|
| `oracle` | 73 | 0 | 0 | 17 |
| `direct` | 24 | 49 | 3 | 14 |
| `direct+rag` | 66 | 7 | 2 | 15 |
| `harness` | 67 | 6 | 2 | 15 |

Derived rates:

| System | `presumption_rate` ↓ | `over_clarify_rate` ↓ | `policy_accuracy` |
|---|---|---|---|
| `oracle` | 0.0% | 0.0% | 100.0% |
| `direct` | 17.6% | 67.1% | 42.2% |
| `direct+rag` | 11.8% | 9.6% | 90.0% |
| `harness` | 11.8% | 8.2% | 91.1% |

Per-partition correct-action rate:

| System | `clarify` + `refuse` (`clarification_correct`) |
|---|---|
| `oracle` | 100.0% |
| `harness` | 88.2% |
| `direct` | 82.4% |
| `direct+rag` | 88.2% |

The baselines answer cases whose referenced metric does not exist: `direct` presumes on
3 of 17 clarification cases and `direct+rag` on 2; the agent
presumes on 2. The agent declines or requests disambiguation in 15 of
17, a
**+5.9 pt**
improvement on this axis vs `direct`. The cost is a
8.2% over-clarification rate on the answerable
partition; answer rate is 76.7% for the agent vs
30.0% (`direct`) and
75.6% (`direct+rag`).
<!-- POLICY:END -->

### 3.3 Efficiency

<!-- EFFICIENCY:BEGIN -->
| System | calls / case | tokens / case | cached share | cost / case (CNY) | p50 | p95 |
|---|---|---|---|---|---|---|
| `direct` | 1.0 | 492 | 94.2% | 0.00046 | 1.49 s | 3.20 s |
| `direct+rag` | 1.0 | 1,557 | 83.9% | 0.00119 | 1.55 s | 3.53 s |
| `harness` | 1.0 | 1,557 | 95.6% | 0.00119 | 1.46 s | 3.48 s |
| `oracle` | — | — | — | — | — | — |

Total over the 90 cases: `direct` ¥0.0413 · `direct+rag` ¥0.1071 · `harness` ¥0.1072.

- **Retrieval multiplies the per-case cost 2.6×** (`direct` → `direct+rag`) for a
  +37.0 pt EX gain. It is the only component that materially changes cost.
- **The harness adds no second model call on the single-turn eval path.** It issues
  **1.0 calls/case** and costs **1.00×** the retrieval baseline; the eval
  harness calls `generate_sql`, so router/helper calls are outside this measurement.
- **Prompt caching does not reduce cost on the generation model.**
  `Qwen/Qwen3-Coder-30B-A3B-Instruct` has no published cached-input discount (cached tokens are
  billed at the input rate), so caching saves prompt processing but not spend. The discount
  applies to `deepseek-ai/DeepSeek-V3` (¥0.20 vs ¥2.00 / M), which the pinned baseline does not use.
- Prices are recorded explicitly in `app/eval/pricing.py` (CNY per 1M tokens, 2026-09) and are
  an external input: a cost figure is only valid against that dated list.
<!-- EFFICIENCY:END -->

### 3.4 Reference-set validity and adjudication

An automated audit against the live database established that the reference set required
material repair before any score was interpretable:

| Defect | Detected | Resolution |
|---|---|---|
| Ungrounded literals — referenced `index_name` / `index_category` values absent from the database | 13 cases | Reclassified as `refuse` |
| Temporal type error — `record_date` is `character varying`, compared as a timestamp | 15 cases | Explicit `::timestamp` / `::date` casts applied at build time |
| Temporal literal mismatch — bare `'YYYY-MM-DD'` against a value shaped `...T00:00:00Z` | 12 cases | `record_date::date` normalisation |
| Malformed data — a single row stored an invalid timestamp | 1 row | Corrected |
| Protocol-induced label bias — the answer-only collection protocol cannot express abstention | structural | 3 cases adjudicated as `clarify` |

The final partition (73 / 3 / 14) results from this adjudication; reclassification is recorded
explicitly in `RECLASSIFY` (`scripts/build_golden_dataset.py`) and is reproducible.

---

## 4. Synthesis

### 4.1 Findings

<!-- SYNTHESIS:BEGIN -->
1. Retrieval is the dominant driver of answer quality in both baselines (+37.0 pt EX).
2. On the pinned run the agent's aggregate EX is **+11.0 pt** vs the retrieval baseline (54.8% vs 43.8%), and EX@answered is **+11.2 pt** (59.7% vs 48.5%). Single-sample deltas have not yet been tested for significance.
3. Abstention is more conservative than the baselines: presumption is 17.6% / 11.8% / 11.8% (`direct` / `direct+rag` / `harness`), at 8.2% over-clarification.
4. The agent issues 1.0 model calls per case at **1.00×** the cost of the single-call retrieval baseline.
<!-- SYNTHESIS:END -->

### 4.2 Insights

- **A scalar EX conflates two independent quantities.** Conditioning on coverage separates
  `P(answer)` from `P(correct | answer)`, so a coverage decision is not misread as a generation
  defect. On the pinned run the agent is +11.0 pt in aggregate EX and +11.2 pt in EX@answered
  versus the retrieval baseline; that conditional difference is a single sample and has not
  been tested for significance.
- **Answer quality and abstention behaviour are orthogonal capabilities.** They require separate
  denominators and an action confusion matrix to be interpretable; a conservative policy is
  otherwise penalised by construction.
- **Instrument validity dominates scoring.** The initial harness-vs-baseline comparison
  (+20 pt) was an artefact of measurement: it was computed against a reference set with
  ungrounded literals, a temporal type defect and a protocol-induced answer bias. After repair
  and partition-aware scoring, the effect decomposes into +37.0 pt (retrieval) and +11.0 pt
  (harness above the retrieval baseline).
- **The reference collection protocol is a source of bias, not a neutral substrate.** An
  answer-only protocol forces a single interpretation onto every question and therefore rewards
  presumption; abstention correctness must be labelled independently of the system under test.
- **Observed deltas are not yet statistically identifiable.** The generation model is a
  mixture-of-experts and is not deterministic at zero temperature. Across the baseline runs of
  2026-09-24 / 10-10 / 10-11, `harness` EX@answered moved 58.8% → 59.1% → 59.7% and
  over-clarification 6.9% → 9.6% → 8.2%; an earlier prompt-wording change alone moved `direct`
  EX by ~7 pt. Single-sample deltas of this magnitude cannot support conclusions; paired
  repeated runs with a significance test are required.

### 4.3 Directions

1. **Calibrate the abstention threshold.** This is now the highest-leverage change: on the
   pinned run the agent is above the retrieval baseline on both metrics, so recovering coverage
   without increasing presumption translates directly into aggregate EX. The six over-clarified
   cases are concentrated in temporal-scope questions.
2. **Remove the sentinel-parsing contract** (`SQL_QUERY:`) from the generation stage; parse
   failures currently convert answerable cases into abstentions.
3. **Prompt simplification** — now a second-order concern, given the measured conditional
   advantage.
4. **Cost modelling.** Per-model token accounting and a dated price table are in place
   (`app/eval/pricing.py`); extend to an accuracy–cost frontier once prices are re-verified and
   consider a cheaper generation model, since the schema-only baseline is 2.6× cheaper.
5. **Statistical protocol.** Adopt repeated paired runs with a paired significance test and
   report confidence intervals.
6. **Guardrail axis.** The guardrail dimension is currently unmeasured: no adversarial stratum
   exists, and neither non-`SELECT` output nor database-level rejection occurred in any run.
   An adversarial safety stratum is required before this axis can be reported.

### 4.4 Threats to validity

- **Small strata.** The `easy` stratum contains 3 cases and the `clarify` partition 3; rates
  over these partitions are not stable.
- **Single-sample estimates.** All figures derive from one run per system.
- **Reference-set provenance.** The reference queries were model-generated and subsequently
  repaired; residual ungrounded or ill-posed items may remain undetected by the audit.
- **External validity.** The database comprises 360 rows over a six-day window; conclusions
  about temporal constructs do not transfer to datasets with wider temporal coverage.

---

## Appendix — reproducibility

```bash
python -m pytest tests/eval -q                              # unit tests (no DB, no LLM)
python scripts/audit_golden.py                              # reference-set audit (read-only)
python scripts/build_golden_dataset.py --report tests/eval/build_report.json
python -m app.eval.runner --system oracle
python -m app.eval.runner --system direct
PYTHONNOUSERSITE=1 python -m app.eval.runner --system direct+rag
PYTHONNOUSERSITE=1 python -m app.eval.runner --system harness
python scripts/build_eval_dashboard.py                      # results-vis.html
```

Reports may be regenerated from a raw dump without re-running inference:
`python -m app.eval.reporter <system>-<ts>.raw.jsonl`.
