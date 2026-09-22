#!/usr/bin/env python3
"""Audit the golden set against the live database (read-only).

Classifies cases by why they may not be answerable as written:

  unknown-value        golden references a value absent from the DB -> cannot answer
                       (option A: the correct behaviour is to NOT fabricate)
  relative-date        question depends on "now" (CURRENT_DATE/NOW) while the data
                       is historical -> cannot answer with the current data
  date-literal-format  compares `record_date` (a text column of `...T00:00:00Z`)
                       against a bare `'YYYY-MM-DD'` literal -> golden SQL bug
  empty-result         executes but returns no rows -> review
  all-null             returns rows whose values are all NULL (vacuous aggregate)

Usage:
    python scripts/audit_golden.py
    python scripts/audit_golden.py --json eval_results/golden_audit.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.core.database import ReadOnlyDataBase  # noqa: E402
from app.eval.execute import run_sql  # noqa: E402

GOLDEN = REPO_ROOT / "tests" / "eval" / "golden_dataset.jsonl"
COLUMNS = ("index_category", "index_name", "vehicle_type")

_ASSIGN = re.compile(r"(index_category|index_name|vehicle_type)\s*=\s*'([^']+)'")
_IN = re.compile(r"(index_category|index_name|vehicle_type)\s+IN\s*\(([^)]*)\)", re.I)
_LIKE = re.compile(r"(index_name)\s+LIKE\s+'([^']+)'", re.I)
_DATE_BARE = re.compile(r"record_date\s*(?:=|>=|<=|>|<|BETWEEN)\s*'\d{4}-\d{2}-\d{2}'", re.I)
_RELATIVE = re.compile(r"\b(CURRENT_DATE|CURRENT_TIMESTAMP|NOW\s*\(\))", re.I)

CANNOT_ANSWER = ("unknown-value", "relative-date")


def load_whitelist(db: ReadOnlyDataBase) -> dict[str, set[str]]:
    whitelist: dict[str, set[str]] = {}
    for column in COLUMNS:
        rows = db.execute_query(f"SELECT DISTINCT {column} FROM kpi_benchmark")
        whitelist[column] = {r[column] for r in rows} if isinstance(rows, list) else set()
    return whitelist


def _like_to_regex(pattern: str) -> re.Pattern:
    # re.escape does NOT escape '%' or '_' on py>=3.7, so a plain replace is right.
    body = re.escape(pattern).replace("%", ".*").replace("_", ".")
    return re.compile("^" + body + "$")


def check_sql(sql: str, whitelist: dict[str, set[str]]) -> list[str]:
    reasons: list[str] = []

    used: dict[str, list[str]] = {}
    for match in _ASSIGN.finditer(sql):
        used.setdefault(match.group(1), []).append(match.group(2))
    for match in _IN.finditer(sql):
        used.setdefault(match.group(1), []).extend(re.findall(r"'([^']+)'", match.group(2)))

    for column, literals in used.items():
        missing = sorted({v for v in literals if v not in whitelist[column]})
        if missing:
            reasons.append(f"unknown-value: {column}={', '.join(missing)}")

    for match in _LIKE.finditer(sql):
        pattern = match.group(2)
        if pattern in whitelist["index_name"]:
            continue
        regex = _like_to_regex(pattern)
        if not any(regex.match(value) for value in whitelist["index_name"]):
            reasons.append(f"unknown-value: index_name LIKE {pattern}")

    if _RELATIVE.search(sql):
        reasons.append("relative-date")
    if _DATE_BARE.search(sql):
        reasons.append("date-literal-format")
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, default=GOLDEN)
    parser.add_argument("--json", type=Path, default=None, help="write the audit as JSON")
    args = parser.parse_args()

    cases = [
        json.loads(line)
        for line in args.golden.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    db = ReadOnlyDataBase()
    whitelist = load_whitelist(db)
    print("DB value whitelist:")
    for column in COLUMNS:
        print(f"  {column}: {len(whitelist[column])} values")

    audit: dict[str, list[str]] = {}
    sql_cases = [c for c in cases if not c.get("requires_clarification")]
    for case in sql_cases:
        reasons = check_sql(case["golden_sql"], whitelist)
        result = run_sql(db, case["golden_sql"])
        if not result.executed:
            reasons.append("golden-error")
        elif not result.result:
            reasons.append("empty-result")
        elif all(value is None for row in result.result for value in row.values()):
            reasons.append("all-null")
        if reasons:
            audit[case["id"]] = reasons

    by_category: dict[str, list[str]] = defaultdict(list)
    for case_id, reasons in audit.items():
        for reason in reasons:
            by_category[reason.split(":")[0]].append(case_id)

    for category in sorted(by_category):
        ids = sorted(set(by_category[category]), key=int)
        tag = "CANNOT ANSWER" if category in CANNOT_ANSWER else "review"
        print(f"\n[{tag}] {category}: {len(ids)} cases")
        print("  " + ", ".join(ids))

    cannot = sorted({cid for cid, rs in audit.items() if any(r.split(":")[0] in CANNOT_ANSWER for r in rs)}, key=int)
    print(
        f"\naudited {len(sql_cases)} SQL cases "
        f"({len(cases) - len(sql_cases)} clarification cases skipped) -> "
        f"{len(audit)} flagged, of which {len(cannot)} cannot be answered:"
    )
    print("  " + ", ".join(cannot))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
