"""Execution errors must not reach the analysis model."""

from app.chatbot.nl2sql import NL2SQLChatbot
from app.models.sql import SQLResult


class FakeDB:
    def __init__(self, result):
        self.result = result

    def execute_query(self, sql):
        return self.result


class FakeEngine:
    def __init__(self, reply="SQL_QUERY: SELECT * FROM kpi_benchmark;"):
        self.reply = reply
        self.coder_calls = 0
        self.llm_calls = 0

    def call_coder(self, query, prompt):
        self.coder_calls += 1
        return self.reply

    def call_llm(self, query, prompt):
        self.llm_calls += 1
        return "ANALYSIS TEXT"


def _bot(result):
    bot = NL2SQLChatbot.__new__(NL2SQLChatbot)
    bot.schema_info = {"kpi_benchmark": {}}
    bot.conversation_history = []
    bot.model_engine = FakeEngine()
    bot.db = FakeDB(result)
    bot._needs_explore = lambda query: "no"
    bot._retrieve_relevant_knowledge = lambda query: ""
    bot._detect_followup_question = lambda query: False
    return bot


def test_execution_error_returns_error_without_analysis():
    bot = _bot(
        SQLResult(
            sql="SELECT * FROM kpi_benchmark;",
            executed=False,
            error="relation does not exist",
            execution_time_ms=12.3,
        )
    )

    response = bot.process_query("how many rows?")

    assert "Generated SQL: SELECT * FROM kpi_benchmark;" in response
    assert "relation does not exist" in response
    assert "Execution time: 12 ms" in response
    assert "Processing time:" in response
    assert "Analysis:" not in response
    assert bot.model_engine.llm_calls == 0
    assert bot.model_engine.coder_calls == 1
    assert bot.conversation_history[-1]["system"] == response


def test_success_path_still_analyzes_rows():
    bot = _bot(
        SQLResult(
            sql="SELECT * FROM kpi_benchmark;",
            executed=True,
            result=[{"n": 1}],
            execution_time_ms=1.0,
        )
    )

    response = bot.process_query("how many rows?")

    assert "Results:" in response
    assert "Analysis:" in response
    assert "ANALYSIS TEXT" in response
    assert bot.model_engine.llm_calls == 1
