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

## Metrics (`app/eval/metrics.py`)

| metric | definition |
|---|---|
| `valid_sql` | predicted SQL executed without a DB error |
| `exact_match` (EM) | normalized string equality with the golden SQL |
| `execution_match` (EX) | result sets equal as multisets — the primary metric |
| `schema_adherence` | referenced tables exist in the schema (sqlglot; CTE names excluded) |
| `safety_pass` | safety cases: blocked; otherwise: single SELECT/UNION |
| `clarification_correct` | clarification cases must ask; others must not |

## Output

Each run writes:

- `eval_results/<system>-<ts>.md` — aggregates overall and by difficulty, plus
  failed case ids. Public, safe to commit.
- `eval_results/<system>-<ts>.raw.jsonl` — per-case question, SQL, rows, tokens,
  latency. Private, gitignored.

`<ts>` is the UTC run timestamp (`YYYYMMDDTHHMMSSZ`).

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
