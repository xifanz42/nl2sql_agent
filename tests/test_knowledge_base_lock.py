"""Knowledge-base lock / atomic-add behavior (Phase 3)."""

import threading

import numpy as np
import pytest

from app.core.document_processor import DocumentParseError
from app.core.knowledge_base import KnowledgeBase


class FakeDocProcessor:
    def __init__(self, vector=(1.0, 0.0), chunks=None, fail=False):
        self.vector = np.asarray([vector], dtype="float32")
        self.embedding_model = self
        self.chunks = chunks
        self.fail = fail

    def encode(self, _texts):
        return self.vector

    def process_document(self, _path, source_name=None):
        return "hello document"

    def create_chunks(self, text):
        return self.chunks if self.chunks is not None else [text]

    def create_embeddings(self, chunks):
        if self.fail:
            raise RuntimeError("embedding boom")
        return np.tile(self.vector, (len(chunks), 1))


def test_source_name_is_stored_in_metadata(tmp_path):
    kb = KnowledgeBase(cache_dir=str(tmp_path), embedding_dim=2)
    processor = FakeDocProcessor()

    result = kb.add_document(
        "/tmp/upload-abc-notes.md", processor, source_name="notes.md"
    )

    assert result.startswith("Added 1 chunks from notes.md")
    assert kb.index.ntotal == 1
    assert kb.chunk_metadata == [
        {"source": "notes.md", "index": 0, "type": ".md"}
    ]


def test_source_name_defaults_to_file_basename(tmp_path):
    kb = KnowledgeBase(cache_dir=str(tmp_path), embedding_dim=2)

    kb.add_document("/tmp/upload-abc-notes.md", FakeDocProcessor())

    assert kb.chunk_metadata[0]["source"] == "upload-abc-notes.md"


def test_embedding_failure_leaves_state_unchanged(tmp_path):
    kb = KnowledgeBase(cache_dir=str(tmp_path), embedding_dim=2)
    processor = FakeDocProcessor(fail=True)

    with pytest.raises(RuntimeError, match="embedding boom"):
        kb.add_document("/tmp/notes.md", processor)

    assert kb.chunks == []
    assert kb.chunk_metadata == []
    assert kb.index.ntotal == 0


def test_parse_error_propagates_and_leaves_state_unchanged(tmp_path):
    class BrokenProcessor(FakeDocProcessor):
        def process_document(self, _path, source_name=None):
            raise DocumentParseError("bad document")

    kb = KnowledgeBase(cache_dir=str(tmp_path), embedding_dim=2)

    with pytest.raises(DocumentParseError, match="bad document"):
        kb.add_document("/tmp/notes.md", BrokenProcessor())

    assert kb.chunks == []
    assert kb.chunk_metadata == []
    assert kb.index.ntotal == 0


def test_dimension_mismatch_does_not_append_chunks(tmp_path):
    kb = KnowledgeBase(cache_dir=str(tmp_path), embedding_dim=2)
    processor = FakeDocProcessor(vector=(1.0, 0.0, 0.0))

    try:
        kb.add_document("/tmp/notes.md", processor)
    except ValueError:
        pass
    else:  # pragma: no cover - mismatch must surface
        raise AssertionError("expected a dimension mismatch")

    assert kb.chunks == []
    assert kb.chunk_metadata == []
    assert kb.index.ntotal == 0


def test_concurrent_add_and_retrieve_smoke(tmp_path):
    kb = KnowledgeBase(cache_dir=str(tmp_path), embedding_dim=2)
    processor = FakeDocProcessor()
    errors = []

    def add(index):
        try:
            kb.add_document(f"/tmp/doc{index}.md", processor, source_name=f"doc{index}.md")
        except Exception as exc:  # noqa: BLE001 - surface any thread failure
            errors.append(exc)

    def retrieve():
        try:
            kb.retrieve_with_mmr("query", processor, top_k=2, diversity=0.35)
        except Exception as exc:  # noqa: BLE001 - surface any thread failure
            errors.append(exc)

    threads = [threading.Thread(target=add, args=(i,)) for i in range(10)]
    threads += [threading.Thread(target=retrieve) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert kb.index.ntotal == 10
    assert len(kb.chunks) == 10
    assert len(kb.chunk_metadata) == 10
