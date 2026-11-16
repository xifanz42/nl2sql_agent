"""Conversation state must be isolated per session and exposed as a typed result."""

import uuid

from app.chatbot.nl2sql import NL2SQLChatbot
from app.chatbot.session import InMemorySessionStore, SessionStoreUnavailable
from app.models.sql import SQLResult


class FakeDB:
    def execute_query(self, sql):
        return SQLResult(
            sql=sql, executed=True, result=[{"n": 1}], execution_time_ms=1.0
        )


class FakeEngine:
    def __init__(self):
        self.prompts = []

    def call_coder(self, query, prompt):
        self.prompts.append(prompt)
        return "SQL_QUERY: SELECT * FROM kpi_benchmark;"

    def call_llm(self, query, prompt):
        return "ANALYSIS TEXT"


def _bot():
    bot = NL2SQLChatbot.__new__(NL2SQLChatbot)
    bot.schema_info = {"kpi_benchmark": {}}
    bot.schema_profile = "kpi_benchmark(0):"
    bot.sessions = InMemorySessionStore()
    bot.model_engine = FakeEngine()
    bot.db = FakeDB()
    bot._needs_explore = lambda query: "no"
    bot._retrieve_relevant_knowledge = lambda query: ""
    bot._detect_followup_question = lambda query, session: False
    return bot


def _sid():
    return str(uuid.uuid4())


def test_two_sessions_do_not_share_history():
    bot = _bot()
    a_id, b_id = _sid(), _sid()
    bot.process_query("first question", session_id=a_id)
    bot.process_query("second question", session_id=b_id)

    a = bot.sessions.get(a_id).history
    b = bot.sessions.get(b_id).history

    assert [turn.user for turn in a] == ["first question"]
    assert [turn.user for turn in b] == ["second question"]


def test_same_session_keeps_history_and_other_session_does_not_see_it():
    bot = _bot()
    a_id, b_id = _sid(), _sid()
    bot.process_query("first question", session_id=a_id)
    bot.process_query("follow up", session_id=a_id)
    bot.process_query("unrelated", session_id=b_id)

    assert len(bot.sessions.get(a_id).history) == 2
    assert "first question" in bot.model_engine.prompts[1]
    assert "first question" not in bot.model_engine.prompts[-1]


def test_structured_result_exposes_fields():
    bot = _bot()
    result = bot.process_query_structured("how many rows?", session_id=_sid())

    assert result.kind == "sql"
    assert result.sql == "SELECT * FROM kpi_benchmark;"
    assert result.rows == [{"n": 1}]
    assert result.analysis == "ANALYSIS TEXT"
    assert result.processing_time_ms >= 0


def test_history_does_not_store_result_rows():
    bot = _bot()
    sid = _sid()
    bot.process_query("how many rows?", session_id=sid)

    history = bot.sessions.get(sid).history[-1].system
    assert "SQL: SELECT * FROM kpi_benchmark;" in history
    assert "Rows: 1" in history
    assert "Results:" not in history


def test_invalid_session_id_is_rejected():
    bot = _bot()
    result = bot.process_query_structured("anything", session_id="not-a-uuid")

    assert result.kind == "invalid"
    assert "UUID" in result.message


def test_store_unavailable_returns_store_error():
    class BrokenStore:
        def get(self, session_id):
            raise SessionStoreUnavailable("session store down")

        def save(self, session_id, session):
            raise SessionStoreUnavailable("session store down")

        def delete(self, session_id):
            raise SessionStoreUnavailable("session store down")

    bot = _bot()
    bot.sessions = BrokenStore()
    result = bot.process_query_structured("anything", session_id=_sid())

    assert result.kind == "store_error"
    assert "session store down" in result.message


def test_store_save_failure_preserves_metrics():
    class SaveFailingStore(InMemorySessionStore):
        def save(self, session_id, session):
            raise SessionStoreUnavailable("save failed")

    bot = _bot()
    bot.sessions = SaveFailingStore()
    result = bot.process_query_structured("how many rows?", session_id=_sid())

    assert result.kind == "store_error"
    assert result.processing_time_ms > 0
