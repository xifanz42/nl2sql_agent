"""execute_query bounds rows only when max_rows is provided (Phase 1.5)."""

from contextlib import contextmanager

from app.core.database import DataBase


class FakeMappings:
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)

    def fetchmany(self, size):
        return self.rows[:size]


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return FakeMappings(self.rows)


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.execution_options_kwargs = {}

    def execution_options(self, **kwargs):
        self.execution_options_kwargs.update(kwargs)
        return self

    def execute(self, statement):
        if str(statement).startswith("SET"):
            return None
        return FakeResult(self.rows)


class FakeEngine:
    def __init__(self, rows):
        self.rows = rows
        self.connection = None

    @contextmanager
    def begin(self):
        self.connection = FakeConnection(self.rows)
        yield self.connection


def _db(rows):
    db = DataBase.__new__(DataBase)
    db.engine = FakeEngine(rows)
    return db


def test_max_rows_uses_fetchmany_and_marks_truncated():
    db = _db([{"n": i} for i in range(5)])

    result = db.execute_query("SELECT n", max_rows=3)

    assert result.executed is True
    assert result.result == [{"n": 0}, {"n": 1}, {"n": 2}]
    assert result.truncated is True
    assert db.engine.connection.execution_options_kwargs == {"stream_results": True}


def test_without_max_rows_keeps_full_result():
    db = _db([{"n": i} for i in range(5)])

    result = db.execute_query("SELECT n")

    assert result.executed is True
    assert len(result.result) == 5
    assert result.truncated is False
    assert db.engine.connection.execution_options_kwargs == {}
