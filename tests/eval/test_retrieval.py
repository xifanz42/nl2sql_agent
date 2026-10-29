from app.eval.retrieval import evidence_for, score_retrieval
from app.models.eval import EvalCase


def test_score_retrieval_hit_recall_and_rank():
    score = score_retrieval([("a", 0), ("b", 0)], {("b", 0), ("c", 0)})
    assert score is not None
    assert score.hit is True
    assert score.recall == 0.5
    assert score.reciprocal_rank == 0.5


def test_score_retrieval_miss():
    score = score_retrieval([("a", 0)], {("b", 0)})
    assert score is not None
    assert score.hit is False
    assert score.reciprocal_rank == 0.0


def test_score_retrieval_unlabeled():
    assert score_retrieval([("a", 0)], set()) is None


def test_evidence_from_tags_columns_and_literals():
    case = EvalCase(
        id="x",
        question="查询2025-08-16日AT003的总停车时间",
        golden_sql=(
            "SELECT sum(index_value) FROM kpi_benchmark "
            "WHERE record_date::date = '2025-08-16' "
            "AND vehicle_id = 'AT003' AND index_category = '停车'"
        ),
        difficulty="medium",
        tags=["cat:停车", "date:2025-08-16"],
    )

    evidence = evidence_for(case)
    assert "停车" in evidence
    assert "record_date" in evidence
    assert "vehicle_id" in evidence
    assert "at003" in evidence


def test_specific_evidence_excludes_generic_columns():
    case = EvalCase(
        id="x",
        question="查询2025-08-16日AT003的总停车时间",
        golden_sql=(
            "SELECT sum(index_value) FROM kpi_benchmark "
            "WHERE record_date::date = '2025-08-16' "
            "AND vehicle_id = 'AT003' AND index_category = '停车'"
        ),
        difficulty="medium",
        tags=["cat:停车", "date:2025-08-16"],
    )

    evidence = evidence_for(case, include_columns=False)
    assert "停车" in evidence
    assert "record_date" in evidence
    assert "index_value" not in evidence
    assert "index_category" not in evidence
