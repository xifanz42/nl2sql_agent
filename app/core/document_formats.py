"""Extension whitelist and resource bounds for document uploads.

This module is deliberately dependency-free (no parsing libraries, no torch):
the upload API imports it just to validate extensions, so importing the upload
path must stay cheap.
"""

TIER_1_EXTENSIONS = frozenset(
    {
        ".txt",
        ".log",
        ".md",
        ".markdown",
        ".csv",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".xml",
        ".html",
        ".htm",
        ".sql",
        ".py",
        ".js",
        ".ts",
        ".java",
        ".go",
        ".rs",
        ".sh",
    }
)

TIER_2_EXTENSIONS = frozenset(
    {".pdf", ".docx", ".xlsx", ".pptx", ".rtf", ".odt", ".ods", ".epub"}
)

SUPPORTED_DOCUMENT_EXTENSIONS = TIER_1_EXTENSIONS | TIER_2_EXTENSIONS

MAX_ZIP_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ZIP_MEMBERS = 10_000
MAX_EXTRACTED_CHARS = 1_000_000
MAX_CHUNKS = 5_000

DEFAULT_CHUNK_SIZE = 400
DEFAULT_CHUNK_OVERLAP = 50
