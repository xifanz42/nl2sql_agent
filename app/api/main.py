"""FastAPI application factory and routes (Fix 21)."""

from __future__ import annotations

import logging
import math
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app import PROJECT_ROOT
from app.api.schemas import ChatRequest, ChatResponse
from app.models.chat import ChatResult

logger = logging.getLogger(__name__)


def _default_chatbot():
    """Build the real agent lazily so importing the API stays light."""
    from app.chatbot.nl2sql import NL2SQLChatbot

    return NL2SQLChatbot(documents_dir=str(PROJECT_ROOT / "data"))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal) and not value.is_finite():
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (bytes, memoryview)):
        return bytes(value).hex()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _sanitize_result(result: ChatResult) -> ChatResult:
    rows = [
        {key: _json_safe(value) for key, value in row.items()} for row in result.rows
    ]
    return result.model_copy(update={"rows": rows})


def create_app(*, chatbot=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.chatbot = (
            chatbot
            if chatbot is not None
            else await run_in_threadpool(_default_chatbot)
        )
        yield

    app = FastAPI(title="NL2SQL API", version="v1", lifespan=lifespan)

    @app.middleware("http")
    async def api_guard(request: Request, call_next):
        if request.method == "POST" and request.url.path.startswith("/api/"):
            site = request.headers.get("sec-fetch-site")
            if site and site not in {"same-origin", "none"}:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "cross-site request rejected"},
                    headers={"Cache-Control": "no-store"},
                )
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/chat", response_model=ChatResponse)
    def chat(
        payload: ChatRequest, request: Request, response: Response
    ) -> ChatResponse:
        session_id = payload.session_id or uuid.uuid4()
        result = request.app.state.chatbot.process_query_structured(
            payload.message, session_id=str(session_id)
        )
        result = _sanitize_result(result)
        if result.kind == "store_error":
            logger.warning("session store unavailable: %s", result.message)
            result = result.model_copy(
                update={"message": "session store temporarily unavailable"}
            )
            response.status_code = 503
            response.headers["Retry-After"] = "5"
        return ChatResponse(session_id=session_id, result=result)

    dist = PROJECT_ROOT / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")

    return app


app = create_app()
