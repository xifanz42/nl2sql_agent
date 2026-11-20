import csv
import os
import re
from html.parser import HTMLParser

import markdown
import numpy as np
import PyPDF2

from app.core.document_formats import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    MAX_CHUNKS,
    MAX_EXTRACTED_CHARS,
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
