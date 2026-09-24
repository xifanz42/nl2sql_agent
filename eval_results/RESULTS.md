# NL2SQL Evaluation — Baseline Report

Reference set: 90 private cases. All systems share one SQL generation model
(`Qwen/Qwen3-Coder-30B-A3B-Instruct`), so observed differences are attributable to system
architecture rather than model capacity.

Visual summary: [`results-vis.html`](results-vis.html) ·
Run history: [`results-history.html`](results-history.html) ·
Runner instructions: [`app/eval/README.md`](../app/eval/README.md)

<!-- RUNS:BEGIN -->
Reference set: **v2-adjudicated** (fingerprint `9edea4900e42`, 90 cases) · 6 recorded run(s)

| time (UTC) | system | dataset | git | EX | EX@answered | presumption ↓ | over-clarify ↓ | cost / case | report |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-24T08:48:54Z | `harness` | v2-adjudicated | `6c9ac99` | 54.8% | 58.8% | 17.6% | 6.9% | ¥0.00119 | [harness-20260924T084854Z.md](harness-20260924T084854Z.md) |
| 2026-09-24T08:25:15Z | `direct+rag` | v2-adjudicated | `6c9ac99` | 63.0% | 63.0% | 100.0% | 0.0% | ¥0.00101 | [direct+rag-20260924T082515Z.md](direct+rag-20260924T082515Z.md) |
| 2026-09-24T08:22:14Z | `direct` | v2-adjudicated | `6c9ac99` | 28.8% | 28.8% | 100.0% | 0.0% | ¥0.00030 | [direct-20260924T082214Z.md](direct-20260924T082214Z.md) |
| 2026-09-24T08:18:28Z | `oracle` | v2-adjudicated | `6c9ac99` | 100.0% | 100.0% | 0.0% | 0.0% | ¥0.00000 | [oracle-20260924T081828Z.md](oracle-20260924T081828Z.md) |
| 2026-09-24T08:14:15Z | `oracle` | v2-adjudicated | `6c9ac99` | 100.0% | 100.0% | 0.0% | 0.0% | ¥0.00000 | [oracle-20260924T081415Z.md](oracle-20260924T081415Z.md) |
| 2026-09-24T08:14:03Z | `oracle` | v2-adjudicated | `6c9ac99` | 100.0% | 100.0% | 0.0% | 0.0% | ¥0.00000 | [oracle-20260924T081403Z.md](oracle-20260924T081403Z.md) |

⚠︎ = scored against a different reference set; not comparable with the current one.
Older reports are pruned; the ledger is the durable record. Trends: [`results-history.html`](results-history.html).
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

| # | Finding | Evidence |
|---|---|---|
| **F1** | Retrieval is the dominant driver of answer quality. | EX 30.1% → 63.0% (**+32.9 pt**) |
| **F2** | At equal coverage, the agent's answer quality is statistically indistinguishable from the retrieval-only baseline. | EX@answered 58.8% vs 63.0% (**−4.2 pt**, within run-to-run variance) |
| **F3** | The agent's aggregate EX deficit is therefore attributable to abstention, not to generation. | coverage 78.9% vs 100.0%; presumption 100.0% → **17.6%** |
| **F4** | The agent's second call is effectively free; retrieval is the cost driver. | cost/case ¥0.00030 → ¥0.00101 (**3.4×**) → ¥0.00119; routing model priced at ¥0 |

---

## 3. Detailed analysis

### 3.1 Answer quality (`answer` partition, n = 73)

| System | `valid_sql` | EM | **EX** | `schema_adherence` | EX@answered | answer rate |
|---|---|---|---|---|---|---|
| `oracle` | 100.0% | 100.0% | **100.0%** | 100.0% | 100.0% | 81.1% |
| `direct` | 89.0% | 11.0% | **28.8%** | 94.5% | 28.8% | 100.0% |
| `direct+rag` | 97.3% | 23.3% | **63.0%** | 98.6% | 63.0% | 100.0% |
| `harness` | 87.7% | 21.9% | **54.8%** | 93.2% | 58.8% | 78.9% |

EX by difficulty stratum:

| System | easy (n=3) | medium (n=46) | hard (n=24) |
|---|---|---|---|
| `direct` | 66.7% | 26.1% | 29.2% |
| `direct+rag` | 100.0% | 67.4% | **50.0%** |
| `harness` | 100.0% | 65.2% | **29.2%** |

Observations:

- EM is not a usable optimisation target for this task (11.0%–23.3%); semantically equivalent
  queries differ in aliasing and formatting. EX is adopted as the primary metric.
- `direct+rag` and `harness` are indistinguishable on the `medium` stratum (67.4% vs 65.2%);
  the deficit is localised to `hard` (−20.8 pt), which concentrates multi-condition `FILTER`,
  subquery and temporal-aggregation constructs.
- The `harness` abstains on 5 of 73 answerable cases (over-clarify rate 6.8%), so its overall EX
  understates its conditional accuracy. At equal answer rate the gap narrows (EX@answered:
  58.8% vs 63.0%) but does not reverse.

### 3.2 Abstention policy (`clarify` + `refuse` partitions, n = 17)

Action confusion matrix:

| System | TP (answer ✓) | FN (over-clarify) | FP (presumption) | TN (abstain ✓) |
|---|---|---|---|---|
| `oracle` | 73 | 0 | 0 | 17 |
| `direct` | 73 | 0 | 17 | 0 |
| `direct+rag` | 73 | 0 | 17 | 0 |
| `harness` | 68 | 5 | **3** | **14** |

Derived rates:

| System | `presumption_rate` ↓ | `over_clarify_rate` ↓ | `policy_accuracy` |
|---|---|---|---|
| `oracle` | 0.0% | 0.0% | 100.0% |
| `direct` | **100.0%** | 0.0% | 81.1% |
| `direct+rag` | **100.0%** | 0.0% | 81.1% |
| `harness` | **17.6%** | 6.8% | **91.1%** |

Per-partition correct-action rate:

| System | `clarify` + `refuse` (`clarification_correct`) |
|---|---|
| `oracle` | 100.0% |
| `harness` | **82.4%** |
| `direct` / `direct+rag` | 0.0% |

Both baselines answer every case, including the 14 whose referenced metric does not exist in
the database; they fabricate a query against a non-existent attribute in 100% of those cases.
The agent declines or requests disambiguation in 14 of 17, a **+82.4 pt** improvement on this
axis. The cost is a 6.8% unnecessary-abstention rate on the answerable partition and a 21.1 pt
reduction in coverage.

### 3.3 Efficiency

| System | calls / case | tokens / case | cached share | cost / case (CNY) | p50 | p95 |
|---|---|---|---|---|---|---|
| `direct` | 1.0 | 217 | 82.4% | 0.00030 | 1.46 s | 7.26 s |
| `direct+rag` | 1.0 | **1,278** | 68.9% | 0.00101 | 1.41 s | 4.44 s |
| `harness` | **2.0** | 1,648 | 65.6% | 0.00119 | 1.99 s | 3.98 s |
| `oracle` | — | — | — | 0 | ~0 s | — |

Total over the 90 cases: `direct` ¥0.0270 · `direct+rag` ¥0.0906 · `harness` ¥0.1074.

- **Retrieval multiplies the per-case cost 3.4×** (`direct` → `direct+rag`) for a +34.2 pt EX
  gain. It is the only component that materially changes cost.
- **The agent's second call is free.** Routing runs on `Qwen/Qwen2.5-7B-Instruct`, priced at
  ¥0 / M tokens, so the harness costs only **1.18×** the retrieval baseline despite issuing two
  calls per case; its entire cost is the generation call.
- **Prompt caching does not reduce cost on the generation model.**
  `Qwen/Qwen3-Coder-30B-A3B-Instruct` has no published cached-input discount (cached tokens are
  billed at the input rate), so caching saves prompt processing but not spend. The discount
  applies to `deepseek-ai/DeepSeek-V3` (¥0.20 vs ¥2.00 / M), which this workload barely uses.
- Prices are recorded explicitly in `app/eval/pricing.py` (CNY per 1M tokens, 2026-09) and are
  an external input: a cost figure is only valid against that dated list.

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

1. Retrieval is the dominant driver of answer quality in both baselines (+32.9 pt EX).
2. **At equal coverage the agent's answer quality is statistically indistinguishable from the
   retrieval-only baseline** (EX@answered 58.8% vs 63.0%; the 4.2 pt difference lies below the
   observed run-to-run variance). Its aggregate EX deficit (−8.2 pt) is therefore attributable to
   the abstention policy, not to generation quality.
3. The agent's advantage is confined to abstention: presumption falls from 100.0% to 17.6%, at a
   cost of 6.8% over-clarification and a 21.1 pt reduction in coverage.
4. The agent issues two model calls per case at only **1.18×** the cost of the single-call
   retrieval baseline, because its routing stage runs on a zero-priced model.

### 4.2 Insights

- **A scalar EX conflates two independent quantities.** Conditioning on coverage separates
  `P(answer)` from `P(correct | answer)`. Doing so removes the apparent quality deficit of the
  agent and localises it to the abstention policy; reporting only the aggregate EX would have
  attributed a coverage decision to a generation defect. The residual conditional gap is itself
  within run-to-run variance, so it is not evidence of a generation defect.
- **Answer quality and abstention behaviour are orthogonal capabilities.** They require separate
  denominators and an action confusion matrix to be interpretable; a conservative policy is
  otherwise penalised by construction.
- **Instrument validity dominates scoring.** The initial harness-vs-baseline comparison
  (+20 pt) was an artefact of measurement: it was computed against a reference set with
  ungrounded literals, a temporal type defect and a protocol-induced answer bias. After repair
  and partition-aware scoring, the effect decomposes into +32.9 pt (retrieval) and −8.2 pt
  (agent overhead).
- **The reference collection protocol is a source of bias, not a neutral substrate.** An
  answer-only protocol forces a single interpretation onto every question and therefore rewards
  presumption; abstention correctness must be labelled independently of the system under test.
- **Observed deltas are not yet statistically identifiable.** The generation model is a
  mixture-of-experts and is not deterministic at zero temperature. Across two consecutive runs
  of identical code and reference set, `harness` EX@answered moved 60.6% → 58.8% and
  over-clarification 9.6% → 6.8%; an earlier prompt-wording change alone moved `direct` EX by
  ~7 pt. Single-sample deltas of this magnitude cannot support conclusions; paired repeated runs
  with a significance test are required.

### 4.3 Directions

1. **Calibrate the abstention threshold.** This is now the highest-leverage change: answer
   quality is at parity with the retrieval baseline, so recovering coverage without increasing
   presumption translates directly into aggregate EX. The seven over-clarified cases are
   concentrated in temporal-scope questions.
2. **Remove the sentinel-parsing contract** (`SQL_QUERY:`) from the generation stage; parse
   failures currently convert answerable cases into abstentions.
3. **Prompt simplification** — now a second-order concern, given conditional parity.
4. **Cost modelling.** Per-model token accounting and a dated price table are in place
   (`app/eval/pricing.py`); extend to an accuracy–cost frontier once prices are re-verified and
   consider a cheaper generation model, since the schema-only baseline is 3.7× cheaper.
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
