"""Compact, structural schema profile for the SQL-generation prompt.

Only structure is derived from the database: tables, columns, types, primary
keys, foreign keys, and NOT NULL constraints. Values, ranges, and business
semantics live in the RAG data dictionary, not here: a single sample is
misleading (the 3a eval showed the model using one sample as a filter), and
duplicating value lists with the dictionary creates conflicting context.

No table or column name is hard-coded, so switching databases changes the
profile without code changes. The profile is a snapshot: rebuild it to pick up
schema changes.

Rendered grammar (one line per table)::

    table: col type PK ! FK->table(col)

``PK`` marks primary keys, ``!`` marks NOT NULL columns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.database import DataBase

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


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    reference: str | None = None


@dataclass(frozen=True)
class TableProfile:
    name: str
    columns: tuple[ColumnProfile, ...]


@dataclass(frozen=True)
class SchemaProfile:
    tables: tuple[TableProfile, ...]


def profile_database(db: DataBase) -> SchemaProfile:
    """Profile every table's structure with metadata only (no data SELECTs)."""
    tables = []
    for table in sorted(db.get_tables()):
        primary_keys = set(db.get_primary_keys(table))
        references = _foreign_key_map(db.get_foreign_keys(table))
        columns = tuple(
            _profile_column(
                column,
                primary_key=column["name"] in primary_keys,
                reference=references.get(column["name"]),
            )
            for column in db.get_table_columns(table)
        )
        tables.append(TableProfile(table, columns))
    return SchemaProfile(tuple(tables))


def render_profile(profile: SchemaProfile) -> str:
    """Render the profile as one compact line per table."""
    if not profile.tables:
        return "No tables."
    lines = []
    for table in profile.tables:
        columns = ", ".join(_render_column(column) for column in table.columns)
        lines.append(f"{table.name}: {columns}" if columns else table.name)
    return "\n".join(lines)


def _profile_column(
    column: dict[str, Any],
    *,
    primary_key: bool,
    reference: str | None,
) -> ColumnProfile:
    type_name = type(column["type"]).__name__.upper()
    return ColumnProfile(
        name=column["name"],
        type=_TYPE_NAMES.get(type_name, type_name.lower()),
        nullable=bool(column.get("nullable", True)),
        primary_key=primary_key,
        reference=reference,
    )


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
    rendered = f"{column.name} {column.type}"
    if column.primary_key:
        rendered += " PK"
    elif not column.nullable:
        rendered += "!"
    if column.reference:
        rendered += f" FK->{column.reference}"
    return rendered
