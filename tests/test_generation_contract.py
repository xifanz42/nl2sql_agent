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
        (
            "SQL_QUERY: WITH x AS (SELECT 1) SELECT * FROM x",
            "sql",
            "WITH x AS (SELECT 1) SELECT * FROM x;",
        ),
        # CTE headers that are not plain `name AS (` must still be extracted whole.
        (
            "WITH x(a, b) AS (SELECT 1, 2) SELECT * FROM x",
            "sql",
            "WITH x(a, b) AS (SELECT 1, 2) SELECT * FROM x;",
        ),
        (
            "WITH x(a, b) AS (\nSELECT 1, 2\n) SELECT * FROM x",
            "sql",
            "WITH x(a, b) AS (\nSELECT 1, 2\n) SELECT * FROM x;",
        ),
        (
            "WITH x AS MATERIALIZED (\nSELECT 1\n) SELECT * FROM x",
            "sql",
            "WITH x AS MATERIALIZED (\nSELECT 1\n) SELECT * FROM x;",
        ),
        (
            "WITH x AS NOT MATERIALIZED (SELECT 1) SELECT * FROM x",
            "sql",
            "WITH x AS NOT MATERIALIZED (SELECT 1) SELECT * FROM x;",
        ),
        (
            'WITH "x" AS (\nSELECT 1\n) SELECT * FROM x',
            "sql",
            'WITH "x" AS (\nSELECT 1\n) SELECT * FROM x;',
        ),
        # SQL may follow prose, but must start a line.
        ("Sure:\nSELECT * FROM t", "sql", "SELECT * FROM t;"),
        # A prose "with" must not be parsed as SQL.
        ("该问题需要 join, 无法 with 当前 schema 完成。", "unknown", ""),
        ("With current schema, this is not possible.", "unknown", ""),
        # Keep both statements so the validator can reject the batch.
        ("SELECT 1; DROP TABLE t;", "sql", "SELECT 1; DROP TABLE t;"),
        ("请提供具体信息: 哪个指标？", "clarify", ""),
        ("引导提问: 你想查哪类？", "clarify", ""),
        ("无法回答: 数据中没有能耗指标。", "refuse", ""),
        ("无法回答：当前数据只有 2025-08-15 到 2025-08-20。", "refuse", ""),
        # A refusal may mention SELECT in its reason; it must not become SQL.
        ("无法回答: 该请求超出只读 SELECT 范围。", "refuse", ""),
        ("请提供具体信息: 你要 SELECT 哪一列？", "clarify", ""),
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


def test_refusal_message_is_preserved():
    result = parse_generation("无法回答: 数据中没有能耗指标。")

    assert result.kind == "refuse"
    assert result.message == "数据中没有能耗指标。"
