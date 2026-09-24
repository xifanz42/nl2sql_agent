# Eval harness

How to score an NL2SQL *system* against the golden set, on a read-only database,
and publish sanitized reports.

## Layout

| Path | Contents |
|---|---|
| `app/eval/` | harness code: `metrics`, `execute`, `systems`, `runner`, `reporter`, `paths` |
| `tests/eval/` | `test_*.py` unit tests; `golden_dataset.jsonl` and `expected_results.jsonl` (private) |
| `eval_results/` | reports: `<system>-<ts>.md` (public), `<system>-<ts>.raw.jsonl` (private) |

`golden_dataset.jsonl`, `expected_results.jsonl` and `*.raw.jsonl` are gitignored
because they mirror the closed-source database. The public `.md` holds only
aggregate metrics and case ids — never questions, golden SQL or rows.

## Run

```bash
python -m pytest tests/eval -q          # unit tests: no DB, no LLM

python -m app.eval.runner --system oracle
python -m app.eval.runner --system direct
python -m app.eval.runner --system harness
```

Flags: `--model NAME` (override for `direct`), `--limit N`, `--dataset PATH`,
`--expected-cache PATH`.

## Systems

| system | what it is |
|---|---|
| `oracle` | returns the golden SQL unchanged. Pipeline self-check / upper bound |
| `direct` | baseline: one LLM call with schema + question, no RAG, no guardrails |
| `harness` | the agent under test (`NL2SQLChatbot.generate_sql`) |

### Where the model is configured

`direct` uses, in order of precedence:

1. `--model NAME` on the command line;
2. otherwise `SILICON_FLOW_NL2SQL_MODEL` from `.env`, read by `app/config.py`
   (`Settings.nl2sql_model`) and surfaced as `SiliconFlowLLM.SILICON_FLOW_NL2SQL_MODEL`.

Set the model in `.env` for a reproducible default, or pass `--model` per run.
`oracle` calls no model.

### `direct` prompt (exact)

Schema text is `DataBase.extract_schema()` (tables, columns, types, PK/FK).
One message pair, `temperature=0.0`, `max_tokens=1024`:

```
system:
You are a PostgreSQL expert. Using ONLY the schema below, return a single
read-only SELECT statement that answers the question. Reply with the SQL only,
no explanation or markdown.

<schema>
```

```
user:
<the eval case question, verbatim>
```

The reply is parsed by `extract_sql()` (first `SELECT`/`WITH`, fences stripped)
and executed through `ReadOnlyDataBase`.

## Case contract

Every case declares `required_behavior`, the expected behaviour for that question:

| value | meaning | correct system output |
|---|---|---|
| `answer` | question is fully specified | a SQL answer |
| `clarify` | question is under-specified | a clarifying question |
| `refuse` | no valid SQL exists (e.g. the metric does not exist) | decline / say so |

Scores are reported per axis, never averaged across axes: SQL metrics apply only to
`answer` cases, clarification metrics to the rest. The reporter also emits a policy
confusion matrix (`presumption rate`, `over-clarify rate`, `policy accuracy`) so the
"asked when it should have answered" and "answered when it should have asked" trade-off
is visible instead of hidden inside a single score.

## Artifacts

Each run writes a **public, sanitized** report and a **private** raw dump:

- `eval_results/<system>-<ts>.md` — aggregates, strata, confusion matrix, cost. Public.
- `eval_results/<system>-<ts>.raw.jsonl` — per-case questions, SQL, rows, tokens. Private
  (gitignored).

`<ts>` is the UTC run timestamp (`YYYYMMDDTHHMMSSZ`). Only the latest report per system is
retained; the ledger carries the history.

Two generated views read the latest dump per system:

- `results-vis.html` — charts and the current state (`scripts/build_eval_dashboard.py`).
- `results-history.html` — metric trends across runs (`scripts/build_history_dashboard.py`).

The same script also rewrites the numeric blocks of `RESULTS.md` (between `<!-- NAME:BEGIN -->`
markers) so the markdown scoreboard cannot go stale.

### Run ledger

Every run appends one record to `eval_results/runs.jsonl`: timestamp, git revision, reference-set
identity, model list, metrics, tokens, cost and latency. The ledger is public by design —
aggregates and provenance only. It answers *did the metric move, and was that code, data, model
or noise?* Runs are comparable only when the reference-set fingerprint and the model list agree.

### Reference-set identity

`scripts/build_golden_dataset.py` writes `tests/eval/dataset_version.json` (private) with a
human-readable label and a **truncated** SHA-256 of the golden set. The expected-result cache is
keyed by that fingerprint, so a changed reference set can never silently reuse stale
expectations. Bump `DATASET_LABEL` in the build script whenever cases or labels change.

### Cost

Cost is derived from token counts and the dated price list in `app/eval/pricing.py`
(CNY per 1M tokens). Prices are external: a cost figure is only valid against that list.
Latency and call count do not enter cost.

## Metrics (`app/eval/metrics.py`)

| metric | definition |
|---|---|
| `valid_sql` | predicted SQL executed without a DB error |
| `exact_match` (EM) | normalized string equality with the golden SQL |
| `execution_match` (EX) | result sets equal as multisets — the primary metric |
| `schema_adherence` | referenced tables exist in the schema (sqlglot; CTE names excluded) |
| `safety_pass` | safety cases: blocked; otherwise: single SELECT/UNION |
| `clarification_correct` | clarification cases must ask; others must not |

## Adding a system

1. Add a class in `app/eval/systems.py` implementing `predict(case) -> Prediction`.
2. Register it in `runner.build_system()` and `runner.SYSTEMS`.

Runner, reporter and metrics stay unchanged.

## Data notes

- `record_date` is stored as `character varying`; date math needs an explicit
  `record_date::timestamp`. `scripts/build_golden_dataset.py` applies this cast
  automatically via `fix_temporal_casts()`.
- Build-time validation is syntactic (sqlglot) only. Run `--system oracle` to
  catch type/semantic errors before trusting a baseline.
