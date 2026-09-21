from app.core.database import ReadOnlyDataBase  # noqa: F401  (documents the real impl)
from app.eval.execute import ExpectedResultCache, run_sql
from app.eval.metrics import execution_match
from app.models.sql import SQLResult


class FakeDB:
    """Structural match for execute.QueryExecutor — no live DB needed."""

    def __init__(self, outcome):
        self.outcome = outcome

    def execute_query(self, sql):
        return self.outcome


def test_run_sql_wraps_error():
    result = run_sql(FakeDB({"error": "boom"}), "SELECT 1")
    assert isinstance(result, SQLResult)
    assert result.executed is False and result.error == "boom"


def test_run_sql_wraps_rows():
    result = run_sql(FakeDB([{"n": 1}]), "SELECT 1")
    assert result.executed is True and result.result == [{"n": 1}]


def test_cache_roundtrip(tmp_path):
    cache = ExpectedResultCache(tmp_path / "expected.jsonl")
    cache.set("q1", [(1,)])
    cache.save()
    assert ExpectedResultCache(tmp_path / "expected.jsonl").get("q1") == [(1,)]


def test_expected_result_cache_feeds_execution_match():
    """Regression: cached rows are tuples, not dicts — EX must not crash."""
    cached = [(1,), (2,)]  # what ExpectedResultCache.compute_or_get returns
    live = [{"n": 2}, {"n": 1}]
    assert execution_match(live, cached)
