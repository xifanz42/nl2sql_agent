"""FastAPI application factory and routes (Fix 21)."""

from __future__ import annotations

import logging
import math
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Request, Response, UploadFile
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import PROJECT_ROOT
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    ConfigResponse,
    DocumentUploadResponse,
)
from app.api.uploads import (
    InvalidUpload,
    UploadTooLarge,
    save_upload,
    validate_upload_filename,
)
from app.config import settings
from app.core.document_processor import DocumentParseError
from app.models.chat import ChatResult

logger = logging.getLogger(__name__)

_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)
# Swagger/ReDoc load CDN assets and inline scripts, so a strict policy breaks
# them. The app UI and API are self-contained and stay under the policy.
_CSP_EXEMPT_PREFIXES = ("/docs", "/redoc", "/openapi.json")

# Multipart framing overhead allowed on top of the file byte limit for the
# early Content-Length rejection. save_upload remains the authority per file.
_MULTIPART_OVERHEAD_BYTES = 1024 * 1024


def _security_headers(path: str) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
    }
    if not path.startswith(_CSP_EXEMPT_PREFIXES):
        headers["Content-Security-Policy"] = _CONTENT_SECURITY_POLICY
    return headers


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


def _remove_stored_file(path) -> None:
    """Best-effort cleanup of a stored upload; never expose paths to clients."""
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("failed to remove stored upload", exc_info=True)


def create_app(*, chatbot=None, documents_dir=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.chatbot = (
            chatbot
            if chatbot is not None
            else await run_in_threadpool(_default_chatbot)
        )
        yield

    app = FastAPI(title="NL2SQL API", version="v1", lifespan=lifespan)
    # Test seam: injected chatbots and tests can redirect uploads to tmp_path.
    app.state.documents_dir = (
        Path(documents_dir) if documents_dir is not None else PROJECT_ROOT / "data"
    )

    @app.exception_handler(StarletteHTTPException)
    async def _documents_multipart_error(
        request: Request, exc: StarletteHTTPException
    ):
        # Starlette reports malformed multipart bodies as 400; the upload
        # contract requires 422 for missing/malformed multipart. Our own
        # validation errors are returned directly, so this path is parser-only.
        if (
            exc.status_code == 400
            and request.method == "POST"
            and request.url.path == "/api/v1/documents"
        ):
            return JSONResponse(status_code=422, content={"detail": exc.detail})
        return await http_exception_handler(request, exc)

    @app.middleware("http")
    async def api_guard(request: Request, call_next):
        if request.method == "POST" and request.url.path.startswith("/api/"):
            site = request.headers.get("sec-fetch-site")
            if site and site not in {"same-origin", "none"}:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "cross-site request rejected"},
                    headers={
                        "Cache-Control": "no-store",
                        **_security_headers(request.url.path),
                    },
                )

        # Reject obviously oversized uploads before Starlette spools the
        # multipart body to disk. Bodies without Content-Length (chunked) are
        # still bounded by save_upload's byte counter.
        if request.method == "POST" and request.url.path == "/api/v1/documents":
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    declared_bytes = int(content_length)
                except ValueError:
                    declared_bytes = None
                if (
                    declared_bytes is not None
                    and declared_bytes
                    > settings.max_upload_bytes + _MULTIPART_OVERHEAD_BYTES
                ):
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "file too large"},
                        headers={
                            "Cache-Control": "no-store",
                            **_security_headers(request.url.path),
                        },
                    )

        response = await call_next(request)
        for name, value in _security_headers(request.url.path).items():
            response.headers[name] = value
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/config", response_model=ConfigResponse)
    def config() -> ConfigResponse:
        return ConfigResponse(max_message_chars=settings.max_message_chars)

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

    @app.post("/api/v1/documents", response_model=DocumentUploadResponse)
    async def upload_document(
        request: Request, file: Annotated[UploadFile, File()]
    ) -> DocumentUploadResponse | JSONResponse:
        try:
            filename = validate_upload_filename(file.filename)
        except InvalidUpload as exc:
            return JSONResponse(status_code=400, content={"detail": str(exc)})

        try:
            stored_path = await run_in_threadpool(
                save_upload, file, request.app.state.documents_dir, settings.max_upload_bytes
            )
        except UploadTooLarge as exc:
            return JSONResponse(status_code=413, content={"detail": str(exc)})
        except InvalidUpload as exc:
            return JSONResponse(status_code=400, content={"detail": str(exc)})
        except Exception:
            logger.exception("failed to save uploaded document")
            return JSONResponse(
                status_code=500, content={"detail": "failed to store upload"}
            )

        try:
            message = await run_in_threadpool(
                request.app.state.chatbot.add_document, str(stored_path), filename
            )
        except DocumentParseError as exc:
            # Bad document content, not an infrastructure failure. Log the raw
            # reason server-side; return a path-free generic detail.
            logger.info("rejected unparseable document: %s", exc)
            _remove_stored_file(stored_path)
            return JSONResponse(
                status_code=400, content={"detail": "document could not be parsed"}
            )
        except Exception:
            logger.exception("failed to process uploaded document")
            _remove_stored_file(stored_path)
            return JSONResponse(
                status_code=500, content={"detail": "failed to process document"}
            )

        return DocumentUploadResponse(filename=filename, message=message)

    dist = PROJECT_ROOT / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")

    return app


app = create_app()
