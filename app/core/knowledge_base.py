import os
import pickle
import threading
import time

import faiss
import numpy as np

from app import PROJECT_ROOT


class DocumentSaveError(RuntimeError):
    """Raised when the knowledge base could not be persisted to disk."""


class KnowledgeBase:
    """Lightweight knowledge base for document storage and retrieval"""

    def __init__(self, cache_dir=None, embedding_dim=384):
        self.chunks = []
        self.chunk_metadata = []  # Store source file, position, etc.
        self.cache_dir = cache_dir or str(PROJECT_ROOT / "kb_cache")
        self.embedding_dim = embedding_dim

        # Create cache directory if it doesn't exist
        os.makedirs(self.cache_dir, exist_ok=True)

        # Initialize FAISS index
        self.index = faiss.IndexFlatIP(embedding_dim)

        # For optimizing frequent queries
        self.query_cache = {}
        self.recent_queries = []
        self.max_cache_size = 100

        # The KB is process-wide shared state: parsing/embedding happen outside
        # this lock, but every read or mutation of chunks/metadata/FAISS does not.
        self._lock = threading.RLock()

    def add_document(self, file_path, doc_processor, *, source_name=None):
        """Process document and add to knowledge base.

        Parsing, chunking and embedding run without holding the lock. The local
        lists are only appended to after embeddings succeed and the index
        accepts them, so a failed add leaves the KB unchanged.
        """
        start_time = time.time()

        source_name = source_name or os.path.basename(file_path)
        text = doc_processor.process_document(file_path, source_name=source_name)

        # Create chunks with metadata outside the lock.
        chunks = doc_processor.create_chunks(text)
        file_type = os.path.splitext(source_name)[1]
        metadata = [
            {"source": source_name, "index": i, "type": file_type}
            for i in range(len(chunks))
        ]

        process_time = time.time() - start_time
        if not chunks:
            return f"Added 0 chunks from {source_name} in {process_time:.2f}s"

        embeddings = doc_processor.create_embeddings(chunks)
        print(f"Embeddings shape: {embeddings.shape}")  # Debugging

        # Normalize embeddings for better cosine similarity
        faiss.normalize_L2(embeddings)

        # Mutate shared state only after embeddings are ready.
        with self._lock:
            if embeddings.shape[1] != self.embedding_dim:
                raise ValueError(
                    f"Embedding dimension mismatch: "
                    f"{embeddings.shape[1]} != {self.embedding_dim}"
                )

            self.index.add(embeddings)
            self.chunks.extend(chunks)
            self.chunk_metadata.extend(metadata)
            self.query_cache.clear()
            self.recent_queries.clear()

        process_time = time.time() - start_time
        return f"Added {len(chunks)} chunks from {source_name} in {process_time:.2f}s"

    def retrieve_relevant(self, query, doc_processor, top_k=3):
        """Retrieve most relevant chunks for a query"""
        if not self.chunks:
            return []

        # Computing the query embedding is pure work; do it outside the lock.
        query_embedding = (
            doc_processor.embedding_model.encode([query])[0].reshape(1, -1).astype("float32")
        )
        faiss.normalize_L2(query_embedding)

        with self._lock:
            if not self.chunks:
                return []

            # Get more candidates than needed for MMR
            candidates_k = min(top_k * 3, len(self.chunks))

            # Check if query is in cache
            if query in self.query_cache:
                return self.query_cache[query]

            # Search in FAISS index
            D, indices = self.index.search(query_embedding, candidates_k)

            # Create results
            results = []
            for i, idx in enumerate(indices[0]):
                if idx < len(self.chunks):
                    results.append(
                        {
                            "text": self.chunks[idx],
                            "distance": D[0][i],  # Inner Product distance (higher is better)
                            "metadata": self.chunk_metadata[idx],
                        }
                    )

                    if len(results) == top_k:
                        break

            # Cache the results
            self._update_query_cache(query, results)
            return results

    def _update_query_cache(self, query, results):
        """Update query cache with LRU mechanism"""
        self.query_cache[query] = results
        self.recent_queries.append(query)

        # Remove oldest queries if cache is too large
        if len(self.recent_queries) > self.max_cache_size:
            oldest_query = self.recent_queries.pop(0)
            if oldest_query in self.query_cache:
                del self.query_cache[oldest_query]

    def retrieve_with_mmr(self, query, doc_processor, top_k=5, diversity=0.3):
        """Retrieve chunks with Maximum Marginal Relevance.
        ``diversity`` is the redundancy penalty weight (1 - lambda):
        0 : pure relevance,
        1 : pure diversity.
        The caller uses 0.35.
        """
        if not self.chunks:
            return []

        # Create query embedding outside the lock.
        query_embedding = (
            doc_processor.embedding_model.encode([query])[0].reshape(1, -1).astype("float32")
        )
        # The index is inner product over normalized document vectors, so the
        # query must be normalized too: otherwise relevance is scaled by its
        # norm and the relevance/redundancy trade-off is no longer (1-w)/w.
        faiss.normalize_L2(query_embedding)

        with self._lock:
            if not self.chunks:
                return []

            # Get more candidates than needed for MMR
            candidates_k = min(top_k * 3, len(self.chunks))

            # Search in FAISS index
            D, indices = self.index.search(query_embedding, candidates_k)

            # Apply MMR to select diverse results
            selected_indices = []
            candidate_indices = [idx for idx in indices[0] if idx < len(self.chunks)]

            # Get embeddings for all candidates
            candidate_embeddings = []
            for idx in candidate_indices:
                # We need to extract the embedding from the FAISS index
                embedding = self.index.reconstruct(int(idx))
                candidate_embeddings.append(embedding)

            candidate_embeddings = np.array(candidate_embeddings)

            # Select first document with highest relevance
            selected_indices.append(0)  # First result is the most relevant

            # Select remaining documents
            while len(selected_indices) < top_k and len(candidate_indices) > len(
                selected_indices
            ):
                best_score = -np.inf
                best_idx = -1

                for i in range(len(candidate_indices)):
                    if i in selected_indices:
                        continue

                    # Relevance: cosine similarity (the index is IP over normalized
                    # vectors, so D is cosine and higher is better).
                    relevance = float(D[0][i])

                    # Redundancy: max cosine similarity to the already-selected
                    # chunks. Same scale as relevance, unlike an L2 distance.
                    redundancy = max(
                        float(np.dot(candidate_embeddings[i], candidate_embeddings[j]))
                        for j in selected_indices
                    )

                    # Standard MMR: reward relevance, penalize redundancy.
                    score = (1 - diversity) * relevance - diversity * redundancy

                    if score > best_score:
                        best_score = score
                        best_idx = i

                if best_idx >= 0:
                    selected_indices.append(best_idx)
                else:
                    break

            # Create results
            results = []
            for i in selected_indices:
                idx = candidate_indices[i]
                results.append(
                    {
                        "text": self.chunks[idx],
                        "distance": D[0][i],  # cosine similarity (higher is better)
                        "metadata": self.chunk_metadata[idx],
                    }
                )

            return results

    def save(self):
        """Save knowledge base to disk"""
        with self._lock:
            try:
                # Ensure cache directory exists
                os.makedirs(self.cache_dir, exist_ok=True)

                # Full path for files
                data_path = os.path.join(self.cache_dir, "kb_data.pkl")
                index_path = os.path.join(self.cache_dir, "kb_faiss.index")

                # Save metadata
                with open(data_path, "wb") as f:
                    pickle.dump(
                        {"chunks": self.chunks, "chunk_metadata": self.chunk_metadata}, f
                    )

                # Save FAISS index
                faiss.write_index(self.index, index_path)

                print(f"Saved {len(self.chunks)} chunks to cache")
                return f"Saved {len(self.chunks)} chunks successfully"

            except Exception as e:
                print(f"Error saving knowledge base: {e}")
                return f"Error saving knowledge base: {e}"

    def load(self):
        """Load knowledge base from disk"""
        with self._lock:
            try:
                # Full paths for files
                data_path = os.path.join(self.cache_dir, "kb_data.pkl")
                index_path = os.path.join(self.cache_dir, "kb_faiss.index")

                # Check if cache files exist
                if not (os.path.exists(data_path) and os.path.exists(index_path)):
                    return "No cache found"

                # Load metadata
                with open(data_path, "rb") as f:
                    data = pickle.load(f)
                    self.chunks = data["chunks"]
                    self.chunk_metadata = data["chunk_metadata"]

                # Load FAISS index
                self.index = faiss.read_index(index_path)

                return f"Loaded {len(self.chunks)} chunks from cache"

            except FileNotFoundError:
                return "No cache found"
            except Exception as e:
                print(f"Error loading knowledge base: {e}")
                return f"Error loading knowledge base: {e}"
