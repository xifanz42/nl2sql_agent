import faiss
import numpy as np

from app.core.knowledge_base import KnowledgeBase


class FakeEmbedder:
    def __init__(self, vector):
        self.vector = np.asarray([vector], dtype="float32")
        self.embedding_model = self

    def encode(self, _texts):
        return self.vector


def test_mmr_does_not_select_least_similar(tmp_path):
    kb = KnowledgeBase(cache_dir=str(tmp_path), embedding_dim=2)
    kb.chunks = ["same", "near", "relevant", "bad"]
    kb.chunk_metadata = [
        {"source": "t", "index": i, "type": ".md"} for i in range(4)
    ]

    vectors = np.array(
        [[1.0, 0.0], [0.99, 0.01], [0.8, 0.6], [0.0, 1.0]], dtype="float32"
    )
    faiss.normalize_L2(vectors)
    kb.index = faiss.IndexFlatIP(2)
    kb.index.add(vectors)

    results = kb.retrieve_with_mmr(
        "q", FakeEmbedder([1.0, 0.0]), top_k=2, diversity=0.35
    )
    texts = [r["text"] for r in results]

    assert texts[0] == "same"
    assert "bad" not in texts
