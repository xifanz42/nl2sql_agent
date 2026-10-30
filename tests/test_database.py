"""Unit tests for the execute_query contract without a live database."""

from app.core.database import DataBase


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self._rows


class _Connection:
    def __init__(self, log, fail):
        self.log = log
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement):
        sql = str(statement)
        self.log.append(sql)
        if sql.startswith("SET"):
            return _Result([])
        if self.fail:
            raise RuntimeError("boom")
        return _Result([{"n": 1}])


class _Engine:
    def __init__(self, log, fail=False):
        self.log = log
        self.fail = fail

    def begin(self):
        return _Connection(self.log, self.fail)


def _database(fail=False):
    log: list[str] = []
    db = DataBase.__new__(DataBase)
    db.engine = _Engine(log, fail)
    return db, log


def test_success_returns_executed_sqlresult():
    db, log = _database()

    result = db.execute_query("SELECT 1")

    assert result.executed is True
    assert result.result == [{"n": 1}]
    assert result.error is None
    assert result.sql == "SELECT 1"
    assert result.execution_time_ms >= 0


def test_guard_statements_run_before_user_query():
    db, log = _database()

    db.execute_query("SELECT 1")

    assert log == [
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = '15s'",
        "SELECT 1",
    ]


def test_failure_returns_unexecuted_sqlresult():
    db, _ = _database(fail=True)

    result = db.execute_query("SELECT 1")

    assert result.executed is False
    assert result.error == "boom"
    assert result.result is None
    assert result.sql == "SELECT 1"
