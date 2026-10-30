import pytest

from app.chatbot.nl2sql import NL2SQLChatbot


@pytest.fixture
def bot():
    bot = NL2SQLChatbot.__new__(NL2SQLChatbot)
    bot.schema_info = {"kpi_benchmark": {}}
    return bot


@pytest.mark.parametrize(
    "text, expected",
    [
        ("SQL_QUERY: SELECT * FROM kpi_benchmark", "SELECT * FROM kpi_benchmark;"),
        ("sql_query: SELECT * FROM kpi_benchmark", "SELECT * FROM kpi_benchmark;"),
        ("```sql\nSELECT * FROM kpi_benchmark\n```", "SELECT * FROM kpi_benchmark;"),
        ("SELECT * FROM kpi_benchmark", "SELECT * FROM kpi_benchmark;"),
        (
            "WITH x AS (SELECT 1) SELECT * FROM x",
            "WITH x AS (SELECT 1) SELECT * FROM x;",
        ),
        ("I need more information.", None),
    ],
)
def test_extract_sql(bot, text, expected):
    assert bot._extract_sql_query(text) == expected


@pytest.mark.parametrize(
    "sql, ok",
    [
        ("SELECT * FROM kpi_benchmark;", True),
        ("SELECT * FROM public.kpi_benchmark;", True),
        ("WITH x AS (SELECT 1) SELECT * FROM x;", True),
        ("SELECT 1; DROP TABLE kpi_benchmark;", False),
        ("UPDATE kpi_benchmark SET a = 1;", False),
        ("SELECT * FROM missing_table;", False),
        ("SELECT * INTO new_table FROM kpi_benchmark;", False),
    ],
)
def test_validate_sql(bot, sql, ok):
    valid, _ = bot._validate_sql(sql)
    assert valid is ok
