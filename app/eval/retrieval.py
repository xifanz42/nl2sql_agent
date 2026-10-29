"""Retrieval-side metrics.

End-to-end EX cannot tell whether retrieval surfaced the right chunk. These
helpers build *weak* relevance labels from the golden SQL and score the
retriever on its own: a chunk is relevant if it contains a string the query
needs (a metric name, a category, a column, a literal).

This is a screening metric, not ground truth. Report the unlabeled count with
it; do not read a 1.0 as "retrieval is perfect".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from app.models.eval import EvalCase


def _columns_and_literals(sql: str) -> tuple[set[str], set[str]]:
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:
        return set(), set()

    columns = {column.name for column in tree.find_all(exp.Column) if column.name}
    literals = {
        str(literal.this)
        for literal in tree.find_all(exp.Literal)
        if literal.is_string and literal.this is not None
    }
    return columns, literals


def _tag_evidence(tags: list[str]) -> set[str]:
    evidence = set()
    for tag in tags:
        if tag.startswith(("cat:", "type:")):
            evidence.add(tag.split(":", 1)[1])
        elif tag.startswith("date:"):
            # The docs define the column, not every date value.
            evidence.add("record_date")
    return evidence


def evidence_for(case: EvalCase, *, include_columns: bool = True) -> set[str]:
    """Strings a useful context should contain for this case.

    ``include_columns=False`` keeps only *specific* evidence (metric values,
    categories, vehicle types/ids, dates). Column names are broad — almost every
    chunk mentions ``index_value`` — so the caller should try specific evidence
    first and fall back to columns only when it matches no chunk.
    """
    columns, literals = _columns_and_literals(case.golden_sql)
    evidence = _tag_evidence(case.tags) | literals
    if include_columns:
        evidence |= columns

    # A concrete vehicle id is evidence that the vehicle_id column is needed.
    if any(re.fullmatch(r"[AM]T\d+", item) for item in evidence):
        evidence.add("vehicle_id")

    return {item.lower() for item in evidence if item}


@dataclass(frozen=True)
class RetrievalScore:
    hit: bool
    recall: float
    reciprocal_rank: float
    relevant: int
    retrieved: int


def score_retrieval(
    retrieved: list[tuple[str, int]], relevant: set[tuple[str, int]]
) -> RetrievalScore | None:
    """Score one retrieved chunk-id list against weakly labeled relevant ids."""
    if not relevant:
        return None

    retrieved_set = set(retrieved)
    hits = retrieved_set & relevant
    first_rank = next(
        (rank for rank, chunk in enumerate(retrieved, start=1) if chunk in relevant),
        0,
    )

    return RetrievalScore(
        hit=bool(hits),
        recall=len(hits) / len(relevant),
        reciprocal_rank=1.0 / first_rank if first_rank else 0.0,
        relevant=len(relevant),
        retrieved=len(retrieved_set),
    )
