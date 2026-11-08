"""Schema profile is structural only: no values, ranges, or data SELECTs."""

from sqlalchemy import BOOLEAN, INTEGER, REAL, VARCHAR

from app.core.schema_profile import profile_database, render_profile


class FakeDB:
    def __init__(self, tables, columns, *, primary_keys=None, foreign_keys=None):
        self.tables = tables
        self.columns = columns
        self.primary_keys = primary_keys or {}
        self.foreign_keys = foreign_keys or {}

    def get_tables(self):
        return list(self.tables)

    def get_table_columns(self, table):
        return self.columns[table]

    def get_primary_keys(self, table):
        return self.primary_keys.get(table, [])

    def get_foreign_keys(self, table):
        return self.foreign_keys.get(table, [])

    def execute_query(self, sql):
        raise AssertionError(f"schema profile must not query data: {sql}")


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
    )


def test_renders_schema_only():
    rendered = render_profile(profile_database(_kpi_db()))

    assert rendered == (
        "kpi_benchmark: id int!, record_date text, vehicle_type text, "
        "active bool, index_category text, index_value real"
    )


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
        "orders: id int PK, customer_id int! FK->customers(id), total real!"
    )


def test_render_is_deterministic_and_schema_agnostic():
    db = FakeDB(
        tables=["events"],
        columns={
            "events": [
                {"name": "kind", "type": VARCHAR(20), "nullable": True},
            ]
        },
    )

    first = render_profile(profile_database(db))
    second = render_profile(profile_database(db))

    assert first == second == "events: kind text"
    assert "kpi_benchmark" not in first


def test_profile_does_not_query_data():
    # FakeDB.execute_query raises; reaching it would fail the test.
    rendered = render_profile(profile_database(_kpi_db()))

    assert "kpi_benchmark" in rendered
