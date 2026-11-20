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

SUPPORTED_DOCUMENT_EXTENSIONS = TIER_1_EXTENSIONS | {".pdf"}

MAX_EXTRACTED_CHARS = 1_000_000
MAX_CHUNKS = 5_000

DEFAULT_CHUNK_SIZE = 400
DEFAULT_CHUNK_OVERLAP = 50
