#!/usr/bin/env python3
"""Clean ``sample_querys_2.csv`` -> ``golden_dataset.jsonl`` (spec Week 1 Day 2).

Turns the human-curated NL→SQL pairs into a machine-readable golden dataset:
  1. Normalize SQL (strip BOM, trailing ``;``, collapse newlines/whitespace).
  2. Classify difficulty (easy / medium / hard) from SQL features.
  3. Extract tags (category, vehicle type, date, aggregation, etc.).
  4. Validate every SQL with sqlglot (postgres dialect) when available.
  5. Apply curated fixes for known-broken golden SQL (flagged for review).
  6. Emit one JSON object per line conforming to ``app.models.eval.EvalCase``.

Usage:
    python scripts/build_golden_dataset.py
    python scripts/build_golden_dataset.py \
        --source data/sample_querys_2.csv \
        --output tests/eval/golden_dataset.jsonl \
        --report tests/eval/build_report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Make the project root importable so we can validate against the real EvalCase.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from sqlglot import parse_one
    from sqlglot.errors import SqlglotError

    _HAVE_SQLGLOT = True
except Exception:  # pragma: no cover - optional dependency
    _HAVE_SQLGLOT = False

try:
    from app.models.eval import EvalCase

    _HAVE_EVALCASE = True
except Exception:  # pragma: no cover - optional until app imports resolve
    _HAVE_EVALCASE = False


# Known-broken golden SQL. Corrected versions are proposed here but MUST be
# verified by a human (see cleaning report). Keyed by source row ``id``.
MANUAL_FIXES: dict[str, str] = {
    "44": (
        "SELECT vehicle_id, record_date, "
        "MAX(CASE WHEN index_name = '上下岸桥距离' THEN index_value END) - "
        "MAX(CASE WHEN index_name = '堆场内行驶距离' THEN index_value END) AS distance_diff "
        "FROM kpi_benchmark "
        "WHERE index_name IN ('上下岸桥距离', '堆场内行驶距离') "
        "GROUP BY vehicle_id, record_date "
        "ORDER BY vehicle_id, record_date;"
    ),
}

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_AGG_RE = re.compile(r"(?i)\b(SUM|AVG|MAX|MIN|COUNT|STDDEV|PERCENTILE)\b")


def clean_sql(raw: str) -> str:
    """Normalize SQL: drop trailing semicolon, collapse whitespace/newlines.

    Why: the source CSV has multi-line SQL (rows 44-48) and stray ``;`` that
    break one-line parsing and diffing.
    """
    sql = raw.replace("\r", " ").replace("\n", " ")
    sql = re.sub(r"\s+", " ", sql).strip()
    return sql.rstrip(";").strip()


def classify_difficulty(sql: str) -> str:
    """Heuristic difficulty from SQL features (spec §9 Week 1 Day 2).

    hard   = subquery / JOIN / window(FILTER,OVER,WITHIN GROUP,percentile) /
             HAVING / STDDEV / date math(CURRENT_DATE,INTERVAL,EXTRACT) / CASE / UNION
    medium = GROUP BY / ORDER BY / LIMIT / BETWEEN / LIKE / DISTINCT / IN(...) / multi-condition
    easy   = single-table equality filter only
    """
    s = sql.upper()
    hard_signals = [
        " JOIN ",
        " OVER ",
        "WITHIN GROUP",
        "FILTER (WHERE",
        "STDDEV",
        "PERCENTILE",
        "CURRENT_DATE",
        "EXTRACT(",
        "INTERVAL",
        "CASE WHEN",
        "UNION",
        "HAVING",
    ]
    if any(k in s for k in hard_signals):
        return "hard"
    # Nested subquery => more than one SELECT.
    if s.count("SELECT") > 1:
        return "hard"
    medium_signals = [
        "GROUP BY",
        " ORDER BY",
        " LIMIT",
        " BETWEEN",
        " LIKE",
        " DISTINCT",
        " IN (",
    ]
    if any(k in s for k in medium_signals):
        return "medium"
    if s.count(" AND ") + s.count(" OR ") >= 1:
        return "medium"
    return "easy"


def extract_tags(sql: str) -> list[str]:
    """Extract descriptive tags used by per-tag metrics (spec §4.3.2)."""
    tags: list[str] = []
    for cat in ("行驶距离", "导航速度", "停车"):
        if cat in sql:
            tags.append(f"cat:{cat}")
    if "vehicle_type = 'AT'" in sql or "LIKE 'AT%" in sql:
        tags.append("type:AT")
    if "vehicle_type = 'MT'" in sql or "LIKE 'MT%" in sql:
        tags.append("type:MT")
    if _AGG_RE.search(sql):
        tags.append("agg")
    for d in _DATE_RE.findall(sql):
        tags.append(f"date:{d}")
    s = sql.upper()
    for kw, tag in (
        ("GROUP BY", "group_by"),
        ("HAVING", "having"),
        ("ORDER BY", "order"),
        ("LIMIT", "limit"),
        (" JOIN ", "join"),
        ("FILTER (WHERE", "filter"),
        ("DISTINCT", "distinct"),
    ):
        if kw in s:
            tags.append(tag)
    if "EXTRACT(" in s or "INTERVAL" in s:
        tags.append("datetime")
    if s.count("SELECT") > 1:
        tags.append("subquery")
    return sorted(set(tags))


def validate_sql(sql: str) -> bool:
    """Return True if sqlglot can parse the SQL as Postgres."""
    if not _HAVE_SQLGLOT:
        return True
    try:
        parse_one(sql, read="postgres")
        return True
    except SqlglotError:
        return False
    except Exception:  # pragma: no cover - defensive
        return False


def build(source: Path, output: Path) -> dict:
    """Run the cleaning pipeline and return a summary report dict."""
    cases: list[dict] = []
    report: dict = {
        "source": str(source),
        "total": 0,
        "by_difficulty": Counter(),
        "parse_failures": [],
        "applied_fixes": [],
        "notes": [],
    }

    with source.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row["id"].strip()
            question = row["user_input"].strip()
            golden = clean_sql(row["sql_query"])

            if cid in MANUAL_FIXES:
                golden = clean_sql(MANUAL_FIXES[cid])
                report["applied_fixes"].append(
                    {
                        "id": cid,
                        "reason": "original SQL not valid Postgres; replaced with a "
                        "corrected version — NEEDS HUMAN REVIEW",
                    }
                )

            difficulty = classify_difficulty(golden)
            tags = extract_tags(golden)
            if not validate_sql(golden):
                report["parse_failures"].append({"id": cid, "sql": golden})

            case = {
                "id": cid,
                "question": question,
                "golden_sql": golden,
                "expected_result": None,
                "difficulty": difficulty,
                "tags": tags,
                "requires_clarification": False,
            }
            if _HAVE_EVALCASE:
                EvalCase(**case)  # raise early on schema mismatch
            cases.append(case)
            report["by_difficulty"][difficulty] += 1

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    report["total"] = len(cases)
    report["by_difficulty"] = dict(report["by_difficulty"])
    if not _HAVE_SQLGLOT:
        report["notes"].append("sqlglot not installed; parse validation skipped")
    if not _HAVE_EVALCASE:
        report["notes"].append("app.models.eval.EvalCase not importable; schema not validated")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build golden dataset jsonl from CSV")
    parser.add_argument("--source", default="data/sample_querys_2.csv", type=Path)
    parser.add_argument("--output", default="tests/eval/golden_dataset.jsonl", type=Path)
    parser.add_argument(
        "--report",
        default=None,
        type=Path,
        help="optional path to write the cleaning report as JSON",
    )
    args = parser.parse_args()

    if not args.source.exists():
        print(f"❌ Source not found: {args.source}", file=sys.stderr)
        return 1

    report = build(args.source, args.output)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ Wrote {report['total']} cases -> {args.output}")
    print("   Difficulty distribution:", report["by_difficulty"])
    if report["applied_fixes"]:
        print("⚠️  Applied manual fixes (NEEDS HUMAN REVIEW):")
        for fx in report["applied_fixes"]:
            print(f"   - id={fx['id']}: {fx['reason']}")
    if report["parse_failures"]:
        print("❌ Parse failures remaining:")
        for pf in report["parse_failures"]:
            print(f"   - id={pf['id']}: {pf['sql'][:80]}")
    for note in report.get("notes", []):
        print(f"ℹ️  {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
