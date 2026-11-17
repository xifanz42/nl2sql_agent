"""Per-conversation short-term state (Fix 16).

Redis is the runtime store; SQLite is used when Redis is unreachable at startup.
Both are writable stores: they are deliberately separate from the read-only
analytics database (``nl2sql_ro``).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

import redis
from redis.exceptions import RedisError

from app.config import settings
from app.models.chat import ChatSession

logger = logging.getLogger(__name__)

KEY_PREFIX = "nl2sql:session:"
DEFAULT_SESSION_ID = "00000000-0000-0000-0000-000000000000"


class SessionStoreUnavailable(RuntimeError):
    """Raised when the configured session store cannot serve a request."""


def normalize_session_id(session_id: str | None) -> str:
    """Accept only UUID-shaped ids; ``None`` maps to the CLI default."""
    if session_id is None:
        return DEFAULT_SESSION_ID
    try:
        return str(uuid.UUID(session_id))
    except ValueError as exc:
        raise ValueError("session_id must be a UUID") from exc


class SessionStore(Protocol):
    """Storage contract for one conversation's short-term state."""

    def get(self, session_id: str) -> ChatSession: ...

    def save(self, session_id: str, session: ChatSession) -> None: ...

    def delete(self, session_id: str) -> None: ...


class RedisSessionStore:
    """Redis-backed store with a sliding TTL.

    Read-modify-write of the JSON value is not atomic. The chat UI issues one
    request at a time per session, so that is acceptable for now; a per-session
    lock is the next step if concurrent requests on one session become real.
    """

    def __init__(self, client: redis.Redis, ttl_seconds: int):
        self.client = client
        self.ttl_seconds = ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"{KEY_PREFIX}{session_id}"

    def get(self, session_id: str) -> ChatSession:
        try:
            raw = self.client.get(self._key(session_id))
            if raw is None:
                return ChatSession()
            self.client.expire(self._key(session_id), self.ttl_seconds)
            return ChatSession.model_validate_json(raw)
        except RedisError as exc:
            raise SessionStoreUnavailable(
                f"Redis session store unavailable: {exc}"
            ) from exc

    def save(self, session_id: str, session: ChatSession) -> None:
        try:
            self.client.set(
                self._key(session_id), session.model_dump_json(), ex=self.ttl_seconds
            )
        except RedisError as exc:
            raise SessionStoreUnavailable(
                f"Redis session store unavailable: {exc}"
            ) from exc

    def delete(self, session_id: str) -> None:
        try:
            self.client.delete(self._key(session_id))
        except RedisError as exc:
            raise SessionStoreUnavailable(
                f"Redis session store unavailable: {exc}"
            ) from exc


class SQLiteSessionStore:
    """Single-file fallback store with the same TTL semantics as Redis."""

    def __init__(self, path: str, ttl_seconds: int):
        self.path = path
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS sessions ("
                "session_id TEXT PRIMARY KEY, "
                "data TEXT NOT NULL, "
                "expires_at REAL NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_expires_at "
                "ON sessions(expires_at)"
            )

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.path, check_same_thread=False)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get(self, session_id: str) -> ChatSession:
        now = time.time()
        try:
            with self._lock, self._connection() as conn:
                row = conn.execute(
                    "SELECT data, expires_at FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row is None:
                    return ChatSession()
                if row[1] <= now:
                    conn.execute(
                        "DELETE FROM sessions WHERE session_id = ?", (session_id,)
                    )
                    return ChatSession()
                conn.execute(
                    "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
                    (now + self.ttl_seconds, session_id),
                )
                return ChatSession.model_validate_json(row[0])
        except sqlite3.Error as exc:
            raise SessionStoreUnavailable(
                f"SQLite session store unavailable: {exc}"
            ) from exc

    def save(self, session_id: str, session: ChatSession) -> None:
        now = time.time()
        try:
            with self._lock, self._connection() as conn:
                conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
                conn.execute(
                    "INSERT INTO sessions (session_id, data, expires_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(session_id) DO UPDATE SET "
                    "data = excluded.data, expires_at = excluded.expires_at",
                    (
                        session_id,
                        session.model_dump_json(),
                        now + self.ttl_seconds,
                    ),
                )
        except sqlite3.Error as exc:
            raise SessionStoreUnavailable(
                f"SQLite session store unavailable: {exc}"
            ) from exc

    def delete(self, session_id: str) -> None:
        try:
            with self._lock, self._connection() as conn:
                conn.execute(
                    "DELETE FROM sessions WHERE session_id = ?", (session_id,)
                )
        except sqlite3.Error as exc:
            raise SessionStoreUnavailable(
                f"SQLite session store unavailable: {exc}"
            ) from exc


class InMemorySessionStore:
    """Test double; not used by the runtime entry points."""

    def __init__(self):
        self._sessions: dict[str, ChatSession] = {}

    def get(self, session_id: str) -> ChatSession:
        return self._sessions.get(session_id, ChatSession())

    def save(self, session_id: str, session: ChatSession) -> None:
        self._sessions[session_id] = session

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


def build_session_store() -> SessionStore:
    """Pick Redis, or fall back to SQLite when Redis is unreachable at startup."""
    try:
        client = redis.Redis.from_url(
            settings.redis_url.get_secret_value(),
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        return RedisSessionStore(client, settings.session_ttl_seconds)
    except (RedisError, ValueError) as exc:
        logger.warning(
            "Redis unavailable (%s); falling back to SQLite at %s",
            exc,
            settings.session_sqlite_path,
        )
        return SQLiteSessionStore(
            settings.session_sqlite_path, settings.session_ttl_seconds
        )
