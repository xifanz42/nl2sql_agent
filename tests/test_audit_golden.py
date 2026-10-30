"""Errors loading the golden whitelist must be loud, never an empty set."""

import pytest

from app.models.sql import SQLResult
from scripts.audit_golden import COLUMNS, load_whitelist


class FakeDB:
    def __init__(self, executed=True, error=None):
        self.executed = executed
        self.error = error

    def execute_query(self, sql):
        column = sql.split("DISTINCT ", 1)[1].split(" ", 1)[0]
        return SQLResult(
            sql=sql,
            executed=self.executed,
            result=[{column: "a"}, {column: "b"}] if self.executed else None,
            error=self.error,
            execution_time_ms=0.0,
        )


def test_load_whitelist_reads_sqlresult():
    whitelist = load_whitelist(FakeDB())

    assert whitelist == {column: {"a", "b"} for column in COLUMNS}


def test_load_whitelist_raises_on_failure():
    with pytest.raises(RuntimeError, match="boom"):
        load_whitelist(FakeDB(executed=False, error="boom"))
