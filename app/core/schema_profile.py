"""Compact, data-grounded schema profile for the SQL-generation prompt.

Everything here is derived from the connected database at runtime: types,
constraints, low-cardinality values, and numeric/temporal ranges. No table or
column name is hard-coded, so switching databases changes the profile without
code changes. The profile is a snapshot: rebuild it to pick up schema changes.

Rendered grammar (one line per table)::

    table(rows): col type{value|value} [lo..hi] ~sample PK ! FK->table(col)

``{}`` lists legal values, ``[]`` a range, ``~`` a single sample, ``PK`` and
``!`` mark primary keys and NOT NULL columns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from app.core.database import DataBase

MAX_VALUES = 10
MAX_VALUE_CHARS = 80

_TEXT_TYPES = {"VARCHAR", "TEXT", "CHAR", "STRING", "ENUM", "BOOLEAN", "BOOL"}
_RANGE_TYPES = {
    "INTEGER",
    "INT",
    "BIGINT",
    "SMALLINT",
    "REAL",
    "FLOAT",
    "DOUBLE",
    "DOUBLE_PRECISION",
    "NUMERIC",
    "DECIMAL",
    "TIMESTAMP",
    "DATETIME",
    "DATE",
    "TIME",
}
_TYPE_NAMES = {
    "VARCHAR": "text",
    "TEXT": "text",
    "CHAR": "text",
    "STRING": "text",
    "ENUM": "text",
    "INTEGER": "int",
    "INT": "int",
    "BIGINT": "int",
    "SMALLINT": "int",
    "REAL": "real",
    "FLOAT": "real",
    "DOUBLE": "real",
    "DOUBLE_PRECISION": "real",
    "NUMERIC": "numeric",
    "DECIMAL": "numeric",
    "TIMESTAMP": "timestamp",
    "DATETIME": "timestamp",
    "DATE": "date",
    "TIME": "time",
    "BOOLEAN": "bool",
    "BOOL": "bool",
}
_DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}:\d{2})?")


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    reference: str | None = None
    values: tuple[Any, ...] = field(default_factory=tuple)
    low: Any = None
    high: Any = None
    sample: Any = None


@dataclass(frozen=True)
class TableProfile:
    name: str
    row_count: int | None
    columns: tuple[ColumnProfile, ...]


@dataclass(frozen=True)
class SchemaProfile:
    tables: tuple[TableProfile, ...]


def profile_database(
    db: DataBase, *, max_values: int = MAX_VALUES, max_value_chars: int = MAX_VALUE_CHARS
) -> SchemaProfile:
    """Profile every table exposed by ``db`` with read-only SELECTs."""
    tables = []
    for table in sorted(db.get_tables()):
        primary_keys = set(db.get_primary_keys(table))
        references = _foreign_key_map(db.get_foreign_keys(table))
        columns = tuple(
            _profile_column(
                db,
                table,
                column,
                primary_key=column["name"] in primary_keys,
                reference=references.get(column["name"]),
                max_values=max_values,
                max_value_chars=max_value_chars,
            )
            for column in db.get_table_columns(table)
        )
        tables.append(TableProfile(table, _row_count(db, table), columns))
    return SchemaProfile(tuple(tables))


def render_profile(profile: SchemaProfile) -> str:
    """Render the profile as one compact line per table."""
    if not profile.tables:
        return "No tables."
    lines = []
    for table in profile.tables:
        header = table.name
        if table.row_count is not None:
            header += f"({table.row_count})"
        columns = ", ".join(_render_column(column) for column in table.columns)
        lines.append(f"{header}: {columns}" if columns else header)
    return "\n".join(lines)


def _profile_column(
    db: DataBase,
    table: str,
    column: dict[str, Any],
    *,
    primary_key: bool,
    reference: str | None,
    max_values: int,
    max_value_chars: int,
) -> ColumnProfile:
    name = column["name"]
    type_name = type(column["type"]).__name__.upper()
    base = {
        "name": name,
        "type": _TYPE_NAMES.get(type_name, type_name.lower()),
        "nullable": bool(column.get("nullable", True)),
        "primary_key": primary_key,
        "reference": reference,
    }

    if type_name in _TEXT_TYPES:
        rows = _rows(
            db,
            f'SELECT DISTINCT {_quote(name)} AS v FROM {_quote(table)} '
            f"WHERE {_quote(name)} IS NOT NULL "
            f"ORDER BY {_quote(name)} LIMIT {max_values + 1}",
        )
        values = [row["v"] for row in rows]
        if not values:
            return ColumnProfile(**base)
        ordered = sorted(values, key=str)
        if _DATE_LIKE.match(str(ordered[0])):
            # A text-stored timestamp: the range shows the format and coverage
            # without spending tokens on one value per day.
            return ColumnProfile(**base, low=ordered[0], high=ordered[-1], sample=ordered[0])
        rendered = "|".join(_format_value(value) for value in ordered)
        if len(ordered) <= max_values and len(rendered) <= max_value_chars:
            return ColumnProfile(**base, values=tuple(ordered))
        return ColumnProfile(**base, sample=ordered[0])

    if type_name in _RANGE_TYPES:
        rows = _rows(
            db,
            f'SELECT MIN({_quote(name)}) AS lo, MAX({_quote(name)}) AS hi '
            f"FROM {_quote(table)}",
        )
        if rows and rows[0].get("lo") is not None:
            return ColumnProfile(
                **base, low=rows[0]["lo"], high=rows[0].get("hi"), sample=rows[0]["lo"]
            )
        return ColumnProfile(**base)

    return ColumnProfile(**base)


def _row_count(db: DataBase, table: str) -> int | None:
    rows = _rows(db, f"SELECT COUNT(*) AS n FROM {_quote(table)}")
    if not rows:
        return None
    return int(rows[0]["n"])


def _rows(db: DataBase, sql: str) -> list[dict[str, Any]]:
    outcome = db.execute_query(sql)
    if isinstance(outcome, dict):  # legacy fake/adapter
        return outcome.get("result") or []
    if not getattr(outcome, "executed", False):
        return []
    return outcome.result or []


def _foreign_key_map(foreign_keys: list[dict[str, Any]]) -> dict[str, str]:
    references = {}
    for foreign_key in foreign_keys:
        columns = foreign_key.get("constrained_columns") or []
        referred = foreign_key.get("referred_columns") or []
        if not columns:
            continue
        target = f"{foreign_key['referred_table']}({','.join(referred)})"
        for column in columns:
            references[column] = target
    return references


def _render_column(column: ColumnProfile) -> str:
    facts = ""
    if column.values:
        facts = "{" + "|".join(_format_value(value) for value in column.values) + "}"
    elif column.low is not None and column.high is not None:
        low, high = _format_value(column.low), _format_value(column.high)
        facts = f"~{low}" if low == high else f"[{low}..{high}]"
    elif column.sample is not None:
        facts = "~" + _format_value(column.sample)

    rendered = f"{column.name} {column.type}{facts}"
    if column.primary_key:
        rendered += " PK"
    elif not column.nullable:
        rendered += "!"
    if column.reference:
        rendered += f" FK->{column.reference}"
    return rendered


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date, time)):
        value = value.isoformat()
    text = " ".join(str(value).splitlines())
    if text != text.strip() or any(char in text for char in "|,{}[]~'"):
        return "'" + text.replace("'", "''") + "'"
    return text


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
