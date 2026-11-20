"""Parser tests for the Phase 3 document formats."""

import pytest

import app.core.document_processor as dp
from app.core.document_processor import (
    SUPPORTED_DOCUMENT_EXTENSIONS,
    DocumentParseError,
    DocumentProcessor,
)


def _processor():
    """Build a processor without loading the sentence-transformers model."""
    processor = DocumentProcessor.__new__(DocumentProcessor)
    processor.embedding_model = None
    processor.embedding_dim = 4
    return processor


TIER_1_TEXT_EXTENSIONS = [
    ".txt",
    ".log",
    ".md",
    ".markdown",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".xml",
    ".sql",
    ".py",
    ".js",
    ".ts",
    ".java",
    ".go",
    ".rs",
    ".sh",
]


def test_supported_extensions_are_a_single_source_of_truth():
    assert ".pdf" in SUPPORTED_DOCUMENT_EXTENSIONS
    assert ".txt" in SUPPORTED_DOCUMENT_EXTENSIONS
    assert ".exe" not in SUPPORTED_DOCUMENT_EXTENSIONS


@pytest.mark.parametrize("extension", TIER_1_TEXT_EXTENSIONS)
def test_tier_1_text_extensions(tmp_path, extension):
    path = tmp_path / f"sample{extension}"
    path.write_text("hello world from tier one", encoding="utf-8")

    assert "hello" in _processor().process_document(str(path))


def test_csv_keeps_header_and_first_five_rows(tmp_path):
    path = tmp_path / "sample.csv"
    rows = ["a,b"] + [f"{i},{i + 1}" for i in range(7)]
    path.write_text("\n".join(rows), encoding="utf-8")

    text = _processor().process_document(str(path))

    assert "Columns: a, b" in text
    assert "Row 5" in text
    assert "Row 6" not in text


def test_csv_uses_original_source_name(tmp_path):
    path = tmp_path / "upload-abc-notes.csv"
    path.write_text("a,b\n1,2", encoding="utf-8")

    text = _processor().process_document(str(path), source_name="notes.csv")

    assert "CSV File: notes.csv" in text
    assert "upload-abc" not in text


@pytest.mark.parametrize("extension", [".html", ".htm"])
def test_html_extracts_visible_text_and_skips_script(tmp_path, extension):
    path = tmp_path / f"sample{extension}"
    path.write_text(
        "<html><head><style>.x{color:red}</style></head><body>"
        "<h1>Title</h1><script>alert('bad')</script><p>Body text</p>"
        "</body></html>",
        encoding="utf-8",
    )

    text = _processor().process_document(str(path))

    assert "Title" in text
    assert "Body text" in text
    assert "alert" not in text
    assert "color:red" not in text


def test_text_read_decodes_undecodable_bytes(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_bytes(b"hello \xff world")

    assert "hello" in _processor().process_document(str(path))


def test_extracted_char_cap_is_enforced(tmp_path, monkeypatch):
    path = tmp_path / "big.txt"
    path.write_text("abcdefghij", encoding="utf-8")

    monkeypatch.setattr(dp, "MAX_EXTRACTED_CHARS", 5)

    with pytest.raises(DocumentParseError, match="too large"):
        _processor().process_document(str(path))


def test_chunk_count_cap_is_enforced(tmp_path, monkeypatch):
    path = tmp_path / "chunks.txt"
    path.write_text("one two three four", encoding="utf-8")

    monkeypatch.setattr(dp, "MAX_CHUNKS", 0)

    with pytest.raises(DocumentParseError, match="too many chunks"):
        _processor().process_document(str(path))


def test_pdf_none_extract_text_is_treated_as_empty(tmp_path, monkeypatch):
    class FakePage:
        def extract_text(self):
            return None

    class FakeReader:
        def __init__(self, _file):
            self.pages = [FakePage()]

    monkeypatch.setattr(dp.PyPDF2, "PdfReader", FakeReader)
    path = tmp_path / "scanned.pdf"
    path.write_bytes(b"%PDF-1.4")

    assert _processor().process_document(str(path)) == ""


def test_unsupported_extension_raises(tmp_path):
    path = tmp_path / "sample.exe"
    path.write_bytes(b"nope")

    with pytest.raises(DocumentParseError, match="Unsupported file format"):
        _processor().process_document(str(path))
