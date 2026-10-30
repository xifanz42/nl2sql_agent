"""Live checks that generated SQL cannot write, whatever handle executes it.

Skipped unless ``NL2SQL_LIVE_DB=1`` so the default suite stays DB-free. The
import is deferred so a machine without database settings can still collect the
rest of the suite.
"""

import os
import time

import pytest

pytestmark = [
    pytest.mark.live_db,
    pytest.mark.skipif(
        os.getenv("NL2SQL_LIVE_DB") != "1",
        reason="set NL2SQL_LIVE_DB=1 to run live database checks",
    ),
]


def _error(outcome):
    if isinstance(outcome, dict):
        return outcome.get("error")
    return outcome.error


def _rows(outcome):
    if isinstance(outcome, list):
        return outcome
    return outcome.result or []


@pytest.fixture(params=["production", "eval"])
def db(request):
    from app.core.database import DataBase, ReadOnlyDataBase

    return {"production": DataBase, "eval": ReadOnlyDataBase}[request.param]()


def test_transaction_is_read_only(db):
    assert _rows(db.execute_query("SHOW transaction_read_only")) == [
        {"transaction_read_only": "on"}
    ]


def test_statement_timeout_is_set(db):
    assert _rows(db.execute_query("SHOW statement_timeout")) == [
        {"statement_timeout": "15s"}
    ]


def test_delete_is_rejected(db):
    error = _error(db.execute_query("DELETE FROM kpi_benchmark WHERE false"))
    assert error
    assert "read-only" in error.lower() or "permission denied" in error.lower()


def test_long_query_times_out(db):
    started = time.perf_counter()
    error = _error(db.execute_query("SELECT pg_sleep(20)"))
    elapsed = time.perf_counter() - started

    assert error
    assert "timeout" in error.lower() or "canceling" in error.lower()
    assert 13.0 <= elapsed <= 19.0


def test_multi_statement_batch_is_rejected(db):
    error = _error(db.execute_query("SELECT 1; DELETE FROM kpi_benchmark WHERE false"))
    assert error
    assert "read-only" in error.lower() or "permission denied" in error.lower()
