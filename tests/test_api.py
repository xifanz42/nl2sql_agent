"""FastAPI contract tests for the NL2SQL API (Fix 21)."""

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config import settings
from app.models.chat import ChatResult


class FakeChatbot:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def process_query_structured(self, message, session_id=None):
        self.calls.append((message, session_id))
        return self.result


def _client(result=None):
    result = result or ChatResult(
        kind="sql",
        sql="SELECT 1",
        rows=[{"x": 1}],
        analysis="ok",
        total_rows=1,
        cost_cny=0.001,
    )
    bot = FakeChatbot(result)
    return TestClient(create_app(chatbot=bot)), bot


def test_health():
    client, _ = _client()
    with client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_typed_result_and_generates_session_id():
    client, bot = _client()
    with client:
        response = client.post("/api/v1/chat", json={"message": "  hi  "})

    assert response.status_code == 200
    body = response.json()
    assert uuid.UUID(body["session_id"]).version == 4
    assert body["result"]["kind"] == "sql"
    assert body["result"]["sql"] == "SELECT 1"
    assert body["result"]["cost_cny"] == 0.001
    assert bot.calls == [("hi", body["session_id"])]
    assert response.headers["cache-control"] == "no-store"


def test_chat_reuses_given_session_id():
    session_id = str(uuid.uuid4())
    client, bot = _client()
    with client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "hi", "session_id": session_id},
        )

    assert response.status_code == 200
    assert response.json()["session_id"] == session_id
    assert bot.calls[0][1] == session_id


def test_chat_validation():
    client, _ = _client()
    too_long = "x" * (settings.max_message_chars + 1)
    with client:
        assert client.post("/api/v1/chat", json={"message": "   "}).status_code == 422
        assert client.post("/api/v1/chat", json={"message": too_long}).status_code == 422
        assert (
            client.post(
                "/api/v1/chat",
                json={"message": "hi", "session_id": "not-a-uuid"},
            ).status_code
            == 422
        )


def test_nil_session_id_is_rejected():
    client, _ = _client()
    with client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "hi", "session_id": str(uuid.UUID(int=0))},
        )

    assert response.status_code == 422


def test_chat_rejects_cross_site_post():
    client, _ = _client()
    with client:
        rejected = client.post(
            "/api/v1/chat",
            json={"message": "hi"},
            headers={"sec-fetch-site": "cross-site"},
        )
        accepted = client.post(
            "/api/v1/chat",
            json={"message": "hi"},
            headers={"sec-fetch-site": "same-origin"},
        )

    assert rejected.status_code == 403
    assert accepted.status_code == 200


def test_chat_serializes_non_finite_and_bytes():
    result = ChatResult(
        kind="sql",
        sql="SELECT 1",
        rows=[
            {
                "nan": float("nan"),
                "decimal_nan": Decimal("NaN"),
                "blob": b"\x00\xff",
            }
        ],
        total_rows=1,
    )
    client, _ = _client(result)
    with client:
        response = client.post("/api/v1/chat", json={"message": "hi"})

    assert response.status_code == 200
    row = response.json()["result"]["rows"][0]
    assert row["nan"] is None
    assert row["decimal_nan"] is None
    assert row["blob"] == "00ff"


def test_chat_passes_through_refuse_kind():
    client, _ = _client(ChatResult(kind="refuse", message="数据中没有该指标"))
    with client:
        response = client.post("/api/v1/chat", json={"message": "查询能耗"})

    assert response.status_code == 200
    assert response.json()["result"]["kind"] == "refuse"
    assert response.json()["result"]["message"] == "数据中没有该指标"


def test_store_error_maps_to_503_with_retry_after():
    client, _ = _client(ChatResult(kind="store_error", message="session store down"))
    with client:
        response = client.post("/api/v1/chat", json={"message": "hi"})

    body = response.json()
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert response.headers["cache-control"] == "no-store"
    assert uuid.UUID(body["session_id"])
    assert body["result"]["kind"] == "store_error"
    assert body["result"]["message"] == "session store temporarily unavailable"


def test_injected_chatbot_skips_default_construction(monkeypatch):
    import app.api.main as main

    def boom():
        raise AssertionError("default chatbot should not be constructed")

    monkeypatch.setattr(main, "_default_chatbot", boom)
    client, _ = _client()
    with client:
        assert client.get("/api/v1/health").status_code == 200
