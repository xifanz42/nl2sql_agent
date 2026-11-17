"""Short-term compaction and the analysis row guard (PR1b)."""

import uuid

from app.chatbot.nl2sql import (
    KEEP_RECENT_TURNS,
    MAX_ANALYSIS_ROWS,
    MAX_HISTORY_TURNS,
    MAX_SUMMARY_CHARS,
    NL2SQLChatbot,
)
from app.chatbot.session import InMemorySessionStore
from app.models.chat import ChatSession, Turn
from app.models.sql import SQLResult


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.max_rows = None

    def execute_query(self, sql, max_rows=None):
        self.max_rows = max_rows
        return SQLResult(
            sql=sql,
            executed=True,
            result=self.rows,
            execution_time_ms=1.0,
            truncated=max_rows is not None and len(self.rows) >= max_rows,
        )


class FakeEngine:
    def __init__(self, summary="SUMMARY"):
        self.summary = summary
        self.prompts = []
        self.analysis_prompts = []
        self.helper_calls = 0

    def call_helper(self, query, prompt):
        self.helper_calls += 1
        self.prompts.append(prompt)
        return self.summary

    def call_coder(self, query, prompt):
        self.prompts.append(prompt)
        return "SQL_QUERY: SELECT * FROM kpi_benchmark;"

    def call_llm(self, query, prompt):
        self.analysis_prompts.append(prompt)
        return "ANALYSIS TEXT"


def _bot(rows=None):
    bot = NL2SQLChatbot.__new__(NL2SQLChatbot)
    bot.schema_info = {"kpi_benchmark": {}}
    bot.schema_profile = "kpi_benchmark(0):"
    bot.sessions = InMemorySessionStore()
    bot.model_engine = FakeEngine()
    bot.db = FakeDB([{"n": 1}] if rows is None else rows)
    bot._needs_explore = lambda query: "no"
    bot._retrieve_relevant_knowledge = lambda query: ""
    bot._detect_followup_question = lambda query, session: False
    return bot


def _seed(bot, session_id, turns):
    bot.sessions.save(
        session_id,
        ChatSession(
            history=[Turn(user=f"q{i}", system=f"a{i}") for i in range(turns)]
        ),
    )


def test_no_compaction_below_threshold():
    bot = _bot()
    session_id = str(uuid.uuid4())
    _seed(bot, session_id, 3)

    bot.process_query_structured("next", session_id=session_id)

    assert bot.model_engine.helper_calls == 0


def test_compaction_triggers_at_turn_limit():
    bot = _bot()
    session_id = str(uuid.uuid4())
    _seed(bot, session_id, MAX_HISTORY_TURNS + 1)

    result = bot.process_query_structured("next", session_id=session_id)
    session = bot.sessions.get(session_id)

    assert result.kind == "sql"
    assert bot.model_engine.helper_calls == 1
    assert session.summary == "SUMMARY"
    assert session.summary_upto == MAX_HISTORY_TURNS + 1 - KEEP_RECENT_TURNS
    assert len(session.history) <= KEEP_RECENT_TURNS + 1  # kept + current turn
    # The summary block reaches the generation prompt; summarized turns do not.
    assert "之前的对话摘要：SUMMARY" in bot.model_engine.prompts[-1]
    assert "q0" not in bot.model_engine.prompts[-1]


def test_compaction_triggers_on_char_budget():
    bot = _bot()
    session_id = str(uuid.uuid4())
    bot.sessions.save(
        session_id,
        ChatSession(
            history=[
                Turn(user="q0", system="x" * 13_000),
                Turn(user="q1", system="y" * 13_000),
            ]
        ),
    )

    bot.process_query_structured("next", session_id=session_id)
    session = bot.sessions.get(session_id)

    assert bot.model_engine.helper_calls == 1
    assert session.summary == "SUMMARY"
    assert session.summary_upto == 1


def test_compaction_failure_does_not_block_the_query():
    class FailingEngine(FakeEngine):
        def call_helper(self, query, prompt):
            raise RuntimeError("helper down")

    bot = _bot()
    bot.model_engine = FailingEngine()
    session_id = str(uuid.uuid4())
    _seed(bot, session_id, MAX_HISTORY_TURNS + 1)

    result = bot.process_query_structured("next", session_id=session_id)

    assert result.kind == "sql"
    assert bot.sessions.get(session_id).summary == ""


def test_too_many_rows_skips_analysis_and_warns():
    bot = _bot(rows=[{"n": i} for i in range(MAX_ANALYSIS_ROWS + 1)])
    session_id = str(uuid.uuid4())

    result = bot.process_query_structured("all rows", session_id=session_id)

    assert result.kind == "too_many_rows"
    assert result.total_rows == MAX_ANALYSIS_ROWS + 1
    assert len(result.rows) == MAX_ANALYSIS_ROWS
    assert result.truncated is True
    assert str(MAX_ANALYSIS_ROWS + 1) in result.message
    assert bot.model_engine.analysis_prompts == []
    assert "analysis skipped" in bot.sessions.get(session_id).history[-1].system
    assert "超出可分析范围" in result.render_text()


def test_chat_passes_max_rows_to_db():
    bot = _bot(rows=[{"n": 1}])
    bot.process_query_structured("one row", session_id=str(uuid.uuid4()))

    assert bot.db.max_rows == MAX_ANALYSIS_ROWS + 1


def test_analysis_prompt_is_char_capped():
    bot = _bot(rows=[{"text": "x" * 25_000}])
    session_id = str(uuid.uuid4())

    result = bot.process_query_structured("long text", session_id=session_id)

    assert result.kind == "sql"
    prompt = bot.model_engine.analysis_prompts[-1]
    assert "...(truncated)" in prompt
    assert prompt.count("x") < 25_000


def test_summary_is_capped():
    bot = _bot()
    bot.model_engine.summary = "s" * (MAX_SUMMARY_CHARS + 500)
    session_id = str(uuid.uuid4())
    _seed(bot, session_id, MAX_HISTORY_TURNS + 1)

    bot.process_query_structured("next", session_id=session_id)

    assert len(bot.sessions.get(session_id).summary) == MAX_SUMMARY_CHARS


def test_render_prompt_without_summary_has_no_summary_block():
    bot = _bot()

    prompt = bot.render_prompt(knowledge="K", history="H")

    assert "之前的对话摘要" not in prompt
    assert "和知识库相关内容：K\n\n        以及历史会话记录：H" in prompt


def test_last_sql_is_persisted_for_followups():
    bot = _bot()
    session_id = str(uuid.uuid4())

    bot.process_query_structured("how many rows?", session_id=session_id)

    assert bot.sessions.get(session_id).last_sql == "SELECT * FROM kpi_benchmark;"
