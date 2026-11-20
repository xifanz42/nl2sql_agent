import csv
import os
import re
import zipfile
from html.parser import HTMLParser

import markdown
import numpy as np
import PyPDF2

from app.core.document_formats import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    MAX_CHUNKS,
    MAX_EXTRACTED_CHARS,
    MAX_ZIP_MEMBERS,
    MAX_ZIP_UNCOMPRESSED_BYTES,
    SUPPORTED_DOCUMENT_EXTENSIONS,
)

_HTML_SKIP_TAGS = frozenset({"script", "style"})


class DocumentParseError(RuntimeError):
    """Raised when a document cannot be parsed or exceeds a resource bound."""


class _HTMLTextExtractor(HTMLParser):
    """Collect visible text from HTML, ignoring script/style contents."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _HTML_SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in _HTML_SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self):
        return "\n".join(self._parts)


def _extract_html_text(raw_html):
    parser = _HTMLTextExtractor()
    parser.feed(raw_html)
    parser.close()
    return parser.get_text()


class DocumentProcessor:
    """Handles multiple document formats and creates embeddings for RAG"""

    def __init__(
        self,
        embedding_model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        embedding_dim=384,
    ):
        # Imported lazily so importing this module (or the upload API) does not
        # transitively load torch.
        from sentence_transformers import SentenceTransformer

        self.embedding_model = SentenceTransformer(embedding_model)
        self.embedding_dim = embedding_dim

        # Verify and potentially adjust embedding dimension
        actual_dim = self.embedding_model.get_sentence_embedding_dimension()
        if actual_dim != embedding_dim:
            print(
                f"Warning: Specified embedding dim {embedding_dim} does not match model's actual dim {actual_dim}. Using {actual_dim}."
            )
            self.embedding_dim = actual_dim

    def process_document(self, file_path, source_name=None):
        """Process document based on file extension.

        Returns extracted text. Raises :class:`DocumentParseError` when parsing
        fails, an extension is unsupported, or a resource bound is exceeded.
        ``source_name`` is the original upload name used in CSV headers.
        """
        _, file_extension = os.path.splitext(file_path)
        file_extension = file_extension.lower()

        if file_extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
            raise DocumentParseError(f"Unsupported file format: {file_extension}")

        process_methods = {
            ".pdf": self._process_pdf,
            ".csv": self._process_csv,
            ".txt": self._process_text,
            ".log": self._process_text,
            ".md": self._process_markdown,
            ".markdown": self._process_markdown,
            ".json": self._process_text,
            ".jsonl": self._process_text,
            ".yaml": self._process_text,
            ".yml": self._process_text,
            ".xml": self._process_text,
            ".html": self._process_html,
            ".htm": self._process_html,
            ".sql": self._process_text,
            ".py": self._process_text,
            ".js": self._process_text,
            ".ts": self._process_text,
            ".java": self._process_text,
            ".go": self._process_text,
            ".rs": self._process_text,
            ".sh": self._process_text,
            ".docx": self._process_docx,
            ".xlsx": self._process_xlsx,
            ".pptx": self._process_pptx,
            ".rtf": self._process_rtf,
            ".odt": self._process_odt,
            ".ods": self._process_ods,
            ".epub": self._process_epub,
        }

        try:
            if file_extension == ".csv":
                text = self._process_csv(file_path, source_name=source_name)
            else:
                text = process_methods[file_extension](file_path)
        except DocumentParseError:
            raise
        except Exception as e:
            raise DocumentParseError(f"Error processing {file_path}: {e}") from e

        self._enforce_text_limits(text)
        return text

    # --- resource guards -------------------------------------------------

    def _guard_zip(self, file_path):
        """Reject zip containers that could expand past the resource bounds."""
        try:
            with zipfile.ZipFile(file_path) as archive:
                members = archive.infolist()
                if len(members) > MAX_ZIP_MEMBERS:
                    raise DocumentParseError(
                        f"Archive has too many members ({len(members)}; limit {MAX_ZIP_MEMBERS})"
                    )
                total = sum(member.file_size for member in members)
                if total > MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise DocumentParseError(
                        "Archive expands to too much data "
                        f"({total} bytes; limit {MAX_ZIP_UNCOMPRESSED_BYTES})"
                    )
        except zipfile.BadZipFile as e:
            raise DocumentParseError(f"Not a valid archive: {e}") from e

    def _enforce_text_limits(self, text):
        if len(text) > MAX_EXTRACTED_CHARS:
            raise DocumentParseError(
                f"Extracted text is too large ({len(text)} characters; "
                f"limit {MAX_EXTRACTED_CHARS})"
            )
        words = len(text.split())
        step = max(1, DEFAULT_CHUNK_SIZE - DEFAULT_CHUNK_OVERLAP)
        estimated_chunks = (words + step - 1) // step if words else 0
        if estimated_chunks > MAX_CHUNKS:
            raise DocumentParseError(
                f"Document would create too many chunks ({estimated_chunks}; "
                f"limit {MAX_CHUNKS})"
            )

    # --- shared helpers --------------------------------------------------

    def _read_text(self, file_path):
        with open(file_path, encoding="utf-8", errors="replace") as file:
            return file.read()

    # --- tier 1: plain text formats --------------------------------------

    def _process_text(self, file_path):
        """Extract text from a plain-text file."""
        return self._read_text(file_path)

    def _process_html(self, file_path):
        """Extract visible text from an HTML file."""
        return _extract_html_text(self._read_text(file_path))

    def _process_csv(self, file_path, source_name=None):
        """Extract information from CSV file"""
        with open(file_path, encoding="utf-8", errors="replace") as file:
            csv_reader = csv.reader(file)
            headers = next(csv_reader, [])  # 避免 CSV 为空时报错
            display_name = source_name or os.path.basename(file_path)

            # Get column descriptions and sample data
            desc_text = (
                f"CSV File: {display_name}\nColumns: {', '.join(headers)}\n\n"
            )

            # Add sample data (first 5 rows)
            desc_text += "Sample data:\n"
            for i, row in enumerate(csv_reader):
                if i >= 5:  # Only take first 5 rows as samples
                    break
                desc_text += f"Row {i + 1}: {', '.join(row)}\n"

            return desc_text

    def _process_markdown(self, file_path):
        """Extract text from Markdown file"""
        md_content = self._read_text(file_path)
        # Convert markdown to plain text (simple approach)
        html = markdown.markdown(md_content)
        # Remove HTML tags
        return re.sub(r"<[^>]+>", " ", html)

    # --- tier 2: document formats ---------------------------------------

    def _process_pdf(self, file_path):
        """Extract text from PDF file.

        ``page.extract_text()`` can return ``None`` for scanned pages; treat it
        as empty instead of failing with ``None + str``.
        """
        parts = []
        with open(file_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text = page.extract_text() or ""
                if text.strip():
                    parts.append(text)
        return "\n".join(parts)

    def _process_docx(self, file_path):
        """Extract paragraphs and table cells from a Word document."""
        import docx

        self._guard_zip(file_path)
        document = docx.Document(file_path)
        parts = []
        for paragraph in document.paragraphs:
            if paragraph.text.strip():
                parts.append(paragraph.text)
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))
        return "\n".join(parts)

    def _process_xlsx(self, file_path):
        """Extract per-sheet headers and the first five rows."""
        import openpyxl

        self._guard_zip(file_path)
        workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        parts = []
        try:
            for sheet in workbook.worksheets:
                parts.append(f"Sheet: {sheet.title}")
                rows = sheet.iter_rows(values_only=True)
                header = next(rows, None)
                if header is not None:
                    parts.append(
                        "Columns: " + ", ".join(self._cell_text(value) for value in header)
                    )
                for i, row in enumerate(rows):
                    if i >= 5:
                        break
                    parts.append(
                        f"Row {i + 1}: "
                        + ", ".join(self._cell_text(value) for value in row)
                    )
        finally:
            workbook.close()
        return "\n".join(parts)

    def _process_pptx(self, file_path):
        """Extract slide text frames and speaker notes."""
        from pptx import Presentation

        self._guard_zip(file_path)
        presentation = Presentation(file_path)
        parts = []
        for number, slide in enumerate(presentation.slides, start=1):
            parts.append(f"Slide {number}")
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                text = shape.text_frame.text.strip()
                if text:
                    parts.append(text)
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame.text.strip()
                if notes:
                    parts.append(f"Notes: {notes}")
        return "\n".join(parts)

    def _process_rtf(self, file_path):
        """Extract text from RTF using striprtf."""
        from striprtf.striprtf import rtf_to_text

        return rtf_to_text(self._read_text(file_path), errors="ignore")

    def _process_odt(self, file_path):
        """Extract paragraph and heading text from an OpenDocument text file."""
        from odf import teletype, text
        from odf.opendocument import load

        self._guard_zip(file_path)
        document = load(file_path)
        parts = []
        for element in document.getElementsByType(text.P) + document.getElementsByType(
            text.H
        ):
            value = teletype.extractText(element).strip()
            if value:
                parts.append(value)
        return "\n".join(parts)

    def _process_ods(self, file_path):
        """Extract sheet names and the first rows of an OpenDocument sheet."""
        from odf import teletype
        from odf.opendocument import load
        from odf.table import Table, TableCell, TableRow

        self._guard_zip(file_path)
        document = load(file_path)
        parts = []
        for table in document.getElementsByType(Table):
            parts.append(f"Sheet: {table.getAttribute('name') or ''}")
            rows = table.getElementsByType(TableRow)
            for i, row in enumerate(rows[:6]):
                cells = [
                    teletype.extractText(cell).strip()
                    for cell in row.getElementsByType(TableCell)
                ]
                if any(cells):
                    parts.append(f"Row {i + 1}: " + ", ".join(cells))
        return "\n".join(parts)

    def _process_epub(self, file_path):
        """Extract text from the XHTML chapters of an EPUB book."""
        import ebooklib
        from ebooklib import epub

        self._guard_zip(file_path)
        book = epub.read_epub(file_path)
        parts = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            raw = item.get_content().decode("utf-8", errors="replace")
            text = _extract_html_text(raw)
            if text.strip():
                parts.append(text)
        return "\n".join(parts)

    @staticmethod
    def _cell_text(value):
        return "" if value is None else str(value)

    # --- chunking / embeddings ------------------------------------------

    def create_chunks(self, text, chunk_size=DEFAULT_CHUNK_SIZE, overlap=DEFAULT_CHUNK_OVERLAP):
        """Split text into overlapping chunks for better retrieval"""
        words = text.split()
        chunks = []

        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i : i + chunk_size])
            if chunk:
                chunks.append(chunk)

        return chunks

    def create_embeddings(self, chunks, batch_size=32):
        """Create embeddings for text chunks with dimension control"""
        # Encode chunks
        embeddings = self.embedding_model.encode(
            chunks, batch_size=batch_size, convert_to_numpy=True
        )

        # Ensure correct dimension
        if embeddings.shape[1] != self.embedding_dim:
            print(
                f"Embedding shape {embeddings.shape} does not match expected dimension {self.embedding_dim}"
            )
            # Truncate or pad embeddings if necessary
            if embeddings.shape[1] > self.embedding_dim:
                embeddings = embeddings[:, : self.embedding_dim]
            else:
                pad_width = ((0, 0), (0, self.embedding_dim - embeddings.shape[1]))
                embeddings = np.pad(embeddings, pad_width, mode="constant")

        return embeddings.astype("float32")
