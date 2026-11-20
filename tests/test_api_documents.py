"""Contract tests for POST /api/v1/documents (Phase 3)."""

import os
import re
import subprocess
import sys

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import PROJECT_ROOT
from app.api.main import create_app
from app.api.uploads import InvalidUpload, validate_upload_filename
from app.config import settings
from app.core.document_processor import DocumentParseError, DocumentProcessor
from app.core.knowledge_base import KnowledgeBase

UPLOAD_NAME_RE = re.compile(
    r"^upload-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-notes\.md$"
)


class FakeDocumentChatbot:
    def __init__(self, result="Added 1 chunks from notes.md in 0.01s", error=None):
        self.result = result
        self.error = error
        self.calls = []

    def add_document(self, file_path, source_name=None):
        self.calls.append((file_path, source_name))
        if self.error is not None:
            raise self.error
        return self.result


class _FakeEmbeddingModel:
    def encode(self, texts, batch_size=32, convert_to_numpy=True):
        return np.ones((len(texts), 2), dtype="float32")


class RealDocumentChatbot:
    """Parses with the real processor and stores chunks in a tmp KB."""

    def __init__(self, cache_dir):
        processor = DocumentProcessor.__new__(DocumentProcessor)
        processor.embedding_model = _FakeEmbeddingModel()
        processor.embedding_dim = 2
        self.processor = processor
        self.kb = KnowledgeBase(cache_dir=str(cache_dir), embedding_dim=2)
        self.calls = []

    def add_document(self, file_path, source_name=None):
        self.calls.append((file_path, source_name))
        return self.kb.add_document(
            file_path, self.processor, source_name=source_name
        )


def _client(tmp_path, bot=None):
    bot = bot or FakeDocumentChatbot()
    return TestClient(create_app(chatbot=bot, documents_dir=tmp_path)), bot


def _real_client(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    bot = RealDocumentChatbot(tmp_path / "cache")
    return TestClient(create_app(chatbot=bot, documents_dir=uploads)), bot, uploads


def _upload(client, name="notes.md", content=b"hello world"):
    return client.post(
        "/api/v1/documents",
        files={"file": (name, content, "text/markdown")},
    )


def test_valid_upload_saves_and_returns_original_name(tmp_path):
    client, bot = _client(tmp_path)
    with client:
        response = _upload(client)

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "notes.md"
    assert body["message"].startswith("Added ")

    stored = list(tmp_path.iterdir())
    assert len(stored) == 1
    assert UPLOAD_NAME_RE.match(stored[0].name)
    assert stored[0].read_bytes() == b"hello world"
    assert bot.calls[0][1] == "notes.md"
    assert response.headers["cache-control"] == "no-store"


def test_uppercase_extension_is_accepted(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        response = _upload(client, name="NOTES.MD")

    assert response.status_code == 200
    assert response.json()["filename"] == "NOTES.MD"


def test_unsupported_extension_is_rejected(tmp_path):
    client, bot = _client(tmp_path)
    with client:
        response = _upload(client, name="malware.exe")

    assert response.status_code == 400
    assert bot.calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        ".",
        "..",
        "../etc/passwd",
        "dir\\file.md",
        "nul\x00.md",
        "tab\tname.md",
        "x" * 201 + ".md",
        "noextension",
        "‫name.md",  # Cf: right-to-left override
        "\x85name.md",  # Cc: C1 next-line control
    ],
)
def test_invalid_filenames_are_rejected(name):
    with pytest.raises(InvalidUpload):
        validate_upload_filename(name)


def test_validate_returns_original_basename():
    assert validate_upload_filename("notes.md") == "notes.md"


def test_oversize_upload_is_rejected_and_cleaned_up(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 4)
    client, bot = _client(tmp_path)
    with client:
        response = _upload(client, content=b"12345")

    assert response.status_code == 413
    assert bot.calls == []
    assert list(tmp_path.iterdir()) == []


def test_early_content_length_rejection(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 4)
    client, bot = _client(tmp_path)
    body = b"x" * (settings.max_upload_bytes + 1024 * 1024 + 1)

    with client:
        response = client.post(
            "/api/v1/documents",
            content=body,
            headers={"content-type": "multipart/form-data; boundary=xyz"},
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "file too large"}
    assert response.headers["cache-control"] == "no-store"
    assert bot.calls == []
    assert list(tmp_path.iterdir()) == []


def test_zero_byte_upload_is_rejected(tmp_path):
    client, bot = _client(tmp_path)
    with client:
        response = _upload(client, content=b"")

    assert response.status_code == 400
    assert bot.calls == []
    assert list(tmp_path.iterdir()) == []


def test_missing_file_is_422(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        response = client.post("/api/v1/documents")

    assert response.status_code == 422


def test_malformed_multipart_is_422(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        response = client.post(
            "/api/v1/documents",
            content=b"this is not multipart",
            headers={"content-type": "multipart/form-data; boundary=xyz"},
        )

    assert response.status_code == 422


def test_cross_site_upload_is_403(tmp_path):
    client, bot = _client(tmp_path)
    with client:
        response = client.post(
            "/api/v1/documents",
            files={"file": ("notes.md", b"hello", "text/markdown")},
            headers={"sec-fetch-site": "cross-site"},
        )

    assert response.status_code == 403
    assert bot.calls == []
    assert list(tmp_path.iterdir()) == []


def test_unparseable_document_is_400_and_cleaned_up(tmp_path):
    bot = FakeDocumentChatbot(error=DocumentParseError("bad document"))
    client, _ = _client(tmp_path, bot)
    with client:
        response = _upload(client)

    assert response.status_code == 400
    assert response.json() == {"detail": "document could not be parsed"}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("error.log", b"Error codes: 400, 500\nsecond line"),
        ("unsupported.txt", b"Unsupported features are listed below\nfoo"),
    ],
)
def test_document_text_starting_with_error_prefix_still_uploads(
    tmp_path, name, content
):
    client, bot, uploads = _real_client(tmp_path)
    with client:
        response = _upload(client, name=name, content=content)

    assert response.status_code == 200
    assert response.json()["message"].startswith("Added ")
    assert len(list(uploads.iterdir())) == 1


def test_chatbot_exception_is_500_and_cleaned_up(tmp_path):
    bot = FakeDocumentChatbot(error=RuntimeError("boom with /secret/path"))
    client, _ = _client(tmp_path, bot)
    with client:
        response = _upload(client)

    assert response.status_code == 500
    assert response.json() == {"detail": "failed to process document"}
    assert list(tmp_path.iterdir()) == []


def test_duplicate_filenames_get_distinct_stored_paths(tmp_path):
    client, bot = _client(tmp_path)
    with client:
        first = _upload(client)
        second = _upload(client)

    assert first.status_code == 200
    assert second.status_code == 200
    stored = sorted(path.name for path in tmp_path.iterdir())
    assert len(stored) == 2
    assert stored[0] != stored[1]
    assert all(UPLOAD_NAME_RE.match(name) for name in stored)
    assert all(call[1] == "notes.md" for call in bot.calls)


def test_importing_api_does_not_load_torch():
    code = (
        "import sys; import app.api.main; "
        "print('torch' in sys.modules, 'sentence_transformers' in sys.modules)"
    )
    env = os.environ.copy()
    env.setdefault("SILICON_FLOW_API_KEY", "test")
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False False"
