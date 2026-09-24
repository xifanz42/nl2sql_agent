"""Read-only execution, result canonicalization and the expected-result cache."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Protocol

from app.eval.metrics import canonical_rows
from app.models.sql import SQLResult


class QueryExecutor(Protocol):
    """Anything that can run SQL and return rows-or-error.

    Structural interface so tests can inject a fake without a live database;
    :class:`app.core.database.ReadOnlyDataBase` satisfies it in production.
    """

    def execute_query(self, sql: str) -> Any: ...


def run_sql(db: QueryExecutor, sql: str) -> SQLResult:
    """Run one statement through the read-only handle and wrap the outcome."""
    started = time.perf_counter()
    outcome = db.execute_query(sql)
    elapsed_ms = (time.perf_counter() - started) * 1000

    if isinstance(outcome, dict) and "error" in outcome:
        return SQLResult(
            sql=sql, executed=False, error=outcome["error"], execution_time_ms=elapsed_ms
        )
    return SQLResult(sql=sql, executed=True, result=outcome, execution_time_ms=elapsed_ms)


class ExpectedResultCache:
    """Private cache of golden-SQL result sets, keyed by case id.

    Golden execution is the expensive part (and the thing that mirrors the closed
    DB), so it lives in an ignored file and is computed at most once. The cache is
    keyed by the reference-set fingerprint: when the dataset changes, stale
    expectations are discarded instead of silently reused.
    """

    def __init__(self, path: Path, dataset_hash: str | None = None):
        self.path = path
        self.dataset_hash = dataset_hash
        self._rows: dict[str, list[tuple]] = {}
        self.discarded = False
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("_meta"):
                cached_hash = record.get("dataset_hash")
                if self.dataset_hash and cached_hash and cached_hash != self.dataset_hash:
                    self._rows = {}
                    self.discarded = True
                    return
                continue
            self._rows[record["id"]] = [tuple(row) for row in record["rows"]]

    def get(self, case_id: str) -> list[tuple] | None:
        return self._rows.get(case_id)

    def set(self, case_id: str, rows: list[tuple]) -> None:
        self._rows[case_id] = rows

    def compute_or_get(self, case_id: str, golden_sql: str, db: QueryExecutor) -> list[tuple]:
        """Return cached golden rows, executing (and caching) on first miss."""
        if case_id in self._rows:
            return self._rows[case_id]
        result = run_sql(db, golden_sql)
        rows = canonical_rows(result.result) if result.executed else []
        self._rows[case_id] = rows
        return rows

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps({"_meta": True, "dataset_hash": self.dataset_hash}) + "\n")
            for case_id, rows in self._rows.items():
                handle.write(json.dumps({"id": case_id, "rows": [list(r) for r in rows]}) + "\n")
