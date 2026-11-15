"""Session store backends: Redis with TTL, SQLite fallback, in-memory test double."""

import sqlite3
import time

import fakeredis
import pytest
from redis.exceptions import RedisError

from app.chatbot.session import (
    InMemorySessionStore,
    RedisSessionStore,
    SessionStoreUnavailable,
    SQLiteSessionStore,
)
from app.models.chat import ChatSession, Turn


def _session():
    return ChatSession(history=[Turn(user="hi", system="hello")])


def test_redis_store_round_trip_and_ttl():
    client = fakeredis.FakeStrictRedis(decode_responses=True)
    store = RedisSessionStore(client, ttl_seconds=60)

    store.save("s1", _session())

    assert store.get("s1").history[0].user == "hi"
    assert 0 < client.ttl("nl2sql:session:s1") <= 60

    store.delete("s1")
    assert store.get("s1").history == []


def test_sqlite_store_round_trip_and_expiry(tmp_path):
    path = tmp_path / "sessions.sqlite"
    store = SQLiteSessionStore(str(path), ttl_seconds=60)

    store.save("s1", _session())
    assert store.get("s1").history[0].system == "hello"

    conn = sqlite3.connect(path)
    conn.execute(
        "UPDATE sessions SET expires_at = ? WHERE session_id = 's1'",
        (time.time() - 1,),
    )
    conn.commit()
    conn.close()

    assert store.get("s1").history == []


def test_in_memory_store_isolates_sessions():
    store = InMemorySessionStore()
    store.save("a", ChatSession(history=[Turn(user="a")]))
    store.save("b", ChatSession(history=[Turn(user="b")]))

    assert store.get("a").history[0].user == "a"
    assert store.get("b").history[0].user == "b"


class _BrokenRedis:
    def get(self, *args, **kwargs):
        raise RedisError("down")

    def set(self, *args, **kwargs):
        raise RedisError("down")

    def delete(self, *args, **kwargs):
        raise RedisError("down")

    def expire(self, *args, **kwargs):
        raise RedisError("down")


def test_redis_errors_are_wrapped():
    store = RedisSessionStore(_BrokenRedis(), ttl_seconds=60)

    with pytest.raises(SessionStoreUnavailable):
        store.get("00000000-0000-0000-0000-000000000001")


def test_build_session_store_falls_back_to_sqlite(monkeypatch, tmp_path):
    import app.chatbot.session as session_module

    def no_redis(*args, **kwargs):
        raise session_module.RedisError("redis is down")

    monkeypatch.setattr(session_module.redis.Redis, "from_url", no_redis)
    monkeypatch.setattr(
        session_module.settings, "session_sqlite_path", str(tmp_path / "fallback.sqlite")
    )

    store = session_module.build_session_store()

    assert isinstance(store, SQLiteSessionStore)
