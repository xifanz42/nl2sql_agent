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
    assert ".docx" in SUPPORTED_DOCUMENT_EXTENSIONS
    assert ".epub" in SUPPORTED_DOCUMENT_EXTENSIONS
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


def test_docx_extracts_paragraphs_and_tables(tmp_path):
    import docx

    path = tmp_path / "sample.docx"
    document = docx.Document()
    document.add_paragraph("hello docx")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "alpha"
    table.cell(0, 1).text = "beta"
    document.save(str(path))

    text = _processor().process_document(str(path))

    assert "hello docx" in text
    assert "alpha | beta" in text


def test_xlsx_extracts_sheet_header_and_rows(tmp_path):
    import openpyxl

    path = tmp_path / "sample.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Metrics"
    sheet.append(["vehicle", "speed"])
    sheet.append(["AT", 21])
    sheet.append(["MT", 18])
    workbook.save(str(path))

    text = _processor().process_document(str(path))

    assert "Sheet: Metrics" in text
    assert "Columns: vehicle, speed" in text
    assert "Row 1: AT, 21" in text


def test_pptx_extracts_slide_text_and_notes(tmp_path):
    from pptx import Presentation

    path = tmp_path / "sample.pptx"
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "hello pptx"
    slide.notes_slide.notes_text_frame.text = "speaker note"
    presentation.save(str(path))

    text = _processor().process_document(str(path))

    assert "hello pptx" in text
    assert "speaker note" in text


def test_rtf_is_stripped(tmp_path):
    path = tmp_path / "sample.rtf"
    path.write_text(r"{\rtf1\ansi hello rtf}", encoding="utf-8")

    assert "hello rtf" in _processor().process_document(str(path))


def test_odt_extracts_paragraphs(tmp_path):
    from odf.opendocument import OpenDocumentText
    from odf.text import P

    path = tmp_path / "sample.odt"
    document = OpenDocumentText()
    document.text.addElement(P(text="hello odt"))
    document.save(str(path))

    assert "hello odt" in _processor().process_document(str(path))


def test_ods_extracts_sheet_cells(tmp_path):
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableCell, TableRow
    from odf.text import P

    path = tmp_path / "sample.ods"
    document = OpenDocumentSpreadsheet()
    table = Table(name="Sheet1")
    row = TableRow()
    cell = TableCell()
    cell.addElement(P(text="hello ods"))
    row.addElement(cell)
    table.addElement(row)
    document.spreadsheet.addElement(table)
    document.save(str(path))

    assert "hello ods" in _processor().process_document(str(path))


def test_epub_extracts_chapter_text(tmp_path):
    from ebooklib import epub

    path = tmp_path / "sample.epub"
    book = epub.EpubBook()
    book.set_identifier("test-id")
    book.set_title("Test")
    book.set_language("en")
    chapter = epub.EpubHtml(title="Chapter 1", file_name="chapter1.xhtml", lang="en")
    chapter.content = "<html><body><p>hello epub</p></body></html>"
    book.add_item(chapter)
    book.toc = (chapter,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    epub.write_epub(str(path), book)

    assert "hello epub" in _processor().process_document(str(path))


def test_zip_expansion_cap_is_enforced(tmp_path, monkeypatch):
    import docx

    path = tmp_path / "big.docx"
    document = docx.Document()
    document.add_paragraph("compressible " * 100)
    document.save(str(path))

    monkeypatch.setattr(dp, "MAX_ZIP_UNCOMPRESSED_BYTES", 1)

    with pytest.raises(DocumentParseError, match="too much data"):
        _processor().process_document(str(path))


def test_zip_member_cap_is_enforced(tmp_path, monkeypatch):
    import docx

    path = tmp_path / "many.docx"
    document = docx.Document()
    document.add_paragraph("hello")
    document.save(str(path))

    monkeypatch.setattr(dp, "MAX_ZIP_MEMBERS", 1)

    with pytest.raises(DocumentParseError, match="too many members"):
        _processor().process_document(str(path))


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


def test_corrupt_zip_raises_document_parse_error(tmp_path):
    path = tmp_path / "broken.docx"
    path.write_bytes(b"this is not a zip archive")

    with pytest.raises(DocumentParseError, match="Not a valid archive"):
        _processor().process_document(str(path))
