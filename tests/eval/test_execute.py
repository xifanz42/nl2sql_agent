from app.eval.execute import ExpectedResultCache, run_sql
from app.eval.metrics import execution_match
from app.models.sql import SQLResult


class FakeDB:
    """Structural match for execute.QueryExecutor — no live DB needed."""

    def __init__(self, outcome):
        self.outcome = outcome

    def execute_query(self, sql):
        return self.outcome


def _result(**overrides):
    fields = {
        "sql": "SELECT 1",
        "executed": True,
        "result": None,
        "error": None,
        "execution_time_ms": 12.5,
    }
    fields.update(overrides)
    return SQLResult(**fields)


def test_run_sql_returns_sqlresult_unchanged():
    outcome = _result(result=[{"n": 1}])
    assert run_sql(FakeDB(outcome), "SELECT 1") is outcome


def test_run_sql_corrects_sql_field():
    outcome = _result(sql="SELECT 2")
    assert run_sql(FakeDB(outcome), "SELECT 1").sql == "SELECT 1"


def test_run_sql_preserves_execution_time():
    outcome = _result(execution_time_ms=12.5)
    assert run_sql(FakeDB(outcome), "SELECT 1").execution_time_ms == 12.5


def test_run_sql_wraps_legacy_error():
    result = run_sql(FakeDB({"error": "boom"}), "SELECT 1")
    assert isinstance(result, SQLResult)
    assert result.executed is False and result.error == "boom"


def test_run_sql_wraps_legacy_rows():
    result = run_sql(FakeDB([{"n": 1}]), "SELECT 1")
    assert result.executed is True and result.result == [{"n": 1}]


def test_cache_compute_or_get_reads_sqlresult(tmp_path):
    cache = ExpectedResultCache(tmp_path / "expected.jsonl")
    db = FakeDB(_result(result=[{"n": 1}]))
    assert cache.compute_or_get("q1", "SELECT 1", db) == [(1,)]


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
