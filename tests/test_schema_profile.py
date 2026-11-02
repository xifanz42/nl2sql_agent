"""Schema profiling is data-derived, compact, and independent of table names."""

import re

from sqlalchemy import BOOLEAN, INTEGER, REAL, VARCHAR

from app.core.schema_profile import profile_database, render_profile
from app.models.sql import SQLResult


class FakeDB:
    def __init__(
        self,
        tables,
        columns,
        *,
        row_counts=None,
        values=None,
        ranges=None,
        primary_keys=None,
        foreign_keys=None,
        fail=False,
    ):
        self.tables = tables
        self.columns = columns
        self.row_counts = row_counts or {}
        self.values = values or {}
        self.ranges = ranges or {}
        self.primary_keys = primary_keys or {}
        self.foreign_keys = foreign_keys or {}
        self.fail = fail

    def get_tables(self):
        return list(self.tables)

    def get_table_columns(self, table):
        return self.columns[table]

    def get_primary_keys(self, table):
        return self.primary_keys.get(table, [])

    def get_foreign_keys(self, table):
        return self.foreign_keys.get(table, [])

    def execute_query(self, sql):
        if self.fail:
            return SQLResult(sql=sql, executed=False, error="boom", execution_time_ms=0.0)
        table = re.search(r'FROM "([^"]+)"', sql).group(1)
        if "DISTINCT" in sql:
            column = re.search(r'SELECT (?:DISTINCT )?"([^"]+)" AS v', sql).group(1)
            rows = [{"v": value, "n": 1} for value in self.values.get((table, column), [])]
        elif "MIN(" in sql:
            column = re.search(r'MIN\("([^"]+)"\)', sql).group(1)
            low, high = self.ranges.get((table, column), (None, None))
            rows = [{"lo": low, "hi": high}]
        else:
            rows = [{"n": self.row_counts.get(table, 0)}]
        return SQLResult(sql=sql, executed=True, result=rows, execution_time_ms=0.0)


def _kpi_db():
    return FakeDB(
        tables=["kpi_benchmark"],
        columns={
            "kpi_benchmark": [
                {"name": "id", "type": INTEGER(), "nullable": False},
                {"name": "record_date", "type": VARCHAR(50), "nullable": True},
                {"name": "vehicle_type", "type": VARCHAR(50), "nullable": True},
                {"name": "active", "type": BOOLEAN(), "nullable": True},
                {"name": "index_category", "type": VARCHAR(50), "nullable": True},
                {"name": "index_value", "type": REAL(), "nullable": True},
            ]
        },
        row_counts={"kpi_benchmark": 360},
        values={
            ("kpi_benchmark", "record_date"): [
                "2025-08-20T00:00:00Z",
                "2025-08-15T00:00:00Z",
            ],
            ("kpi_benchmark", "vehicle_type"): ["MT", "AT"],
            ("kpi_benchmark", "active"): [True, False],
            ("kpi_benchmark", "index_category"): ["停车", " Parking"],
        },
        ranges={
            ("kpi_benchmark", "id"): (1, 360),
            ("kpi_benchmark", "index_value"): (0.0, 165.0),
        },
    )


def test_renders_values_ranges_samples_and_quotes_whitespace():
    rendered = render_profile(profile_database(_kpi_db()))

    assert rendered == (
        "kpi_benchmark(360): id int[1..360]!, "
        "record_date text[2025-08-15T00:00:00Z..2025-08-20T00:00:00Z], "
        "vehicle_type text{AT|MT}, "
        "active bool{false|true}, "
        "index_category text{' Parking'|停车}, "
        "index_value real[0.0..165.0]"
    )


def test_high_cardinality_text_falls_back_to_one_sample():
    values = [f"v{index:02d}" for index in range(11)]
    db = FakeDB(
        tables=["events"],
        columns={
            "events": [
                {"name": "event_id", "type": VARCHAR(50), "nullable": True},
            ]
        },
        row_counts={"events": 11},
        values={("events", "event_id"): values},
    )

    rendered = render_profile(profile_database(db))

    assert rendered == "events(11): event_id text~v00"
    assert "v01" not in rendered


def test_wide_value_domain_falls_back_to_sample():
    values = [f"category_{index:02d}_long" for index in range(6)]
    db = FakeDB(
        tables=["wide"],
        columns={
            "wide": [
                {"name": "kind", "type": VARCHAR(50), "nullable": True},
            ]
        },
        row_counts={"wide": 6},
        values={("wide", "kind"): values},
    )

    rendered = render_profile(profile_database(db))

    assert rendered == "wide(6): kind text~category_00_long"
    assert "category_01_long" not in rendered


def test_pk_fk_and_not_null_markers():
    db = FakeDB(
        tables=["orders"],
        columns={
            "orders": [
                {"name": "id", "type": INTEGER(), "nullable": False},
                {"name": "customer_id", "type": INTEGER(), "nullable": False},
                {"name": "total", "type": REAL(), "nullable": False},
            ]
        },
        row_counts={"orders": 3},
        ranges={
            ("orders", "id"): (1, 3),
            ("orders", "customer_id"): (1, 9),
            ("orders", "total"): (5.0, 20.0),
        },
        primary_keys={"orders": ["id"]},
        foreign_keys={
            "orders": [
                {
                    "constrained_columns": ["customer_id"],
                    "referred_table": "customers",
                    "referred_columns": ["id"],
                }
            ]
        },
    )

    rendered = render_profile(profile_database(db))

    assert rendered == (
        "orders(3): id int[1..3] PK, "
        "customer_id int[1..9]! FK->customers(id), "
        "total real[5.0..20.0]!"
    )


def test_render_is_deterministic_and_schema_agnostic():
    db = FakeDB(
        tables=["events"],
        columns={
            "events": [
                {"name": "kind", "type": VARCHAR(20), "nullable": True},
            ]
        },
        row_counts={"events": 2},
        values={("events", "kind"): ["b", "a"]},
    )

    first = render_profile(profile_database(db))
    second = render_profile(profile_database(db))

    assert first == second == "events(2): kind text{a|b}"
    assert "kpi_benchmark" not in first


def test_query_failures_degrade_to_types():
    db = FakeDB(
        tables=["events"],
        columns={
            "events": [
                {"name": "id", "type": INTEGER(), "nullable": False},
                {"name": "kind", "type": VARCHAR(20), "nullable": True},
            ]
        },
        fail=True,
    )

    rendered = render_profile(profile_database(db))

    assert rendered == "events: id int!, kind text"

