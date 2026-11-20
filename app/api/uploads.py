"""Upload filename validation and bounded streaming to disk (Phase 3)."""

from __future__ import annotations

import contextlib
import os
import unicodedata
import uuid
from pathlib import Path

from starlette.datastructures import UploadFile

from app.core.document_formats import SUPPORTED_DOCUMENT_EXTENSIONS

MAX_FILENAME_BYTES = 200
STREAM_CHUNK_BYTES = 64 * 1024


class InvalidUpload(ValueError):
    """The upload is empty, has an unsafe name, or an unsupported extension."""


class UploadTooLarge(ValueError):
    """The upload exceeded the configured byte limit."""


def _is_control_character(char: str) -> bool:
    # Cc covers C0/C1 controls (including NUL); Cf covers bidi overrides and
    # other invisible formatting characters.
    return unicodedata.category(char) in {"Cc", "Cf"}


def validate_upload_filename(raw: str | None) -> str:
    """Validate a client-supplied filename and return its basename.

    Rejects empty/whitespace-only names, ``.``/``..``, path separators, NUL and
    other control characters, over-long names, and unsupported extensions.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidUpload("filename is required")

    if raw in {".", ".."}:
        raise InvalidUpload("invalid filename")

    if "/" in raw or "\\" in raw:
        raise InvalidUpload("filename must not contain path separators")

    if any(_is_control_character(char) for char in raw):
        raise InvalidUpload("filename must not contain control characters")

    if len(raw.encode("utf-8")) > MAX_FILENAME_BYTES:
        raise InvalidUpload("filename is too long")

    extension = os.path.splitext(raw)[1].lower()
    if extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
        raise InvalidUpload(f"unsupported file extension: {extension or '(none)'}")

    return raw


def save_upload(file: UploadFile, directory: str | Path, max_bytes: int) -> Path:
    """Stream ``file`` to a unique path inside ``directory``.

    The target is created with ``"xb"`` so an existing file is never
    overwritten. Partial files are removed if validation fails midway.
    """
    basename = validate_upload_filename(file.filename)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    target = directory / f"upload-{uuid.uuid4()}-{basename}"
    total = 0

    try:
        with open(target, "xb") as destination:
            while True:
                chunk = file.file.read(STREAM_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise UploadTooLarge(
                        f"file exceeds the {max_bytes} byte upload limit"
                    )
                destination.write(chunk)

        if total == 0:
            raise InvalidUpload("file is empty")
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            target.unlink()
        raise

    return target
