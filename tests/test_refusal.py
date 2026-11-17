"""Refusal is a first-class outcome: no SQL, no analysis, no execution."""

import uuid

from app.chatbot.nl2sql import NL2SQLChatbot
from app.chatbot.session import InMemorySessionStore
from app.models.chat import ChatResult
from app.models.sql import SQLResult


class FakeDB:
    def __init__(self):
        self.calls = 0

    def execute_query(self, sql, max_rows=None):
        self.calls += 1
        return SQLResult(sql=sql, executed=True, result=[], execution_time_ms=1.0)


class FakeEngine:
    def __init__(self, reply):
        self.reply = reply
        self.analysis_calls = 0
        self.coder_prompts = []

    def call_coder(self, query, prompt):
        self.coder_prompts.append(prompt)
        return self.reply

    def call_llm(self, query, prompt):
        self.analysis_calls += 1
        return "ANALYSIS SHOULD NOT RUN"

    def call_helper(self, query, prompt):
        return "no"


def _bot(reply):
    bot = NL2SQLChatbot.__new__(NL2SQLChatbot)
    bot.schema_info = {"kpi_benchmark": {}}
    bot.schema_profile = "kpi_benchmark(0):"
    bot.sessions = InMemorySessionStore()
    bot.model_engine = FakeEngine(reply)
    bot.db = FakeDB()
    bot._needs_explore = lambda query: "no"
    bot._retrieve_relevant_knowledge = lambda query: ""
    bot._detect_followup_question = lambda query, session: False
    return bot


def test_refusal_is_not_clarification_or_sql():
    bot = _bot("无法回答: 数据中没有能耗指标。")
    result = bot.process_query_structured("查询能耗", session_id=str(uuid.uuid4()))

    assert result.kind == "refuse"
    assert "能耗" in result.message
    assert bot.db.calls == 0
    assert bot.model_engine.analysis_calls == 0


def test_generate_sql_returns_refusal_message():
    bot = _bot("无法回答: 当前数据只有 2025-08-15 到 2025-08-20。")
    output = bot.generate_sql("查询 2024 年数据")

    assert output == "当前数据只有 2025-08-15 到 2025-08-20。"
    assert "SELECT" not in output


def test_refusal_mentioning_select_is_not_executed():
    bot = _bot("无法回答: 该请求超出只读 SELECT 范围。")
    result = bot.process_query_structured(
        "SELECT * FROM kpi_benchmark", session_id=str(uuid.uuid4())
    )

    assert result.kind == "refuse"
    assert "SELECT" in result.message
    assert bot.db.calls == 0
    assert bot.model_engine.analysis_calls == 0


def test_bare_refusal_gets_a_fallback_message():
    bot = _bot("无法回答:")
    result = bot.process_query_structured("查询能耗", session_id=str(uuid.uuid4()))

    assert result.kind == "refuse"
    assert result.message == "当前数据无法支持该问题。"
    assert result.render_text()


def test_refusal_renders_as_message_only():
    result = ChatResult(kind="refuse", message="没有该指标。")

    assert result.render_text() == "没有该指标。"
    assert result.history_text() == "没有该指标。"
