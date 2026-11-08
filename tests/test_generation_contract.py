"""The shared generation parser is the single source of truth for reply kinds."""

import pytest

from app.core.generation import parse_generation, strip_fences


@pytest.mark.parametrize(
    "text, kind, sql",
    [
        ("SQL_QUERY: SELECT * FROM t", "sql", "SELECT * FROM t;"),
        ("sql_query: SELECT * FROM t", "sql", "SELECT * FROM t;"),
        ("```sql\nSELECT * FROM t\n```", "sql", "SELECT * FROM t;"),
        # Stray closing fence (the 3a direct+rag regression).
        ("SQL_QUERY: SELECT * FROM t;\n```", "sql", "SELECT * FROM t;"),
        # Unclosed opening fence.
        ("```sql\nSELECT * FROM t", "sql", "SELECT * FROM t;"),
        ("Sure:\n```sql\nSELECT * FROM t\n```", "sql", "SELECT * FROM t;"),
        (
            "WITH x AS (SELECT 1) SELECT * FROM x",
            "sql",
            "WITH x AS (SELECT 1) SELECT * FROM x;",
        ),
        # Keep both statements so the validator can reject the batch.
        ("SELECT 1; DROP TABLE t;", "sql", "SELECT 1; DROP TABLE t;"),
        ("请提供具体信息: 哪个指标？", "clarify", ""),
        ("引导提问: 你想查哪类？", "clarify", ""),
        (
            "Generated SQL_QUERY is not valid: Only SELECT queries are allowed, got Intersect",
            "error",
            "",
        ),
        ("Only a single SQL statement is allowed", "error", ""),
        ("I need more information.", "unknown", ""),
        ("", "unknown", ""),
    ],
)
def test_parse_generation(text, kind, sql):
    result = parse_generation(text)

    assert result.kind == kind
    assert result.sql == sql


@pytest.mark.parametrize(
    "text, expected",
    [
        ("```sql\nSELECT 1\n```", "SELECT 1"),
        ("SELECT 1;\n```", "SELECT 1;"),
        ("```sql\nSELECT 1", "SELECT 1"),
        ("SELECT 1", "SELECT 1"),
    ],
)
def test_strip_fences(text, expected):
    assert strip_fences(text) == expected


def test_validator_error_never_becomes_sql():
    result = parse_generation(
        "Generated SQL_QUERY is not valid: Only SELECT queries are allowed, got Intersect"
    )

    assert result.kind == "error"
    assert result.sql == ""
