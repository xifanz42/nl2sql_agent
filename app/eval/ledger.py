"""Append-only run ledger and dataset identity.

Design intent
-------------
Each evaluation run appends one JSON line to ``eval_results/runs.jsonl``. The
ledger is **public by design**: it contains aggregates and provenance only —
never questions, reference SQL or result rows. It makes three questions
answerable after the fact:

* *Did the metric move?* — ordered per-system history.
* *Was the move caused by code, data, model or noise?* — the record carries the
  git revision, a dataset fingerprint and the model list.
* *Is this number trustworthy?* — every aggregate traces to a recorded run.

The dataset fingerprint is a **truncated** SHA-256 plus a human-readable label.
It is used solely to decide whether two runs are comparable; it is deliberately
not a full digest, which would allow verifying a guessed dataset file.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import PROJECT_ROOT

LEDGER_PATH = PROJECT_ROOT / "eval_results" / "runs.jsonl"
DATASET_PATH = PROJECT_ROOT / "tests" / "eval" / "golden_dataset.jsonl"
DATASET_META_PATH = PROJECT_ROOT / "tests" / "eval" / "dataset_version.json"

HASH_CHARS = 12


@dataclass(frozen=True)
class DatasetIdentity:
    """Identity of the reference set a run was scored against."""

    label: str
    hash: str
    n: int

    def as_dict(self) -> dict[str, Any]:
        return {"label": self.label, "hash": self.hash, "n": self.n}


def dataset_identity(
    dataset_path: Path | None = None, meta_path: Path | None = None
) -> DatasetIdentity:
    """Fingerprint the reference set (truncated digest + declared label)."""
    path = dataset_path or DATASET_PATH
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()[:HASH_CHARS]
    label = digest

    meta_file = meta_path or DATASET_META_PATH
    if meta_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        label = meta.get("label") or digest

    n = sum(1 for line in raw.decode("utf-8").splitlines() if line.strip())
    return DatasetIdentity(label=label, hash=digest, n=n)


def git_revision() -> str:
    """Short git revision of the working tree, or ``"unknown"`` outside a repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001 - provenance must never break a run
        return "unknown"


def make_record(
    *,
    system: str,
    dataset: DatasetIdentity,
    models: list[str],
    metrics: dict[str, float],
    tokens: dict[str, float],
    cost_cny: dict[str, float],
    latency_ms: dict[str, float],
    report: str,
    notes: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "system": system,
        "git": git_revision(),
        "dataset": dataset.as_dict(),
        "models": models,
        "metrics": {k: round(float(v), 4) for k, v in metrics.items()},
        "tokens": {k: round(float(v), 2) for k, v in tokens.items()},
        "cost_cny": {k: round(float(v), 6) for k, v in cost_cny.items()},
        "latency_ms": {k: round(float(v), 1) for k, v in latency_ms.items()},
        "report": report,
    }
    if notes:
        record["notes"] = notes
    return record


def append_run(record: dict[str, Any], path: Path | None = None) -> None:
    target = path or LEDGER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_runs(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or LEDGER_PATH
    if not target.exists():
        return []
    runs = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if line.strip():
            runs.append(json.loads(line))
    return runs


def latest_per_system(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in runs:
        latest[record["system"]] = record
    return latest


def history_for(runs: list[dict[str, Any]], system: str) -> list[dict[str, Any]]:
    return [r for r in runs if r["system"] == system]


def is_comparable(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Two runs are comparable only when the reference set and models agree."""
    return a["dataset"]["hash"] == b["dataset"]["hash"] and a.get("models") == b.get("models")
